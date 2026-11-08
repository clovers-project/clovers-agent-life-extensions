import json
import tomllib
import asyncio
import httpx

from pathlib import Path

LOCAL_PATH = Path(__file__).parent
CONFIG_PATH = LOCAL_PATH / "config.toml"
STATE_PATH = LOCAL_PATH / "batch_state.json"
METADATA_PATH = LOCAL_PATH / "metadata.jsonl"

PROMPT = """\
请根据图片内容生成一句简洁、自然、准确的描述，用于贴纸（Sticker）的分类、检索和语义搜索。

描述时优先关注：
1. 角色或主体：人物、动物、物品及其外观特征。
2. 动作与画面：正在做什么，手持什么物品，画面中有什么关键元素。
3. 表情与情绪：准确描述表情，以及能够从画面中明确判断的情绪。
4. 文字信息：如果图片中存在文字，准确提取并结合画面理解其含义。
5. 表达含义：概括这张贴纸适合表达的情绪、态度或交流意图。

要求：
- 只描述图片中能够观察到的信息，不要编造背景、故事或未经证实的使用场景。
- 不要过度解读角色的心理活动或情绪。
- 优先保留有助于区分这张贴纸的特征。
- 不要重复描述相同的信息，不使用冗余修饰词。
- 没有文字时，不要刻意补充文字相关内容。
- 使用一句话。
- 直接返回描述，不要添加标题、解释或其他内容。
"""


def load_metadata():
    if not METADATA_PATH.exists():
        return set()
    names = set()
    with METADATA_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                names.add(item[0])
            except (json.JSONDecodeError, IndexError, TypeError):
                continue
    return names


async def main():
    with CONFIG_PATH.open("rb") as f:
        config = tomllib.load(f)
    base_url = config["url"].rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {config['api_key']}"}
    model = config["model"]
    # 找出尚未生成 Metadata 的图片
    completed_names = load_metadata()
    names = sorted(p.name for p in LOCAL_PATH.glob("*.b64") if p.name not in completed_names)
    if not names:
        print("没有需要处理的图片")
        return
    images = [(name, (LOCAL_PATH / name).read_text(encoding="utf-8")) for name in names]
    async with httpx.AsyncClient(timeout=60) as client:
        # 1. 生成 JSONL
        lines = []
        for i, (name, image) in enumerate(images):
            lines.append(
                {
                    "custom_id": f"image-{i}",
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": image}}],
                            }
                        ],
                        # "max_tokens": 150,
                    },
                }
            )
        jsonl = "\n".join(json.dumps(x, ensure_ascii=False) for x in lines)
        # 2. 上传 JSONL
        response = await client.post(
            base_url + "files",
            headers=headers,
            data={"purpose": "batch"},
            files={"file": ("batch_input.jsonl", jsonl.encode("utf-8"), "application/jsonl")},
        )
        response.raise_for_status()
        file_id = response.json()["id"]
        print(f"上传成功: {file_id}")
        # 3. 创建 Batch
        response = await client.post(
            base_url + "batches",
            headers={**headers, "Content-Type": "application/json"},
            json={"input_file_id": file_id, "endpoint": "/v1/chat/completions", "completion_window": "24h"},
        )
        response.raise_for_status()
        batch = response.json()
        batch_id = batch["id"]
        print(f"Batch 创建成功: {batch_id}")
        # 4. 保存任务信息
        state = {
            "batch_id": batch_id,
            "input_file_id": file_id,
            "image_names": names,
            "status": batch["status"],
            "output_file_id": None,
            "processed": False,
        }
        temp_path = STATE_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(STATE_PATH)
        print(f"任务信息已保存: {STATE_PATH}")
        print("提交完成，退出。")


if __name__ == "__main__":
    asyncio.run(main())
