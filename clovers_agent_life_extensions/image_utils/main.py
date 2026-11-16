from clovers_agent import CloversAgent, Turn, Event
from ..base import TOOLS, CONFIG
from .constants import IMAGE_UTILS, IMAGE_TIMEOUT

from typing import cast

image_config = CONFIG.image
URL = image_config.url.rstrip("/")
API_KEY = image_config.api_key
MODEL = image_config.model


@TOOLS.create_category(IMAGE_UTILS, "生成或编辑图像")
async def _(agent: CloversAgent, turn: Turn, event: Event) -> str:
    return """\
image_utils 部分参数说明

prompt: 生图提示词，如要生成图像的内容、主体、场景与风格等。留空时使用用户当前消息。此参数为视觉提示词，不应在此参数中约束其他格式。
size: 输出尺寸（WIDTHxHEIGHT）。宽高须为 16 的倍数，长宽比须在 1:3 到 3:1 之间，如 1536x864。默认为 auto。
quality: 图像质量，默认 auto。
output_format: 输出图像的格式，默认 png。
inspect_result: 是否将结果图附加给助手继续查看，默认 false。"""


@TOOLS.register(
    "text2image",
    "根据文字描述生成图像",
    {
        "prompt": {"type": "string"},
        "size": {"type": "string"},
        "quality": {"type": "string", "enum": ["auto", "low", "medium", "high", "xhigh", "max"]},
        "output_format": {"type": "string", "enum": ["png", "jpeg", "webp", "svg", "gif"]},
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
    output_format: str = "png",
    inspect_result: bool = False,
) -> str:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "prompt": prompt or event.message,
        "size": size,
        "quality": quality,
        "output_format": output_format,
    }
    url = f"{URL}/images/generations"
    response = await agent.async_client.post(url, headers=headers, json=payload, timeout=IMAGE_TIMEOUT)
    result = cast(dict[str, str], response.json()["data"][0])
    if "b64_json" in result:
        mime_type = result.get("mime_type") or f"image/{output_format}"
        b64 = result["b64_json"]
        image = f"data:{mime_type};base64,{b64}"
    elif "url" in result and (b64url := await turn.api.download_url(result["url"], ())):
        image = b64url
    else:
        return "接口返回结果错误"
    await event.send("image", image)
    if inspect_result:
        turn.pending_content.append({"type": "image_url", "image_url": {"url": image}})
    return "OK"


@TOOLS.register(
    "image2image",
    "根据原图和编辑指令生成新图像。原图从用户消息内自动获取",
    {
        "prompt": {"type": "string"},
        "size": {"type": "string"},
        "quality": {"type": "string", "enum": ["auto", "low", "medium", "high", "xhigh", "max"]},
        "output_format": {"type": "string", "enum": ["png", "jpeg", "webp", "svg", "gif"]},
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
    output_format: str = "png",
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
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "images": [{"image_url": image_url} for image_url in images],
    }
    url = f"{URL}/images/edits"
    response = await agent.async_client.post(url, headers=headers, json=payload, timeout=IMAGE_TIMEOUT)
    result = cast(dict[str, str], response.json()["data"][0])
    if "b64_json" in result:
        mime_type = result.get("mime_type") or f"image/{output_format}"
        b64 = result["b64_json"]
        image = f"data:{mime_type};base64,{b64}"
    elif "url" in result and (b64url := await turn.api.download_url(result["url"], ())):
        image = b64url
    else:
        return "接口返回结果错误"
    await event.send("image", image)
    if inspect_result:
        turn.pending_content.append({"type": "image_url", "image_url": {"url": image}})
    return "OK"
