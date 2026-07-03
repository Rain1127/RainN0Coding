# Python E2E Agent Timing Report

- 测试日期: 2026-06-28
- 测试目标: 验证 Python 侧完整工作流是否能为 Java 侧提供可流式传输的生成结果
- 测试输入: `做一个简单的登录页面，包含用户名、密码输入框和登录按钮`
- 测试入口: `python-agent/tests/test_e2e_workflow.py`
- 观测方式: 在工作流各 Agent 外层加阶段计时打印，直接执行完整 e2e 工作流

## 结果概览

- 工作流最终完成: `completed`
- 最终构建: `OK`
- 最终评审: `PASS`
- 总耗时: `199.77s`
- 结论: Python 侧可以完成网站生成，并能走完整的 SSE/工作流链路返回给 Java 侧，但整体耗时主要集中在 `coder_agent` 和 `reviewer_agent`

## 各 Agent 耗时

| Agent | 耗时 | 备注 |
| --- | ---: | --- |
| `mode_detector` | `0.00s` | 仅做模式判断，无外部调用 |
| `intent_agent` | `11.78s` | 走 `deepseek-chat` 轻量路由 |
| `pm_agent` | `4.42s` | 走结构化 JSON 路由 |
| `architect_agent` | `11.51s` | 走结构化 JSON 路由 |
| `image_collector_agent` | `0.00s` | 零 LLM，规则化产出 |
| `coder_agent` | `132.84s` | 主耗时点，ReAct 多轮工具调用，直到第 17 轮才退出 |
| `reviewer_agent` | `49.42s` | 先尝试 `deepseek-chat`，JSON 非法后 fallback 到 `GLM-4.7-Flash` |
| `builder_agent` | `0.01s` | 质量门禁和构建收尾 |

## 关键日志摘要

### `coder_agent`

- 共经历 17 轮 ReAct 交互后退出
- 日志中显示第 1 到第 17 轮均有工具调用
- 退出点: `exit_tool` 被调用
- 结论: 主要瓶颈在多轮模型调用和工具调用循环

### `reviewer_agent`

- 首次使用 `deepseek-chat` 解析 Review JSON 时失败
- 失败原因: 返回了非法 JSON
- 随后 fallback 到 `GLM-4.7-Flash` 并成功
- 结论: 次要瓶颈在评审模型的 JSON 格式稳定性和 fallback 开销

### `builder_agent`

- 构建成功
- 质量门禁给出 `FAIL`，但不影响工作流最终完成
- 该阶段耗时几乎可以忽略

## 结论

这次 e2e 实测说明：

1. Python 侧工作流能完成网站生成。
2. SSE/工作流链路可以跑通到最终结果。
3. 真正拖慢全链路的不是 Java 桥接，而是 Python 侧的 `coder_agent` 长循环，以及 `reviewer_agent` 的 fallback 重试。

