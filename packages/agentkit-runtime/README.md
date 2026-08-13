# agentkit-runtime

M2 实现:基于 langchain v1 `create_agent` 的 Option B orchestrator。

`LanggraphOrchestrator` 实现 `agentkit_protocol.protocols.Orchestrator` Protocol:
持有一个 langchain `BaseChatModel` + 一个 `ComponentAdapter`,用 `create_agent` 跑
agent↔tools 循环(`recursion_limit` 预算,等价于 `MAX_HOPS`),前端动词 tool-call 时
yield `CopilotFunctionCall` 并终止流(Option B 状态机)。

**无状态**:每次 `run()` 从 `request.messages` 重建 langchain 消息,不用 checkpointer。
状态全在 `messages` 里(§6.3)。前端 `FunctionCall` 往返用 `FrontendActionRequested`
异常跳出--它是 langgraph `interrupt()` 的无状态等价(`interrupt()` 需要 checkpointer,
会打破"状态全在 messages"的冻结契约)。

**Provider 无关**:本包运行时依赖 `langchain`(提供 `create_agent` + `ToolErrorMiddleware`)
+ `langgraph` + `langchain-core`。`BaseChatModel` 实例由调用方构造(如 `ChatOpenAI`、
`ChatAnthropic`、`ChatOllama`)--provider 切换是 langchain 自己的事,本包不掺和(§6.4)。
Provider factory(如 OpenRouter 配置)属于应用层,见 `example/_common/openrouter.py`。

**流式**:`astream_events(version="v2")` + `adispatch_custom_event`(config 显式,3.10 安全)。
`get_stream_writer` / `stream_mode="custom"` 是 3.11+ async 专属(contextvar),项目支持 3.10,
不能用。

## 模块构成

| 模块 | 职责 |
|---|---|
| `orchestrator` | `LanggraphOrchestrator`(Orchestrator Protocol 实现)。`run()` 是 async generator,驱动 `create_agent` 图的 `astream_events`,映射到 6 个 SSE 事件;捕获 `FrontendActionRequested` -> `CopilotFunctionCall`,`GraphRecursionError` -> 优雅收尾。`ToolErrorMiddleware` 把 `NotImplementedError` 转成 error `ToolMessage` 让 LLM 恢复,其余异常透传。 |
| `tools` | `verb_tools(adapter)` 把 11 个 `VerbSpec` 转成 langchain `StructuredTool`(args_schema 从冻结的 `VerbSpec.input_schema` 构建);前端动词 coroutine 抛 `FrontendActionRequested`,后端动词调 adapter 并经 `adispatch_custom_event` 发 status/artifact 旁路事件。 |
| `messages` | `to_langchain_messages(request.messages) -> list[BaseMessage]`。孤儿 `role=tool` Message 前自动合成 `AIMessage(tool_calls=[...])`(OpenAI 要求 tool message 跟在带 tool_calls 的 assistant 后)。 |

## 用法

```python
from agentkit_runtime import LanggraphOrchestrator

orchestrator = LanggraphOrchestrator(
    llm,                 # langchain BaseChatModel（调用方构造，provider 无关）
    adapter,             # agentkit_protocol.ComponentAdapter 实现
    *,
    max_hops=5,          # backend-sync 工具调用预算（-> recursion_limit = max_hops*2+2）
    system_prompt=None,  # 烤进 create_agent 图；str -> SystemMessage，每次 model call 前置
)
async for event in orchestrator.run(request):  # request: QueryRequest
    ...  # event: BaseSSE（6 种之一），event.to_sse() -> {"event","data"}
```

`system_prompt` 在构造时烤进图（与 `create_agent` 一致）;per-request 定制可往 `request.messages`
里加一条 `role=system` `Message`,它会被追加到烤入的 system prompt 之后。verb 工具已通过
`bind_tools` 描述给 LLM,`system_prompt` 只负责角色/行为指引。

## 为什么不用 `interrupt()` / checkpointer

langgraph 官方 HITL 机制 `interrupt()` 需要 server-side checkpointer 才能跨 `FunctionCall`
往返 resume,但"无状态 / 状态全在 messages"是冻结契约原则(contracts.md L57-58)。引入
checkpointer 会反转该原则、需要 prod 持久化(Redis/Postgres)、且 resume 路径上 `request.messages`
与 checkpoint 双源。`FrontendActionRequested` 是它的无状态一一对照物,零基础设施,两种部署模式
(FastAPI HTTP / PySide in-process)对称。`interrupt()` 留待将来 wire 契约往 session/resume
做 major bump 时再上。

## 状态

M2 ✅。`Orchestrator` Protocol 的实现落地。罐装 `CopilotPromptSuggestions`(真 impl 需 follow-up
LLM call,加延迟 + 成本,M3+)。`CopilotCitationCollection` M2 不发。`get_skill_content`/`execute_tool`
报 `NotImplementedError` 让 LLM 恢复(M4/M6 才有真 impl)。adapter 硬接进构造器(无
`agentkit.adapters` entry-point 注册--live discovery 是 M2 之后)。

冻结契约见 [`docs/contracts.md`](../../docs/contracts.md),完整设计见
[`agentkit-architecture.md`](../../agentkit-architecture.md)。
