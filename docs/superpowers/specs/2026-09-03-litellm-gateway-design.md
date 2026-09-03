# LiteLLM Gateway 设计

## 1. 背景与目标

当前调用链为：

```text
Vue -> Spring Boot -> FastAPI/LangGraph -> Python ModelRouter -> DeepSeek/智谱
```

Python 侧已经在 `core/model_router.py` 与 `core/model_registry.py` 中实现模型候选、瞬时重试、熔断和供应商切换。随着模型数量、调用量和成本治理要求增加，供应商接入、可靠性、密钥、预算与监控继续留在业务进程中会造成职责混杂。

本次在 Python Agent 与模型供应商之间增加独立 LiteLLM Gateway，目标是：

- 统一 DeepSeek 与智谱 GLM 的 OpenAI 兼容入口。
- 集中管理供应商密钥、超时、重试、冷却与故障转移。
- 支持虚拟密钥、RPM/TPM 限流、消费记录和长期预算。
- 复用现有 Redis，并新增独立 PostgreSQL 保存 LiteLLM 管理数据。
- 将 LiteLLM 指标接入现有 Prometheus、Grafana 和全链路追踪体系。
- 消除 Python 与 LiteLLM 的双层供应商重试。
- 保持现有 Spring Boot 业务网关、FastAPI 工作流与 SSE 返回协议不变。

## 2. 范围

### 2.1 本期包含

- LiteLLM Proxy 独立服务及配置。
- `reasoning`、`structured`、`lightweight` 三类业务模型组的网关映射。
- DeepSeek 主模型与智谱 GLM 备用模型的有序故障转移。
- LiteLLM 虚拟密钥、预算、RPM/TPM 限流和消费账单。
- PostgreSQL 持久化与 Redis 命名空间隔离。
- Python ModelRouter 收缩为业务模型组适配器。
- Prometheus 指标、Grafana 仪表盘及 `request_id`/`trace_id` 关联。
- 本地原生运行脚本、云端 Docker 镜像和纯 Docker 部署脚本。
- 单元、契约、集成和端到端测试。

### 2.2 本期不包含

- 用 LiteLLM 替代 Spring Boot 业务网关。
- 把用户登录、应用 CRUD 或 SSE 代理迁入 LiteLLM。
- 购买 LiteLLM Enterprise、接入 SSO/SCIM 或企业审计功能。
- 启用语义响应缓存。Agent 请求上下文变化频繁，错误复用旧结果的风险高。
- Kubernetes、Docker Swarm 或 Docker Compose 编排。
- 对外开放 LiteLLM、FastAPI、数据库或监控采集端口。
- 改变 LangGraph 的 Reviewer 到 Coder 质量重试语义。

## 3. 方案选择

采用“LiteLLM 负责供应商级路由，Python ModelRouter 只负责业务模型组映射”的方案。

未采用的方案：

- Python 保留完整路由、LiteLLM 只做审计：配置和可靠性逻辑仍然分散。
- Python 与 LiteLLM 都保留完整路由：容易形成重试放大和重复收费调用。

Python 只选择任务需要的模型能力，不选择具体供应商。LiteLLM 是访问 DeepSeek 与智谱的唯一出口。

## 4. 总体架构

```text
Vue 前端
   | 用户请求 / SSE
   v
Spring Boot 业务网关
   | 登录鉴权、业务限流、App 数据、SSE 代理
   v
FastAPI Agent 服务
   | 并发控制、LangGraph、RAG、Agent 调度
   v
精简后的 ModelRouter
   | reasoning / structured / lightweight
   v
LiteLLM Gateway :4000
   | 虚拟密钥、预算、RPM/TPM、重试、冷却、故障转移
   +-------------------+
   v                   v
DeepSeek API       智谱 GLM API
```

旁路依赖：

```text
LiteLLM -> PostgreSQL：虚拟密钥、消费账单、预算和 fallback 记录
LiteLLM -> Redis：分布式限流、鉴权缓存和多实例协调
LiteLLM -> Prometheus -> Grafana：指标、仪表盘和告警
Java/Python/LiteLLM -> OTel/日志：request_id 与 trace_id 关联
```

## 5. 组件职责

### 5.1 Spring Boot

