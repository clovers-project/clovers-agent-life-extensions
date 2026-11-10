# clovers-agent-life-extensions

Clovers Agent 的生活化扩展：让助手回忆历史话题、维护用户画像，并通过贴纸、语音、私聊和跨群消息参与交流。

本插件导出 `TOOLS`，由 `clovers-agent` 的工具插件加载器接入。当前源码版本为 `0.3.4`，需要 Python `>=3.12,<4.0` 和 `clovers-agent>=0.3.8`。

## 功能

| 模块     | 能力                                                       |
| -------- | ---------------------------------------------------------- |
| 长期历史 | 检索核心生成的历史摘要，混合关键词与语义排序，按需展开正文 |
| 用户画像 | 记录称呼、标签、偏好、印象与星级记忆，按轮次提醒维护       |
| 用户拉黑 | 根据画像中的截止时间，在场景路由前停止处理该用户的正式输入 |
| 贴纸     | 收藏当前消息中的图片，按情绪与表达意图选择贴纸回复         |
| 语音     | 使用参考音频生成语音，支持表达风格与唱歌模式               |
| 定向消息 | 向当前群聊用户发送私聊，或向指定的其他群发送文字           |

历史召回、画像注入和工具绑定在核心 `on_chat` 场景。拉黑检查使用 `:router` 钩子，在场景选择前运行；核心的主动插话与主任务执行中的旁路回复不经过这项检查。

## 安装与加载

在仓库根目录，将插件安装到 Clovers 宿主使用的 Python 环境：

```bash
python -m pip install -e .
```

在核心 `clovers_agent` 配置中，将模块名加入 `plugins`，并保留原有插件：

```json
{
  "plugins": ["clovers_agent_life_extensions"]
}
```

启动或重启宿主，由核心加载本插件。核心的模型接入点与消息准入规则需先配置完成，本包不提供独立的机器人入口。

依赖以 [pyproject.toml](pyproject.toml) 为准。历史检索与贴纸预筛选复用核心句向量模型，无需另外配置向量服务或数据库。

仓库的 uv 开发配置将核心源码指向 `D:/CLOVERS/clovers-agent/clovers-agent`。在其他机器使用 uv 同步时，应先调整该来源；pip 安装按项目声明的依赖解析。

## 配置

插件使用 `Config.sync_config("clovers_agent_life_extensions")` 接入宿主配置系统，配置文件位置由宿主决定。配置定义见 [config.py](clovers_agent_life_extensions/config.py)。修改后重启宿主。

### 历史与画像

| 字段                                   | 默认值 | 说明                                                   |
| -------------------------------------- | ------ | ------------------------------------------------------ |
| `histories.keyword_fuzz_threshold`     | `85`   | 关键词字符串模糊匹配阈值，预期范围 0–100               |
| `histories.recall_limit`               | `30`   | 历史召回候选上限，之后按候选均分进一步筛选；应为正整数 |
| `histories.max_memory_size`            | `120`  | 每日归档时保留的活动历史数量                           |
| `user_profile.profile_memory_size`     | `30`   | 用户记忆触发整体衰减的数量阈值                         |
| `user_profile.reminder_cooldown_turns` | `4`    | 距上次更新的计数小于此值时，提示非必要不更新           |
| `user_profile.reminder_turns`          | `8`    | 计数严格大于此值时，提醒检查画像是否过时               |
| `user_profile.strong_reminder_turns`   | `16`   | 计数严格大于此值时，提示及时更新                       |

画像提醒计数按会话、用户分别记录，统计已有画像进入普通聊天钩子的次数；不代表用户的全局消息数量。编辑后重置当前会话计数，重启或会话清理后计数重新开始。

### 贴纸与聊天提示

| 字段                          | 默认值 | 说明                                           |
| ----------------------------- | ------ | ---------------------------------------------- |
| `chat.max_sticker_candidates` | `32`   | 贴纸数量超过此值时，先用描述语义相似度筛选候选 |
| `chat.chat_utils_prompt`      | 见源码 | 发送工具的使用提示，启动时追加到核心聊天提示词 |

贴纸选择模型使用核心 `apis.sticker`，未配置时回退核心默认模型。它需要支持 JSON object 响应，并按提示返回包含 `indices` 整数数组的 JSON。

### 语音

插件配置示例：

