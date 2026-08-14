# agentkit 示例

自然语言驱动的节点编辑器示例:用 [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt)
+ PySide6 + qasync + AgentKit 0.3.0 协议栈,做一个可对话的节点图。

## 示例

| 示例 | 模式 | 传输 | 说明 |
|---|---|---|---|
| [`node-editor/`](./node-editor/) | 本地(DCC 宿主) | 进程内(对象) | NodeGraphQt 节点图 + 右侧聊天面板,LLM 经 `interrupt()` HITL 驱动图操作 |

## 运行

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
uv run --with NodeGraphQt --with PySide6 --with qasync --with langchain-openai \
    python example/node-editor/app.py
```

## 你会看到什么

1. 窗口左边是空的 NodeGraphQt 节点图,右边是聊天面板
2. 输入"加一个值为 42 的数字节点" → LLM 调 `add_component_to_dashboard`,节点出现在图上
3. 输入"再加一个数字节点值为 8,然后连到加法节点" → LLM 调 `connect_nodes`,图上出现连线
4. 输入"图里有哪些节点" → LLM 调 `get_catalog`,返回节点列表

## 0.3.0 有状态 interrupt/resume

每个用户输入生成一个 `thread_id`。LLM 调前端动词(如 `add_component_to_dashboard`)时
`interrupt()` 暂停图,后端 yield `CopilotFunctionCall` SSE 并结束流。前端执行 UI 动作
(创建/修改/连接节点)后,用**同一个 `thread_id` + `resume`** 恢复(不重发 messages)。
langgraph 的 checkpointer 持有暂停状态。

详见 [`node-editor/README.md`](./node-editor/README.md)。
