# clovers-agent-life-extensions

为 Clovers Agent 增加长期历史召回、用户画像和聊天发送工具。插件导出 `TOOLS`，由核心 Agent 的工具插件加载器合并，不提供独立启动程序。

当前源码版本 `0.3.4`。本说明依据 Python 实现编写，不涉及仓库 `StickerPack/` 中资源的检查或整理。

## 功能与生效时机

| 功能     | 实际行为                                                                   |
| -------- | -------------------------------------------------------------------------- |
| 历史召回 | 索引核心生成的 Markdown 摘要，以关键词、句向量和顺序衰减召回，按需展开正文 |
| 用户画像 | 保存称呼、标签、偏好、印象、星级记忆，按对话计数提醒维护                   |
| 用户拉黑 | 在路由前读取当前用户档案，未到期则结束本次正式处理                         |
| 贴纸     | 保存当前输入中的图片，按意图选择并发送已收藏贴纸                           |
| 语音     | 配置参考音频和 TTS 密钥后，注册语音发送工具，支持风格与唱歌参数            |
| 定向发送 | 从群聊向当前用户私聊，或向指定其他群发送文字                               |

历史召回、画像注入及本插件普通工具绑定到核心的 `on_chat` 分类 / 场景。拉黑检查绑定 `:router` 钩子，在场景选择之前运行，因此也会阻止原本可能进入任务场景的正式输入；核心独立的主动插话与执行中旁路不经过这项检查。

## 安装与接入

要求 Python `>=3.12,<4.0`，核心依赖下限为 `clovers-agent>=0.3.8`。从本仓库安装到宿主使用的环境：

```bash
python -m pip install -e .
```

依赖以 [pyproject.toml](pyproject.toml) 为准，包含 NumPy、Pydantic、python-frontmatter、RapidFuzz、PyTorch。句向量模型复用核心的 `agent.sentence_model`，不额外配置 embedding API 或外部数据库。

在核心 `clovers_agent` 配置的 `plugins` 中加入模块名，并保留已有插件，由 Clovers 宿主加载核心插件并启动即可。仅安装本包不会自动启用。核心的模型配置和消息准入规则仍需事先配置。

仓库的 `tool.uv.sources` 将核心指向开发机路径 `D:/CLOVERS/clovers-agent/clovers-agent`。该路径是本仓库 uv 开发配置，其他机器使用 uv 同步前需自行准备可用的核心来源；上述 pip 安装按声明依赖解析。

## 配置

通过 `Config.sync_config("clovers_agent_life_extensions")` 同步，存放位置由宿主配置系统决定。字段定义见 [config.py](clovers_agent_life_extensions/config.py)。配置在模块导入时读取，修改后重启宿主。

### 画像与历史

| 字段                                   | 默认值 | 含义                                             |
| -------------------------------------- | ------ | ------------------------------------------------ |
| `user_profile.profile_memory_size`     | `30`   | 画像记忆触发整体衰减的条数阈值，不是硬性保留上限 |
| `user_profile.reminder_cooldown_turns` | `4`    | 计数小于该值时提示非必要不更新                   |
| `user_profile.reminder_turns`          | `8`    | 计数严格大于该值时提示检查是否过时               |
| `user_profile.strong_reminder_turns`   | `16`   | 计数严格大于该值时强提醒                         |
| `histories.keyword_fuzz_threshold`     | `85`   | 字符串模糊匹配阈值，预期范围 0–100               |
| `histories.recall_limit`               | `30`   | 取分数最高的候选条数，之后还会按候选均分筛选     |
| `histories.max_memory_size`            | `120`  | 每日归档时希望留在活动历史索引中的条数           |

`recall_limit` 应设为正整数。画像提醒计数保存在当前会话内，按已有画像进入 `on_chat` 钩子的次数增加，不是用户在所有会话中的总发言次数；重启或会话清理后重新计数。

### 聊天工具

| 字段                          | 默认值                          | 含义                                                   |
| ----------------------------- | ------------------------------- | ------------------------------------------------------ |
| `chat.max_sticker_candidates` | `32`                            | 贴纸过多时先按描述语义筛选到此数量                     |
| `chat.chat_utils_prompt`      | 见源码                          | 发送工具及贴纸使用提示，启动时追加到核心 `chat_prompt` |
| `chat.mimo_tts.url`           | `https://api.xiaomimimo.com/v1` | TTS 接入点，客户端追加 `/chat/completions`             |
| `chat.mimo_tts.model`         | `mimo-v2.5-tts-voiceclone`      | TTS 模型名                                             |
| `chat.mimo_tts.api_key`       | 空字符串                        | TTS 密钥，空值时不注册 `send_voice`                    |
| `chat.mimo_tts.extra_body`    | `{"audio":{"format":"wav"}}`    | TTS 额外请求体，需保留 `audio` 对象                    |

贴纸选择另用核心 `apis.sticker`，缺省回退核心默认 API。选择模型需能按 `response_format={"type":"json_object"}` 返回包含 `indices` 数组的 JSON。TTS 使用本插件 `chat.mimo_tts`，不是核心 `apis` 中的同名配置。

