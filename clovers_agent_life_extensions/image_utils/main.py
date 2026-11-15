from clovers_agent import CloversAgent, Turn, Event
from ..base import TOOLS, CONFIG
from .constants import IMAGE_UTILS, IMAGE_TIMEOUT

image_config = CONFIG.image
URL = image_config.url.rstrip("/")
API_KEY = image_config.api_key
MODEL = image_config.model


@TOOLS.create_category(IMAGE_UTILS, "生成或编辑图像")
async def _(agent: CloversAgent, turn: Turn, event: Event) -> str:
    return """\
image_utils 部分参数说明

prompt: 生图提示词。留空时使用用户当前消息。
inspect_result: 是否将结果图附加给助手继续查看，默认 false。
"""


@TOOLS.register(
    "text2image",
    "根据文字描述生成图像",
    {
        "prompt": {
            "type": "string",
            "description": "要生成图像的内容、主体、场景与风格",
        },
        "size": {
            "type": "string",
            "description": "输出尺寸，默认 auto 或传入 WIDTHxHEIGHT。宽高须为 16 的倍数，长宽比须在 1:3 到 3:1 之间。",
        },
        "quality": {
            "type": "string",
            "enum": ["auto", "low", "medium", "high", "xhigh", "max"],
        },
        "inspect_result": {"type": "boolean"},
    },
    IMAGE_UTILS,
    required=[],
)
async def _(
    agent: CloversAgent,
    turn: Turn,
    event: Event,
    prompt: str = "",
    size: str = "auto",
    quality: str = "auto",
    inspect_result: bool = False,
) -> str:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "prompt": prompt or event.message,
        "size": size,
        "quality": quality,
        "output_format": "png",
    }
    url = f"{URL}/images/generations"
    response = await agent.async_client.post(url, headers=headers, json=payload, timeout=IMAGE_TIMEOUT)
    result = response.json()["data"][0]
    mime_type = result["mime_type"]
    b64 = result["b64_json"]
    image = f"data:{mime_type};base64,{b64}"
    await event.send("image", image)
    if inspect_result:
        turn.pending_content.append({"type": "image_url", "image_url": {"url": image}})
    return "OK"


@TOOLS.register(
    "image2image",
    "根据原图和编辑指令生成新图像。原图从用户消息内自动获取",
    {
        "prompt": {"type": "string", "description": "要生成图像的内容、主体、场景与风格"},
        "inspect_result": {"type": "boolean"},
    },
    IMAGE_UTILS,
    required=[],
)
async def _(
    agent: CloversAgent,
    turn: Turn,
    event: Event,
    prompt: str = "",
    inspect_result: bool = False,
) -> str:
    message = next((x for x in reversed(turn.payload["messages"]) if x["role"] == "user"), None)
    if not message or not (isinstance(content := message["content"], list)):
        return "未从当前用户信息中找到图片。"
    images = [x["image_url"]["url"] for x in content if x["type"] == "image_url"]
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "prompt": prompt or event.message,
        "images": [{"image_url": image_url} for image_url in images],
    }
    url = f"{URL}/images/edits"
    response = await agent.async_client.post(url, headers=headers, json=payload, timeout=IMAGE_TIMEOUT)
    result = response.json()["data"][0]
    mime_type = result["mime_type"]
    b64 = result["b64_json"]
    image = f"data:{mime_type};base64,{b64}"
    await event.send("image", image)
    if inspect_result:
        turn.pending_content.append({"type": "image_url", "image_url": {"url": image}})
    return "OK"
