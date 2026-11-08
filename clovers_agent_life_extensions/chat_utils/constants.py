from ..constants import LIFE

KEY_STICKER_PACK = f"{LIFE}.sticker_pack"

SEND_STICKER_PROMPT = """\
请根据给定的用户要求，从以下贴纸中选择最符合用户要求的的 1-10 个序号。
- 通常返回 2–6 个。
- 如果某个贴纸明显比其他贴纸更符合用户要求，则只返回这 1 个；如果符合用户要求的贴纸较多，可以适当增加返回数量。

你应该输出 JSON 格式的 array[integer] 如:
```
[3, 5, 8]
```
候选贴纸：
{candidates}

请根据用户要求返回贴纸序号
"""