参考音频放到 `{clovers_agent.path}/chat_utils/`，文件名主体必须是 `ref_voice`，如 `ref_voice.wav`。代码在模块导入时寻找第一个匹配文件，并按识别的 MIME 子类型接受 MPEG / MP3 / WAV；参考音频可用且密钥非空才注册语音工具。准备好后需重启。

## 数据布局

所有路径基于核心 `clovers_agent.path`，默认 `./data/CloversAgent/`，不是仓库目录：

```text
{clovers_agent.path}/
├── UserProfile/
│   └── <user_id>.json
├── chat_utils/
│   └── ref_voice.wav
├── StickerPack/                  # 聊天工具运行时资源目录
└── sessions/
    └── <session_id>/
        ├── histories/            # 核心生成、等待处理的摘要
        ├── histories_processed/  # 活动历史
        ├── histories_unrecognized/
        └── histories_archived/
            └── YYYYMM/
```

画像按用户 ID 存一份文件，跨会话共用；历史按核心 Session 隔离。历史索引、召回列表、画像缓存、维护计数和贴纸列表缓存保存在 `session.extra`，不持久化为数据库。

## 长期历史

### 摘要来源与索引

核心压缩后生成 UTF-8 Markdown，front matter 必须能解析为 `overview` 字符串、`keywords` 集合和 `timestamp` 时间戳。正文是供 `expand_history` 展开的摘要内容，不是完整原始聊天记录。

进入 `on_chat` 时按以下流程准备：

1. 首次为该 Session 建立索引时读取 `histories_processed/`，复用核心句向量模型编码 overview。
2. 扫描归档 Markdown，仅补充关键词词表及相关统计，不将归档正文加入活动召回。
3. 检查 `histories/`，把有效且时间戳严格小于本批最大时间戳的条目移入 `histories_processed/` 并增量索引。
4. 不能解析的项目移入 `histories_unrecognized/`；该目录不自动修复或删除。

最新时间戳的一批摘要会留在 `histories/`，等后续出现更新的摘要才处理。因此只有一条新摘要时，它不会立即出现在召回中。

### 查询与排序

查询取当前 `message_history` 中的用户消息及助手文本，用户消息前带昵称；其他系统 / 历史标签不作为查询正文。

关键词先去两端空白、小写化，以 RapidFuzz 字符串相似度建立别名。这不是语义同义词归并，不能保证把“天气”和“天气预报”合并。

```text
相关性 = 0.5 × 归一化 BM25 + 0.5 × overview 余弦相似度
最终分数 = 相关性 × 2^(-i/30)
```

`i` 是按时间从新到旧排列后的零基位置，衰减取决于条目顺序，不是实际经过的天数。先取前 `recall_limit` 条，再仅保留不低于这些候选均分的条目；这是相对筛选，没有绝对相关度阈值。

注入模型的是从 1 开始的编号、时间与 overview。模型需要细节时调用 `expand_history(index)`，返回 Markdown 正文；编号只对应当前会话最近生成的召回列表，不能长期保存使用。

### 归档

启动钩子把归档函数登记到核心 `daily_tasks`，跟随核心每日维护执行。它只处理当时仍在 `agent.sessions` 且已有索引的会话；核心先清理过期会话，因此不是对磁盘全部历史目录进行全量扫描。

超过 `max_memory_size` 时，按最旧时间戳把多余活动历史移入 `histories_archived/YYYYMM/` 并从索引移除。归档不删除文件，不限制总磁盘占用，也不清除已有关键词统计。需要重新参与召回时，可停机后把目标文件移回 `histories_processed/`，下次建立索引时读取。

## 用户画像

### 字段与读写

| 字段          | 含义                                  |
| ------------- | ------------------------------------- |
| `nickname`    | 平台昵称，编辑时更新                  |
| `address_as`  | 助手对用户的称呼                      |
| `tags`        | 简短特征关键词字符串                  |
| `preferences` | 稳定偏好                              |
| `impression`  | 整体印象                              |
| `memories`    | 含 `id`、`content`、`star` 的记忆列表 |
| `block_until` | 拉黑截止 Unix 时间戳，`0` 为未拉黑    |

路由钩子先读取当前用户画像，普通聊天钩子再将画像转为 Markdown 注入上下文。没有画像时注入首次维护提示。Markdown 展示记忆编号和内容，不展示星级。

画像文件不是合法 JSON 或不符合模型结构时，当前实现会删除该文件并视为无画像。已缓存的画像不会在每轮重新读盘；跨会话写入或手工改文件不会立即刷新其他会话缓存。

### 维护工具

`update_user_profile()` 只返回维护准则和编辑参数说明，不写盘。随后用 `edit_user_profile()` 更新当前事件用户：

