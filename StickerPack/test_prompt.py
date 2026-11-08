import tomllib
import random
import asyncio
import httpx

from pathlib import Path

LOCAL_PATH = Path(__file__).parent
CONFIG_PATH = LOCAL_PATH / "config.toml"

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


async def main():
    # 读取配置
    with CONFIG_PATH.open("rb") as f:
        config = tomllib.load(f)

    base_url = config["url"].rstrip("/") + "/"
    headers = {"Authorization": f"Bearer {config['api_key']}"}
    model = config["model"]

    # 随机选择一张图片
    images = list(LOCAL_PATH.glob("*.b64"))

    if not images:
        print("没有找到 .b64 图片")
        return
    image_path = random.choice(images)
    image = image_path.read_text(encoding="utf-8").strip()
    print(f"测试图片: {image_path.name}")
    print("正在请求模型...\n")
    # 直接调用 Chat Completions
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            base_url + "chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": image}}]}
                ],
            },
        )

        response.raise_for_status()
        result = response.json()

    description = (result["choices"][0]["message"]["content"] or "").strip()

    print("图片描述:")
    print(description)


if __name__ == "__main__":
    asyncio.run(main())
