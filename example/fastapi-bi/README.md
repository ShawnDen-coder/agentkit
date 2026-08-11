# fastapi-bi 示例

C&S(客户端/服务器)部署:浏览器前端通过 SSE wire 协议跟 FastAPI 后端通信。
这是 BI 仪表盘 / OpenBB Workspace 那种模型。

## 运行

```bash
# .env 里写:OPENROUTER_API_KEY=sk-or-v1-...  (可选:OPENROUTER_MODEL=anthropic/claude-sonnet-4)
uv run --env-file .env --with fastapi --with uvicorn --with langchain-openai python example/fastapi-bi/backend.py
```

打开 <http://127.0.0.1:8000>,输入"显示各地区销售额",发送。

## 展示了什么

- **窄腰 ②(SSE)**:`backend.py` 驱动 `orchestrator.run()`,把每个 `BaseSSE` 事件用
  `to_sse()` 序列化成 `event:` / `data:` 帧(`StreamingResponse`,`text/event-stream`)。
  浏览器从 `fetch` POST 响应里手动解析流(`EventSource` 只支持 GET)。
- **窄腰 ①(ComponentAdapter)**:[`bi_adapter.py`](./bi_adapter.py) 是一个 mock BI 后端
  (widget 目录 + 罐头表格数据)。这是厂商 adapter 唯一要实现的契约。
- **Auth 缝隙**:`backend.py` 在 SSE 路径**之前**跑 `Authenticator` -> `Principal` ->
  `session_from_principal` -> `SessionContext`。`auth_token` 走 `Authorization` header
  (绝不走 body)。`AllowAllAuthorizer` 顶替真实的按动词 RLS。
- **Option B 前端往返**:收到 `copilotFunctionCall` 时,浏览器执行 UI 动作(往仪表盘加一个
  widget),然后带 `role=tool` 重新 POST 以恢复流。

## 文件

- `backend.py` - FastAPI 应用:`/v1/query` SSE 端点、auth、装配 orchestrator。
- `bi_adapter.py` - mock BI `ComponentAdapter`。
- `static/index.html` - 最小聊天 UI:SSE 流 + FunctionCall 往返。

## `agentkit-runtime` 已落地

本示例已接入 `LanggraphOrchestrator`(M2,langgraph StateGraph)。`FakeOrchestrator`
保留在 `example/_common/` 作为无 LLM 的教学回退——换回它只需改一行 import。

## 关于 LLM

本示例用 `LanggraphOrchestrator` + 真 LLM。设 `OPENROUTER_API_KEY` env(OpenRouter key);
默认 model `anthropic/claude-sonnet-4`,可通过 `OPENROUTER_MODEL` env 覆盖。
注意区分两个 token:`SessionContext.auth_token`(用户的委托取数凭据,走 Authorization
header)≠ `OPENROUTER_API_KEY`(后端 env,LLM provider)。
