# 成熟 Benchmark 评测体系设计

## 1. 背景与结论

项目已经具备 `python-agent/agent_eval` Golden Trajectory、RAGAS 评估器、pytest 分层测试和 Reviewer 质量门禁，但当前 Golden 数据集只有少量开发案例，真实 LLM 评测依赖预先保存的输出，也没有统一的基线比较、回归门禁和可视化报告。

本设计采用“分层 Benchmark 平台”方案：保留现有 `agent_eval` 和 RAGAS，在外层建立统一的数据集、Runner、Evaluator、指标、基线、门禁与报告体系。第一阶段优先覆盖 Intent、Coder、Reviewer、Supervisor、RAG 和端到端生成链路，同时兼顾生产回归与面试展示。

## 2. 目标

1. PR 阶段能够在无模型密钥、无外部网络的条件下运行确定性回归并阻断明确的质量退化。
2. 夜间任务能够通过现有 LiteLLM 网关运行真实 LLM 评测，记录质量、稳定性、性能和成本数据。
3. 每次运行都能追溯到代码、模型、Prompt、数据集和配置版本。
4. 生成机器可读的 JSON 报告和可独立打开的单页 HTML 报告。
5. 将原始输出、评分结果和基线分离，使历史结果能够使用新版评分器重新计算。
6. 建立可扩展契约，后续能够覆盖其余 Agent、更多语言和线上反馈样本。

## 3. 非目标

第一阶段不建设常驻 Web 服务、数据库或复杂在线评测平台；不一次性覆盖全部 8 个 Agent；不把 Reviewer 自评分当作独立 Benchmark 结论；不在普通 PR 中调用真实 LLM；不对所有语言和框架组合做穷举测试。

## 4. 方案选择

### 4.1 直接扩展现有 `agent_eval`

优点是改动少、交付快；缺点是 Runner、评分、指标和报告会继续耦合，难以承载多种执行模式、基线管理和真实模型重复运行。

### 4.2 分层 Benchmark 平台（采用）

保留现有能力，通过稳定契约连接数据集、执行器、评分器、指标、门禁和报告。该方案能以中等改造成本形成完整闭环，并允许逐步扩展。

### 4.3 第三方评测平台作为主系统

第三方平台通常具备更完整的实验管理和看板，但会增加外部依赖、费用、隐私风险和现有 LangGraph 状态适配成本。第一阶段不将其作为主系统，后续可以通过导出接口接入。

## 5. 总体架构

```text
版本化数据集
    ↓
Runner 执行层
├─ deterministic：Supervisor、规则、Guardrail
├─ replay：评估已保存的 Agent 输出
├─ live：经 LiteLLM 调用真实模型
├─ rag：执行真实检索和 RAGAS
└─ e2e：运行完整代码生成链路
    ↓
Evaluator 评分层
├─ 声明式断言
├─ 结构化输出校验
├─ 代码执行与构建验证
├─ 检索指标与 RAGAS
└─ 人工评分导入
    ↓
Metrics 聚合层
├─ 质量
├─ 稳定性
├─ 性能
├─ 成本
└─ 工程行为
    ↓
Baseline Comparator
    ↓
Regression Gate
    ↓
benchmark-result.json + benchmark-report.html
```

模块边界遵循单一职责：Runner 只负责获得原始结果，Evaluator 只负责评分，Aggregator 只负责汇总，Gate 只负责做通过或失败决策，Reporter 不参与评分。

## 6. 目录设计

```text
python-agent/
├─ benchmark/
│  ├─ cli.py
│  ├─ config.py
│  ├─ contracts.py
│  ├─ dataset.py
│  ├─ runners/
│  │  ├─ deterministic.py
│  │  ├─ replay.py
│  │  ├─ live_llm.py
│  │  ├─ rag.py
│  │  └─ end_to_end.py
│  ├─ evaluators/
│  │  ├─ assertions.py
│  │  ├─ code_execution.py
│  │  ├─ retrieval.py
│  │  └─ aggregate.py
│  ├─ gates/
│  │  ├─ baseline.py
│  │  └─ policy.py
│  └─ reporting/
│     ├─ json_report.py
│     ├─ html_report.py
│     └─ template.html
├─ benchmarks/
│  ├─ datasets/
│  │  ├─ dev/
│  │  ├─ regression/
│  │  ├─ nightly/
│  │  └─ adversarial/
│  ├─ policies/
│  ├─ baselines/
│  ├─ records/
│  └─ reports/
└─ tests/
   └─ benchmark/

.github/workflows/benchmark.yml
```

`records/` 和按次生成的 `reports/` 默认不提交 Git；经过审核的基线和数据集需要提交。仓库远程地址为 GitHub，因此第一阶段使用 GitHub Actions 承载 PR 和夜间任务。

## 7. 数据集设计

### 7.1 数据分层

- `dev`：Prompt、规则和评分器调试，可频繁变化，不用于最终质量声明。
- `regression`：经过审核的冻结回归集，PR 必须运行。
- `nightly`：需要真实 LLM、重复运行或高成本依赖的案例。
- `adversarial`：Prompt 注入、越权、恶意代码、敏感信息和路径逃逸等安全案例。

