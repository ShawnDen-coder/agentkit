# agentkit-runtime

`Orchestrator` Protocol 实现:基于 langchain v1 `create_agent` + langgraph `interrupt()` 的
Option B orchestrator(0.3.0 插件重定位)。

`LanggraphOrchestrator` 实现 `agentkit_protocol.protocols.Orchestrator` Protocol:
持有一个 langchain `BaseChatModel` + 一个 `ComponentAdapter`,用 `create_agent` 跑
agent↔tools 循环(`recursion_limit` 预算,等价于 `MAX_HOPS`)。前端动词 tool-call 时调
langgraph `interrupt(args)` 暂停图,`run()` 经 `astream_events(v2)` 的 `on_tool_error`
捕获 `GraphInterrupt`,yield `CopilotFunctionCall` 并结束流(Option B 状态机)。

## 0.3.0 插件重定位

AgentKit 是 langchain/langgraph 的插件,不是并行框架(架构附录 E):

- **后端 langchain-native**:用户写 `@tool`、配 `create_agent`、传 `BaseChatModel`、配
  checkpointer。runtime 提供 `build_adapter_tools()` + `build_frontend_tools()` helper。
- **前端 wire-native**:6 SSE 事件 + `FunctionCall` 回环,不碰 langchain。
- **有状态(默认)**:`create_agent` + checkpointer + `thread_id`。前端 verb 用 `interrupt()`;
  `run()` 捕获 `GraphInterrupt` → `CopilotFunctionCall`,前端用 `thread_id` + `resume` 恢复。
- **无状态**:不传 checkpointer 时用 `InMemorySaver()`(per-request 丢弃,状态只在请求内)。

不再有 `FrontendActionRequested` 异常、`verb_tools` 合成、`_maybe_artifact` 嗅探 —— 这些在
0.3.0 重定位中被删除,让 langchain 原生形态自然落地。

## 模块构成

| 模块 | 职责 |
|---|---|
| `orchestrator` | `LanggraphOrchestrator`(`Orchestrator` Protocol 实现)。`run()` 是 async generator,驱动 `create_agent` 图的 `astream_events(v2)`,映射到 6 个 SSE 事件;捕获 `GraphInterrupt`(经 `on_tool_error`)→ `CopilotFunctionCall`,`GraphRecursionError` → 优雅收尾。`ToolErrorMiddleware` 把 `NotImplementedError` 转成 error `ToolMessage` 让 LLM 恢复。支持 `extra_tools`(skill/MCP 注入)、`authorizer`(per-verb RLS)、`checkpointer`(有状态)。 |
| `adapter_tools` | `build_adapter_tools(adapter, *, to_artifact=None, authorizer=None)` 把 5 个已实现后端 verb 转成 langchain `StructuredTool`(pydantic `args_schema`,不用 `create_model` 合成)。每个 tool 发 `status` 旁路事件、调 adapter 方法、可选经 profile 注入的 `to_artifact` hook 发 `artifact` 事件。stub verb(`get_skill_content`/`execute_tool`)不暴露(M4/M6 落地前)。 |
| `frontend_tools` | `build_frontend_tools()` 把 4 个前端 verb 转成 langchain `StructuredTool`,每个 tool 调 `interrupt(args)` 暂停图(langgraph 原生 HITL)。 |
| `messages` | `to_langchain_messages(request.messages) -> list[BaseMessage]`。0.3.0 用 langchain `convert_to_messages`;0.2.0 风格孤儿 `role=tool`(无 `tool_call_id`)仍合成 `AIMessage(tool_calls=[...])` 向后兼容。 |

## 用法

```python
from agentkit_runtime import LanggraphOrchestrator

orchestrator = LanggraphOrchestrator(
    llm,                 # langchain BaseChatModel（调用方构造，provider 无关）
    adapter,             # agentkit_protocol.ComponentAdapter 实现
    *,
    checkpointer=None,   # 默认 InMemorySaver()（per-process）；生产用 PostgresSaver 等
    extra_tools=None,    # 额外 langchain tools（skill/MCP 注入，idiomatic 扩展点）
    authorizer=None,     # Authorizer（per-verb RLS；None 则跳过）
    to_artifact=None,    # profile hook: ComponentData dump -> Artifact | None
    max_hops=5,          # backend-sync 工具调用预算（-> recursion_limit = max_hops*2+2）
    system_prompt=None,  # 烤进 create_agent 图；str -> SystemMessage，每次 model call 前置
)
async for event in orchestrator.run(request):  # request: QueryRequest
    ...  # event: BaseSSE（6 种之一），event.to_sse() -> {"event","data"}
```

**有状态 interrupt/resume**(0.3.0 核心):

1. 前端发 `QueryRequest(messages=[...], thread_id="thread-1")`
2. 后端 `interrupt()` 暂停 → yield `CopilotFunctionCall(name, arguments, tool_call_id)` → 流结束
3. 前端执行 UI 动作 → 发 `QueryRequest(thread_id="thread-1", resume={result, tool_call_id})`
4. 后端 `Command(resume=...)` 恢复 → 流式返回最终答案 + suggestions

`thread_id` 由前端生成(如 `crypto.randomUUID()`);同一对话轮内 interrupt/resume 用**同一个**
`thread_id`,checkpointer 持有暂停状态。

## Provider 无关

本包运行时依赖 `langchain`(提供 `create_agent` + `ToolErrorMiddleware`)+ `langgraph` +
`langchain-core`。`BaseChatModel` 实例由调用方构造(如 `ChatOpenAI`、`ChatAnthropic`、
`ChatOllama`)—— provider 切换是 langchain 自己的事,本包不掺和(§6.4)。Provider factory(如
OpenRouter 配置)属于应用层,见 `example/_common/openrouter.py`。

## 流式

`astream_events(version="v2")` + `adispatch_custom_event`(config 显式,3.10 安全)。
`get_stream_writer` / `stream_mode="custom"` 是 3.11+ async 专属(contextvar),项目支持 3.10,
不能用。

## 状态

0.3.0 ✅。`Orchestrator` Protocol 的实现落地。罐装 `CopilotPromptSuggestions`(真 impl 需
follow-up LLM call,加延迟 + 成本,M3+)。`CopilotCitationCollection` 不发。
`get_skill_content`/`execute_tool` 不暴露给 LLM(M4/M6 才有真 impl)。adapter 硬接进构造器
(无 `agentkit.adapters` entry-point 注册 —— live discovery 是 M2 之后)。

冻结契约见 [`docs/contracts.md`](../../docs/contracts.md),完整设计见
[`agentkit-architecture.md`](../../agentkit-architecture.md)(附录 E 覆盖 0.3.0 插件重定位)。
