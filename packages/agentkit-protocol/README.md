# agentkit-protocol

[agentkit](https://github.com/ShawnDen-coder/agentkit) 的域中立协议 + 框架核心。
冻结了可迁移性所依赖的**两个窄腰**:

- **窄腰 ② - SSE 协议**:6 个 copilot 事件 + `QueryRequest` / `Message` / `SessionContext`。
- **窄腰 ① - 适配器契约**:`Component` / `ComponentSchema` 信封 + `ComponentAdapter` Protocol。

Core **领域无关且零框架依赖**(仅依赖 `pydantic` + `xxhash`)。领域语义
(`BiSemanticModel`、`DccSchema`、chart artifact)由 profile 包(`agentkit-bi`、未来的
`agentkit-dcc`)承载。Core **从不解析** `ComponentSchema` 或 `Artifact` 的内容——它们以
不透明多态信封的形式穿过 core。`langchain` **不是**依赖;它只进入 `LlmClient` 层(M2,
`agentkit-llm-langchain`)。

冻结面与版本策略见 [`docs/contracts.md`](../../docs/contracts.md),完整设计见
[`agentkit-architecture.md`](../../agentkit-architecture.md)。

## 模块构成

| 模块 | 冻结的内容 |
|---|---|
| `models` | SSE 6 事件(`BaseSSE.to_sse()` -> `{"event","data"}`);`QueryRequest`/`Message`/`SessionContext`;域中立信封 `Component`/`ComponentSchema`/`ComponentData`/`Refinement`;`ComponentParam`/`ComponentCapabilities`/`AdapterCapabilities`/`Field`;泛化 artifact(`TextArtifact`/`MarkdownArtifact`/`TableArtifact`/`ErrorArtifact`);`Citation` |
| `protocols` | `ComponentAdapter`(窄腰 ①)、`Orchestrator`、`LlmClient` Protocol;`VerbHandler` 类型 |
| `verbs` | `VerbSpec` + 11 个标准动词(`STANDARD_VERBS` = 7 个后端同步 `BACKEND_VERBS` + 4 个前端 FunctionCall `FRONTEND_VERBS`);`verb_to_tool`(转 `ToolDef`,丢 `executes_on`);`VerbBinding`/`VerbAlias`/`VerbBindings`(动词绑定与别名声明 + 查找容器) |
| `helpers` | `deterministic_uuid(origin, component_id)`(xxhash,跨轮回稳定) |
| `testing` | `CopilotResponse` DSL + `collect_stream` / `query` / `human_message`,用于契约测试 |

`PROTOCOL_VERSION = "0.2.0"`。

## 安装

本包是 uv workspace 的一部分;消费方以 `agentkit-protocol`(dist)/ `agentkit_protocol`(import)依赖它。
在 monorepo 内:`uv sync --all-packages --all-groups`。

## 快速示例

```python
from agentkit_protocol import (
    Component,
    ComponentSchema,
    CopilotMessageArtifact,
    TableArtifact,
    deterministic_uuid,
)

# 窄腰 ②:SSE 事件按 wire 契约序列化。
event = CopilotMessageArtifact(artifact=TableArtifact(columns=["region", "sales"], rows=[["N", 100]]))
assert event.to_sse() == {
    "event": "copilotMessageArtifact",
    "data": '{"artifact":{"kind":"table","columns":["region","sales"],"rows":[["N",100]]}}',
}

# 窄腰 ①:Component 携带一个不透明 schema 信封。Core 不解析它;
# profile(agentkit-bi)提供有类型的 schema,如 BiSemanticModel(kind="bi.semantic")。
component = Component(
    component_id="w1",
    origin="superset",
    name="Sales by Region",
    schema=ComponentSchema(kind="bi.semantic", dimensions=[{"name": "region"}]),
)
roundtripped = Component.model_validate_json(component.model_dump_json(by_alias=True))
assert roundtripped.schema_.kind == "bi.semantic"          # core 只读 `kind`
assert "dimensions" in roundtripped.schema_.model_dump()   # profile 字段被保留

# 确定性、跨轮回稳定的 component UUID。
assert deterministic_uuid("superset", "w1") == deterministic_uuid("superset", "w1")
```

## 设计要点

- **多态信封**:profile 的 schema 以 `kind` Literal + 有类型字段子类化 `ComponentSchema`。
  `Component.schema_` 字段类型为 `SerializeAsAny[ComponentSchema] | None`,因此子类字段能
  穿越 core 的 JSON 往返(反序列化回不透明基类时靠 `extra="allow"` 保留;profile 用
  `model_validate` 反向取回)。`Artifact` 同理。
- **`schema_` 属性**:Python 属性名是 `schema_`(尾下划线避免 shadow `BaseModel.schema`);
  它序列化为 wire key `schema`。这是唯一的别名字段。
- **`AdapterCapabilities` 分层**:core 持跨域标志(`supports_catalog`、`supports_selection`、
  `max_concurrent_fetch`);profile 扩展领域标志(BI:`can_filter` / `can_drill` /
  `can_add_widget` / `supports_semantic_model`)。
- **严格事件、开放信封**:SSE 事件用 `extra="forbid"`;信封(`ComponentSchema`、`Artifact`、
  capabilities、`Field`)用 `extra="allow"` 以支持前向兼容。

## 状态

M1 ✅ - 契约已冻结。`Orchestrator` / `LlmClient` 仅为 Protocol(实现在 M2);活的
`VerbRegistry`、FastAPI app、真实 adapter 在后续里程碑落地。