开发集和正式评测集必须隔离，避免针对正式用例反复调参。每次变更正式数据集都提升 `dataset_version` 并记录内容摘要。

### 7.2 统一 Case 契约

每个案例至少包含：

- `id`、`schema_version`、`dataset_version`。
- `target`、`category`、`difficulty`、`tags`。
- `input`、固定上下文和 Fixture 引用。
- `execution.mode`：`deterministic`、`replay`、`live`、`rag` 或 `e2e`。
- `expectations`：声明式断言、构建要求、检索标注或人工评分要求。
- `metrics`：需要采集和聚合的指标。
- `gate`：案例级硬失败和阈值覆盖。
- `provenance`：来源类型、复核状态和脱敏状态。

数据加载阶段必须执行严格 Schema 校验、重复 ID 检查、Fixture 存在性检查和路径安全检查。

### 7.3 样本来源

第一阶段样本由现有 Golden Case、核心业务需求、历史缺陷、固定合成边界案例和安全对抗案例组成。真实用户请求只有在完成脱敏和人工复核后才能进入正式数据集。

覆盖不以单纯案例数量衡量，而以覆盖矩阵验收：正常路径、边界输入、失败与降级、安全场景、输出协议错误和历史缺陷回归都必须有对应案例。

## 8. 核心评测维度

| 对象 | 核心指标 | 独立证据 |
|---|---|---|
| Intent | 意图分类准确率、槽位准确率、澄清合理率、结构化输出成功率 | 冻结标签与 Schema 校验 |
| Coder | 文件覆盖率、语法通过率、构建成功率、功能测试通过率、安全违规率 | 实际文件、编译器、构建工具和测试结果 |
| Reviewer | 缺陷召回率、误报率、严重级别准确率、关键安全问题漏检率 | 同时包含缺陷代码和干净代码的标注集 |
| Supervisor | 路由准确率、重试策略准确率、架构升级准确率、人工介入准确率 | 生产路由函数的实际返回值 |
| RAG | Recall@K、Precision@K、MRR、nDCG、Faithfulness、Context Recall、检索延迟 | 人工相关性标注与 RAGAS |
| 端到端 | 任务成功率、构建成功率、验收测试通过率、延迟、Token、成本、重试和降级率 | 完整运行记录和可执行产物 |

现有基于检索分数阈值计算的在线 `context_precision` 和 `context_hit_rate` 只作为健康信号，不作为正式 Benchmark 的 Precision/Recall。正式检索指标必须基于人工标注的相关文档集合。

## 9. 执行模式

### 9.1 PR Suite

PR Suite 运行确定性案例、保存输出回放、固定 Fixture 的 RAG 指标、代码检查和少量端到端冒烟。它不访问真实 LLM 和外部网络，保证速度、稳定性与可复现性。

### 9.2 Nightly Suite

Nightly Suite 通过现有 LiteLLM 网关执行真实 Agent 与端到端案例。重复次数由 Suite 配置管理；报告同时展示平均结果、最差结果和波动，不允许只选取最佳运行。

### 9.3 手动 Suite

高成本模型对比、Prompt 实验和基线晋升使用手动命令执行。所有手动运行仍需生成同一报告契约，不能产生无法比较的临时格式。

## 10. 指标与统计

报告必须同时保留案例级结果与聚合结果。聚合维度包括总体、目标 Agent、类别、难度、模型、Prompt 版本和 Suite。

质量指标包括通过率、断言通过率、准确率、召回率、误报率、构建成功率和任务成功率；运行指标包括 P50/P95 延迟、输入/输出 Token、费用、重试次数、降级率和检索数量。费用优先使用 LiteLLM 返回的实际 spend 数据；无法获得可靠价格时只报告 Token，并将费用标记为不可用，禁止用过期价格静默估算。

重复运行指标需要保留每次观测值，并报告均值、最小值、最大值和波动。样本量不足时不宣称具有统计显著性，只展示观测结果。

## 11. 基线与回归门禁

每条运行记录都保存代码版本、模型、Prompt 指纹、数据集版本、Suite 和关键配置。基线兼容键由模型、Prompt 指纹、数据集版本、Suite 和影响结果的关键配置组成；代码版本只用于追溯，不进入兼容键，否则新提交将无法与旧代码基线比较。Prompt 指纹从实际 Prompt 模板内容自动计算，避免人工版本号漏更新。只有经过审核的运行才能晋升为基线，晋升操作不得静默覆盖已有基线。

门禁分三层：

1. 案例硬门禁：安全关键漏检、非法路由、Schema 失败和要求构建成功的案例构建失败。
2. 指标绝对门禁：指标低于策略文件定义的最低要求。
3. 基线回归门禁：指标相对同身份基线的退化超过允许范围。

阈值存放在版本化 YAML 策略文件中，不硬编码到评分器。首次基线运行完成前只生成候选报告，不编造阈值；阈值由真实基线结果和业务风险共同确定。

