# pyside-dcc 示例

本地部署:agent 跟 PySide6 桌面 UI 跑在**同一进程**。这是 DCC 宿主模型
(Maya / UE / PySide 工具面板)。没有 HTTP,没有 SSE 序列化--UI 直接消费 `BaseSSE` 事件对象。

## 运行

```bash
uv run --with pyside6 --with qasync python example/pyside-dcc/app.py
```

弹出一个窗口,带聊天面板和场景树。输入"场景里有什么",发送。

## 展示了什么

- **进程内事件消费**:`app.py` 迭代 `async for event in orchestrator.run(req)`,按 `BaseSSE`
  子类分发(`CopilotMessageChunk` / `CopilotMessageArtifact` / `CopilotFunctionCall` / …)。
  不调 `to_sse()`--对象直接消费。这是跟 `fastapi-bi/` 的关键区别:同样的事件,不走 wire 序列化。
- **窄腰 ①(ComponentAdapter)**:[`dcc_adapter.py`](./dcc_adapter.py) 是一个 mock DCC 宿主--
  以选择为中心(`get_selection` 返回当前选中的场景节点)。跟 BI adapter 是同一个
  `ComponentAdapter` 契约;领域差异只是信封 `kind`(`dcc.node` vs `bi.semantic`)。
- **用 qasync 做异步**:`qasync` 把 asyncio loop 接到 Qt 事件循环上,async 的
  `orchestrator.run()` 跟 Qt 控件一起跑。async 路径里的 UI 更新在 Qt 线程上。
- **Option B 进程内往返**:收到 `copilotFunctionCall` 时,UI 执行动作(往场景树加一个节点),
  然后带 `role=tool` 消息重新调 `run()`--没有 HTTP 断连,就是进程内恢复。

## 文件

- `app.py` - PySide6 `QMainWindow` + qasync;进程内 `BaseSSE` 消费。
- `dcc_adapter.py` - mock DCC `ComponentAdapter`(场景节点、选择)。

## `agentkit-runtime` 落地后

把 `app.py` 里的 `FakeOrchestrator` import 换成 `LanggraphOrchestrator`(M2,langgraph)。
对进程内 DCC 场景,langgraph checkpointer 用内存版 `MemorySaver` 即可(不用持久化)。
`app.py` / `dcc_adapter.py` 其它都不用改。

## DCC profile 下的 auth

本示例为简洁直接构造 `SessionContext`。真实 DCC 宿主里,同一个
`Authenticator` / `Authorizer` 缝隙照样适用--`AuthContext` 从工作室 session 填充
(不是 HTTP header),因为缝隙是传输无关的。

## 关于 LLM

同 `fastapi-bi`:本示例用 `FakeOrchestrator`(不调 LLM),没有 LLM token 位置。真实 LLM 由
`agentkit-runtime`(M2)提供,从 env 读 provider key。