```json
{
  "chat": {
    "mimo_tts": {
      "url": "https://api.xiaomimimo.com/v1",
      "model": "mimo-v2.5-tts-voiceclone",
      "api_key": "your-api-key"
    }
  }
}
```

这三个默认字段中，`api_key` 默认为空字符串。`mimo_tts` 也支持 `extra_body`，默认空对象。客户端在 `url` 后追加 `/chat/completions`；语音工具会在请求中设置 `audio={"format":"wav","voice":参考音频}`，无需额外配置 `audio`。

将参考音频放到核心数据目录的 `chat_utils/` 中，文件名主体为 `ref_voice`，例如：

```text
./data/CloversAgent/chat_utils/ref_voice.wav
```

代码在模块导入时寻找首个匹配文件，按文件内容识别 MPEG / MP3 / WAV。参考音频可用且 TTS 密钥非空时才注册 `send_voice`，因此放入音频或修改密钥后需要重启。

## 工具

以下工具在普通聊天场景中可用，发送功能需要平台适配器支持。

| 工具                  | 参数                                                          | 作用                                                |
| --------------------- | ------------------------------------------------------------- | --------------------------------------------------- |
| `expand_history`      | `index`                                                       | 展开本轮召回列表中指定编号的历史正文，编号从 1 开始 |
| `update_user_profile` | 无                                                            | 返回画像维护准则与编辑参数说明，本身不写盘          |
| `edit_user_profile`   | 见下文，全部可选                                              | 更新当前用户画像与记忆                              |
| `block_user`          | `block_days`                                                  | 设置当前用户的拉黑截止时间，天数限制在 1–30         |
| `save_sticker`        | `image_index`、`description`                                  | 收藏当前输入中的图片，图片索引从 0 开始，支持负数   |
| `send_sticker`        | `intent`，可选 `stop_after_send=true`                         | 根据意图选择并发送一张贴纸                          |
| `send_voice`          | `content`，可选 `style`、`sing=false`、`stop_after_send=true` | 生成并发送语音，仅在语音配置就绪时注册              |
| `send_direct_message` | `message`                                                     | 从群聊向当前用户发送私聊                            |
| `send_group_message`  | `group_id`、`message`                                         | 向指定的其他群发送文字                              |

### 发送与结束轮次

贴纸和语音的 `stop_after_send=true` 表示发送成功后结束当前轮次，避免再补文字。设为 `false` 时返回 `OK`，允许继续操作或回复。发送内容同时写入当前会话的短期记录。

贴纸先按描述筛选候选，再调用选择模型，从模型返回的编号中随机取一个发送。候选从 1 编号，代码转换为列表下标后读取对应文件。保存贴纸从当前 payload 的最后一条 user 消息取图；若图片已经被核心视觉转换为文字，可能无法找到原图。

语音的 `style` 用于描述表达方式；`sing=true` 时在内容前添加唱歌标记，不使用 `style`。响应需包含 `message.audio.data` 的 base64 音频，再通过 `voice` 类型发送。

私聊和跨群发送通过后台任务执行，工具立即返回的 `OK` 表示已提交发送。后台任务等待目标会话锁，发送成功后将来源说明与助手文字写入目标短期窗口，不立即生成一条 JSONL 完成轮次。当前已在私聊时不能再向自身私聊会话发送，跨群目标也不能等于当前群。

## 长期历史

### 索引与召回

历史来源是核心压缩后生成的 UTF-8 Markdown。front matter 需要 `overview`、`keywords`、`timestamp`，正文是摘要文本。

进入普通聊天时，插件为会话准备索引：首次读取 `histories_processed/` 建立内存索引，再处理 `histories/` 的新文件。无法解析的项目移到 `histories_unrecognized/`。当前批次中时间戳最新的摘要保留在 `histories/`，等出现更新摘要后再入索引，因此单条新摘要不会立即参与召回。

查询来自当前短期消息窗口，包含用户名、用户文本和助手文本。关键词去两端空白并转小写，再以 RapidFuzz 字符串相似度归一；语义匹配使用 overview 的句向量。

```text
相关性 = 0.5 × 归一化 BM25 + 0.5 × overview 余弦相似度
最终分数 = 相关性 × 2^(-i/30)
```

`i` 是条目按时间从新到旧排列后的位置，从 0 开始。衰减按条目顺序计算。取前 `recall_limit` 条后，仅保留不低于这些候选平均分的条目。

模型先看到编号、时间和 overview，需要细节时调用 `expand_history(index)` 读取正文。编号随召回结果变化，应以当前列表为准。