CLI 退出码：

- `0`：评测完成且门禁通过。
- `1`：评测完成但质量门禁失败。
- `2`：数据、配置、依赖、模型服务或报告生成异常，评测结论无效。

## 12. 报告设计

### 12.1 JSON 报告

JSON 是 CI 和其他系统使用的稳定契约，包含运行身份、环境元数据、总体结论、分组指标、基线差异、门禁结果、案例详情和脱敏后的错误信息。报告契约具有独立版本号。

### 12.2 HTML 报告

HTML 使用内嵌 CSS、JavaScript 和数据生成单文件报告，不依赖 CDN 或服务器。页面包含：

- 总体通过状态与运行身份。
- 当前结果和基线差异。
- 六个核心评测对象的指标概览。
- 质量、稳定性、延迟、Token 和成本图表。
- 失败案例的期望、实际结果、评分和 Trace 信息。
- 模型与 Prompt 对比。
- 可复制的项目介绍和面试摘要。

报告展示层不得重新计算评分，所有数字必须直接来自 JSON 报告。

## 13. 错误处理与安全

- 网络、限流和短暂服务错误可以按配置有限重试；质量不合格不能自动重试，以免掩盖模型不稳定性。
- 单个案例失败后继续执行其余案例，并在最终报告区分质量失败和基础设施失败。
- Runner 原始输出与 Evaluator 结果分开保存，评分器更新后可以重放评分。
- API Key、访问令牌、用户隐私、绝对用户路径和生成代码中的敏感值在日志及报告中统一脱敏。
- Fixture 与生成产物只能写入受控临时目录，沿用项目现有路径安全约束。
- Nightly 所需密钥只通过 CI Secret 注入，不进入数据集、基线或报告。

## 14. 测试策略

- 单元测试：Case Schema、断言、指标、分位数、基线匹配、门禁策略、退出码和脱敏。
- 集成测试：所有 Runner 使用固定 Fixture，默认不访问真实模型。
- 故障测试：超时、限流、无效 JSON、重复 Case ID、Fixture 缺失、构建失败和报告失败。
- 报告测试：JSON Schema 校验、HTML 单文件检查、中文编码和失败详情渲染。
- Live 测试：单独 marker，普通 pytest 默认不执行，只由手动或夜间工作流启用。
- 兼容测试：现有 `agent_eval` 案例及相关测试继续通过。

## 15. 第一阶段实施顺序

1. 建立契约、数据加载器和配置，迁移现有 Golden Case。
2. 实现断言评分、指标聚合、原始记录和 JSON 报告。
3. 实现 deterministic、replay Runner 与 PR Suite。
4. 实现基线管理、策略门禁和退出码。
5. 实现单页 HTML 报告。
6. 接入 Coder 构建验证、带标注的 RAG 评测和端到端冒烟。
7. 实现 LiteLLM live Runner 与 Nightly Suite。
8. 增加 GitHub Actions PR 和夜间工作流，补全文档与故障测试。

每一步都必须先完成对应测试，不能等全部模块完成后再集中补测试。

## 16. 第一阶段验收标准

1. `python -m benchmark.cli validate` 能校验正式数据集、策略和 Fixture。
2. `python -m benchmark.cli run --suite pr` 能在无模型密钥、无外部网络时稳定执行。
3. `python -m benchmark.cli run --suite nightly` 能通过 LiteLLM 执行真实模型案例并记录模型、Token、延迟和成本。
4. 已知质量回归返回退出码 `1`，基础设施错误返回 `2`。
5. JSON 报告符合固定 Schema；HTML 能离线打开，并展示六个核心对象、基线差异和失败详情。
6. 当前审核通过的基线能够通过门禁；注入安全漏检、错误路由或构建失败时门禁能够阻断。
7. 原始输出、评分结果和基线相互独立且可追溯。
8. 现有 `agent_eval` 相关测试继续通过，新 Benchmark 模块的单元及集成测试通过。
9. GitHub Actions 的 PR 工作流不使用真实模型密钥；夜间工作流只从 Secret 读取 LiteLLM 凭证。
10. 文档说明新增案例、运行 Suite、阅读报告、审核结果和晋升基线的完整流程。

## 17. 后续阶段

- 第二阶段：覆盖 PM、Architect、Image Collector、Builder 等剩余 Agent。
- 第三阶段：引入人工评分校准、更多模型横向对比和重复运行置信区间。
- 第四阶段：接入长期存储、趋势看板和线上反馈样本回流。

## 18. 已确认决策

- 使用场景：生产回归和面试展示并重。
- 执行策略：PR 离线低成本评测，夜间真实 LLM 评测。
- 第一阶段交付：直接实现可运行版本，而非只交付方案。
- 第一阶段覆盖：Intent、Coder、Reviewer、Supervisor、RAG 和端到端链路。
- 报告格式：JSON 加单页离线 HTML。
- 架构路线：复用现有能力的分层 Benchmark 平台。
