# Benchmark 运行手册

本目录是 RainN0Coding 多维度 Benchmark 的版本化资产区。评测框架代码位于 `python-agent/benchmark/`，本目录只保存数据集、回放 Fixture、Suite、门禁策略和经审核的基线。

## 目录与来源规则

- `datasets/regression/`：PR 必跑的冻结回归案例，来自已审核 Golden Case、历史缺陷或固定合成边界。
- `datasets/nightly/`：需要真实 LLM、实时检索、RAGAS 或重复观测的高成本案例。
- `datasets/adversarial/`：Prompt 注入、越权、敏感信息、恶意路径等对抗案例；目录尚未建立时 Suite 会跳过它。
- `datasets/dev/`：评分器和 Prompt 调试用例，不用于生产质量声明。
- `fixtures/`：可重放的 Agent、RAG 和端到端原始输出。Fixture 与评分结果分离，便于评分器升级后重算。
- `suites/`：定义数据根、可用 Runner、离线属性、策略和基线目录。
- `policies/`：版本化的案例级、绝对指标和基线回归门禁。
- `baselines/`：人工审核后晋升的不可覆盖基线。
- `records/runs/` 与 `reports/`：按次生成的原始记录和报告，已被 Git 忽略，CI 会将其作为 Artifact 保留。

每个正式 Case 必须有稳定 `id`、`dataset_version`和 `provenance`。`provenance.reviewed` 与 `provenance.sanitized` 必须为 `true`。真实用户请求只能在去除姓名、账号、密钥、内网地址、绝对用户路径和业务数据，并完成人工复核后加入。禁止将原始对话或真实凭证复制到数据集、Fixture、基线或报告。

## 本地命令

以下命令均从 `python-agent/` 执行：

```powershell
# 校验 Suite、Case Schema、Fixture 和路径
.venv/Scripts/python.exe -m benchmark.cli validate --suite benchmarks/suites/pr.yaml

# PR 离线门禁：不调用真实 LLM 或外部网络
.venv/Scripts/python.exe -m benchmark.cli run --suite benchmarks/suites/pr.yaml --output benchmarks/reports/pr-result.json --html-output benchmarks/reports/pr-report.html

# Nightly：需要 LiteLLM 凭证，不要在普通 PR 中执行
.venv/Scripts/python.exe -m benchmark.cli run --suite benchmarks/suites/nightly.yaml --output benchmarks/reports/nightly-result.json --html-output benchmarks/reports/nightly-report.html

# 使用版本化策略对比候选报告与兼容基线
.venv/Scripts/python.exe -m benchmark.cli compare --candidate benchmarks/reports/pr-result.json --baseline benchmarks/baselines/<baseline>.json --policy benchmarks/policies/default.yaml

# 审核通过后晋升；相同兼容键已存在时会拒绝覆盖
.venv/Scripts/python.exe -m benchmark.cli baseline promote --report benchmarks/reports/pr-result.json --baseline-dir benchmarks/baselines
```

CLI 退出码是稳定契约：

- `0`：评测完成且门禁通过。
- `1`：评测完成，但案例硬门禁、绝对阈值或基线回归失败。
- `2`：数据、Fixture、配置、依赖、模型服务或报告生成异常；此时质量结论无效。

## 新增或修改 Case

1. 确定所属数据层，补全来源、审核和脱敏记录。
2. 将可重放原始输出放在 `fixtures/`，Case 中只使用受数据根边界约束的相对路径。
3. 使用声明式期望和稳定指标名，不要根据某次模型输出倒推期望。
4. 提升 `dataset_version`，执行 `validate`、`pytest -m benchmark`和 PR Suite。
5. 审核 JSON 的案例明细、门禁原因和元数据，再在浏览器中打开 HTML 报告检查人类可读性。HTML 是内嵌数据的单文件，无需 CDN 或服务器。

`Reviewer` 的 `review.score` 是被测 Agent 的自评信号，不是 Benchmark 裁决。最终通过与否由冻结标签、Schema、实际构建/测试、评分器和版本化门禁独立决定。

RAG 的正式 `Precision@K`、`Recall@K`、`MRR` 和 `nDCG` 只基于经复核的相关文档 ID 标注。线上按相似度分数阈值统计的 `context_precision` 或命中率只是运行健康信号，不能冒充带标签的 Precision/Recall。

## 基线审核与 CI

晋升前必须确认 Git SHA、Prompt 指纹、数据集版本/指纹、模型别名和 Suite 身份正确，并复核所有失败案例。`baseline promote` 采用不覆盖发布；重复晋升会返回 `2`，需要保留旧基线并通过新的兼容身份生成新文件，不得手工静默覆盖。

GitHub Actions 的 `benchmark-pr` job 只运行 marker 测试和离线 PR Suite，不注入任何 LiteLLM 凭证。`benchmark-nightly` 只在定时或手动触发时运行，需在 GitHub Secrets 配置：

- `LITELLM_BASE_URL`
- `LITELLM_API_KEY`

密钥只由 nightly job 的环境变量读取，不得写入 Case、Fixture、基线或 Artifact。两个 job 都使用 `always()` 上传 `reports/` 和 `records/runs/`，因此门禁失败后仍可下载证据排查。
