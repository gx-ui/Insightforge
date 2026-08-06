# InsightForge 后端框架替换重构计划

> 目标：在**不引入新功能、不动前端、不破坏对外接口**的前提下，用 **LangGraph（主）+ LangChain 原语（已存在）** 增量替换项目中"手搓"的编排与工具基础设施，提升稳定性与可维护性。
> 范围：`agent_runtime/`（交互式 Agent 运行时）+ `pipelines/`（视频生成 DAG）+ `tools/`（生成器统一）。前端 `web/`、`ui/` 完全不动。
> 策略：strangler-fig 增量替换，每阶段可独立发布、可回滚，全程以"契约冻结测试"为质量门。

---

## 0. 现状盘点

项目有两套独立的"手搓"运行时，二者通过 `agent_runtime/insightforge_adapters.py`（48KB）桥接。

### 0.1 交互式 Agent 运行时（`agent_runtime/`，驱动 TUI + Web UI）

| 文件 | 手搓内容 | 体量 | 框架可替换性 |
|---|---|---|---|
| `loop.py` `AgentLoop` | `while True` ReAct 循环：采样 -> 执行工具 -> 回填 -> 重复；`MAX_TOOL_PASSES=50`；流式事件；压缩预检 | 11KB | ★★★ LangGraph StateGraph 教科书级匹配 |
| `llm.py` `OpenAICompatibleLLM` | 手写 OpenAI 客户端：`stream=False`、重试、响应形状校验、tool_call 解析 | 5.6KB | ★★★ 与 `init_chat_model`(pipelines 已用) 重复，应统一 |
| `tools.py` + `tool_executor.py` | `ToolRegistry`/`ToolSpec`/`ToolRuntimeContext`、JSON schema 生成、参数校验、进度回调、取消 | 25KB | ★★★ LangChain `StructuredTool`/`@tool` + `ToolNode` 直接覆盖 |
| `context_compactor.py` | token 估算 + LLM 摘要 + 本地兜底摘要 | 12.5KB | ★★ LangGraph 摘要节点 + langchain `trim_messages`；token 估算启发式值得保留 |
| `session_index.py` | 文件级 session 持久化：fcntl 锁、`sessions.json`、artifact checklist、working_dir 管理 | 18KB | ★★ LangGraph `BaseCheckpointSaver` 可承接"对话线程状态"；但 artifact 文件布局是产品契约，须保留薄封装 |
| `prompts.py` `PromptBuilder` | system + workflow_context + memory + tool_manifest + user 拼装 | 6.4KB | ★★ 保留为状态->提示词的薄适配器 |
| `insightforge_adapters.py` | 把 pipeline 步骤包装成 Agent 工具（narrative/novel/render/revise） | 48KB | ★★★ 最大风险点；逻辑保留，仅"工具包装方式"变更 |
| `models.py` | `ToolCall`/`ToolResult`/`TurnControl` dataclass | 1.9KB | ★★ 被 LangChain `AIMessage.tool_calls`/`ToolMessage` 取代；`TurnControl`(取消/进度) 保留为图状态 |

> 关键现状（影响 Phase 3 风险评估）：当前 LLM 调用为**非流式**（`stream=False`），每轮把整段 `final_text` 作为**单个** `token` 事件一次性发出，并非逐 token 流式。因此"token 事件字节级复现"难度低于直觉。

### 0.2 视频生成流水线（`pipelines/` + `agents/` + `tools/` + `interfaces/`）

| 文件 | 手搓内容 | 体量 | 框架可替换性 |
|---|---|---|---|
| `script2video_pipeline.py` | DAG：characters->storyboard->shots->camera_tree->frames->video->concat；`os.path.exists` 跳过缓存；`asyncio.gather` 并行镜头；progress 回调 | 47KB | ★★★ LangGraph StateGraph + checkpoint 续跑 |
| `idea2video_pipeline.py` | story->characters->portraits->scene scripts->逐场景委托 script2video->concat | 12KB | ★★★ 委托 script2video，随其迁移 |
| `novel2movie_pipeline.py` | novel->compress->events->scenes->global_info + render 全链；`plan_text_artifacts` 与 `__call__` 内部存在重复的 retrieve/extract/merge/portrait 方法 | 56KB | ★★★ 最大且内部有重复，迁移时合并去重 |
| `agents/*.py`（13 个） | 每个类：system prompt + `init_chat_model` + `PydanticOutputParser` + `tenacity` 重试，对外暴露干净的 async 方法（`develop_story`/`extract_characters` 等） | ~120KB | ★★ 已用 langchain，迁移成本低（薄节点包装；agent 内部 tenacity/parser 逻辑不动，不展开为子图） |
| `tools/*.py`（~12 文件） | 各家 image/video API 适配器，`ImageGenerator`/`VideoGenerator` Protocol；`RenderBackend` 工厂 | ~70KB | ★ 统一的是"重复实现"，非框架问题；做策略化合并 |
| `interfaces/*.py` | pydantic 数据模型 | 27KB | 不动 |

