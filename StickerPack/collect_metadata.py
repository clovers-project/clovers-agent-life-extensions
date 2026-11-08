import json
import tomllib
import asyncio
import httpx

from pathlib import Path

LOCAL_PATH = Path(__file__).parent
CONFIG_PATH = LOCAL_PATH / "config.toml"
STATE_PATH = LOCAL_PATH / "batch_state.json"
METADATA_PATH = LOCAL_PATH / "metadata.jsonl"


def load_metadata():
    metadata = []
    if not METADATA_PATH.exists():
        return metadata
    with METADATA_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    metadata.append(item)
            except json.JSONDecodeError:
                continue
    return metadata


def save_metadata(metadata):
    temp_path = METADATA_PATH.with_suffix(".tmp")
    content = "\n".join(json.dumps(x, ensure_ascii=False) for x in metadata)
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(METADATA_PATH)


async def main(wait=False):
    if not STATE_PATH.exists():
        print("找不到 batch_state.json")
        return
    with CONFIG_PATH.open("rb") as f:
        config = tomllib.load(f)
    base_url = config["url"].rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {config['api_key']}"}
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if state.get("processed"):
        print("这个 Batch 已经生成过 Metadata")
        return
    batch_id = state["batch_id"]
    async with httpx.AsyncClient(timeout=60) as client:
        # 1. 检查 Batch 状态
        while True:
            response = await client.get(base_url + f"batches/{batch_id}", headers=headers)
            response.raise_for_status()
            batch = response.json()
            status = batch["status"]
            state["status"] = status
            state["output_file_id"] = batch.get("output_file_id")
            print(f"Batch 状态: {status}")
            # 任务完成
            if status == "completed":
                break
            # 任务失败
            if status in ("failed", "expired", "cancelled"):
                temp_path = STATE_PATH.with_suffix(".tmp")
                temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                temp_path.replace(STATE_PATH)
                raise RuntimeError(f"Batch 执行失败: {batch}")
            # 不等待，直接退出
            if not wait:
                print("Batch 尚未完成，退出。")
                return
            # 等待下一次检查
            await asyncio.sleep(10)
        # 2. 保存完成状态
        output_file_id = batch.get("output_file_id")
        if not output_file_id:
            raise RuntimeError("Batch 没有生成输出文件")
        # 3. 下载结果
        response = await client.get(base_url + f"files/{output_file_id}/content", headers=headers)
        response.raise_for_status()
        # 4. 解析结果
        results = {}
        for line in response.text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            custom_id = item["custom_id"]
            if item.get("error"):
                results[custom_id] = ""
                continue
            body = item.get("response", {}).get("body", {})
            choices = body.get("choices", [])
            if choices:
                results[custom_id] = (choices[0]["message"].get("content") or "").strip()
            else:
                results[custom_id] = ""
        # 5. 更新 Metadata
        metadata = load_metadata()
        existing_names = {x[0] for x in metadata}
        image_names = state["image_names"]
        for i, name in enumerate(image_names):
            if name in existing_names:
                continue
            description = results.get(f"image-{i}", "")
            metadata.append([name, description])
        # 6. 原子写入 Metadata
        save_metadata(metadata)
        # 7. 标记已经处理
        state["processed"] = True
        state["status"] = "completed"
        state["output_file_id"] = output_file_id
        temp_path = STATE_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(STATE_PATH)
        print(f"Metadata 更新完成，共 {len(metadata)} 条")


if __name__ == "__main__":
    try:
        asyncio.run(main(True))
    except KeyboardInterrupt:
        print("\n已中断。任务状态已保留，下次可以继续运行。")
