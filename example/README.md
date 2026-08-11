# agentkit 示例

两种部署模式,**同一套协议**。这些示例把"可迁移"这个承诺做实:同一份
`agentkit_protocol` 契约(`QueryRequest` / `Message` / `SessionContext` 进,
`BaseSSE` 事件出,`ComponentAdapter` 接后端)同时驱动一个浏览器+服务器的 BI 应用
和一个进程内的 DCC 桌面应用。

| 示例 | 模式 | 传输 | 前端往返 |
|---|---|---|---|
| [`fastapi-bi/`](./fastapi-bi/) | C&S(BI 仪表盘) | HTTP + SSE(`to_sse()`) | 断连 + 重发 `role=tool` |
| [`pyside-dcc/`](./pyside-dcc/) | 本地(DCC 宿主) | 进程内(对象) | 带 `role=tool` 重新调 `run()` |

## 现在就能跑(不用 LLM、不用 API key)

`agentkit-runtime`(M2,langchain/langgraph 第一公民)还没建。两个示例都用一个脚本化的
[`FakeOrchestrator`](_common/fake_orchestrator.py),它实现 `Orchestrator` 协议,用
**真实的 adapter 调用**(货真价实的窄腰 ①)+ 脚本化的 SSE 事件来跑通 Option B 状态机。
等 `agentkit-runtime` 落地,把 `FakeOrchestrator` 换成 `LanggraphOrchestrator` 即可--
示例里的 adapter、auth、前端、SSE 装配都不用改。

这个替换本身就是教学点:**wire 契约(`agentkit_protocol`)是稳定的缝;orchestrator
是可替换的实现。**

## 前置

```bash
uvx --from rust-just just init          # 同步 workspace(装好 agentkit_protocol)
```

示例专属依赖(fastapi/uvicorn、pyside6/qasync)在各自的运行命令里用
`uv run --with` **临时**提供--不用单独安装,不污染 venv。见各示例 README。

## 你会看到什么

两个示例,在一条用户消息上,都跑完整的 Option B 回路:

1. **后端同步**(真实 adapter 调用)-> `copilotStatusUpdate` + `copilotMessageArtifact`
2. **前端 FunctionCall** -> `copilotFunctionCall`(流结束,往返开始)
3. 前端执行 UI 动作(加一个 widget / 场景节点)
4. **恢复** -> `copilotMessageChunk`(最终答案)+ `copilotPromptSuggestions`

区别只在传输:HTTP+SSE(BI)vs 进程内对象(DCC)。