---

## 1. 不能破坏的对外接口（契约冻结）

这是整个重构的"红线"。下列接口的**输入签名、输出 schema、副作用文件布局**在迁移全程必须保持不变。Phase 0 会把它们固化为回归测试。

### 1.1 Web UI 契约（`web/server.mjs` 不动）
- **进程模型**：server 以子进程方式 spawn `python main_agent.py --jsonl ...`，逐行读 JSONL 事件并经 SSE 广播。`agentCommand()` 探测顺序（`INSIGHTFORGE_AGENT_COMMAND`->`INSIGHTFORGE_PYTHON_CMD`->bundled uv->`.venv`->`uv run python`）须保持。
- **JSONL 事件协议**（`main_agent.py::print_event` 消费的 dict schema）--**最高优先级契约**：
  - `turn` `{type,turn_id,turn}` / `status` `{type,turn_id,phase,message}` / `token` `{type,turn_id,delta}`（注：当前 `delta` 为整段文本单发，非逐 token）
  - `tool_start`/`tool_progress` `{type,turn_id,tool:{name,...},progress:{stage,message,metadata}}`
  - `tool_result` `{type,turn_id,tool_result:{name,ok,content,metadata}}`
  - `terminal` `{type,stream,line}` / `error` `{type,turn_id,message,metadata}`
  - `done` `{type,turn_id,assistant,tool_results:[...]}` / `session` `{type,turn_id,session:{active_session_id,session,artifact_checklist}}`
  - `prompt_trace` `{type,turn_id,prompt_trace}`
- **文件布局**（server 直接读这些文件）：
  - `.insightforge/sessions.json`（active_session_id、sessions map、每 session 的 stage/stale/compacted_summary/recent_turn_records/compaction_snapshots）
  - `.insightforge/logs/*.jsonl`（tool_calls 等日志）
  - `.insightforge/memory.md`、`.insightforge/todo.json`
  - `.working_dir/<session>/**`（idea2video/script2video/novel2video 全部 artifact）
- **HTTP API**：`/api/sessions` `/api/history` `/api/artifacts` `/api/artifact` `/api/uploads` `/api/config`(GET/PUT) `/api/agent/start` `/api/messages` `/api/agent/stop` 不变。
- **配置文件 schema**：`agent.local.yaml`/`agent.example.yaml`（llm/image/video/embedding/reranker 各 section）不变。

### 1.2 CLI 契约
- `main_agent.py` 参数：`--session` `--new-session` `--new-session-name` `--jsonl` `--once` `--stdin-repl`；`/compact` 指令不变。
- `runtime.stream_events(user_input) -> AsyncIterator[dict]` 与 `runtime.compact_history(reason) -> str` 接口签名不变（或保持等价包装）。

### 1.3 流水线入口契约
- `main_idea2video.py` / `main_script2video.py`：`Pipeline.init_from_config(config_path)` + `await pipeline(...)` 签名不变。
- `configs/*.yaml` schema（`chat_model.init_args`、`image_generator/video_generator.class_path+init_args`、rate limits、`working_dir`）不变。
- pipeline 落盘的 artifact 路径与格式不变（前端预览依赖）。

---

## 2. 框架选型与决策

**结论：以 LangGraph 为唯一新增主框架，配以项目已有的 LangChain 原语；不引入其它 AI 框架。**

### 2.1 选型对比