### 归档

归档函数登记到核心每日维护任务，只处理当时仍在内存且已建立索引的会话。超过 `max_memory_size` 时，把最旧条目移入 `histories_archived/YYYYMM/` 并从活动索引移除。

归档内容不参与正文召回；索引重建时会读取归档关键词补充词表与相关统计。归档不删除文件，因此总磁盘占用仍会增长。需要重新召回的文件可停机后移回 `histories_processed/`，待下次重建索引。

## 用户画像

画像按用户 ID 存在 `UserProfile/<user_id>.json`。缓存保存在 `agent.extra`，同一 Agent 进程的不同会话共享画像对象；提醒计数仍保存在各自的 Session 中。

| 字段          | 内容                                  |
| ------------- | ------------------------------------- |
| `nickname`    | 平台昵称，编辑时更新                  |
| `address_as`  | 助手对用户的称呼                      |
| `tags`        | 特征关键词字符串                      |
| `preferences` | 稳定偏好                              |
| `impression`  | 整体印象                              |
| `memories`    | 含 `id`、`content`、`star` 的记忆列表 |
| `block_until` | 拉黑截止 Unix 时间戳，`0` 表示未拉黑  |

普通聊天将画像转为 Markdown 提示，没有画像时提示在上下文充分后首次建立。展示记忆编号与内容，不展示星级。文件解析失败时，当前实现会删除该文件并视为无画像；手工修改文件后应重启以刷新内存缓存。

### 编辑画像

先调用 `update_user_profile` 获取准则，再调用 `edit_user_profile`：

| 参数                                              | 行为                                                                         |
| ------------------------------------------------- | ---------------------------------------------------------------------------- |
| `address_as`、`tags`、`preferences`、`impression` | 非空字符串覆盖旧值，空字符串不会清空                                         |
| `new_memories`                                    | 字符串列表，新增为 1 星                                                      |
| `promote_memories`                                | 按 `id` 强化，加 1 星，上限 5；可用 `content` 合并内容，未知 ID 带内容时新增 |
| `demote_memory_ids`                               | 将尚未被本次强化处理的指定记忆降 1 星                                        |

参数全部可选。维护顺序由工具描述约定，代码不强制校验是否先调用过维护工具。

编辑后按星级排序并从 1 重新编号，后续操作应使用最新 ID。总数小于 `profile_memory_size` 时保留非负星级；达到或超过阈值时，丢弃原本低于 1 星的记忆，其余整体降 1 星。该配置是衰减阈值，当前不按条数截断。

### 拉黑

`block_user` 修改当前用户的 `block_until` 并写盘。Python 默认值是 7 天，但工具 schema 将 `block_days` 标为必填，模型调用时应显式提供。拉黑在后续路由检查中生效，不立即停止当前调用链，也不代替宿主平台的黑名单功能。

## 数据目录

根目录来自核心 `clovers_agent.path`，默认 `./data/CloversAgent/`：

```text
{clovers_agent.path}/
├── UserProfile/
│   └── <user_id>.json
├── chat_utils/
│   └── ref_voice.wav
├── StickerPack/
└── sessions/
    └── <session_id>/
        ├── histories/
        ├── histories_processed/
        ├── histories_unrecognized/
        └── histories_archived/
            └── YYYYMM/
```

画像跨会话共用，历史按 Session 隔离。历史索引与召回列表只存内存，重启后按文件重建。本说明仅描述代码使用的贴纸资源路径，不验证仓库贴纸资源。

## 排查

| 现象                | 检查项                                                                     |
| ------------------- | -------------------------------------------------------------------------- |
| 插件工具未出现      | 是否在宿主环境安装、核心 `plugins` 是否加载模块、当前是否普通聊天场景      |
| 新摘要没有召回      | 是否为暂留的最新摘要，是否进入 `on_chat`                                   |
| `send_voice` 不存在 | 参考文件的路径与识别格式、TTS 密钥，以及修改后是否重启                     |
| 定向消息没有送达    | 平台适配器是否支持 `private_message` / `group_message`，并查看后台任务日志 |
| 聊天提示丢失        | 核心单独调用 `reload_prompts()` 会重建提示，不会自动重新追加插件启动提示   |

画像、历史与工具描述可能进入模型上下文，数据以本地明文保存。建议定期备份画像及历史目录。

## License

MIT，见 [LICENSE](LICENSE)。