| 参数                                              | 行为                                                                                |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `address_as`、`tags`、`preferences`、`impression` | 非空字符串才覆盖，空字符串不能清空旧字段                                            |
| `new_memories`                                    | 字符串列表，新增为 1 星                                                             |
| `promote_memories`                                | 按 `id` 强化，星级加 1、上限 5；可用 `content` 合并内容；未知 ID 带内容时作为新记忆 |
| `demote_memory_ids`                               | 已存在且尚未被本次强化处理的 ID 降 1 星                                             |

所有编辑参数可选。先调用维护工具的要求来自工具描述，没有代码层面的调用顺序校验。编辑会更新昵称、写入 JSON，并尝试将当前会话该用户的提醒计数归零。

记忆按强化、弱化、新增、未处理旧记忆的顺序汇总，再按星级排序并重新从 1 编号。总数小于 `profile_memory_size` 时保留非负星级；达到或超过阈值时，先丢弃原本低于 1 星的记忆，再将剩余记忆整体降 1 星。代码没有按数量截断，所以记忆条数可能继续超过阈值；ID 也可能在每次编辑后改变。

### 拉黑

`block_user(block_days)` 针对当前用户，实际将天数夹在 1–30 之间并写入画像。Python 默认值为 7，但工具 schema 将该参数标为必填，模型调用时应显式提供。

未到期用户在后续路由钩子处结束处理，不发送额外回复；设置拉黑本身不会立即停止正在进行的当前调用链。它不是宿主平台黑名单，也不拦截绕过路由的主动插话或旁路路径。

## 聊天发送工具

这些工具属于 `on_chat`，需要适配器支持相应发送类型。

| 工具                  | 参数                                                          | 行为                                                                     |
| --------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `save_sticker`        | `image_index`、`description`                                  | 从当前 payload 最后一条 user 消息中的图片保存贴纸；索引从 0 起，支持负数 |
| `send_sticker`        | `intent`、可选 `stop_after_send=true`                         | 按意图选择并发送一张贴纸                                                 |
| `send_voice`          | `content`，可选 `style`、`sing=false`、`stop_after_send=true` | 条件注册的 TTS 语音工具，发送音频字节                                    |
| `send_direct_message` | `message`                                                     | 从群聊向当前 `event.user_id` 发送私聊，当前已是私聊则拒绝                |
| `send_group_message`  | `group_id`、`message`                                         | 向其他群发送文字，目标等于当前群时拒绝                                   |

### 贴纸与语音的轮次结束

`stop_after_send=true` 在成功发送后调用核心 `complete_session()` 结束当前轮次，避免再补文字；`false` 返回 `OK` 并继续工具循环。发送记录写入当前会话短期窗口，不等同于一次独立完成轮次的持久化。

贴纸超过候选数量时先按描述语义筛选，再让 `sticker` 模型返回候选编号，随机选择返回列表中的一个发送。保存图片从当前 payload 读取；若核心视觉转换已把图片替换为文字，工具可能提示没有找到图片。

语音普通模式可提供 `style`；`sing=true` 时在文本前加唱歌标记，不使用 `style`。请求依赖接入点返回 `message.audio.data` 的 base64 音频，平台需支持 `voice` 消息。

### 私聊与跨群

通过 `asyncio.create_task()` 后台发送，立即返回的 `OK` 只表示已提交，不能据此认定平台发送成功。后台任务会获取目标会话的执行锁与旁路锁；发送成功后将来源消息和助手文字写入目标短期窗口，不立即形成 JSONL 完成轮次。

使用适配器发送类型 `private_message`、`group_message`，消息体内是 `Result("text", message)`。目标是否可达由平台和适配器决定；群目标无需已存在 Session，工具会通过核心创建。

## 当前实现的边界与排查

| 现象 / 边界          | 说明                                                                                          |
| -------------------- | --------------------------------------------------------------------------------------------- |
| 安装后没生效         | 核对核心 `plugins`、宿主环境与当前场景；本包没有单独 `PLUGIN`                                 |
| 新摘要未召回         | 最新时间戳的一批会暂留；任务场景不运行普通聊天召回钩子                                        |
| 重启后召回语义不准确 | 当前初建索引排序条目与批量 embedding 使用的顺序可能不一致，不能保证所有条目向量正确对应       |
| 画像条数超过配置     | 配置是触发衰减的阈值，代码未按数量裁剪                                                        |
| `send_voice` 不存在  | 检查参考文件、识别格式、TTS 密钥；它们在导入时决定注册，需要重启                              |
| 贴纸选错或越界       | 当前候选提示从 1 编号，但结果直接作为 Python 列表下标使用，存在编号偏移；此说明未验证资源内容 |
| 修改提示词后效果丢失 | 插件启动时追加聊天提示；之后单独调用核心 `reload_prompts()` 会重建聊天提示，不自动重新追加    |

画像、摘要与贴纸描述会进入模型上下文，文件本身为本地明文。插件写入和发送在宿主权限下执行，没有独立数据库事务；备份时需考虑画像文件可能因解析失败被删除，以及归档并不回收磁盘空间。

## License

MIT，见 [LICENSE](LICENSE)。