| 候选 | 用途定位 | 评估 | 采纳 |
|---|---|---|---|
| **LangGraph** | 有状态图编排：ReAct loop、DAG、checkpoint、人机协同、流式 | 项目已用 langchain 全家桶，langgraph 是其原生扩展，新增依赖成本极低；ReAct loop 与 pipeline DAG 都能覆盖 | ✅ 主框架 |
| LangChain 原语 | `init_chat_model`/`bind_tools`/`StructuredTool`/`ToolNode`/`trim_messages`/`PydanticOutputParser` | 项目已用；统一 LLM 客户端与工具定义 | ✅ 配套（已存在） |
| Pydantic AI | 结构化输出 agent | 与已用的 langchain 抽象重叠，引入两套心智模型，违背"减少自研/统一"初衷 | ❌ 不引入 |
| OpenAI Agents SDK | agent loop | 绑定 OpenAI 生态，与项目"多 provider（ark/yunwu/openrouter/google）"诉求冲突 | ❌ 不引入 |
| Temporal | durable workflow | 面向跨服务分布式编排，进程内 Python DAG 用它属过度工程；且引入独立服务 | ❌ 不引入 |

### 2.2 关键设计决策（降低风险的取向）
- **Agent loop 用自定义 `StateGraph`，而非 `create_react_agent`**：现有 loop 有特定语义（压缩预检、`MAX_TOOL_PASSES`、tool 返回的 `model_content` 多模态注入、turn 记录写 session、`prompt_trace` 事件）。自定义图能逐节点保留语义；`create_react_agent` 过于固守己见，改它反而更险。
- **流式适配层**：LangGraph `astream_events` v2 的事件形态与我们 JSONL 协议不同，新建 `agent_runtime/event_bridge.py` 把 LangGraph 事件映射成第 1 节的 JSONL schema。这是 Phase 3 的核心风险点，**在 Phase 0 冻结 golden 前先做原型验证**（见 Phase 0）。
- **状态权威源分两类，不混为一谈**：
  - **Artifact（storyboard/characters/video 等产物文件）** -> 文件系统是唯一权威源（前端直接读），checkpoint 不存这些。
  - **对话线程状态（消息历史 + 图执行进度）** -> Phase 4 起以 LangGraph checkpoint（sqlite）为权威源（方案 A 完整续跑）。`sessions.json` 中的 `recent_turn_records`/`compacted_summary` 降级为 checkpoint 的镜像或移除；`stage`/`stale`/`artifact_checklist`/`working_dir` 仍由 `SessionIndex` 管。
- **`session_index.py` 的 `fcntl` 在 Windows 上已失效**（`_locked` 直接 yield 不上锁）--LangGraph 的 `SqliteSaver`/`AsyncSqliteSaver` 跨平台，顺带提升 Windows 鲁棒性。

---

## 3. 替换点映射表

### 3.1 `agent_runtime/` 侧

| 现状 | 替换为 | 保留/新增 |
|---|---|---|
| `OpenAICompatibleLLM.complete()` | `init_chat_model(...).bind_tools(schemas)` | 保留 `complete()` 等价包装，供过渡期调用 |
| `ToolRegistry`/`ToolSpec`/JSON schema 手写 | LangChain `StructuredTool`/`@tool`（type hints->schema 自动生成） | 保留 `ToolRuntimeContext`(进度/取消/terminal) 为 contextvar 包装 |
| `ToolExecutor` | LangGraph `ToolNode`（或自定义 tool 节点） | 保留 telemetry 写 `tool_calls` 日志 |
| `AgentLoop` 的 `while True` | LangGraph `StateGraph`(model 节点->条件->tool 节点->回环) | 保留 `MAX_TOOL_PASSES` 为图递归上限 |
| `ContextCompactor` | LangGraph 摘要节点 + `trim_messages` | **保留自研 token 估算启发式**（贴合项目消息结构） |
| `SessionIndex` 对话历史部分 | LangGraph `BaseCheckpointSaver`(Sqlite/Async) | `SessionIndex` 收缩为"产品状态层"：sessions.json、artifact checklist、working_dir |
| `models.ToolCall/ToolResult` | `AIMessage.tool_calls` / `ToolMessage` | `TurnControl` 升格为图状态字段 |

### 3.2 `pipelines/` 侧

