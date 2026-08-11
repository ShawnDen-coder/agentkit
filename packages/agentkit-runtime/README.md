# agentkit-runtime

M2 实现:基于 langgraph `StateGraph` 的 Option B orchestrator。

`LanggraphOrchestrator` 实现 `agentkit_protocol.protocols.Orchestrator` Protocol:
持有一个 langchain `BaseChatModel` + 一个 `ComponentAdapter`,在单个 `run()` 调用内跑
多跳 backend-sync 工具调用(`MAX_HOPS` 预算),前端动词 tool-call 时 yield
`CopilotFunctionCall` 并终止流(Option B 状态机)。

**无状态**:每次 `run()` 从 `request.messages` 重建 langgraph 消息,不用 checkpointer。
状态全在 `messages` 里(§6.3)。

**Provider 无关**:本包只依赖 `langgraph` + `langchain-core`。`BaseChatModel` 实例由调用方
构造(如 `ChatOpenAI`、`ChatAnthropic`、`ChatOllama`)——provider 切换是 langchain 自己的事,
本包不掺和(§6.4)。Provider factory(如 OpenRouter 配置)属于应用层,见
`example/_common/openrouter.py`。

## 模块构成

| 模块 | 职责 |
|---|---|
| `orchestrator` | `LanggraphOrchestrator`(Orchestrator Protocol 实现)。`run()` 是 async generator,驱动 langgraph `astream_events`,映射到 6 个 SSE 事件。 |
| `graph` | `build_graph()` 构造 `StateGraph`:`agent` ↔ `tools` 两节点,`route_after_agent` 在 `hops < MAX_HOPS` 且有 `tool_calls` 时走 `tools`,否则 END。无 checkpointer。 |
| `tools` | `FrontendActionRequested` 异常;`_verb_tool_schemas()` 把 11 个 `VerbSpec` 转 OpenAI fn dict;`_build_tool_handlers()` 把动词名绑到 adapter 方法。 |
| `messages` | `to_langchain_messages(request.messages) -> list[BaseMessage]`。孤儿 `role=tool` Message 前自动合成 `AIMessage(tool_calls=[...])`(OpenAI 要求 tool message 跟在带 tool_calls 的 assistant 后)。 |
| `artifacts` | `to_artifact(verb_name, data) -> Artifact`。从 `ComponentData` peek `columns`/`rows` 选 Table/Text(example-grade;真实 profile-typed artifact 来自 profile,M3+)。 |

## 状态

M2 ✅。`Orchestrator` Protocol 的实现落地。罐装 `CopilotPromptSuggestions`(真 impl 需 follow-up
LLM call,加延迟 + 成本,M3+)。`CopilotCitationCollection` M2 不发。`get_skill_content`/`execute_tool`
报 `NotImplementedError` 让 LLM 恢复(M4/M6 才有真 impl)。adapter 硬接进构造器(无
`agentkit.adapters` entry-point 注册——live discovery 是 M2 之后)。

冻结契约见 [`docs/contracts.md`](../../docs/contracts.md),完整设计见
[`agentkit-architecture.md`](../../agentkit-architecture.md)。
