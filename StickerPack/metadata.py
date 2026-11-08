if __name__ == "__main__":
    import json
    import tomllib
    import asyncio
    import httpx

    from pathlib import Path

    from typing import cast

    LOCAL_PATH = Path(__file__).parent
    METADATA_PATH = LOCAL_PATH = LOCAL_PATH / "metadata.jsonl"
    CONFIG_PATH = LOCAL_PATH / "config.toml"
    with CONFIG_PATH.open("rb") as f:
        config = tomllib.load(f)
    base_url = config["url"].rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {config["api_key"]}"}
    model = config["model"]
    prompt = "结合使用场景，图片内容、画面中的文字、角色、表情、情绪和表达含义对图片进行简单描述。只返回描述，不要返回其他任何内容。"

    async def get_desc(images: list[str]) -> list[str]:
        async with httpx.AsyncClient(timeout=60) as client:
            lines = []
            for i, image in enumerate(images):
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
                                    "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image}}],
                                }
                            ],
                            "max_tokens": 150,
                        },
                    }
                )
            jsonl = "\n".join(json.dumps(item, ensure_ascii=False) for item in lines)
            # 2. 上传 JSONL 文件
            response = await client.post(
                base_url + "files",
                headers=headers,
                data={"purpose": "batch"},
                files={"file": ("batch_input.jsonl", jsonl.encode("utf-8"), "application/jsonl")},
            )
            response.raise_for_status()
            file_id = response.json()["id"]
            # 3. 创建 Batch 任务
            response = await client.post(
                base_url + "batches",
                headers={**headers, "Content-Type": "application/json"},
                json={"input_file_id": file_id, "endpoint": "/v1/chat/completions", "completion_window": "24h"},
            )
            response.raise_for_status()
            batch_id = response.json()["id"]
            print(f"Created batch {batch_id}")
            # 4. 轮询任务状态
            while True:
                response = await client.get(base_url + f"batches/{batch_id}", headers=headers)
                try:
                    response.raise_for_status()
                except Exception as e:
                    print(e)
                    await asyncio.sleep(5)
                    continue
                batch = response.json()
                status = batch["status"]
                if status == "completed":
                    break
                if status in ("failed", "expired", "cancelled"):
                    raise RuntimeError(f"Batch 执行失败: {batch}")
                await asyncio.sleep(10)
            # 5. 下载结果文件
            output_file_id = batch.get("output_file_id")
            if not output_file_id:
                raise RuntimeError("Batch 没有生成输出文件")
            response = await client.get(base_url + f"files/{output_file_id}/content", headers=headers)
            response.raise_for_status()
            results = {}
            for line in response.text.splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                custom_id = item["custom_id"]
                if item.get("error"):
                    results[custom_id] = ""
                    continue
                body = item["response"]["body"]
                choices = body.get("choices", [])
                if choices:
                    results[custom_id] = (choices[0]["message"]["content"] or "").strip()
                else:
                    results[custom_id] = ""
            return [results.get(f"image-{i}", "") for i in range(len(images))]

    def load_jsonl(file: Path):
        if not file.exists():
            return
        arr = []
        with file.open("r", encoding="utf-8") as f:
            try:
                arr.extend(json.loads(data) for line in f if (data := line.strip()))
            except json.JSONDecodeError:
                return
        return arr

    if METADATA_PATH.exists():
        metadata = cast(list[list[str] | tuple[str, str]], load_jsonl(METADATA_PATH))
    else:
        metadata = cast(list[list[str] | tuple[str, str]], load_jsonl(LOCAL_PATH / "metadata.json"))
    names = {x.name for x in LOCAL_PATH.glob("*.b64")}
    flag = False
    for name, description in metadata.copy():
        if name in names:
            names.remove(name)
        else:
            flag = True
            name = ""
    if flag:
        METADATA_PATH.unlink()
        metadata = [x for x in metadata if x[0]]
    images = [(LOCAL_PATH / name).read_text() for name in names]
    descs = asyncio.run(get_desc(images))
    metadata.extend(zip(names, descs))
    metadata_jsonl = [json.dumps(x) for x in metadata]
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text("\n".join(metadata_jsonl))