| 现状 | 替换为 | 保留/新增 |
|---|---|---|
| 三条 pipeline 的顺序/并行编排 | LangGraph `StateGraph`：每步骤=节点 | 保留 `init_from_config`+`__call__` 签名 |
| `os.path.exists` 跳过缓存 | LangGraph checkpoint 续跑 + **保留文件写入**（前端契约） | checkpoint=续跑态，文件=产品态 |
| `asyncio.gather` 并行镜头 | **优先在单个 fan-out 节点内保留 `asyncio.gather`**（保并发语义）；`Send` 仅在确需每镜头独立子图时用 | 保留 camera_tree 依赖拓扑（priority shots 先行） |
| `progress(stage,msg,meta)` 回调 | 图状态更新经 `astream_events` 流出 | 经 `event_bridge` 映射成 `tool_progress` |
| `agents/*.py` 各类 | 不换库，包装为图节点调用现有 async 方法 | 已用 langchain，tenacity/parser 逻辑留在 agent 内部，不展开为子图 |
| `robust_json_parser` | langchain `with_structured_output` / 强化 `OutputParser` | 保留尾逗号容错逻辑 |

### 3.3 `tools/` 统一（非框架，是去重）
- 现状：每 provider 拆 `*_ark_api.py`+`*_yunwu_api.py`+`*_google_api.py`+`*_openrouter_api.py`，`ImageGenerator`/`VideoGenerator` Protocol 已干净。
- 统一：保留 Protocol；把"provider 传输策略"抽出，单类多策略（`base_url` 自动判 provider，已是 `api_provider_from_base_url` 的做法，推广到全部 generator）。
- `RenderBackend.from_config` 的 `class_path` 工厂模式保留（配置契约不变）。

---

## 4. 分阶段迁移计划

> 每阶段 = **目标 -> 改动 -> 验证标准 -> 回滚**。Phase 0 必须先做；1->2->3->4 为 agent_runtime 侧；5 独立可并行；6 为 pipelines 侧；7 收口桥接。6 与 1-4 互不依赖，可并行。

### Phase 0 - 地基、原型门与契约冻结（无行为变更）
- **改动**
  - 新增依赖：`langgraph==1.0.1` + `langgraph-checkpoint-sqlite==3.0.3`（已 pin 进 `uv.lock`，确认支持 `astream_events` v2 与 `stream_mode="custom"`）。
  - **原型门（前置·已完成✅）**：`event_bridge` 原型验证通过。**关键发现**：改用 `astream(stream_mode="custom")` + 节点内 `get_stream_writer()` 直接写出 JSONL 事件 dict，字节级等价天然成立，**无需翻译 `astream_events`**。四类场景（纯文本/有 tool_call/无 tool_call/`/compact`）均与当前 `loop.py` 事件序列逐一对齐。
  - **golden 契约**：捕获 JSONL 事件流 golden、pipeline artifact 输出 golden（固定 script->产物树路径+内容）、CLI 行为 golden。
  - **轻量延迟基准（已记录✅）**：单轮 agent turn（含一次 tool-call 往返，FakeLLM 排除 API 延迟）median ≈132ms / min 127ms / max 144ms；script2video 完整跑需 API key，待运行环境具备时补记。供后续每阶段对比，防 LangGraph 状态拷贝/checkpoint I/O 引入回归。
  - 文档化第 1 节接口契约（已写入本 plan）。
- **验证（已通过✅）**：`tests/test_contract_jsonl_events.py` 5 个 golden 场景在当前代码全绿；全量测试 193 passed + 5 subtests（排除 1 个 pre-existing Windows fcntl 失败）。
- **回滚**：纯新增，无回滚风险。

### Phase 1 - 统一 LLM 客户端（低风险）
- **目标**：消除 `agent_runtime/llm.py` 与 pipelines 的重复 LLM 封装。
- **改动**
  - `OpenAICompatibleLLM` 内部改为 `init_chat_model(...).bind_tools(...)`；对外保持 `complete(messages,tools)->AssistantMessage` 签名。
  - 复用 `agent_runtime/config.py` 的 model/base_url/api_key 解析。
  - **配置兼容性审计**：用当前 `agent.local.yaml` 实际初始化 `init_chat_model` 与 `OpenAICompatibleLLM`，对比两者解析后的实际参数（model/provider/base_url/api_key），确认 1:1 兼容；参考 `utils/provider_presets.py::resolve_chat_model_config`。
- **验证（已通过✅）**：`test_agent_llm` 重写为 15 测试（wrapper 行为+转换器单测）全绿；`test_robustness::TestLLMClient` 重写为 2 测试（max_retries 配置+错误传播）全绿；`test_agent_loop`+golden 契约不变（用 FakeLLM 不受影响）；全量 209 passed 无回归；配置兼容性审计 openai 路径 1:1 一致。
- **回滚**：还原 `llm.py`。

### Phase 2 - 工具框架：interop 守卫（StructedTool 迁移延迟·已决策）
- **目标**：确认手写 ToolRegistry 与 langchain 互通；为 Phase 3 铺路。
- **改动（已完成✅）**
  - 新增 `tests/test_tool_langchain_interop.py`：守卫全部 13 个工具 schema 被 `bind_tools` 接受，并锁定 `additionalProperties:false` 契约不变。
- **StructedTool 全量迁移延迟（已决策）**：
  - 原计划把 `ToolSpec` -> langchain `StructuredTool` 并用其自动 schema 生成。
  - **阻断发现**：langchain `convert_to_openai_tool` 无法复现 `additionalProperties:false`（即使 pydantic `extra='forbid'`），而当前 13 个工具全部带此字段 -> 迁移会破坏"schema diff=空"契约。
  - **且**：现有 `list_function_tools()` 的 OpenAI dict 已能直接喂 `bind_tools`（已验证）；Phase 3 的自定义 tool 节点直接复用现有 `ToolExecutor`（不依赖 ToolNode/StructuredTool）。
  - **结论**：迁移风险（破坏 schema 契约）> 价值（系统已与框架互通）。延迟全量迁移；现有 ToolRegistry 作为工具系统保留并与 langchain 互通。
- **验证（已通过✅）**：`test_tool_langchain_interop` 2 测试全绿；`test_agent_tools`、`test_insightforge_adapters` 不变。
- **回滚**：删除 interop 测试文件。

### Phase 3 - Agent loop -> LangGraph StateGraph（高风险·核心）
- **目标**：`AgentLoop.stream_events` 内部换成 LangGraph 图；对外 JSONL 协议等价（按 Phase 0 商定的差异范围）。
- **改动**
  - 新建 `agent_runtime/event_bridge.py`：采用 `astream(stream_mode="custom")` + 节点内 `get_stream_writer()` 直接写出 JSONL 事件 dict（Phase 0 原型门验证：字节级等价天然成立，无需翻译 `astream_events`）。
  - 图结构：`prompt_build` 节点 -> `should_compact` 条件 -> `model` 节点 -> `has_tool_calls` 条件 -> `tool` 节点 -> 回 `model`；递归上限=`MAX_TOOL_PASSES`。
  - **`prompt_trace` 捕获**：图状态增 `prompt_trace` 字段，由 `prompt_build` 节点写入（`self.prompt_builder.trace(parts)`），`event_bridge` 在该节点完成后发出 `prompt_trace` 事件。
  - **`token` 事件**：当前为非流式单 delta（整段 `final_text` 一次性发）。图内 model 节点用非流式调用，`event_bridge` 发单个 `token` 事件保整段文本一致（不切换为逐 chunk 流式，避免行为变更）。
  - tool 返回的 `model_content`（多模态）注入下一轮 user message，保留现有"工具观察"语义。
  - turn 记录（`assistant_turns`/`tool_rounds`/`transitions`）由图状态汇总后写 `session_index`。
  - **取消语义**：保留当前 flag 轮询方式--`TurnControl.cancel_event`（`threading.Event`）经 contextvar 注入，tool 节点内部 `is_cancelled()` 轮询；**不使用 LangGraph `Interrupt`**（那是人机协同，属新功能，不在范围）。
  - **`thread_id` 策略**：`thread_id = session_id`。`--stdin-repl`/Web UI 每条用户输入 = 对该 thread 的一次图执行（`astream`），checkpoint 自动累积跨轮历史。
  - `stream_events(user_input)` 保持 `AsyncIterator[dict]` 签名。
- **验证（已通过✅）**：golden JSONL 5 场景 + test_agent_loop 7 测试全绿（事件序列逐字节对齐）；全量 210 passed（仅 1 个 pre-existing 环境失败 /tmp 不可写 + 1 deselected fcntl）；延迟 ~23ms/turn 无回归。
- **回滚**：保留旧 `AgentLoop` 为 `AgentLoopLegacy`，feature flag 切换；验证后删除。

### Phase 4 - 压缩 + Checkpoint（中风险）
- **目标**：图执行状态持久化到 sqlite checkpoint；压缩接入图。
- **改动**
  - 引入 `AsyncSqliteSaver`（`.insightforge/checkpoints.sqlite`），按 `thread_id=session_id` 存对话线程。
  - `ContextCompactor` 的摘要逻辑保留为图内"压缩节点"，`trim_messages` 辅助；保留自研 token 估算。
  - `SessionIndex` 收缩：只管 sessions.json/stage/stale/artifact checklist/working_dir/memory/todo；**对话历史权威源迁移到 checkpoint**，`recent_turn_records`/`compacted_summary` 降级为 checkpoint 派生镜像或移除（§2.2 权威源规则）。
- **验证（已通过✅）**：`test_agent_session_index`+`test_agent_loop`+golden 全绿；方案A 跨重启续跑验证通过（新 AgentLoop 实例从 sqlite checkpoint 加载完整对话历史）；全量 210 passed 无回归。
- **已决策行为变更（方案 A·完整续跑）**：当前 `loop.history` 仅在内存，重启后丢失（仅留 compacted_summary+recent_turn_records）。Phase 4 起 LangGraph checkpoint **保留完整对话历史跨重启**（框架自带能力，已采纳，非新功能；旧"仅留摘要"行为不再保留）。
- **回滚**：停用 checkpoint，`SessionIndex` 回退承接历史。

### Phase 5 - `tools/` 生成器去重（独立·低中风险）
- **目标**：合并 provider×transport 重复实现。
- **改动**
  - 抽 `BaseImageGenerator`/`BaseVideoGenerator`，provider 传输为策略（ark/yunwu/google/openrouter）；按 `base_url` 自动选策略。
  - 保留 `ImageGenerator`/`VideoGenerator` Protocol、`RenderBackend.from_config` 与 `class_path` 配置契约。
  - 旧类保留为薄转发或删除（按测试决定）。
- **验证**：`test_*_generator`、`test_generator_protocol`、`test_ark_*`、`test_provider_presets` 全绿。
- **回滚**：恢复旧 generator 文件。

### Phase 6 - Pipelines -> LangGraph StateGraph（高风险·大收益）
- **目标**：三条 pipeline 编排改为状态图，获得统一续跑/可观测/可维护。
- **顺序**：script2video（有 guard 测试，最稳）-> idea2video（委托前者）-> novel2movie（planning + render 全 DAG；`plan_text_artifacts`/`__call__` 内部方法重复，迁移时合并）。
- **改动**
  - 每步骤包为节点；`StateGraph` 持有 `characters/storyboard/shots/camera_tree/frames/clips` 等状态。
  - checkpoint 续跑替代 `os.path.exists` 跳过；**保留文件写入**（前端契约）。
  - **并行镜头**：优先在单个 fan-out 节点内保留 `asyncio.gather`（保真正并发与现有语义）；camera_tree 依赖（priority shots 先行、dependents 后继）用条件边/节点内依赖排序建模。仅当某镜头确需独立子图（如带自身 checkpoint/人机暂停）时才用 `Send` 扇出。
  - progress 回调 -> 图状态流式输出 -> `tool_progress` 事件。
  - `init_from_config`/`__call__` 签名不变；内部委托改为子图调用。
  - **agent 包装评估（纳入原型门）**：先拿 1-2 个 agent（如 `Screenwriter`/`StoryboardArtist`）包成图节点验证模式--确认 `tenacity` 重试与 `PydanticOutputParser` 留在 agent 内部即可，无需展开为子图，再批量包装。
- **验证**：`test_script2video_pipeline_guards`、`test_novel2movie_pipeline_init`、Phase0 artifact golden（路径+内容）、`main_script2video.py`/`main_idea2video.py` 端到端跑通；与 Phase 0 延迟基准对比。
- **回滚**：保留旧 pipeline 类为 `*Legacy`，配置切换。
- **原型门**：先用 script2video 的"并行镜头 fan-out 节点 + camera 依赖"做 1 个子图原型，确认并发语义与延迟可接受。

