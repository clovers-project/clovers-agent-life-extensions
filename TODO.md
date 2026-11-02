# clovers_agent_life_extensions TODO

> 快照：2026-11-02 22:07（Asia/Shanghai）
> 版本：包内 `__version__ = "0.3.0"`；无 `pyproject.toml`、README、LICENSE、测试
> 规模：约 750 行，`memory`（长期记忆）+ `user_profile`（用户画像）两个子模块
> 说明：基于静态审阅；当前工作区没有依赖环境，未做运行时验证。路径均相对工作区根目录。

## 一、现状

### 它解决什么问题

`clovers-agent` 自带的记忆是「当前会话的滑动窗口 + 超长时压缩摘要」。本插件在它之上补了两件事：

- **长期记忆**：把压缩后的历史摘要建立索引，按「关键词 BM25 + 语义向量 + 新近度」混合召回，并在需要时展开原文
- **用户画像**：按用户维护称呼、标签、偏好、印象和带星级的用户记忆，附带更新提醒、拉黑与两步式编辑工具

### 代码结构

| 文件 | 作用 |
| --- | --- |
| `base.py` | `TOOLS = AgentTools()`，同步插件配置 |
| `config.py` | `user_profile` / `histories` 两组配置 |
| `__init__.py` | 在 `ON_CHAT` intro 上挂钩子：先检索历史，再拼用户画像 |
| `memory/main.py` | 索引准备、召回、`expand_history`、每日归档 |
| `memory/utils.py` | `HistoryEntry` / `HistoryIndex`：别名归一化、BM25、向量、时间衰减 |
| `user_profile/main.py` | 画像注入、提醒、`update_user_profile` / `edit_user_profile` / `block_user` |
| `user_profile/constants.py` | 画像维护准则与工具说明提示词 |
| `user_profile/typing.py` | `UserProfile` 模型与 Markdown 渲染 |

### 一次聊天里的流程

1. `ON_CHAT` intro 被选中后触发钩子（`__init__.py:8`）
2. `intro_retrieve_history` 把当前会话的 `histories/*.md` 建索引并召回相关摘要
3. `intro_user_profile` 读取 `{agent.path}/UserProfile/<user_id>.json`，拼成 Markdown，并按轮数追加更新提醒
4. 模型可调用 `expand_history` 展开某条摘要；可调用 `update_user_profile` 拿到维护提示词，再调用 `edit_user_profile` 落盘
5. 每日 02:00 的维护任务把超过 `max_memory_size` 的旧摘要移到 `histories_archived/YYYYMM/`

### 已有设计亮点

- 混合召回：BM25（关键词）+ 语义相似度 + 按条目序号的时间衰减，权重可调
- 关键词别名：模糊匹配（rapidfuzz）把近义词归一到同一 canonical keyword，降低措辞差异
- 索引增量：已处理的摘要移入 `histories_processed/`，只在首次构建时读目录
- 与 `clovers-agent` 的摘要 front matter 直接兼容（`overview` / `keywords` / `timestamp`）
- 画像有两层：结构化字段（称呼/标签/偏好/印象）+ 星级用户记忆，支持 promote / demote / 新增 / 合并
- 提醒有冷却与强弱分级，避免每轮都催模型更新
- 无法识别的历史文件会移入 `histories_unrecognized/`，而不是直接删除

### 关键缺口

- **没有打包**：没有 `pyproject.toml`，直接 `import` 会缺 `rapidfuzz`
- **没有测试**：索引、画像状态机、拉黑都没有回归保护
- **只有 `ON_CHAT` 生效**：任务场景（如 `on_task`）既不会注入画像/记忆，也不会检查拉黑
- **数据安全**：画像 JSON 直接 `write_text`，无锁、无原子写、无备份；损坏即删
- **路径安全**：`user_id` 直接拼文件路径，未做字符校验
- **可观测性**：静默跳过、静默归档、静默吞异常，出问题很难定位

## 二、P0 — 发布前必须处理

