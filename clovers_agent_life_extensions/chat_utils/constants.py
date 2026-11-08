from ..constants import LIFE

KEY_STICKER_PACK = f"{LIFE}.sticker_pack"

SEND_STICKER_PROMPT = """\
请根据给定的用户要求，从以下贴纸中选择选择语义和情绪最匹配的 2-10 个序号。
你应该输出 JSON 格式的 array[integer] 如:
```
[3, 5, 8]
```
候选贴纸：
{candidates}

请根据用户要求返回贴纸序号
"""
