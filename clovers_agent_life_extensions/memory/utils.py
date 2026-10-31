import math
import contextlib
import frontmatter
import torch

from pathlib import Path
from collections import Counter, defaultdict
from torch import Tensor
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer

from typing import TypedDict
from collections.abc import Iterable
from pydantic import BaseModel, PrivateAttr


class HistoryEntry(BaseModel):
    overview: str
    keywords: set[str]
    timestamp: float
    path: Path

    @classmethod
    def from_file(cls, path: Path):
        with contextlib.suppress(Exception):
            if path.suffix != ".md":
                return
            with path.open("r", encoding="utf-8") as f:
                post = frontmatter.load(f)
            entry = cls.model_validate({**post.metadata, "path": path})
            entry.overview = entry.overview.strip()
            entry.keywords = {k.lower() for keyword in entry.keywords if (k := keyword.strip())}
            return entry

    @property
    def content(self) -> str:
        with self.path.open("r", encoding="utf-8") as f:
            post = frontmatter.load(f)
            return post.content


class IndexedHistory(HistoryEntry):
    normalized_keywords: set[str]
    keyword_count: int
    _overview_embedding: Tensor = PrivateAttr()

    @property
    def overview_embedding(self) -> Tensor:
        return self._overview_embedding

    @overview_embedding.setter
    def overview_embedding(self, value: Tensor):
        self._overview_embedding = value

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


class HistoryIndex:

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

    def __init__(self, similarity_threshold: float, entries: list[HistoryEntry], sentence_model: SentenceTransformer):
        self.bm25_k1: float = 1.2
        self.bm25_b: float = 0.75
        self.keyword_weight: float = 0.5
        self.semantic_weight: float = 0.5
        self.recency_half_life: float = 30
        self.sentence_model_batch_size: int = 256
        self.sentence_model: SentenceTransformer = sentence_model
        self.similarity_threshold = similarity_threshold
        self.entries: list[IndexedHistory] = []
        self.keyword_aliases: dict[str, str] = {}
        self.canonical_keywords: set[str] = set()
        self.document_frequency: Counter[str] = Counter()
        self.known_keywords: set[str] = set()
        self.sorted_keywords: list[str]
        self.keywords_by_first_char: defaultdict[str, list[str]] = defaultdict(list)
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
        overview_embeddings = self.sentence_model.encode(
            [entry.overview for entry in entries],
            batch_size=self.sentence_model_batch_size,
            convert_to_tensor=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        for i, entry in enumerate(self.entries):
            entry.overview_embedding = overview_embeddings[i]

    def update(self, entry: HistoryEntry):
        keywords = entry.keywords
        for keyword in keywords:
            self.register_keyword(keyword)
        normalize_keywords = self.normalize_keywords(keywords)
        self.document_frequency.update(normalize_keywords)
        indexed_entry = IndexedHistory.from_entry(entry, normalize_keywords)
        indexed_entry.overview_embedding = self.sentence_model.encode(
            entry.overview,
            convert_to_tensor=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        entries = self.entries
        entries.append(indexed_entry)
        entries.sort(key=lambda entry: entry.timestamp, reverse=True)
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

    def bm25(self, sentence: str):
        entries = self.entries
        n = len(entries)
        tokens = set[str]()
        for seg in sentence.split():
            tokens.update(self.extract_keywords(seg))
        if not tokens:
            return
        avgdl = sum(h.keyword_count for h in entries) / n
        if avgdl == 0:
            return
        # BM25 IDF
        idf = {token: math.log(1 + (n - c + 0.5) / (c + 0.5)) for token in tokens if (c := self.document_frequency[token]) > 0}
        if not idf:
            return
        # BM25
        k1, b = self.bm25_k1, self.bm25_b
        bm25_scores = list[float]()
        for entry in entries:
            dl = entry.keyword_count
            bm25 = 0.0
            for token, weight in idf.items():
                if token not in entry.normalized_keywords:
                    continue
                denominator = 1 + k1 * (1 - b + b * dl / avgdl)
                bm25 += weight * (k1 + 1) / denominator
            bm25_scores.append(bm25)
        return bm25_scores

    def search(self, sentence: str):
        entries = self.entries
        if not entries:
            return
        # Normalize BM25
        if (bm25_scores := self.bm25(sentence)) and (max_bm25 := max(bm25_scores)) > 0:
            bm25_scores = [score / max_bm25 for score in bm25_scores]
        else:
            bm25_scores = [0.0] * len(entries)
        # Semantic similarity
        query_embedding = self.sentence_model.encode(
            sentence,
            convert_to_tensor=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        semantic_scores = torch.stack([entry.overview_embedding for entry in entries]) @ query_embedding
        # Combine relevance and ordinal decay
        scored: list[tuple[float, IndexedHistory]] = []
        keyword_weight = self.keyword_weight
        semantic_weight = self.semantic_weight
        recency_half_life = self.recency_half_life
        for i, (entry, bm25, semantic) in enumerate(zip(entries, bm25_scores, semantic_scores.cpu().tolist())):
            relevance = keyword_weight * bm25 + semantic_weight * semantic
            recency = 2 ** (-i / recency_half_life) if recency_half_life > 0 else 1.0
            scored.append((relevance * recency, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored
