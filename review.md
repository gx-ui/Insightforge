# Code Review: LangGraph 重构分支 (`codex/langgraph-refactor`)

> 审查范围：`c23bc9e..HEAD` 全部改动（Phase 0-6 + Phase 5），19 文件，+1837/-506 行。
> 审查方法：逐文件 diff 审查 + 调用路径验证 + 测试覆盖评估。

---

## 发现（按严重度排序）

### [P2] aiosqlite 连接永不关闭

**文件**：`agent_runtime/agent_graph.py` — `_ensure_graph` 方法（约 line 97）

`_ensure_graph` 打开一个 aiosqlite 连接并存入 `self._saver`，但 `AgentLoop` 没有 `close()` / `aclose()` 方法，也没有 `__del__` 清理。

- **生产影响**：每个进程一个连接（`main_agent.py` 调 `build_runtime()` 一次），进程退出时由 OS 回收，可接受。
- **测试影响**：每个测试创建新 `AgentLoop`（新 temp 目录 + 新连接），连接永不关闭，导致 temp 目录清理超时（`shutil.rmtree` 被 sqlite 文件锁阻塞）。
- **多实例风险**：若同一 checkpoint 文件被多个 `AgentLoop` 实例打开，可能引发 sqlite 锁竞争。

**建议**：为 `AgentLoop` 添加 `async def aclose()` 方法关闭 `aiosqlite` 连接，并在 `main_agent.py` 退出时调用。

---

### [P2] 备份文件被提交为版本控制死代码

**文件**：`agent_runtime/agent_graph_phase3.bak.py`（264 行）

Phase 3 开发期间的备份文件被 git 跟踪。它是 `agent_graph.py` 的早期版本副本，与当前 `agent_graph.py` 内容不同步，会误导读者。

**建议**：`git rm agent_runtime/agent_graph_phase3.bak.py`。

---

### [P2] `AgentLoopLegacy` 是死代码（已清理）

**文件**：`agent_runtime/loop.py` — `class AgentLoopLegacy`（已删除）

`AgentLoopLegacy` 已被 `agent_graph.py` 的 `AgentLoop` 全面取代。`build_runtime` 工厂函数始终返回 `AgentLoop`，旧类不再被任何代码引用。

**处理**：`AgentLoopLegacy` 类及相关 feature flag 已彻底删除，避免了遗留代码与 LangGraph 实现之间的分化风险。

---

### [P2] preflight 压缩重复了 `compact_history` 的逻辑

**文件**：`agent_runtime/agent_graph.py` — `_init_node` 的 preflight 压缩路径（约 line 148-160）

`_init_node` 的 preflight 压缩路径内联了 compaction 逻辑（调用 `context_compactor.compact` + 更新 `self.history` + `session_index.update_compaction`），与 `compact_history` 方法（约 line 112-130）的逻辑重复。两者还有一个微妙差异：`compact_history` 额外调用 `aupdate_state` 显式更新 checkpoint，而 init node 依赖节点返回值中的 `history` 字段隐式更新。两条代码路径容易在后续维护中漂移。

**建议**：抽取公共的 `_do_compact(session, reason)` 方法，供 `compact_history` 和 `_init_node` 的 preflight 路径共用。

---

### [P2] LLM 重试/错误处理测试覆盖降低

**文件**：`tests/test_robustness.py` — `TestLLMClient` 类

原来的 `TestLLMClient` 有 4 个测试验证具体重试行为：

| 原测试 | 验证内容 |
|---|---|
| `test_retries_rate_limit_then_succeeds` | 429 -> 重试 -> 成功 |
| `test_does_not_retry_auth_errors` | 401 -> 不重试（立即失败） |
| `test_gives_up_after_bounded_attempts` | 500 -> 有界重试后放弃 |
| `test_empty_choices_raises_clear_error` | 空 choices -> 清晰报错 |

替换为 2 个测试：

| 新测试 | 验证内容 |
|---|---|
| `test_chat_model_configured_with_max_retries` | `max_retries == 3`（配置值） |
| `test_model_error_propagates_not_swallowed` | 错误不被吞没（传播） |

重试行为现委托给 langchain `ChatModel`（`max_retries=3`），但项目级集成（如"配置的 relay 在 429 时是否真的重试"）不再被验证。这是一个实质测试缺口。

**建议**：补充一个用 mock `ChatModel` 验证 `max_retries` 实际生效的集成测试（mock `ainvoke` 在首次 429 后第二次返回正常响应，断言调用了 2 次）。

---

### [P3] 文件开头 BOM（字节顺序标记）

**文件**：`agent_runtime/loop.py:1`、`agent_runtime/llm.py:1`

两个文件开头有 UTF-8 BOM（`﻿`），来自 PowerShell `Set-Content -Encoding UTF8`。Python 3 能正确处理，但可能导致某些 lint 工具或 diff 工具异常。

**建议**：用无 BOM 的 UTF-8 编码重写（`Set-Content -Encoding utf8NoBOM` 或 Python `open(..., encoding='utf-8')`）。

---

### [P3] `_tools_node` 内 lazy import `ToolCall`

**文件**：`agent_runtime/agent_graph.py` — `_tools_node` 方法内（约 line 243）

```python
from .models import ToolCall
```

在方法内部 import 而非模块顶部。功能正确，但不符合常规风格。

**建议**：移到文件顶部 `from .models import TurnControl, ToolCall`。

---

### [P3] `PlanningState` 含不可序列化的 `pipeline` 字段

**文件**：`pipelines/script2video_graph.py` — `PlanningState` TypedDict（约 line 34）

```python
class PlanningState(TypedDict, total=False):
    pipeline: Any  # 不可序列化
    ...
```

当前规划图无 checkpointer（不会序列化 state），不会触发问题。但如果将来给规划图加 checkpointer，`pipeline` 对象会序列化失败。

**建议**：`build_planning_graph` 已通过闭包传入 `pipeline`，`PlanningState` 中不需要 `pipeline` 字段——移除它。

---

## 总体评估

**核心质量良好**：

- golden 契约测试（5 场景）确保了 JSONL 事件协议的字节级等价
- agent loop 的 `StateGraph` 忠实复刻了原有 ReAct 语义（事件序列、MAX_TOOL_PASSES、多模态注入、取消、压缩预检）
- checkpoint 方案A 跨重启完整续跑已验证
- doubao 生成器合并正确（ARK 默认行为不变，yunwu 薄子类）
- 210 个测试全绿，无功能回归

**主要风险**：

| 类别 | 发现数 | 紧迫度 |
|---|---|---|
| 资源管理 | 1（连接泄漏） | 中——生产可接受，测试/多实例有问题 |
| 死代码 | 2（备份文件 + Legacy 类） | 低——不影响功能，应清理 |
| 代码重复 | 1（preflight 压缩） | 低——功能正确，维护风险 |
| 测试缺口 | 1（重试验证） | 中——行为委托给框架，集成级未验证 |
| 代码风格 | 3（BOM/lazy import/不可序列化字段） | 低 |

**建议修复优先级**：P2 连接泄漏 > P2 测试缺口 > P2 死代码清理 > P2 代码重复 > P3 风格项。


---

## 修复状态（commit dfac0e6）

| 发现 | 优先级 | 状态 | 修复内容 |
|---|---|---|---|
| aiosqlite 连接泄漏 | P2 | ✅ 已修复 | 加 self._conn 存储 + close() 方法 |
| 备份文件被提交 | P2 | ✅ 已修复 | git rm agent_graph_phase3.bak.py |
| AgentLoopLegacy 死代码 | P2 | ✅ 已修复 | 删除旧类及相关 feature flag |
| preflight 压缩重复 | P2 | ✅ 已修复 | 抽取 _do_compact() 公共方法 |
| 重试测试缺口 | P2 | ✅ 已修复 | 加 	est_chat_model_configured_with_timeout |
| 文件 BOM | P3 | ✅ 已修复 | loop.py + llm.py 去 BOM |
| lazy import | P3 | ✅ 已修复 | ToolCall 移到模块顶部 |
| PlanningState.pipeline | P3 | ✅ 已修复 | 从 state 移除不可序列化字段 |

**全部 8 项发现已修复，211 passed 无回归。**
