# agentkit 示例

两种部署模式,**同一套协议**。这些示例把"可迁移"这个承诺做实:同一份
`agentkit_protocol` 契约(`QueryRequest` / `Message` / `SessionContext` 进,
`BaseSSE` 事件出,`ComponentAdapter` 接后端)同时驱动一个浏览器+服务器的 BI 应用
和一个进程内的 DCC 桌面应用。

| 示例 | 模式 | 传输 | 前端往返 |
|---|---|---|---|
| [`fastapi-bi/`](./fastapi-bi/) | C&S(BI 仪表盘) | HTTP + SSE(`to_sse()`) | `thread_id` + `resume` 恢复 |
| [`pyside-dcc/`](./pyside-dcc/) | 本地(DCC 宿主) | 进程内(对象) | `thread_id` + `resume` 恢复 |

## 0.3.0:有状态 interrupt/resume

两个示例都用 `LanggraphOrchestrator`(基于 langchain v1 `create_agent` + langgraph
`interrupt()`)。前端 verb(如 `add_component_to_dashboard`)调用 `interrupt(args)` 暂停图,
后端 yield `CopilotFunctionCall` SSE 事件并结束流。前端执行 UI 动作后,用**同一个
`thread_id` + `resume`** 恢复(不重发 messages)—— langgraph 的 checkpointer 持有对话状态。

| 步骤 | 请求 | 响应 |
|---|---|---|
| 1. 用户提问 | `{messages, thread_id}` | `copilotStatusUpdate` + `copilotMessageArtifact`(后端同步取数) |
| 2. 前端 UI 动作 | — | `copilotFunctionCall`(流结束,`tool_call_id` 带 interrupt id) |
| 3. 前端执行 + 恢复 | `{thread_id, resume: {result, tool_call_id}}` | `copilotMessageChunk`(最终答案) + `copilotPromptSuggestions` |

## 前置

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."   # 两个示例都用 OpenRouter LLM
uvx --from rust-just just init              # 同步 workspace(装好 agentkit_protocol + agentkit_runtime)
```

示例专属依赖(fastapi/uvicorn、pyside6/qasync)在各自的运行命令里用
`uv run --with` **临时**提供 —— 不用单独安装,不污染 venv。见各示例 README。

## 运行

```bash
# FastAPI BI 示例(C&S / HTTP+SSE)
uv run --with fastapi --with uvicorn --with langchain-openai python example/fastapi-bi/backend.py
# 打开 http://127.0.0.1:8000

# PySide6 DCC 示例(本地 / 进程内)
uv run --with pyside6 --with qasync --with langchain-openai python example/pyside-dcc/app.py
```

## 你会看到什么

两个示例,在一条用户消息上,都跑完整的 Option B 回路:

1. **后端同步**(真实 adapter 调用)-> `copilotStatusUpdate` + `copilotMessageArtifact`
2. **前端 FunctionCall** -> `copilotFunctionCall`(流结束,`interrupt()` 暂停图)
3. 前端执行 UI 动作(加一个 widget / 场景节点)
4. **恢复** -> `copilotMessageChunk`(最终答案)+ `copilotPromptSuggestions`

区别只在传输:HTTP+SSE(BI)vs 进程内对象(DCC)。

## 不用 LLM 也能跑

`example/_common/fake_orchestrator.py` 是一个脚本化的 `Orchestrator` 实现(不用 langchain,
不用 API key),用真实 adapter 调用 + 脚本化 SSE 事件跑通 Option B 状态机。适合快速验证
wire 契约。把 `FakeOrchestrator` 换成 `LanggraphOrchestrator` 即可接入真 LLM —— adapter、
auth、前端、SSE 装配都不用改。

这个替换本身就是教学点:**wire 契约(`agentkit_protocol`)是稳定的缝;orchestrator
是可替换的实现。**
