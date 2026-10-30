import math
import time
import json
import contextlib
import shutil
import pydantic
import frontmatter
from pathlib import Path
from collections import Counter, defaultdict
from torch import Tensor
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer, util
from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.session import Session
from clovers_agent.config import CONFIG as AGENT_CONFIG
from clovers_agent.constants import ON_CHAT
from clovers_agent.embedding import batch_similarity

from typing import TYPE_CHECKING, TypedDict
from collections.abc import Iterable
from pydantic import BaseModel


class HistoryEntry(BaseModel):
    overview: str
    keywords: set[str]
    timestamp: float
    content: str

    @classmethod
    def from_file(cls, path: Path):
        with contextlib.suppress(Exception):
            if path.suffix != ".md":
                return
            with path.open("r", encoding="utf-8") as f:
                post = frontmatter.load(f)
            entry = cls.model_validate({**post.metadata, "content": post.content})
            entry.overview = entry.overview.strip()
            entry.keywords = {k.lower() for keyword in entry.keywords if (k := keyword.strip())}
            return entry


class IndexedHistory(HistoryEntry):
    normalized_keywords: set[str]
    keyword_count: int

    @classmethod
    def from_entry(cls, entry: HistoryEntry, normalized_keywords: set[str]):
        data = {
            **entry.model_dump(),
            "normalized_keywords": normalized_keywords,
            "keyword_count": len(normalized_keywords),
        }
        return cls.model_validate(data)


class KeywordCluster(TypedDict):
    keywords: set[str]
    # centroid: Tensor


def find_fuzzy_match(text: str, candidates: list[str], start: int, text_length: int, threshold: float) -> tuple[str, int] | None:
    n = text_length - start
    for keyword in candidates:
        keyword_len = len(keyword)
        if 200 * min(keyword_len, n) / (keyword_len + n) < threshold:
            continue
        max_edits = round(keyword_len * (100 - threshold) / 100)
        if max_edits < 1:
            continue
        min_len = max(1, keyword_len - max_edits)
        max_len = min(n, keyword_len + max_edits)
        if min_len > max_len:
            continue
        for match_len in range(min_len, max_len + 1):
            similarity = fuzz.ratio(keyword, text[start : start + match_len])
            if similarity >= threshold:
                return keyword, start + match_len


class HistoryIndex(BaseModel):
    similarity_threshold: int
    entries: list[IndexedHistory]
    keyword_aliases: dict[str, str]
    canonical_keywords: set[str]
    document_frequency: Counter[str]
    known_keywords: set[str]
    sorted_keywords: list[str]
    keywords_by_first_char: dict[str, list[str]]

    def register_keyword(self, keyword: str):
        similarity_threshold = self.similarity_threshold
        if keyword in self.keyword_aliases:
            return
        n = len(keyword)
        for key in self.canonical_keywords:
            key_length = len(key)
            if 200 * min(n, key_length) / (n + key_length) < similarity_threshold:
                continue
            if fuzz.ratio(key, keyword) >= similarity_threshold:
                self.keyword_aliases[keyword] = key

                break
        else:
            self.keyword_aliases[keyword] = keyword
            self.canonical_keywords.add(keyword)

    def normalize_keywords(self, keywords: Iterable[str]) -> set[str]:
        return {self.keyword_aliases[keyword] for keyword in keywords}

    def __init__(self, similarity_threshold: int, entries: list[HistoryEntry]):
        self.k1: float = 1.2
        self.b: float = 0.75
        self.alpha: float = 0.5
        self.decay_half_life: float = 30
        super().__init__(
            similarity_threshold=similarity_threshold,
            entries=[],
            keyword_aliases={},
            canonical_keywords={},
            document_frequency=Counter(),
            known_keywords=set(),
            sorted_keywords=[],
            keywords_by_first_char={},
        )
        known_keywords = self.known_keywords
        for entry in entries:
            known_keywords.update(entry.keywords)
        for keyword in known_keywords:
            self.register_keyword(keyword)
        for entry in entries:
            indexed_entry = IndexedHistory.from_entry(entry, self.normalize_keywords(entry.keywords))
            self.entries.append(indexed_entry)
            self.document_frequency.update(indexed_entry.normalized_keywords)
        self.entries.sort(key=lambda entry: entry.timestamp, reverse=True)
        self.sorted_keywords = sorted(known_keywords, key=len, reverse=True)
        for kw in self.sorted_keywords:
            self.keywords_by_first_char[kw[0]].append(kw)

    def update(self, entry: HistoryEntry):
        keywords = entry.keywords
        for keyword in keywords:
            self.register_keyword(keyword)
        normalize_keywords = self.normalize_keywords(keywords)
        self.document_frequency.update(normalize_keywords)
        self.entries.append(IndexedHistory.from_entry(entry, normalize_keywords))
        self.entries.sort(key=lambda entry: entry.timestamp, reverse=True)
        known_keywords = self.known_keywords
        diff = keywords.difference(known_keywords)
        known_keywords.update(diff)
        first_chars = set[str]()
        keywords_by_first_char = self.keywords_by_first_char
        for kw in diff:
            keywords_by_first_char[kw[0]].append(kw)
            first_chars.add(kw[0])
        for char in first_chars:
            keywords_by_first_char[char].sort(key=len, reverse=True)
        sorted_keywords = self.sorted_keywords
        sorted_keywords.extend(diff)
        sorted_keywords.sort(key=len, reverse=True)

    def extract_keywords(self, sentence: str):
        similarity_threshold = self.similarity_threshold
        keyword_aliases = self.keyword_aliases
        keywords_by_first_char = self.keywords_by_first_char
        tokens = set[str]()
        i, n = 0, len(sentence)
        while i < n:
            c = sentence[i]
            if c not in keywords_by_first_char:
                i += 1
                continue
            keywords = keywords_by_first_char[c]
            if exact := next((k for k in keywords if sentence.startswith(k, i)), None):
                tokens.add(keyword_aliases[exact])
                i += len(exact)
                continue
            result = find_fuzzy_match(sentence, keywords, i, n, similarity_threshold)
            if result:
                kw, end = result
                tokens.add(keyword_aliases[kw])
                i = end
                continue
            i += 1
        return tokens

    def search(
        self,
        sentence: str,
        sentence_model: SentenceTransformer,
    ):
        if not self.entries:
            return
        tokens = set[str]()
        for seg in sentence.split():
            tokens.update(self.extract_keywords(seg))
        if not tokens:
            return
        n = len(self.entries)
        lam = math.log(n) / n
        avgdl = sum(h.keyword_count for h in self.entries) / n
        # BM25 IDF
        idf = {token: math.log(1 + (n - c + 0.5) / (c + 0.5)) for token in tokens if (c := self.document_frequency[token]) > 0}
        if not idf:
            return
        # BM25 排序
        scored: list[tuple[float, IndexedHistory]] = []
        k1, b = self.k1, self.b
        emb_simi = batch_similarity(
            [x.overview for x in self.entries],
            sentence,
            sentence_model,
        )
        for i, entry in enumerate(self.entries):
            dl = entry.keyword_count
            bm25 = 0.0
            for token, weight in idf.items():
                if token not in entry.normalized_keywords:
                    continue
                tf = 1
                denominator = tf + k1 * (1 - b + b * dl / avgdl)
                bm25 += weight * (tf * (k1 + 1) / denominator)
            # (n - i) / n 为归一化线性遗忘系数
            score = (bm25 + emb_simi[i]) * math.exp(-lam * i)
            scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored
