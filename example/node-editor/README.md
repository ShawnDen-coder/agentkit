# node-editor 示例

自然语言驱动的 NodeGraphQt 节点编辑器。用户用中文描述意图,LLM 经 langchain
`create_agent` + langgraph `interrupt()` HITL 驱动节点图操作。

## 运行

```bash
# .env 里写:OPENROUTER_API_KEY=sk-or-v1-...  (可选:OPENROUTER_MODEL=anthropic/claude-3.5-sonnet)
uv run --env-file .env --with NodeGraphQt --with PySide6 --with qasync --with langchain-openai \
    python example/node-editor/app.py
```

弹出一个窗口,左边是空节点图,右边是聊天面板。输入"加一个值为 42 的数字节点"。

## 节点类型

6 种自定义 NodeGraphQt 节点(`nodes.py`,注册在 `math.nodes` 命名空间):

| 节点类 | 端口 | 内嵌 widget |
|---|---|---|
| `NumberNode` | out: value | QSpinBox(数字) |
| `StringNode` | out: value | QLineEdit(文本) |
| `AddNode` | in: a, b / out: result | — |
| `SubtractNode` | in: a, b / out: result | — |
| `MultiplyNode` | in: a, b / out: result | — |
| `OutputNode` | in: value | —(debug sink) |

## LLM 能力

| 动作 | 工具 | 类型 | 说明 |
|---|---|---|---|
| 创建节点 | `add_component_to_dashboard` | 前端 HITL | `component_id` 格式 `NodeType:value`(如 `NumberNode:42`) |
| 修改节点 | `update_component_in_dashboard` | 前端 HITL | `changes={"value": <新值>}` |
| 连接节点 | `connect_nodes` | 前端 HITL(runtime 扩展) | `source_node`/`target_node`/`source_port`/`target_port` |
| 查询图 | `get_catalog` | 后端同步 | 列出所有节点 |
| 读节点值 | `get_component_data` | 后端同步 | 读节点的 widget 值 |
| 读端口 schema | `get_semantic_model` | 后端同步 | 返回节点端口列表 |

`connect_nodes` 是 runtime 层扩展的第 5 个前端动词 —— core 的 4 个冻结前端 verb 不变
(插件定位:core 冻结数据契约,runtime 扩展 tool 暴露)。

## 展示了什么

- **窄腰 ①(ComponentAdapter)**:[`node_adapter.py`](./node_adapter.py) 把 NodeGraphQt 的
  `NodeGraph` 包装成 `ComponentAdapter`,节点 ↔ `Component` 信封。
- **窄腰 ②(SSE 协议)**:[`chat_panel.py`](./chat_panel.py) 进程内消费 `BaseSSE` 事件对象
  (不调 `to_sse()`,无序列化)。
- **0.3.0 插件定位**:LLM 调 `@tool`(langchain-native),`interrupt()` 暂停图(langgraph-native),
  `thread_id` + `resume` 恢复(checkpointer stateful)。
- **qasync**:asyncio loop 接 Qt 事件循环,`orchestrator.run()` 跟 Qt 控件一起跑。

## interrupt/resume 回环

```
用户输入 → ChatPanel._run(thread_id)
  ↓ orchestrator.run(QueryRequest)
  ↓ LLM 调 add_component_to_dashboard tool
  ↓ interrupt({"component_id": "NumberNode:42"}) 暂停图
  ↓ run() yield CopilotFunctionCall(name, arguments, tool_call_id)
ChatPanel 调 MainWindow._execute_fc(fc)
  ↓ graph.create_node("math.nodes.NumberNode", ...), set_property("value", 42)
ChatPanel._run(resume={"result": "created", "tool_call_id": fc.tool_call_id})
  ↓ orchestrator.run(QueryRequest(thread_id=同上, resume=...))
  ↓ Command(resume=...) 恢复图
  ↓ LLM 流式返回答案 + CopilotPromptSuggestions
```

## 文件

- [`app.py`](./app.py) — `MainWindow`:NodeGraphQt 图 + ChatPanel + `_execute_fc`(UI 动作执行点)
- [`nodes.py`](./nodes.py) — 6 种自定义 NodeGraphQt 节点类
- [`node_adapter.py`](./node_adapter.py) — `NodeGraphQtAdapter`(`ComponentAdapter` 实现)
- [`chat_panel.py`](./chat_panel.py) — `ChatPanel`(`QDockWidget` + interrupt/resume 回环)

## 关于 LLM

设 `OPENROUTER_API_KEY` env(OpenRouter key);默认 model
`anthropic/claude-3.5-sonnet`,可通过 `OPENROUTER_MODEL` env 覆盖。LLM 配置工厂在
[`_common/openrouter.py`](../_common/openrouter.py)。