- 保持面向用户的身份认证、权限控制和业务限流。
- 保持应用、聊天记录、版本等业务数据管理。
- 保持调用 FastAPI 及 SSE 透明代理。
- 不直接调用 LiteLLM，也不持有模型供应商密钥。

### 5.2 FastAPI 与 LangGraph

- 保持 Agent 工作流、RAG、并发控制、Guardrail 和 SSE 事件生成。
- 使用一个 LiteLLM Virtual Key 访问允许的 `code-*` 模型组。
- 将 `request_id`、`trace_id`、`app_id`、`user_id` 和 Agent 阶段作为调用元数据传给网关。
- 不持有 DeepSeek 或智谱原始 API Key。

### 5.3 Python ModelRouter

- 保留 `reasoning`、`structured`、`lightweight` 业务接口，减少 Agent 调用方改动。
- 将业务组映射为 `code-reasoning`、`code-structured`、`code-lightweight`。
- 负责请求参数适配、响应解析和 LiteLLM 标准错误到工作流错误的转换。
- 不再维护供应商候选列表、供应商级熔断状态或跨供应商循环重试。
- LiteLLM 全部失败后不绕过网关直连供应商。

### 5.4 LiteLLM Gateway

- 作为模型供应商唯一出口。
- 管理供应商原始 API Key。
- 执行模型超时、一次瞬时重试、失败冷却和有序 fallback。
- 执行 Virtual Key 鉴权、模型访问控制、RPM/TPM 限流和预算检查。
- 记录模型、Token、费用、延迟、错误和 fallback 元数据。
- 暴露健康检查、管理接口和 Prometheus 指标。

### 5.5 PostgreSQL

- 使用独立数据库与独立最小权限账号，例如数据库名 `litellm_gateway`。
- 只保存 LiteLLM 控制面和消费数据，不替代现有业务 MySQL。
- 使用持久化存储，并纳入云端备份与恢复流程。

### 5.6 Redis

- 复用现有 Redis 服务。
- LiteLLM 使用独立命名空间，例如 `litellm:*`；如客户端能力要求数据库编号，则同时分配独立 Redis DB。
- 承担分布式限流、鉴权缓存和多实例协调。
- 本期不缓存模型完整响应。

## 6. 模型组与路由

| Python 业务组 | 对外模型名 | 主模型 | 备用顺序 |
|---|---|---|---|
| `reasoning` | `code-reasoning` | DeepSeek v4-pro | DeepSeek Chat -> GLM Flash |
| `structured` | `code-structured` | DeepSeek Chat | GLM Flash |
| `lightweight` | `code-lightweight` | DeepSeek Chat | GLM Flash |

LiteLLM 内部使用独立主模型组和备用模型组表达顺序，不把主备模型放入随机负载均衡组。Python 永远只请求稳定的 `code-*` 名称。

模型版本、API Base 和供应商 Key 通过环境变量注入。配置文件中不得出现真实密钥。生产镜像固定到通过兼容性验证的明确 LiteLLM stable 版本，不使用浮动的 `main-latest`。

## 7. 重试、熔断与降级

### 7.1 允许供应商切换的故障

- 连接失败或请求超时。
- HTTP 429。
- 供应商 HTTP 5xx。
- 网关检测到成功响应缺少业务所需内容。

空响应校验在 LiteLLM 网关扩展点中转换为可重试的网关错误，使 fallback 仍发生在网关层。若所固定版本无法可靠支持该扩展点，则空响应由 Python 转换为失败事件，不恢复 Python 的供应商直连或候选循环。

### 7.2 不允许盲目切换的故障

- 请求参数或消息格式错误。
- Virtual Key 无效或无权访问模型组。
- 预算耗尽。
- 输入被安全策略拒绝。

### 7.3 重试边界

- LiteLLM：单个模型对瞬时故障最多重试一次，然后按顺序 fallback。
- Python：不执行供应商级重试；只进行错误翻译和工作流收尾。
- LangGraph：Reviewer 到 Coder 的质量重试继续保留，因为它修复的是生成质量而不是基础设施故障。

所有模型均失败时，Python 输出现有协议可识别的失败或降级 SSE 事件。LiteLLM 不可用时不允许旁路直连，以免绕开预算、审计和密钥边界。

## 8. 三层流量控制

```text
Spring Boot：用户/IP 业务请求频率
      v
FastAPI：同时运行的 Agent 工作流数量
      v
LiteLLM：Virtual Key/用户/项目的 RPM、TPM 和消费预算
```