- [ ] **补 `pyproject.toml`，声明 `rapidfuzz`**：`memory/utils.py:9` 直接 `from rapidfuzz import fuzz`，但它不在 `clovers-agent` 的依赖里；当前仓库也没有任何依赖声明，干净环境会 `ImportError`
    - 直接依赖至少：`clovers-agent>=0.3.4`、`pydantic`、`python-frontmatter`、`rapidfuzz`、`torch`、`sentence-transformers`
    - 同时补 `README.md`、`LICENSE`、`requires-python >=3.12`，版本与 `__init__.__version__` 单一来源
- [ ] **修 `block_user` 在目录不存在时崩溃**：`user_profile/main.py:61-68` 直接 `write_text`，但 `UserProfile/` 只在 `edit_user_profile` 里创建（`main.py:113`）；首次拉黑一个没有画像的用户会 `FileNotFoundError`
- [ ] **修 `block_user` 对损坏 JSON 的处理**：`main.py:64` 的 `model_validate_json` 没有 `try`；画像损坏时拉黑工具直接失败，且没有隔离/备份
- [ ] **修画像容量衰减导致的记忆清空**：`main.py:158-161` 在达到 `profile_memory_size` 时把所有 `star >= 1` 的记忆统一减 1，但**减完不再过滤**：
    - 第一次触顶：所有 1 星变 0 星并保留
    - 下一次触顶：0 星被 `if star >= 1` 全部过滤 → 用户记忆整体消失
    - 建议：只淘汰最低星级/最旧的超额部分，或先保留 top N 再做衰减，并加不变量测试
- [ ] **修每日归档后的索引失效**：`archive_history`（`memory/main.py:107-115`）把文件移到 `histories_archived/`，但内存索引里的 `IndexedHistory.path` 仍指向旧位置；之后 `expand_history` 读 `entry.content`（`memory/utils.py:36-39`）会 `FileNotFoundError`
    - 归档时同步从索引移除或更新路径；`expand_history` 对缺失文件回退到归档目录