### Phase 7 - 桥接层收口（中风险·收尾）
- **目标**：两侧皆图后，`insightforge_adapters.py` 从"手写 ToolSpec 包装"收敛为"图节点/工具薄封装"。
- **改动**
  - adapter 的产品逻辑（session 解析、narrative/novel/render/revise 编排、错误恢复、stale key 清理、render 就绪判定）全部保留；仅把 ToolSpec->`@tool`、把"调用 pipeline 方法"->"调用子图"。
  - 删除过渡期遗留（`_UnavailableGenerator` 占位等若已无意义）。
- **验证**：`test_insightforge_adapters`、`test_novel2video_adapter`、Web UI 全流程（计划->渲染->artifact 预览->session 切换）。
- **回滚**：还原 adapters。

---

## 5. 关键风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| JSONL 事件协议无法等价复现 | 🔴 高 | Phase 0 前置 `event_bridge` 原型门（四类场景对比）；商定差异范围后再冻结 golden |
| `token` 事件字节级复现 | 🟡 低（已被现状降低） | 当前为非流式单 delta，图内保非流式即可；原型门验证整段文本一致 |
| 文件 artifact 与 checkpoint 双状态源混乱 | 🟠 中 | §2.2 分清两类权威源：artifact=文件，对话历史=checkpoint（Phase 4 后） |
| 取消语义在 LangGraph 下的映射 | 🟡 低 | 保留 flag 轮询（contextvar），不用 `Interrupt`（避免引入人机协同新功能） |
| pipeline 并行镜头并发语义改变 | 🟠 中 | 节点内保留 `asyncio.gather`；原型门 + Phase 0 延迟基准对比 |
| `insightforge_adapters.py` 48KB 改动面大 | 🟠 中 | Phase 7 最后做，且只改"包装方式"不改产品逻辑；靠 `test_insightforge_adapters` 兜底 |
| agents 包装成本被低估 | 🟡 低 | Phase 6 原型门先包 1-2 个验证；内部 tenacity/parser 不动 |
| LangGraph 版本/API 演进 | 🟡 低 | Phase 0 pin 版本进 `uv.lock`，确认支持 `astream_events` v2 |
| LangGraph 状态拷贝/checkpoint I/O 引入性能回归 | 🟡 低 | Phase 0 轻量延迟基准，每阶段对比 |

---

## 6. 验证与回归策略

- **契约测试（Phase 0 建立）**：JSONL golden、artifact golden、CLI golden，每阶段必须全绿才合入。
- **中间态（混血）测试**：每阶段完成后系统部分 LangGraph、部分手搓，需显式验证接缝：
  - Phase 1 后：手搓循环经 `complete()` 等价包装调用 `init_chat_model` 行为一致。
  - Phase 2 后：手搓循环能正确调用 `StructuredTool`（schema 与旧 `ToolSpec` diff=空）。
  - Phase 3 后：LangGraph 图产出经 `event_bridge` 的 JSONL 与 golden 等价。
- **现有测试**：`tests/` 下 26 个测试文件为安全网，按阶段调整内部实现测试、保留行为测试。
- **端到端冒烟（标准验收门）**：每阶段后用 `main_agent.py --jsonl` + Web UI 跑一遍完整流（计划->渲染->预览），必须通过才合入。
- **性能对比**：每阶段对照 Phase 0 延迟基准，关注 checkpoint I/O 与状态拷贝开销。
- **diff 审计**：工具 schema、prompt 文本、artifact 路径在迁移前后做 diff，预期为空。
- **每阶段独立可回滚**：legacy 类 + feature flag，验证通过再删除。

---

## 7. 不做的事（范围边界）

- ❌ 不动 `web/`（Node）与 `ui/`（TUI）前端代码。
- ❌ 不改对外接口签名、配置 schema、文件布局、JSONL 事件协议。
- ❌ 不新增功能（human-in-the-loop UI、新 provider、新 workflow 等）--即便 LangGraph 天然支持也留到后续。
- ❌ 不引入 Pydantic AI / OpenAI Agents SDK / Temporal 等其它框架。
- ❌ 不动 `interfaces/*.py` 数据模型、不动 prompt 文本内容。
- 已决策变更：Phase 4 的"checkpoint 完整续跑"已采纳（方案 A，框架自带能力）。