生产 RPM、TPM、并发数和预算不固化在代码中，全部通过环境变量或 LiteLLM 管理数据配置。实施阶段使用低额度测试策略验证拒绝行为；生产数值依据云服务器容量、供应商配额和压测结果设置。该容量调优不改变本设计的组件边界。

## 9. 鉴权、密钥与隐私

- FastAPI 只持有 LiteLLM Virtual Key。
- DeepSeek、智谱、LiteLLM Master Key 和数据库凭据只注入对应服务运行环境。
- `.env.example` 只保留变量名和非敏感示例，不保存真实值。
- 云端使用 root-only 的环境文件或等价的主机秘密注入方式，不把密钥写进镜像、Git、日志或前端。
- 默认不记录完整 Prompt、生成代码或模型回复。
- 监控标签不得包含 API Key、Prompt、代码正文等敏感或高基数字段。
- `user_id`、`app_id` 如需进入 LiteLLM 消费维度，使用受控元数据，并限制管理界面的访问范围。

## 10. 可观测性

Prometheus 分别抓取 Spring Boot、FastAPI 和 LiteLLM。Grafana 至少展示：

- LLM 请求成功率、错误率与吞吐量。
- P50、P95、P99 延迟。
- 各业务模型组及实际供应商的调用量。
- 输入 Token、输出 Token 和估算费用。
- 429、超时、5xx 和鉴权失败数量。
- 主模型切换备用模型的次数与最终结果。
- Virtual Key 预算使用率。
- Redis 与 PostgreSQL 请求失败和延迟。

`request_id` 与 `trace_id` 从 Spring Boot 传入 FastAPI，再作为 LiteLLM 请求元数据传递。日志与指标用于定位请求，完整链路 Span 是否由 LiteLLM 原生导出或由客户端补充，以固定版本的兼容性测试结果为准；无论采用哪种方式，都必须能用同一 `trace_id` 关联 Java、Python 与网关记录。

监控后端故障不得阻塞正常模型调用。采集失败只触发告警并形成监控缺口。

## 11. 本地运行

本地不使用 Docker 或 Docker Compose 启动 LiteLLM 相关依赖：

- PostgreSQL 作为本地服务运行并创建 `litellm_gateway` 数据库。
- Redis 复用现有本地实例并隔离 LiteLLM 命名空间。
- LiteLLM 使用独立 Python 虚拟环境运行，避免污染 `python-agent/.venv`。
- FastAPI、Spring Boot 和 Vue 沿用当前原生启动方式。
- Prometheus、Grafana 与 OTel 组件按现有本地工具方式启动。

建议新增：

```text
infrastructure/
└─ litellm/
   ├─ config.yaml
   ├─ .env.example
   ├─ start-local.ps1
   ├─ health-check.ps1
   └─ README.md
```

本地启动脚本必须输出明确健康标记和端口，不自动写入真实密钥。

## 12. 云端 Docker 部署

云端使用一个服务一个容器，而不是单体大容器。第一阶段不使用 Docker Compose、Swarm 或 Kubernetes，通过幂等 PowerShell/Shell 部署脚本、固定 Docker Network、健康检查和持久化 Volume 管理容器。

容器集合：

```text
frontend/nginx | java-api | python-agent | litellm
mysql | postgresql | redis | vector-db
prometheus | grafana | otel-collector | tempo
```

启动顺序：

1. 创建私有 Docker Network 与持久化 Volume。
2. 启动 MySQL、PostgreSQL、Redis 和向量数据库。
3. 逐个健康检查通过后启动 LiteLLM。
4. LiteLLM 健康后启动 FastAPI。
5. FastAPI 健康后启动 Spring Boot 与前端。
6. 启动监控组件并验证所有采集目标。

禁止用固定 `sleep` 代替健康检查。部署脚本重复执行不得破坏现有 Volume 或生成新密钥。

公网只开放 Nginx 的 80/443。Grafana 如需外部访问，必须启用身份认证并限制来源。Spring Boot、FastAPI、LiteLLM、数据库、Redis、向量数据库、Prometheus、OTel Collector 与 Tempo 均只在私有网络可达。

## 13. 故障处理