- [ ] **校验 `user_id` 路径**：`user_profile/main.py:32`、`61`、`112` 都用 `f"{user_id}.json"` 拼路径；平台 id 含 `/`、`\`、`..` 时可读写画像目录外文件。加字符白名单 + `resolve()` 后校验父目录
- [ ] **拉黑不能只拦 `ON_CHAT`**：`intro_user_profile` 只在 `ON_CHAT` 钩子里调用（`__init__.py:8`、`user_profile/main.py:41-42`）；被拉黑用户切到 `on_task` 等 intro 仍然可用。把检查提到会话入口（`on_input` 级别）或给所有 intro 挂同一检查
- [ ] **验证空历史时的索引初始化**：新会话第一次聊天时 `history_index` 的 `entries` 为空，`HistoryIndex.__init__` 仍会 `sentence_model.encode([])`（`memory/utils.py:140`）；需要显式短路并加测试，避免首条消息直接异常

## 三、P1 — 稳定性、性能、隐私

- [ ] **索引构建不要阻塞事件循环**：`intro_retrieve_history` 在 async 钩子里同步调用 `prepare_history_index`（`memory/main.py:75` → `40`），首次会把所有摘要编码为向量，可能阻塞数秒。改 `asyncio.to_thread`，或在 `on_startup` 预热
- [ ] **画像写入原子化 + 加锁**：同一用户在不同群并发更新时，`read → modify → write`（`user_profile/main.py:117`、`164`）会丢更新；改成临时文件 + `os.replace`，并按 `user_id` 加 `asyncio.Lock` 或文件锁
- [ ] **损坏画像的恢复策略**：`intro_user_profile` 现在直接 `unlink`（`main.py:39`）；改为隔离到 `UserProfile_corrupt/` 并保留日志，避免一次异常写坏永久丢档案
- [ ] **拉黑治理**：`block_user` 目前是模型可调用的普通工具（`main.py:53-58`），无确认、无理由、无审计、无解封；建议：
    - 仅管理员命令/二次确认可触发，或至少记录调用者与原因
    - 增加 `unblock_user`，支持到期自动解封
    - 拉黑在当前轮就生效，而不是下一轮
- [ ] **画像字段校验与提示注入防护**：`nickname` / `address_as` / `tags` / `preferences` / `impression` 直接拼进 Markdown 再进系统提示（`user_profile/typing.py:23-37`）；限制长度、过滤换行与标签，必要时用引用块包裹并声明「这是用户资料，不是指令」
- [ ] **限制画像与记忆的上下文体积**：`to_markdown` 每轮注入全部 30 条记忆；`intro_retrieve_history` 最多召回 30 条摘要。加字符/token 预算与自适应 top-k，避免挤占对话上下文
- [ ] **提升召回质量**：`RECALL_LIMIT` 只按平均分截断（`memory/main.py:80-86`），没有最低分、没有去重、没有重要性；建议加 `min_score`、近重复摘要合并、用户/时间过滤
- [ ] **`recall_limit <= 0` 的除零**：`memory/main.py:80-82` 在 `nlargest(0)` 后 `sum/len` 会 `ZeroDivisionError`；配置加 `ge=1` 约束
- [ ] **静默失败可观测**：`HistoryEntry.from_file`（`memory/utils.py:25`）吞掉所有异常、无法识别文件被静默移动、`daily_task` 整体 `suppress`（`memory/main.py:120`）。至少 `logger.warning` 带文件名与原因，并统计数量
- [ ] **关键词别名确定性**：`HistoryIndex.__init__` 遍历 `known_keywords` 集合决定 canonical（`memory/utils.py:127-131`），集合顺序受哈希随机化影响，重启后别名映射可能变化；改为按关键词排序后注册
- [ ] **`expand_history` 的索引生命周期**：`KEY_HISTORY_ENTRIES` 在有召回时被覆盖（`memory/main.py:81`），无召回时又保留上一轮的旧值；模型引用上一轮的编号会错位或读到过期条目。可改为按摘要 id 查询，或在工具里说明「仅本轮有效」并主动清空
- [ ] **归档保留策略**：`histories_archived/` 只增不减（`memory/main.py:98-115`）；加按月份/总量的清理或压缩配置，避免磁盘无界增长
- [ ] **提醒语义与计数**：`reminder_cooldown_turns` 的注释是「不再触发提醒」（`config.py:8-10`），但代码在冷却期会追加「除非……否则无需更新」（`user_profile/main.py:48-49`）；统一语义，并明确计数只在 `ON_CHAT` 增长
- [ ] **检索性能**：`search` 每轮对全部条目做 Python 循环 + 一次 query encode（`memory/utils.py:234-261`）；条目上千后考虑向量矩阵预计算、批量 top-k、embedding 缓存
- [ ] **空查询与超长查询**：`message_history` 为空（长时间静默后）时仍会编码空串；超长消息会拖慢关键词扫描。加长度上限与空查询短路

## 四、P2 — 工程质量

- [ ] **测试骨架**：`pytest` + `pytest-asyncio`，用固定向量模型替身（不要真下载模型）
    - `HistoryIndex`：空索引、BM25、模糊匹配、别名归一、更新、时间衰减、重复条目
    - 画像状态机：新增/提升/弱化、触顶淘汰不变量、损坏文件、拉黑/解封
    - 钩子集成：`ON_CHAT` 注入内容、`on_task` 不注入（若保持现状）
- [ ] **CI**：3.12 / 3.13，`ruff check`、`ruff format --check`、`mypy`、`pytest`
- [ ] **类型与静态检查**：`memory/utils.py` 里 `find_fuzzy_match` 的隐式 `None`、`HistoryEntry.from_file` 的 `Path | None`、`bm25` 的 `list[float] | None` 都可以收紧
- [ ] **README / 架构说明**：配置、数据目录、隐私边界、与 `clovers-agent` 的版本兼容
- [ ] **CHANGELOG + 版本策略**：当前 0.3.0；明确与 `clovers-agent` 的配套关系
- [ ] **配置开关**：`memory_enabled` / `profile_enabled`、按群/按用户禁用、拉黑名单外置；目前只要装了插件就全量生效
- [ ] **日志与指标**：召回条数/最高分/耗时、画像更新次数、拉黑事件、归档数量
- [ ] **多进程/持久化**：索引在 `session.extra` 内存里，重启重建；多进程部署时画像文件需要文件锁
- [ ] **数据备份/迁移**：画像 JSON 的 schema 变更需要迁移脚本；`UserProfile` 目前没有版本字段

## 五、功能建议

按「先补体验闭环，再做深度」排序；★ 为推荐优先做。

### 记忆

| 建议 | 价值 | 实现要点 | 量 |
| --- | --- | --- | --- |
| ★ 主动回忆扩展到更多场景 | 现在只在 `ON_CHAT` 注入；任务、插话、旁路都用不上长期记忆 | 把钩子挂到 `on_task` / `chime_in`，或给 `clovers-agent` 加统一的 pre-turn 上下文钩子 | M |
| ★ 显式记忆检索工具 `search_history(query, time_range)` | 自动召回只覆盖「当前话题」；用户问「上次那个方案」时需要精确检索 | 复用 `HistoryIndex.search`，支持 `before` / `after` 过滤，返回可展开的编号 | S |
| ★ 夜间整合与遗忘 | 人类会在睡眠中巩固记忆；当前只在 02:00 做归档，没有合并/晋升 | 每日任务里用 `summary` 模型：合并近重复摘要、把反复出现的事实晋升到用户画像、对长期未命中的记忆降权 | L |
| 时间感知检索 | 「上周」「我生日那天」这类查询目前只能靠语义碰运气 | 解析相对时间、给摘要加时间桶、把「序号衰减」换成「时间衰减」 | M |
| 记忆去重与冲突检测 | 同一件事可能被压缩成多条摘要，注入后重复且互相矛盾 | 注入前按 embedding 相似度去重；与旧记忆冲突时标记「待确认」，不要直接覆盖 | M |
| 记忆管理命令 | 用户无法查看/删除被记住的内容，隐私上不可接受 | `/memory list`、`/memory search`、`/memory forget`、`/memory pin`；与 `expand_history` 共用编号 | M |
| 群组记忆 | 群规、梗、项目背景是「群的」而不是「某个用户的」 | 以 `group_id` 为键维护群画像，与用户画像分开注入 | M |
| 持久化向量索引 | 每次重启/会话过期都重建 embedding，成本高 | SQLite/JSONL + 向量缓存（按文件 mtime/hash），跨进程共享 | L |
| 召回质量评测 | 现在权重（0.5/0.5）、阈值（85）、半衰期（30）都是拍脑袋 | 构造 golden query → 期望摘要，离线算 recall@k / MRR / 延迟，再调参 | M |

### 用户画像

| 建议 | 价值 | 实现要点 | 量 |
| --- | --- | --- | --- |
| ★ 结构化字段与校验 | 现在是自由文本，模型容易写长、写乱、写重复 | `tags: list[str]`（硬限制 5 个）、时区/语言/禁忌/重要日期；字段长度与格式校验 | S |
| ★ 后台批量整理 | 目前每轮靠提示词催模型调两次工具，费 token 且打断聊天 | 用 `summary` 模型在 N 轮后或每日离线提炼，写入画像；主对话只读不写 | M |
| ★ 记忆强度可解释 | `star` 对模型不可见，promote/demote 的效果无法验证 | 在 Markdown 里显示强度/时间，或只注入 top-K；明确衰减规则 | S |
| 画像版本与回滚 | 一次错误编辑会覆盖称呼/印象，且无法恢复 | 每次写入保留上一版快照（`UserProfile/history/`），支持 diff/rollback | M |
| 用户控制与导出 | 用户应能查看、导出、删除自己的档案 | `/profile show`、`/profile export`、`/profile delete`；删除时同步清理摘要中的个人信息 | M |
| 拉黑治理 | 模型自行拉黑用户风险高，且没有解封入口 | 管理员命令 + 原因/时长/审计 + 到期自动解封；全 intro 生效 | S |
| 关系时间线 | 「上次你说面试，后来怎么样」是最能体现长期记忆的体验 | 记录首次见面、共同经历、称呼变化；在合适时机由模型自然引用，避免硬提醒 | M |
| 重要日期提醒 | 生日、考试、旅行等时间点很适合主动关心 | 画像增加日期字段（opt-in），每日任务检查并生成提醒；注意时区与隐私 | S |

### 体验与运营

| 建议 | 价值 | 实现要点 | 量 |
| --- | --- | --- | --- |
| ★ 配置开关与分群策略 | 不同群对「被记住」的接受度不同 | `enabled`、按群白名单、按用户 opt-out；配置校验 | S |
| 管理命令 | 运维需要看召回/画像/拉黑状态 | `/memory stats`、`/profile show`、`/block`、`/unblock` | S |
| 可观测性 | 出问题时只能翻日志猜 | 召回数量/分数/耗时、画像更新、归档、拉黑事件；结构化日志 | S |
| Agent 自传记忆 | 记住「自己答应过什么/做过什么」，减少前后矛盾 | 单独存 agent 侧事件（承诺、任务结果），与用户画像分离 | L |
| 多语言与分词 | 关键词匹配对中文短词、英文词形变化都不够稳 | 按语言选择分词/归一化；英文词干化；短 CJK 词放宽模糊阈值 | M |
| 提示注入与 PII | 画像内容会再次进入系统提示，等于可被用户间接注入 | 包裹为数据块、过滤控制字符、敏感信息脱敏、保留期与删除策略 | M |

### 生活化功能（更远）

| 建议 | 价值 | 实现要点 | 量 |
| --- | --- | --- | --- |
| 日程与提醒 | 「下周三提醒我交材料」是长期关系里最自然的需求 | 解析时间/重复规则 → `clovers_apscheduler` 定时任务 → 到点用唤醒消息提醒；支持取消/改期/时区 | M |
| 主动问候 | 久未联系、早晚安、节日时主动开口，关系更像「活的」 | 基于 `last_active_time`、画像与最近话题生成；严格 opt-in + 频率上限，避免骚扰 | M |
| 周记 / 回忆录 | 把一周的摘要整理成「我们这周聊了什么」，可回看、可分享 | 复用 `summary` 模型与 `histories_processed/`；按周聚合，生成 Markdown 存到用户目录 | M |
| 习惯与目标追踪 | 用户提到健身、学习、项目计划时，能持续跟进而不是聊完就忘 | 画像增加目标条目（带状态/截止时间），在合适时机轻量询问；不要变成打卡监督 | L |

如果只能先做三件事：**主动回忆扩展到任务/插话**、**显式 `search_history`**、**后台画像整理**。它们直接决定「长期记忆是否真的被用起来」，而不用先改存储层。

## 六、里程碑建议

| 版本 | 范围 | 预估 |
| --- | --- | --- |
| 0.3.1 | P0 全部 + 打包 + README + 最小测试 | 1-2 天 |
| 0.4.0 | P1 稳定性/安全 + 索引预热 + 测试/CI | 1-2 周 |
| 0.5.0 | 后台画像整理、`search_history`、记忆管理命令 | 2-3 周 |
| 0.6.0 | 夜间整合、持久索引、群组记忆、召回评测 | 1-2 个月 |

## 七、需要拍板

1. **拉黑权**：只允许管理员命令，还是保留模型在明确被要求时调用？当前模型可自行拉黑，风险最高
2. **画像范围**：一个用户一份全局画像，还是允许「群内人设」覆盖？现在跨群共享
3. **记忆范围**：摘要目前属于会话（群），用户画像属于用户；是否要跨群用户记忆
4. **注入范围**：只在 `ON_CHAT`，还是所有 intro（含任务）都带画像/记忆？这决定是否需要改 `clovers-agent` 的钩子
5. **星级语义**：`star` 是重要性、置信度还是新近度？当前同时承担「强化」和「容量淘汰」，语义不清
6. **存储后端**：继续文件 + 内存索引，还是上 SQLite（画像 + 索引 + 归档元数据）？
7. **隐私基线**：默认记住多少、保留多久、用户如何 opt-out；这会影响默认配置与文档