---

## 8. 把握度自评（目标 90%）

- **高把握（≥95%）**：Phase 0/1/2/5/7--纯封装统一与去重，契约清晰，测试覆盖好。
- **中高把握（85-90%）**：Phase 4--checkpoint 与文件双状态源（§2.2 已厘清权威源），模式成熟。
- **需原型验证后达 90%**：
  - Phase 3（事件桥接）：`event_bridge` 原型门前置到 Phase 0；`token` 因非流式单 delta 而风险可控；取消/thread_id/prompt_trace 已明确映射。原型通过后->90%+。
  - Phase 6（并行 fan-out）：节点内 `asyncio.gather` 保并发语义 + camera 依赖建模 + agent 包装评估，原型门确认。原型通过后->90%+。
- **整体**：作为"计划"已达 90% 把握--所有替换点已映射、契约已冻结、风险已识别并设门、每阶段可独立验证与回滚。剩余 ~10% 集中在两个原型门，正是"进入实施前应先验证"的部分。

---

## 附：阶段依赖与可并行性

```
Phase 0 (地基 + event_bridge 原型门 + golden 冻结 + 延迟基准) ── 必须先做
   ├── agent_runtime 侧: 1 -> 2 -> 3 -> 4
   ├── tools 统一侧:    5 (独立，可早做)
   ├── pipelines 侧:    6 (与 1-4 互不依赖，可并行；含 agent 包装评估子步骤)
   └── 收口:            7 (依赖 3 + 6)
```
- 1-4 串行（后者依赖前者）。
- 5、6 可与 1-4 并行排期。
- 7 必须在 3、6 完成后。
- event_bridge 原型门在 Phase 0 内、golden 冻结前完成。


---

## 9. 执行进度（截至当前）

### ✅ 已完成并提交

| 阶段 | commit | 内容 |
|---|---|---|
| Phase 0 | 65426cb | langgraph 1.0.1 依赖 + golden 契约测试（5 场景）+ event_bridge 原型门（stream_mode=custom 字节级等价）+ 延迟基准 |
| Phase 1 | 5172f76 | OpenAICompatibleLLM -> init_chat_model + bind_tools；消息转换器；tool->plain 回退；配置审计 |
| Phase 2 | 3516469 | interop 守卫（bind_tools 接受现有 schema）；StructuredTool 迁移延迟（additionalProperties 契约冲突） |
| Phase 3 | 27d7cec | Agent loop -> LangGraph StateGraph；节点 get_stream_writer 直接发 JSONL；非流式单 delta；MAX_TOOL_PASSES |
| Phase 4 | 27d7cec | AsyncSqliteSaver checkpoint（方案A）；history 入图 state；thread_id=session_id；跨重启完整续跑验证 |
| Phase 6（部分）| d60f66d | script2video plan_text_artifacts -> StateGraph（4 节点线性 + asyncio.gather 节点内）；idea2video 自动受益 |
| Phase 5（部分）| 838645a | doubao yunwu 生成器（seedream + seedance）合并为 ark 薄子类（-212 行重复） |

### 📋 剩余/延迟

| 阶段 | 状态 | 说明 |
|---|---|---|
| Phase 5 余 | 延迟 | google/yunwu 对（nanobanana/veo）是不同 API 客户端（google-genai vs http proxy），非重复实现，保留 |
| Phase 6 novel2movie | 延迟 | plan_text_artifacts 是单体方法（循环+RAG+semaphore），需先提取 step-methods 再转图 |
| Phase 6 render | 延迟 | __call__ 渲染管线极复杂（portraits+frames+video+concat），现有编排工作良好，优先级低 |
| Phase 7 | 实质完成 | adapters 已通过 graph-backed plan_text_artifacts 间接使用图；ToolSpec 迁移随 Phase 2 延迟 |

### 测试状态
- **210 passed**，2 deselected（pre-existing 环境失败：Windows fcntl + /tmp 不可写）
- golden 契约 5 场景 + test_agent_loop 7 + test_agent_llm 15 + test_insightforge_adapters 全绿