| 故障 | 预期行为 |
|---|---|
| DeepSeek 429/超时/5xx | LiteLLM 按策略重试并切换 GLM |
| 所有模型不可用 | LiteLLM 返回标准错误，Python 输出失败/降级 SSE |
| LiteLLM 不可用 | FastAPI 快速失败，不绕过网关 |
| PostgreSQL 不可用 | 禁止新建密钥和修改预算；未知密钥失败关闭；告警 |
| Redis 不可用 | 分布式限流/缓存能力降级或请求失败，具体按固定版本验证；告警且不得静默绕过预算 |
| Prometheus/Grafana 不可用 | 模型调用继续，形成监控缺口并告警 |
| Virtual Key 无效或预算耗尽 | 直接拒绝，不切换模型 |

PostgreSQL 和 Redis 故障时的精确缓存行为需要用最终固定 LiteLLM 版本做故障注入测试。安全原则固定为：未知身份失败关闭，已有请求不得通过绕过网关恢复。

## 14. 测试设计

### 14.1 单元测试

- 三个 Python 业务组映射到正确的 `code-*` 模型名。
- Python 不再执行供应商候选循环和供应商级熔断。
- LiteLLM 标准异常正确映射为工作流错误。
- 元数据不泄露供应商 Key 或完整 Prompt。

### 14.2 契约测试

使用本地假的 OpenAI 兼容 HTTP 服务模拟成功、429、超时、500、非法 JSON 和空响应：

- 验证 LiteLLM 的一次瞬时重试和有序 fallback。
- 验证不可重试错误不会访问备用模型。
- 验证响应格式与当前 LangChain `ChatOpenAI` 调用兼容。
- 测试不调用真实收费模型。

### 14.3 本地集成测试

- DeepSeek 与 GLM 分别能通过 LiteLLM 调通。
- Virtual Key 只能访问三个允许的业务模型组。
- 低额度 RPM、TPM 和预算策略能够拒绝超限请求。
- PostgreSQL 中能查询 Token、费用和 fallback 记录。
- Redis 中的 LiteLLM Key 使用独立命名空间。
- Prometheus 能抓取 LiteLLM 指标。

### 14.4 端到端验证

- 从前端发起代码生成并完整收到 SSE。
- 代码文件保存行为与接入前一致。
- 同一 `request_id`/`trace_id` 能关联 Java、Python 和 LiteLLM。
- 在非生产环境让主模型返回可重试错误，确认任务通过备用模型完成。
- Python 运行环境不再包含供应商原始 API Key。

## 15. 完成标准

以下条件全部满足才算完成：

- 三个 Agent 模型组全部通过 LiteLLM 调用。
- Python 不再直接访问 DeepSeek 或智谱。
- Python 与 LiteLLM 双层供应商重试已消除。
- Virtual Key、预算、消费账单与 fallback 记录可持久化。
- Redis 限流/协调状态与现有业务 Key 隔离。
- Grafana 可查看成功率、延迟、Token、费用和 fallback。
- 主模型故障演练、预算拒绝和鉴权拒绝均通过。
- 原有代码生成、Reviewer 重试、文件保存和 SSE 流程无回归。
- 本地原生运行与云端纯 Docker 部署均有可复制文档和健康检查。
- 仓库与镜像中不存在真实供应商 Key、Master Key 或数据库密码。

## 16. 实施顺序

1. 建立 LiteLLM 本地独立环境、配置骨架和假的供应商契约测试。
2. 接入 PostgreSQL、Redis、Virtual Key 与监控。
3. 配置三个业务模型组、重试、冷却和有序 fallback。
4. 收缩 Python ModelRouter，并保持 Agent 调用接口兼容。
5. 完成本地集成与端到端回归。
6. 构建固定版本容器镜像与纯 Docker 部署脚本。
7. 在云端完成健康、安全、故障注入和监控验收。

## 17. 参考资料

- LiteLLM Getting Started: <https://docs.litellm.ai/>
- LiteLLM Fallbacks: <https://docs.litellm.ai/docs/proxy/reliability>
- LiteLLM Virtual Keys: <https://docs.litellm.ai/docs/proxy/virtual_keys>
- LiteLLM Prometheus Metrics: <https://docs.litellm.ai/docs/proxy/prometheus>
- LiteLLM Caching: <https://docs.litellm.ai/docs/proxy/caching>
- LiteLLM Repository: <https://github.com/BerriAI/litellm>
