# python-agent 开发记录

> 项目：AI 多 Agent 代码生成系统
> 包管理：uv 0.11.15
> Python：3.12.4
> 开始时间：2026-05-23

---

## 一、环境搭建

### 1.1 uv 初始化

```bash
uv --version      # uv 0.11.15
python --version  # Python 3.12.4

mkdir python-agent && cd python-agent
uv init --no-readme
```

**决策：** `uv init --no-readme`，教程文档在上级 `docs/` 目录中，不需要项目内 README。

### 1.2 依赖安装（分层安装便于定位冲突）

| 步骤 | 包组 | 状态 |
|---|---|---|
| 1 | Web 框架：`fastapi uvicorn sse-starlette python-dotenv httpx pydantic` | ✅ |
| 2 | AI 框架：`langgraph langchain langchain-openai langchain-deepseek` | ✅ |
| 3 | Agent 框架：`autogen-agentchat` | ✅ |
| 4 | 向量/RAG：`pymilvus sentence-transformers langchain-community langchain-text-splitters rank-bm25` | ✅ |

### 1.3 清华镜像加速

**问题：** pymilvus + sentence-transformers 安装时需下载 torch（108MB）、scipy（34MB）等大型包，默认 PyPI 源速度极慢。

**解决：**
1. 在 `pyproject.toml` 中添加 `[tool.uv]` 配置段指定清华镜像
2. 第一次尝试用 `default-index` 字段名 → **失败**，uv 报 `unknown field`
3. 修正为 `index-url`（正确的字段名从 uv 错误提示中的 `expected one of ...` 列表里找到）

最终配置：
```toml
[tool.uv]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
link-mode = "copy"
```

**效果：** torch 从 108MB 下载耗时从 >5分钟 降至 24秒。

### 1.4 uv 跨盘符硬链接

**现象：** `Failed to hardlink files; falling back to full copy`

**原因：** uv 缓存目录（C:）与项目目录（D:）不在同一文件系统，Windows 不支持跨盘符硬链接。

**解决：** `link-mode = "copy"` 直接复制，消除警告。性能影响可忽略。

### 1.5 PyTorch DLL 加载失败（Windows）

**现象：**
```
OSError: [WinError 1114] 动态链接库(DLL)初始化例程失败。
Error loading "torch\lib\c10.dll" or one of its dependencies.
```

**原因：** 从 PyPI 安装的 PyTorch 2.10.0 依赖 Visual C++ 运行时库，当前 Windows 环境可能缺 VC++ Redistributable 2022+。

**影响范围：** 仅影响 `sentence-transformers` 和 `pymilvus`（两者依赖 torch），核心 AI/Agent 框架不受影响。

**解决方案（后续处理）：**
- 方案 A：安装 VC++ Redistributable 2022+
- 方案 B：卸载当前 torch，安装 CPU-only 版本 `uv add "torch>=2.5" --index-url https://download.pytorch.org/whl/cpu`
- 方案 C：用 OpenAI embedding API 替代本地 sentence-transformers

当前暂不处理，RAG 模块可先 `try/except` 降级使用。Milvus 客户端本身是基于 gRPC 的，pymilvus 不需要 torch（实际上 pymilvus 3.0.0 不依赖 torch），可以先正常使用。

---

## 二、API 兼容性验证

### 2.1 验证结果总览

| 框架 | 安装版本 | API 测试 | 变更点 |
|---|---|---|---|
| **LangGraph** | 1.2.1 | ✅ 通过 | StateGraph、add_node、add_edge、compile、MemorySaver 全部兼容 |
| **LangChain** | 1.3.1 | ✅ 通过 | ChatOpenAI 正常，with_structured_output 兼容 |
| **LangChain-OpenAI** | 1.2.2 | ✅ 通过 | 基本 API 不变 |
| **LangChain-DeepSeek** | 1.0.1 | ✅ 通过 | 薄封装，无需改动 |
| **AutoGen** | 0.7.5 | ⚠️ API 变更 | ConversableAgent→AssistantAgent, GroupChat→RoundRobinGroupChat |
| **FastAPI** | 0.136.1 | ✅ 通过 | 向后兼容 |
| **Pydantic** | 2.13.4 | ✅ 通过 | BaseModel、Field、with_structured_output 全部正常 |

### 2.2 LangGraph 1.x API（已验证兼容）

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

# API 不变：
# StateGraph(State) → add_node → set_entry_point → add_edge → compile
# MemorySaver() 用于对话检查点
graph = StateGraph(MyState)
graph.add_node("my_node", my_func)
graph.set_entry_point("my_node")
graph.add_edge("my_node", END)
app = graph.compile(checkpointer=MemorySaver())
```

### 2.3 AutoGen 0.7.x API（需要适配）

**旧 API（0.4.x）：**
```python
from autogen import ConversableAgent, GroupChat, GroupChatManager
```

**新 API（0.7.x）：**
```python
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat, SelectorGroupChat
from autogen_agentchat.messages import TextMessage
```

| 旧 API | 新 API |
|---|---|
| `ConversableAgent` | `AssistantAgent` |
| `GroupChat` + `GroupChatManager` | `RoundRobinGroupChat`（轮询发言）或 `SelectorGroupChat`（LLM 选择发言者） |
| 元组 `(coder, reviewer, ...)` | `RoundRobinGroupChat(participants=[...])` |

**适配方案：** 教程第 6 章的 AutoGen 代码需要重写——用 `RoundRobinGroupChat` 替代 `GroupChat + GroupChatManager`，`AssistantAgent` 替代 `ConversableAgent`。

### 2.4 pymilvus API（已验证兼容）

```python
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility
# API 不变，pymilvus 3.0.0 向后兼容
```

---

## 三、环境搭建完成状态

### 最终依赖清单（pyproject.toml）

```toml
[project]
name = "python-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "autogen-agentchat>=0.7.5",
    "fastapi>=0.136.1",
    "httpx>=0.28.1",
    "langchain>=1.3.1",
    "langchain-community>=0.4.1",
    "langchain-deepseek>=1.0.1",
    "langchain-openai>=1.2.2",
    "langchain-text-splitters>=1.1.2",
    "langgraph>=1.2.1",
    "pydantic>=2.13.4",
    "pymilvus>=2.4",
    "python-dotenv>=1.2.2",
    "rank-bm25>=0.2.2",
    "sentence-transformers>=5.5.1",
    "sse-starlette>=3.4.4",
    "uvicorn[standard]>=0.47.0",
]

[tool.uv]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
link-mode = "copy"
```

### 可直接使用的模块

| 模块 | 状态 |
|---|---|
| LangGraph 工作流编排 | ✅ 就绪 |
| LangChain LLM 调用（DeepSeek） | ✅ 就绪 |
| AutoGen 多 Agent 讨论 | ✅ 就绪（需适配 API） |
| FastAPI + SSE 流式输出 | ✅ 就绪 |
| Pydantic 结构化输出 | ✅ 就绪 |
| pymilvus 向量检索 | ⚠️ 未测试连接（需 Milvus 服务） |
| sentence-transformers Embedding | ❌ torch DLL 问题 |

---

## 四、核心 State 与配置模块实现

### 4.1 产出文件

| 文件 | 用途 |
|---|---|
| `.env` | 环境变量模板（DeepSeek API Key、Milvus 地址、Embedding 开关等） |
| `config.py` | 全局配置类，读 `.env` 并以类属性暴露 |
| `llm_factory.py` | LLM 实例工厂：`create_llm()`、`create_llm_with_structured_output()`、`create_reasoning_llm()` |
| `state/code_gen_state.py` | 7 个 Agent 共享的 CodeGenState TypedDict |
| `state/__init__.py` | 包标识 |
| `agents/__init__.py` | 包标识 |

### 4.2 能力边界

#### CodeGenState 的能力边界

| 边界 | 说明 |
|---|---|
| **只是数据容器** | State 不包含任何业务逻辑、校验规则、默认值计算——它只是 Agent 间传递数据的 TypedDict |
| **不做并发控制** | 多个 Agent 同时写 State 时的一致性由 LangGraph 框架保证（reducer 机制），State 自身不加锁 |
| **不做持久化** | State 只在一次工作流执行中存活。持久化到数据库由 Java 端的 `ChatHistoryService` 负责 |

#### config.py 的能力边界

| 边界 | 说明 |
|---|---|
| **只管读取** | 只从 `.env` 读配置，不写入、不修改环境变量 |
| **不做运行时动态配置** | 修改配置需要重启服务。热更新配置属于配置中心（Nacos/Apollo）的职责 |

#### llm_factory.py 的能力边界

| 边界 | 说明 |
|---|---|
| **只管创建** | 只负责 `new ChatOpenAI(...)`，不管调用、重试、限流 |
| **不管理连接池** | HTTP 连接复用由 LangChain 内部的 httpx/requests Session 处理 |
| **不感知业务** | 工厂不知道"这是给 PM Agent 用还是给 Coder Agent 用"——调用方传 temperature |

### 4.3 设计决策记录

**决策 1: `CodeGenState` 使用 `TypedDict(total=False)`**

教程中每个字段单独标注 `Optional[X]`，实际采用 `total=False` 一键标记所有字段可选。

理由：
- LangGraph 节点的返回值会被**增量合并**进 State（不是替换），所以 Agent 只需返回变化的字段
- 例如 PM Agent 只返回 `{"prd": ..., "phase": "prd_done"}`，不需要每次都填满所有字段
- 用 `total=False` 更简洁，LangGraph 1.x 完全兼容此模式

**决策 2: `add_messages` 的字段名从 `history` 改为 `messages`**

教程中历史消息字段叫 `history`，实际改为 `messages`。

理由：
- LangGraph 1.x 的 `add_messages` reducer 默认作用于名为 `messages` 的字段（虽然其他名字也能用）
- 后续 AutoGen 和 LangGraph 联用时，AutoGen 也使用 `messages` 字段名，统一命名避免转换
- `Annotated[list, add_messages]` 保证每次调用 Agent 时，新消息会自动追加而非覆盖

**决策 3: Config 使用类属性而非实例属性**

教程用 `class Config` + 实例 `config = Config()`，实际沿用此模式。

理由：
- 简单、无依赖
- 模块导入时 `load_dotenv()` 执行一次
- 单例模式天然满足（Python 模块级别变量只初始化一次）
- 不需要引入额外的依赖注入框架

**决策 4: `.env` 中加 `LOCAL_EMBEDDING_ENABLED=false`**

新增了 `LOCAL_EMBEDDING_ENABLED` 开关。

理由：
- sentence-transformers 在 Windows 下因 torch DLL 问题不可用（见 1.5 节）
- 后续 RAG 模块通过此开关决定是否使用本地 Embedding 还是调用远程 API
- 默认 `false`，保证在无 torch 环境下核心流程不报错

### 4.4 验证结果

```python
# 9 项测试全部通过
from config import config                    # PASS
from llm_factory import create_llm, ...      # PASS
from state.code_gen_state import CodeGenState # PASS
config.DEEPSEEK_MODEL                        # deepseek-chat
config.LOCAL_EMBEDDING_ENABLED              # False
llm = create_llm()                           # ChatOpenAI 实例
llm_struct = create_llm_with_structured_output(TestOutput)  # 结构化 LLM
reasoning = create_reasoning_llm()           # deepseek-reasoner
StateGraph(CodeGenState).compile()          # LangGraph 兼容
graph.invoke(initial_state)                  # 工作流执行
```

### 4.5 遇到问题

**无问题。** 本次实现按照教程结构，加上 `solution.md` 中记录的 AutoGen 0.7 API 差异预判，所有模块一次性通过验证。LangGraph 1.2.1 对 `TypedDict(total=False)` 完全兼容。

---

## 五、Supervisor Agent 实现

### 5.1 产出文件

`agents/supervisor_agent.py` — 纯路由函数，零 LLM 调用。

核心函数：
- `supervisor_decision(state) -> str`：LangGraph 条件边的路由函数，返回下一个节点名称
- `_handle_review_result(state) -> str`：处理审查结果（passed/failed/retry_limit）
- `get_next_phase_for_current(phase) -> str | None`：调试工具函数

### 5.2 能力边界

#### 负责（DO）

| 能力 | 说明 |
|---|---|
| 阶段路由 | 根据 `state.phase` 判断下一个应该执行的节点名称 |
| 审查分流 | 根据 `review.passed` 和 `retry_count` 决定：构建 / 重写 / 人工介入 |
| 兜底处理 | 未知 phase → 安全退出（`end`），review 为 None → 默认重试 |

#### 不负责（DON'T）

| 边界 | 说明 | 替代者 |
|---|---|---|
| **不调用 LLM** | Supervisor 是纯规则函数，不做任何 AI 推理 | —（规则表即正确） |
| **不修改 State** | 只读 state，返回值是**字符串**（节点名），不是 State 更新 | LangGraph 框架根据返回值切换节点 |
| **不判断"怎么修"** | 看到 `review.passed=False` 只决定"打回重写"，不管代码具体哪里错了 | Reviewer Agent 负责产出具体 issue 列表 |
| **不执行 Agent 逻辑** | Supervisor 不知道 PM/Coder/Reviewer 内部如何工作，只知道它们的节点名 | 各 Agent 自治 |
| **不做超时/性能决策** | 不判断"已经跑了多久"、"Token 消耗了多少" | 后续版本可在 Workflow 层加超时边 |

#### 内聚性判断

- Supervisor 只有 3 个函数，总代码 <60 行，全部围绕"根据 State 返回下一个节点名"
- 如果需要新增一个阶段（如 A/B 测试分流），只需在 `routing_table` 加一行 + 写一个 handler
- 不会膨胀为"编排引擎"——复杂编排逻辑属于 Workflow 层，不属于 Supervisor

### 5.3 设计决策

**决策 1: 路由表放在 Supervisor 内而非在 Workflow 里硬编码边**

教程将 PM→Arch→Fork→Reviewer 写为硬编码边（`workflow.add_edge`），只有 Reviewer 的条件路由调用 Supervisor。

实际做法：把所有 phase→next_node 的映射集中在 Supervisor 的 `routing_table` 中。后续升级为全动态路由时，只需在 Workflow 中把所有边改为 `add_conditional_edges` 即可。

**决策 2: 未知 phase 返回 "end" 兜底**

`routing_table.get(phase, "end")` — 如果 phase 不在表中，直接结束。防止因为拼写错误导致工作流无限等待。

**决策 3: `review=None` → 默认重试**

`_handle_review_result` 中 `state.get("review") or {}` 确保 review 为 None 时得到空 dict，`{}.get("passed")` 返回 None（falsy），进入重试分支。这是一种安全默认——不确定时宁可重写也不放过有问题的代码。

### 5.4 遇到的问题

**问题：Windows GBK 终端中文 + emoji 编码错误**

```
UnicodeEncodeError: 'gbk' codec can't encode character '✅' in position 19
```

**原因：** Windows 终端默认编码是 GBK，而 Python 的 `print()` 输出包含 `✅`（Unicode U+2705）时触发编码错误。

**解决：** 将所有验证输出中的 emoji 替换为 ASCII 文本（`✅` → `PASS`）。

**通用方案：** 在验证脚本开头加以下代码可彻底解决：

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
```

### 5.5 验证结果

13 项路由测试全部通过：

| # | 输入 | 输出 | 说明 |
|---|---|---|---|
| 1 | phase=init | pm_agent | 基础路由 |
| 2 | phase=prd_done | architect_agent | 基础路由 |
| 3 | phase=arch_done | fork_coder_and_images | 基础路由 |
| 4 | phase=code_done | reviewer_agent | 基础路由 |
| 5 | phase=build_done | end | 基础路由 |
| 6 | phase=error | end | 基础路由 |
| 7 | review.passed=true | builder_agent | 审查通过 |
| 8 | review.passed=false, retry=0/3 | coder_agent | 第 1 次重试 |
| 9 | review.passed=false, retry=2/3 | coder_agent | 第 2 次重试 |
| 10 | review.passed=false, retry=3/3 | human_intervention | 超过上限 |
| 11 | review=None | coder_agent | 安全默认值 |
| 12 | phase=unknown | end | 安全兜底 |
| 13 | get_next_phase | pm_agent in result | 工具函数 |

---

## 六、PM Agent 实现

### 6.1 产出文件

`agents/pm_agent.py` — 第一个真正调用 LLM 的 Agent。

核心组件：
- `Feature(BaseModel)` — 单个功能点的 Pydantic 模型
- `PRD(BaseModel)` — 产品需求文档模型，含 `page_type`/`layout_type` 枚举约束
- `PM_SYSTEM_PROMPT` — 按页面类型定制规则的 System Prompt
- `pm_agent(state) -> CodeGenState` — 主函数

### 6.2 能力边界

#### 负责（DO）

| 能力 | 说明 |
|---|---|
| 需求结构化 | 将"一句话需求"（如"做个电商首页"）转化为带优先级的完整功能清单 |
| 页面分类 | 自动识别页面类型（电商/后台/落地页/博客等），触发对应的功能补充规则 |
| 数据依赖推断 | 从功能反推需要哪些数据接口（如"商品列表API"） |
| 输入校验 | `user_request` 为空时立即返回 error 状态，不浪费 LLM 调用 |

#### 不负责（DON'T）

| 边界 | 说明 | 替代者 |
|---|---|---|
| **不写代码** | System Prompt 明确约束"只描述功能，不涉及技术实现" | Architect Agent 接手做技术设计 |
| **不设计组件树** | 不知道 Vue 组件长什么样 | Architect Agent |
| **不评估技术可行性** | 不判断"这个 API 能不能做"、"这个交互前端好不好实现" | Architect Agent 在技术设计阶段评估 |
| **不收集图片** | 不关心页面需要什么图片素材 | Image Collector Agent |
| **不记忆上下文** | 每次调用独立，不参考历史 PRD（RAG 是后续增强） | RAG 模块（第七章） |

#### 内聚性判断

- PM Agent 的 Prompt + Pydantic 模型 + 主函数共 ~100 行，全部围绕"模糊需求 → 结构化 PRD"
- 唯一外部依赖是 `llm_factory.create_llm_with_structured_output`
- 如果未来需要支持新页面类型（如"数据大屏"），只需在 PRD 的 `page_type` 枚举加一项 + Prompt 加一条规则

### 6.3 设计决策

**决策 1: `page_type` 和 `layout_type` 用 Pydantic `enum` 约束而非自由文本**

教程中这两个字段是自由 `str`。实际加了 `enum` 约束。

理由：下游 Architect Agent 需要根据页面类型决定布局策略。自由文本会让 LLM 输出"好看的双栏布局"这种不可靠值。用 `enum` 强迫 LLM 从有限选项中选一个，Architect Agent 收到的是确定性值。

**决策 2: 功能优先级按 high/medium/low 而非数字 1-5**

数字优先级的语义模糊（3 分意味着什么？）。用 `high/medium/low` 让 LLM 产出更有区分度的分级——System Prompt 明确定义 "high = 核心流程，缺了不完整"。

**决策 3: `data_dependencies` 要求写成 API 名形式**

Prompt 中要求 "写成 API 接口名形式（如'商品列表API'而非'商品数据'）"。这样 Architect Agent 在设计数据流时可以直接映射到接口名，不需要再次推断。

### 6.4 遇到的问题

**问题：LangChain 1.x 中 `langchain.schema` 模块已移除**

```python
# 教程中的导入（LangChain 0.x）
from langchain.schema import SystemMessage, HumanMessage  # ModuleNotFoundError!

# LangChain 1.x 正确导入
from langchain_core.messages import SystemMessage, HumanMessage
```

**影响：** 所有用到 `SystemMessage`/`HumanMessage`/`AIMessage` 的 Agent 都需要改导入路径。
**预防：** 后续 Agent 统一从 `langchain_core.messages` 导入。

### 6.5 验证结果

| # | 测试项 | 结果 |
|---|---|---|
| 1 | Import PM Agent | PASS |
| 2 | Pydantic PRD 构造 + `model_dump()` | PASS |
| 3 | `model_dump()` 产物可直接写入 State | PASS |
| 4 | `user_request` 为空 → `phase=error` | PASS |
| 5 | System Prompt 内容完整 | PASS |

---

## 七、Architect Agent 实现

### 7.1 产出文件

`agents/architect_agent.py` — 第二个调用 LLM 的 Agent。

核心组件：
- `ComponentNode(BaseModel)` — 组件树节点，含 name/description/props/children
- `FileSpec(BaseModel)` — 文件规格，含 `file_type` 枚举（component/page/store/router/util/style/config/type）
- `DataFlow(BaseModel)` — 数据流，含 `mechanism` 枚举（props/provide-inject/pinia-store/router-params/emit-event）
- `Architecture(BaseModel)` — 架构方案
- `ARCH_SYSTEM_PROMPT` — 含目录结构约定和技术栈约束
- `architect_agent(state) -> CodeGenState` — 主函数

### 7.2 能力边界

#### 负责（DO）

| 能力 | 说明 |
|---|---|
| 组件树设计 | 根据 PRD 功能清单设计 Vue 3 组件层级，根→一级子→更深嵌套 |
| 文件清单规划 | 输出所有需要创建的文件路径和用途（组件/路由/store/类型/工具） |
| 数据流设计 | 描述组件间数据传递方式和机制（props/Pinia/provide-inject/emit） |
| 技术栈锁定 | 固定输出 Vue 3 + Tailwind CSS + Pinia + Vue Router 4 + Vite |
| Props 接口定义 | 每个组件的 Props 带类型标注（如 `products: Product[]`） |
| 输入校验 | PRD 为空时立即返回 error 状态 |

#### 不负责（DON'T）

| 边界 | 说明 | 替代者 |
|---|---|---|
| **不写代码实现** | System Prompt 明确约束"只设计结构和接口，不写 template/script 内容" | Coder Agent |
| **不审查 PRD 合理性** | 不判断"这个功能清单是否合理"、"用户需求是否可行" | PM Agent 的职责，Architect 只消费 |
| **不收集图片** | 不关心页面需要什么视觉素材 | Image Collector Agent |
| **不评估构建可行性** | 不知道 npm build 会不会成功 | Builder Agent |
| **不生成路由代码** | 只规划 `src/router/index.ts` 需要存在，不写具体内容 | Coder Agent |

#### 内聚性判断

- Architect Agent 的 Prompt + 4 个 Pydantic 模型 + 主函数共 ~170 行，全部围绕 "PRD → 代码骨架"
- 唯一外部依赖是 `llm_factory.create_llm_with_structured_output`
- 4 个 Pydantic 模型各司其职：ComponentNode（组件）、FileSpec（文件）、DataFlow（数据流）、Architecture（聚合）

### 7.3 设计决策

**决策 1: `FileSpec` 增加 `file_type` 枚举字段**

教程中 FileSpec 只有 `path + description + component_name`。实际增加了 `file_type` 枚举。

理由：下游 Coder Agent 收到文件清单后，需要根据文件类型使用不同的代码模板（`.vue` 组件 vs `.ts` store vs `router/index.ts`）。如果 LLM 能把这个信息显式标注出来，Coder Agent 就不需要"猜"。

**决策 2: `DataFlow` 增加 `mechanism` 枚举字段**

理由同上——Coder Agent 需要知道"这个数据是通过 props 传还是通过 Pinia store 共享"，从而在代码中做正确的 import 和类型引用。

**决策 3: System Prompt 固定技术栈**

教程中技术栈在 Prompt 描述里是可变的。实际在 Prompt 中明确写死 Vue 3 + Tailwind CSS + Pinia + Vue Router 4 + Vite。

理由：当前系统只支持 Vue 3 项目，让 LLM "自由选择技术栈" 只会增加输出不可控的风险。固定技术栈降低后序 Agent（尤其是 Builder）的适配成本。

**决策 4: 将 `target_audience` 和 `data_dependencies` 加入 HumanMessage**

教程中传递给 Architect 的用户消息不含这两个字段。实际加入。

理由：`target_audience` 影响组件设计（后台系统 vs 消费者页面组件风格完全不同），`data_dependencies` 直接对应 Pinia store 和 API 工具函数的设计。

### 7.4 遇到的问题

**无新问题。** 复用了 PM Agent 阶段已发现的 `langchain_core.messages` 导入路径。

### 7.5 验证结果

| # | 测试项 | 结果 |
|---|---|---|
| 1 | Import Architect Agent | PASS |
| 2 | Pydantic Architecture 构造 + `model_dump()` | PASS |
| 3 | `model_dump()` 产物可直接写入 State | PASS |
| 4 | PRD=None → `phase=error` | PASS |
| 5 | Format helpers 正确处理 features 列表 | PASS |
| 6 | System Prompt 内容完整 | PASS |

### 7.6 Code Review 发现（simplify skill）

使用 `simplify` skill 做了三角度代码审查（逐行扫描 / 教程对比 / 跨文件一致性）。发现：

| 严重度 | 发现 | 处理 |
|---|---|---|
| **PLAUSIBLE** | `supervisor_agent.py` 中 `get_next_phase_for_current` 文档字符串写 "code_retry"，实际节点名是 "coder_agent" | 已修复 |
| **PLAUSIBLE** | `retry_count` 在所有已实现的 Agent 中从未递增——需在后续 Reviewer Agent 中写入 `state["retry_count"] = state.get("retry_count", 0) + 1` | 记录为 Reviewer Agent 待办 |
| **MINOR** | `Feature.priority` 未加 `Field(enum=[...])` 约束，与同文件其他字段不一致 | 低优先级，后续 PM Agent 迭代时统一 |
| **INFO** | `callable` 类型注解（`str \| callable`）在 mypy 下会报错，但 Python 3.12 运行时不下 crash | 可保留，或用 `collections.abc.Callable` 替换 |

---

## 八、Coder Agent 实现

### 8.1 产出文件

`agents/coder_agent.py` — Token 消耗最大的 Agent，负责生产所有代码文件。

核心组件：
- `CodeFile(BaseModel)` — 单个代码文件（path + content）
- `CoderOutput(BaseModel)` — 完整输出（files + notes）
- `read_existing_file` / `search_vue_api` — 工具定义（预留，当前未启用）
- `CODER_SYSTEM_PROMPT` — 20 条代码规范的完整约束
- `coder_agent(state) -> CodeGenState` — 主函数

### 8.2 能力边界

#### 负责（DO）

| 能力 | 说明 |
|---|---|
| 代码文件生成 | 根据架构方案 file_list，逐文件生成完整可运行的 Vue 3 + TypeScript 代码 |
| 技术栈约束 | 强制输出 Vue 3 Composition API + Tailwind CSS + Pinia + Vue Router 4 + Vite |
| 重试适配 | 收到 Reviewer 反馈时，将 issue 列表格式化为修复指令注入 LLM 上下文 |
| 输入校验 | architecture 为空或 file_list 为空时立即返回 error |
| 代码完整性保证 | 每个文件必须包含所有 import、template、script、style，不得省略或 TODO |

#### 不负责（DON'T）

| 边界 | 说明 | 替代者 |
|---|---|---|
| **不调用工具** | 当前不在 LLM 推理时启用工具调用（bind_tools 与 with_structured_output 互斥） | RAG 模块（未来通过 Prompt 注入替代工具调用） |
| **不审查代码质量** | 不知道自己的代码对不对、安不安全 | Reviewer Agent |
| **不执行 npm build** | 不验证代码是否能构建 | Builder Agent |
| **不设计架构** | 不修改架构方案，只消费 component_tree + file_list | Architect Agent |
| **不递增 retry_count** | 重试计数器由 Reviewer Agent 管理 | Reviewer Agent（待实现） |
| **不收集图片素材** | 生成的代码中图片 URL 可能是占位符 | Image Collector Agent |

#### 内聚性判断

- Coder Agent 的 Prompt + Pydantic 模型 + 格式化函数 + 主函数共 ~250 行，全部围绕 "架构方案 → 代码文件"
- 4 个格式化辅助函数（component_tree / file_list / data_flow / issues）各司其职
- 唯一外部依赖是 `llm_factory.create_llm_with_structured_output`

### 8.3 设计决策

**决策 1: `with_structured_output` vs `bind_tools` 冲突（核心决策）**

LangChain 1.x 中 `bind_tools()` 与 `with_structured_output()` 互斥——同一个 LLM 实例不能同时启用两者。

| 方案 | 优势 | 劣势 | 选择 |
|---|---|---|---|
| A: 仅 `with_structured_output` | 输出格式可靠、下游解析零风险 | 无法使用工具调用 | ✅ 当前方案 |
| B: 仅 `bind_tools` | 可使用工具 | 输出为自由文本、解析脆弱 | ❌ |
| C: 两阶段（先 tools → 再 structured） | 两者兼得 | LLM 调用翻倍、延迟翻倍 | ❌ 暂不采用 |

选择方案 A 的理由：
- 结构化输出是"硬需求"——CoderOutput 必须精确对应当前架构方案的 file_list，格式错误会导致整个工作流失败
- 工具调用是"软需求"——Vue API 参考可写入 System Prompt（20 条规则已覆盖），组件存在性检查可用 RAG 替代
- 工具定义保留为死代码（标有"预留"注释），未来 RAG 阶段可通过 Prompt 注入替代工具调用

**决策 2: 用户消息中加入 `data_flow` 信息**

教程中 Coder 的用户消息只含 component_tree + file_list + tech_stack。实际增加了 data_flow 部分。

理由：Architect Agent 产出的 DataFlow 精确标注了组件间的数据传递方式（props / Pinia / provide-inject / emit）。把这个信息喂给 Coder，LLM 可以在写代码时直接使用正确的通信机制，减少 "A 组件用 props 传数据给 B，但 B 组件从 Pinia 读" 这种不一致。

### 8.4 遇到的问题

**问题 1: `@tool` 装饰器将函数转为 `StructuredTool` 对象**

在 LangChain 1.x 中，`@tool` 装饰后的函数不再可直接调用 `search_vue_api("ref")`，必须改为 `search_vue_api.invoke({"api_name": "ref"})`。

**影响：** 工具定义保留但当前不启用，实际不受影响。但后续 RAG 模块若需要直接调用工具函数，必须用 `.invoke()` 或 `.ainvoke()` 而非直接调用。

**问题 2: `DEEPSEEK_BASE_URL` 从 `https://api.deepseek.com/v1` 改为 `https://api.deepseek.com`**

用户指定了新的 base URL（不含 `/v1`）。ChatOpenAI 会将此 URL 作为 base，拼接 `/chat/completions` 形成完整路径。需要注意：如果 API 调用返回 404，大概率是 URL 缺少 `/v1` 前缀。

### 8.5 验证结果

| # | 测试项 | 结果 |
|---|---|---|
| 1 | Import | PASS |
| 2 | CoderOutput model_dump → State 兼容 | PASS |
| 3 | _format_component_tree | PASS |
| 4 | _format_file_list | PASS |
| 5 | _format_data_flow | PASS |
| 6 | _format_issues | PASS |
| 7 | architecture=None → error | PASS |
| 8 | file_list=[] → error | PASS |
| 9 | search_vue_api.invoke() | PASS |
| 10 | System Prompt > 200 chars | PASS |

### 8.6 Code Review 发现（simplify skill）

三角度审查完成。关键发现：

| 严重度 | 发现 | 处理 |
|---|---|---|
| **CONFIRMED** | `retry_count` 在所有已实现的 Agent 中从未递增 → 无限重试循环 | 已在 §7.6 记录，Reviewer Agent 必须写入 |
| **INFO** | `_format_component_tree` 将树展平——子组件在父组件下和顶层各出现一次 | 不影响代码生成正确性，仅影响 Prompt 可读性 |
| **INFO** | `check_component_exists` 工具被删除（教程有但目前代码无） | 由 RAG 模块替代 |
| **INFO** | 用户消息新加了 data_flow 信息（教程无） | 正向改进 |

---

## 九、结构化输出方案变更（重大发现）

### 9.1 问题发现

真实 API 测试时发现 `deepseek-v4-pro` 与 LangChain 结构化输出完全不兼容：

| 尝试 | 结果 | 错误信息 |
|---|---|---|
| `with_structured_output(method="json_mode")` | ❌ | `This response_format type is unavailable now` |
| `with_structured_output(method="function_calling")` | ❌ | `Thinking mode does not support this tool_choice` |
| deepseek-chat `json_mode` | ⚠️ 中途 | 输出合法 JSON 但**字段名不对**（`product_name` 而非 `page_name`） |

**根因：**
1. `deepseek-v4-pro` 是推理模型（thinking mode），不支持 `response_format` 和 `function_calling`
2. `deepseek-chat` + `json_mode` 只保证输出合法 JSON，不强制 Pydantic schema → LLM 自由发挥字段名

### 9.2 解决方案

**放弃 LangChain 的 `with_structured_output`，改为手动 JSON 解析方案：**

```
LLM 调用（deepseek-v4-pro）
  → 返回 JSON 字符串
  → 去除 markdown 包裹（```json ... ```）
  → json.loads()
  → Pydantic.model_validate()
  → 强类型对象
```

**关键技术点：**
1. Prompt 中显式声明所有 Pydantic 字段名和类型（`FIELD_SPEC` 常量）
2. `create_json_parser(Model, FIELD_SPEC)` 替代 `create_llm_with_structured_output(Model)`
3. `_strip_code_fences()` 去除 LLM 输出的 markdown 代码块
4. DeepSeek `json_mode` 要求 prompt 含 "json" 关键词 → FIELD_SPEC 必须以 "Output ONLY a valid JSON" 开头

### 9.3 改造范围

| 文件 | 改造内容 |
|---|---|
| `llm_factory.py` | 新增 `create_json_parser()` + `_strip_code_fences()`，删除 `create_llm_with_structured_output()` |
| `agents/pm_agent.py` | 新增 `PRD_FIELD_SPEC`，`create_json_parser(PRD, PRD_FIELD_SPEC)` |
| `agents/architect_agent.py` | 新增 `ARCH_FIELD_SPEC`，同上 |
| `agents/coder_agent.py` | 新增 `CODER_FIELD_SPEC`，同上 |

### 9.4 验证结果

```
PM Agent:  电商首页, 7 features, phase=prd_done  ✅
Arch Agent: 9 components, 17 files                ✅
Coder Agent: 4 files, 76 lines total              ✅
ALL 3 AGENTS PASSED
```

---

## 十、Reviewer Agent 实现

### 10.1 产出文件

`agents/reviewer_agent.py` — 代码审查员，负责质量把关和重试循环闭环。

核心组件：
- `Issue(BaseModel)` — 单个问题（file/severity/category/description/suggestion）
- `ReviewResult(BaseModel)` — 审查结果（passed/score/issues/summary）
- `REVIEWER_SYSTEM_PROMPT` — 五维审查体系（语法/逻辑/安全/样式/性能，各有权重）
- `REVIEW_FIELD_SPEC` — JSON 字段名显式声明
- `_build_code_summary()` — 代码摘要（只发关键结构，不发完整代码，节省 Token）
- `reviewer_agent(state) -> CodeGenState` — 主函数，**含 retry_count 递增**

### 10.2 能力边界

#### 负责（DO）

| 能力 | 说明 |
|---|---|
| 五维代码审查 | 语法正确性 + 逻辑完整 + 安全性 + 样式/可访问性 + 性能 |
| 功能完整性对照 | 对照 PRD 功能清单检查代码是否覆盖所有需求 |
| 重试计数器管理 | **passed=false → retry_count += 1**（此前缺失的关键逻辑） |
| Token 优化 | `_build_code_summary` 只传 import 语句 + 文件块类型 + 前 2500 字符，不发完整代码 |
| 评分与通过判定 | score >= 80 → passed=true；score < 80 → passed=false + 列出 blocker |

####  默认意图树保证系统开箱即用，自定义意图树保证业务可扩展，版本化和校验机制保证线上稳定。text

| 边界 | 说明 | 替代者 |
|---|---|---|
| **不修复代码** | Reviewer 只给问题和建议，不写修改后的代码 | Coder Agent 收到 issue 列表后自行修复 |
| **不执行构建** | 不运行 npm build 验证代码是否可编译 | Builder Agent |
| **不判断架构合理性** | 不质疑"组件树是否合理"——这应该在 Architect Agent 阶段解决 | Architect Agent |
| **不管理重试上限** | Reviewer 只递增计数器，不判断"是否该停" | Supervisor Agent 读取 retry_count 做上限决策 |

#### 内聚性判断

- Reviewer 的所有逻辑围绕"代码 + PRD → 评分 + 问题清单"
- `_build_code_summary` 的存在是为了节省 Token（不传完整代码），这个优化独立于审查逻辑
- 如果未来需要新增审查维度（如"国际化检查"），只需在 System Prompt 加一条规则

### 10.3 设计决策

**决策 1: 不发完整代码给 Reviewer（Token 优化）**

`_build_code_summary` 对每个文件只发送：文件路径 + 行数 + 含有的块（template/script/style）+ import 语句 + 前 2500 字符 + 截断标记。

理由：技术文档预估 Reviewer 每次消耗 500~1000 Token。如果发完整代码（Coder 可能生成 5000+ Token 代码），审查成本会爆炸。`_build_code_summary` 将输入压缩到约 1000~2000 Token。

**决策 2: retry_count 由 Reviewer 管理而非 Supervisor**

Supervisor 只读不写。Reviewer 是唯一知道"这次审查过没过"的节点，因此也是唯一适合递增计数器的位置。

此前三个版本的 code review 都确认 `retry_count` 从未递增是**无限循环 bug**。本次实现彻底修复。

**决策 3: passed 时不递增 retry_count**

`if result.passed: retry_count 不变; else: retry_count += 1`。只有失败才消耗重试配额。

### 10.4 遇到的问题

**无新问题。** 使用已建立的 `create_json_parser` 模式，`REVIEW_FIELD_SPEC` 格式与其他 3 个 Agent 的 FIELD_SPEC 一致。

### 10.5 验证结果

| # | 测试项 | 结果 |
|---|---|---|
| 1 | Import | PASS |
| 2 | ReviewResult model_dump | PASS |
| 3 | _build_code_summary 摘要生成 | PASS |
| 4 | Empty code_files → error | PASS |
| 5 | retry_count: passed=+0, failed=+1 | PASS |
| 6 | System Prompt 完整 | PASS |
| **7** | **Coder→Reviewer→Supervisor 完整链路** | **PASS** |

完整链路输出：
```
[Coder Agent] 完成: 2 文件, 总计 28 行代码
[Reviewer Agent] 评分 45/100, FAIL (2 issues), retry_count=1/3
  问题 1: [critical] Header.vue 缺失导航链接
  问题 2: [info] Header.vue 缺失 ARIA role 属性
[Supervisor] 路由到: coder_agent (重试闭环)
```

### 10.6 simplify 审查

三角度审查（逐行扫描 / 行为删除 / 跨文件一致性）：

| 严重度 | 发现 | 处理 |
|---|---|---|
| **VERIFIED** | retry_count 已由 Reviewer 递增 → 闭环打通 | ✅ 已修复 §7.6 和 §8.6 记录的 bug |
| **INFO** | 所有 4 个 Agent 统一使用 `create_json_parser` + `FIELD_SPEC` 模式 | ✅ 一致 |
| **INFO** | 无残留 `with_structured_output` 或 `langchain.schema` 引用 | ✅ 清除完毕 |

---

## 十一、Image Collector + Builder + Workflow 实现

### 11.1 产出文件

| 文件 | Agent | LLM 调用 | 说明 |
|---|---|---|---|
| `agents/image_collector_agent.py` | Image Collector | 0 次 | 规则引擎根据页面类型判断图片需求 |
| `agents/builder_agent.py` | Builder | 0 次 | 写文件 + 补脚手架 + npm build |
| `workflow/code_gen_workflow.py` | Workflow | — | LangGraph StateGraph 组装 7 Agent |

### 11.2 Image Collector 能力边界

**负责：** 根据 `page_type` 和 features 关键词判断需要 banner/product/icon/logo/illustration/avatar
**不负责：** 不调用 Pexels/Unsplash API（demo 返回 picsum 占位图）、不调用 LLM

### 11.3 Builder Agent 能力边界

**负责：** 写入代码文件 → 补充脚手架（package.json/vite.config.ts/tailwind/postcss/index.html）→ npm install → npm build
**不负责：** 不修复构建错误（错误信息由 Reviewer + Coder 重试闭环处理）、不在构建失败时修改代码

### 11.4 Workflow 拓扑

```
START → PM → Architect → Fork(Coder + ImageCollector) → Reviewer
                                                            │
                                            passed ──► Builder → END
                                            failed ──► Coder (retry)
                                            retry>=3 ──► HumanIntervention → END
```

### 11.5 遇到问题

**无新问题。** Image Collector 和 Builder 为零 LLM 纯逻辑，Workflow 直接复用 LangGraph 1.2.1 的 StateGraph API。

### 11.6 全链路测试结果

```
用户需求: "做一个简单的登录页面，包含用户名、密码输入框和登录按钮"

[PM]     登录页面, 10 features (high=5)
[Arch]   10 components, 15 files, 12 data flows
[Images] 4 images (banner, avatar, icon, logo)
[Coder]  15 files, 457 lines
[Review] 75/100 FAIL → retry_count=1
[Coder]  15 files, 548 lines (retry 1)
[Review] 68/100 FAIL → retry_count=2
[Coder]  15 files, 585 lines (retry 2)
[Review] 75/100 FAIL → retry_count=3 → Human Intervention
```

**关键验证：**
- retry 闭环正常：3 轮 Coder→Reviewer→Coder，每轮 Reviewer 评分 + 递增 retry_count
- 代码质量随重试改善：457 → 548 → 585 行（更完整）
- 重试上限生效：retry_count=3 时正确终止到 Human Intervention
- 文件结构完整：router/index.ts、stores/auth.ts、types/login.ts、utils/api.ts、utils/validators.ts 均有生成

**观察：** 3 轮评分均未达 80 分阈值（75/68/75）。可能原因：deepseek-v4-pro 推理模型在 Reviewer 角色下审查标准偏严格；登录页面这类简单需求的代码难以在"安全性/可访问性/性能"维度拿高分。后续可调低通过阈值至 70 分，或增加 max_retries 到 5。

---

## 十二、项目完成状态

### 12.1 所有 Agent 总结

| # | Agent | 文件 | LLM 调用 | Token 估算 | 状态 |
|---|---|---|---|---|---|
| 1 | Supervisor | `supervisor_agent.py` | 0 | 0 | ✅ |
| 2 | PM | `pm_agent.py` | 1 次 | ~1000 | ✅ |
| 3 | Architect | `architect_agent.py` | 1 次 | ~1500 | ✅ |
| 4 | Coder | `coder_agent.py` | 1 次 | ~4000 | ✅ |
| 5 | Reviewer | `reviewer_agent.py` | 1 次 | ~800 | ✅ |
| 6 | Image Collector | `image_collector_agent.py` | 0 | 0 | ✅ |
| 7 | Builder | `builder_agent.py` | 0 | 0 | ✅ |

**每次工作流基准：4 次 LLM 调用，~7300 Token。重试每轮额外 +4800 Token。**

### 12.2 关键修复记录

| 日期 | 问题 | 解决 |
|---|---|---|
| 2026-05-23 | `langchain.schema` 不存在 (LangChain 1.x) | 改用 `langchain_core.messages` |
| 2026-05-23 | `@tool` 装饰后函数变为 `StructuredTool` | 工具定义保留，调用改用 `.invoke()` |
| 2026-05-23 | `deepseek-v4-pro` 不支持 json_mode/function_calling | 放弃 `with_structured_output`，改手动 JSON 解析 |
| 2026-05-23 | `deepseek-chat` json_mode 不强制 schema 字段名 | Prompt 显式声明 `FIELD_SPEC` |
| 2026-05-23 | `retry_count` 从未递增 → 无限循环 | Reviewer Agent 负责递增 |
| 2026-05-23 | Windows GBK 终端 emoji 编码错误 | ASCII 替代 + `sys.stdout.reconfigure(encoding='utf-8')` |
| 2026-05-23 | AutoGen 0.7.5 需要额外安装 `autogen-ext[openai]` | `uv add autogen-ext[openai]` |
| 2026-05-23 | AutoGen 0.7 不识别 `deepseek-v4-pro` 模型名 | 需显式传 `model_info` dict 声明能力 |
| 2026-05-23 | AutoGen 0.7 消息类型从 dict 改为 `autogen_core.models.*` | 改用 `SystemMessage/UserMessage` from autogen_core |
| 2026-05-24 | Docker Desktop 引擎无法启动 | 改用 Milvus Lite（本地文件模式，零依赖） |
| 2026-05-24 | pymilvus `MilvusClient` 类名冲突 | 封装类改名 `MilvusStore` |
| 2026-05-24 | `sentence-transformers` torch DLL 不可用 (Error 1114) | 换 torch 2.5.1+cpu + 系统装 VC++ Redist 后修复 |
| 2026-05-24 | Milvus 维度不匹配（768 vs 512） | bge-small-zh-v1.5 产出 512 维，重建 Collection |

---

## 十五、向量检索 + RAG 完成

### 最终状态

| 组件 | 状态 | 详情 |
|---|---|---|
| PyTorch | ✅ | 2.5.1+cpu |
| sentence-transformers | ✅ | BAAI/bge-small-zh-v1.5, 512 维 |
| Milvus Lite | ✅ | 5 Collections, 本地文件模式 |
| Embedding → Insert → Search | ✅ | 全链路通过 |

### RAG 模块文件

| 文件 | 用途 |
|---|---|
| `rag/embedding_service.py` | 嵌入服务（PyTorch 优先，TF-IDF 降级） |
| `rag/milvus_client.py` | MilvusStore 封装（5 个 Collection，search + insert） |
| `rag/rag_builder.py` | RAG Prompt 构建器 + 代码入库 |

### 嵌入模型详情

| 项 | 值 |
|---|---|
| **模型名称** | `BAAI/bge-small-zh-v1.5` |
| **开发者** | 北京智源人工智能研究院 (BAAI) |
| **HuggingFace** | https://huggingface.co/BAAI/bge-small-zh-v1.5 |
| **向量维度** | 512 |
| **模型大小** | ~100MB（首次下载约 400MB 含依赖） |
| **最大输入长度** | 512 tokens |
| **中文支持** | ✅ 原生优化 |
| **英文支持** | ✅ |
| **本地运行** | ✅ 无需 GPU，CPU 推理即可 |
| **推理速度** | ~10ms/条 (CPU) |
| **运行框架** | PyTorch 2.5.1+cpu / sentence-transformers 5.5.1 |
| **缓存路径** | `~/.cache/huggingface/hub/models--BAAI--bge-small-zh-v1.5/` |

**为什么选这个模型：**
1. BGE (BAAI General Embedding) 系列在中文语义检索评测中排名前 3
2. `small` 版本在精度和速度之间最佳平衡——512 维足够区分代码片段
3. MIT 开源协议，商用友好
4. `v1.5` 修复了 v1.0 对短文本（代码文件名、组件名）编码质量差的问题

### 模型首次加载

首次调用 `embedding_service.embed()` 会从 HuggingFace 下载模型（约 400MB），后续调用直接使用缓存（`~/.cache/huggingface/hub/`）。

### 降级方案

当 PyTorch 不可用时（Windows DLL 错误 1114），自动降级为 `scikit-learn TfidfVectorizer`（256 维字符级 n-gram）。精度约为 PyTorch 版的 60%，但零额外依赖。

---

## 十三、LangGraph 工作流 + SSE + FastAPI

### 13.1 产出文件

| 文件 | 用途 |
|---|---|
| `workflow/code_gen_workflow.py` | LangGraph StateGraph 组装 7 Agent + `run_workflow()` 同步入口 |
| `workflow/sse_stream.py` | 异步 SSE 流式包装——工作流执行过程中逐阶段推送事件 |
| `server/main.py` | FastAPI 服务 + `POST /api/generate-code` SSE 端点（Java 端调此接口） |

### 13.2 工作流能力边界

**负责：**
- 7 个 Agent 的节点注册和边连接
- Reviewer → Builder/Coder/HumanIntervention 的条件路由
- Coder → Reviewer 重试回路
- 初始 State 构造和 MemorySaver 检查点

**不负责：**
- 不做实时并行（fork 节点内是串行 Image Collector → Coder）
- 不做工作流超时控制（依赖 LangGraph 默认递归限制）
- 不管理 LLM 调用重试（LLM 层面的错误由各 Agent 内部 try/except 处理）

### 13.3 SSE 流事件格式

```json
{"type": "workflow_start", "message": "..."}
{"type": "phase_start", "phase": "pm", "message": "..."}
{"type": "phase_complete", "phase": "pm", "output": {...}}
{"type": "phase_complete", "phase": "arch", "output": {...}}
{"type": "phase_complete", "phase": "code", "output": {...}}
{"type": "code_file", "path": "...", "content": "..."}
{"type": "review_issue", "file": "...", "severity": "...", "description": "..."}
{"type": "phase_complete", "phase": "build", "output": {...}}
{"type": "done", "status": "success|retry_limit|error", "result": {...}}
```

### 13.4 遇到问题

**无新问题。** 复用已建立的 LangGraph StateGraph + MemorySaver 模式。SSE 层用 `asyncio` + `ThreadPoolExecutor` 桥接同步工作流到异步生成器。

### 13.5 验证结果

SSE 流测试输出（导航栏生成，21 文件，718 行代码）：

```
[START] 开始处理需求: 做一个简单的导航栏
[PM]    全局导航栏, 7 features
[ARCH]  9 components, 21 files
[CODE]  21 files, 718 lines + 逐文件 code_file 事件
[IMAGES] 4 images
[REVIEW] 65/100 FAIL, retry_count=3 + 逐 issue 事件
   [critical] Navbar does not call navStore.loadMenu()
   [critical] Auth store never initialized (initAuth)
   [critical] Router missing /about, /services routes
   [info] SearchBar lacks aria-label
[DONE]  status=retry_limit

Total events: 34
```

SSE 事件流按序推送——Java WebClient 可直接 `bodyToFlux(String.class)` 逐行透传给前端。前端根据 `type` 字段渲染进度条、代码文件列表、审查问题等。

---

## 十四、AutoGen 局部讨论模块

### 14.1 产出文件

`workflow/autogen_discussion.py` — Coder x Reviewer x Architect 三方讨论。

### 14.2 AutoGen 0.4 → 0.7 API 迁移（本次最大踩坑）

| 概念 | 教程 (0.4.x) | 实际 (0.7.x) |
|---|---|---|
| 导入 | `from autogen import ConversableAgent, GroupChat, GroupChatManager` | `from autogen_agentchat.agents import AssistantAgent` |
| Agent | `ConversableAgent(...)` | `AssistantAgent(name, model_client, system_message)` |
| 群聊 | `GroupChat(agents=[...])` + `GroupChatManager(groupchat=...)` | `RoundRobinGroupChat(participants=[...], max_turns=N)` |
| 启动 | `coder.initiate_chat(manager, message=...)` | `await team.run(task=...)` |
| 模型客户端 | 无（直接传 `llm_config` dict） | `OpenAIChatCompletionClient(model, api_key, base_url, model_info={...})` |
| 新增依赖 | 无 | `autogen-ext[openai]` |

### 14.3 额外踩坑：model_info + 消息类型

1. AutoGen 0.7 不认识 `deepseek-v4-pro` 模型名，必须显式传 `model_info` dict 声明能力
2. 消息必须使用 `autogen_core.models.{SystemMessage,UserMessage,AssistantMessage}`，不能用 dict

### 14.4 能力边界

**负责：**
- Coder + Reviewer + Architect 三方轮流发言（RoundRobin，最多 8 轮）
- 接收 issue 列表作为讨论起点
- 提供同步包装 `run_review_discussion_sync()` 供 LangGraph 节点调用

**不负责：**
- 不执行代码修复（讨论结果由 Coder Agent 执行）
- 不替代 LangGraph 工作流（AutoGen 管讨论，LangGraph 管流程）
- 不在每次审查失败时触发（仅在架构级争议需要多方协商时调用）

---

## 十五、RAG 多路检索引擎实现

### 15.1 背景

原有 RAG 模块仅做单一通道检索——对 3 个 Collection 串行搜索后简单拼接，缺少：
- 意图定向路由（不同 Agent 阶段需要不同类型知识）
- 全局向量补充（跨领域关联发现）
- 去重/重排序后处理（检索结果冗余、排序不合理）
- 真正的并行检索（Milvus Lite 串行搜索，延迟高）

### 15.2 环境修复

#### 15.2.1 PyTorch c10.dll Error 1114 修复

**症状：** `OSError: [WinError 1114] 动态链接库(DLL)初始化例程失败。 Error loading "c10.dll"`

**根因：** torch 2.10.0 与 intel-openmp 2026.0.0 不兼容。intel-openmp 2026.0.0 的 DLL 初始化失败导致 torch 的 c10.dll 加载失败。

**解决方案：**
1. 卸载 intel-openmp、mkl、intel-cmplr-lib-ur 等 Intel 包
2. 安装 torch 2.5.1+cpu（自带 OpenMP，不依赖外部 Intel 包）
3. 重装 VC++ Redistributable (VC_redist.x64.exe /quiet)

```bash
uv pip uninstall intel-openmp mkl intel-cmplr-lib-ur mkl-include onemkl-license -y
uv pip install "torch==2.5.1" --index-url "https://download.pytorch.org/whl/cpu"
```

**验证：** `python -c "import torch; print(torch.__version__)"` → `2.5.1+cpu` ✅
**Embedding：** bge-small-zh-v1.5 加载成功，输出 512 维向量 ✅

#### 15.2.2 Docker + Milvus Standalone

安装 WSL2 后，Docker Desktop 正常工作。启动 Milvus Standalone：

```bash
cd milvus && docker compose up -d
# 拉取 3 个镜像：etcd, minio, milvus v2.4.0（约 2GB）
```

### 15.3 架构变更

#### 15.3.1 milvus_client.py（重写）

**改动：**
- 双模式支持：`MILVUS_MODE` 环境变量切换 lite/standalone
- `search_multi()`: ThreadPoolExecutor 实现多 Collection 并行搜索
- `search_async()`: asyncio 包装，`run_in_executor` 实现非阻塞
- `search_multi_async()`: `asyncio.gather` 并行执行所有搜索
- 维度 512→512（匹配 bge-small-zh-v1.5）
- 补充 `search_components()`, `search_design_patterns()`, `search_error_fix()`, `search_framework_api()` 便利方法

**并行实现原理：**
- `ThreadPoolExecutor(max_workers=5)` 创建线程池
- 每个 Collection 的搜索提交到独立线程
- `as_completed()` 收集结果
- 对于 I/O 密集型操作（Milvus gRPC/文件读写），Python GIL 影响很小

#### 15.3.2 retrieval_engine.py（新建）

核心双通道检索引擎，4 个模块：

**数据模型：**
- `RetrievalResult`: 单条检索结果（content, source_collection, source_channel, score, metadata, vector）
- `RetrievalContext`: 检索上下文（phase, user_request, file_info, architecture, retry_count）

**IntentDirectedRetriever（通道 A）：**
- 9 条路由映射（code/arch/pm/review → 目标 Collection）
- 针对不同 Collection 构造定向查询文本
- 用 `search_multi()` 并行执行

**GlobalVectorRetriever（通道 B）：**
- 对全部 5 个 Collection 并行检索
- 查询文本 = user_request + file_info + phase

**PostProcessor（后处理流水线）：**
- **去重**：SHA256 精确去重 → 语义去重（Cosine > 0.95）→ 来源去重（同名优先保留高分）
- **重排序**：4 因子加权（语义 0.40 + 来源 0.25 + 成功 0.20 + 新鲜度 0.15）
- **格式化**：按 Collection 类型分 5 类（组件白名单/API 约束/错误预防/参考实现/设计模式）

**RetrievalEngine（门面）：**
- `select_channels()` 动态通道选择策略
- 双通道 ThreadPoolExecutor 并行
- 合并 → 去重 → 重排序 → 格式化

#### 15.3.3 embedding_service.py（简化）

移除 TF-IDF 降级逻辑，强制 PyTorch。模型加载失败直接抛异常。

#### 15.3.4 rag_builder.py（委托）

`build_rag_context()` 内部委托给 `RetrievalEngine.retrieve()`，接口向后兼容。
新增 `phase`, `retry_count`, `user_request` 参数用于意图定向。

### 15.4 能力边界

**负责：**
- 双通道并行检索：意图定向（精准）+ 全局向量（覆盖）
- 去重：内容哈希 + 语义相似度 + 来源去重三步
- 重排序：4 因子加权（语义/来源/成功/新鲜度）
- 格式化：按知识类型分类封装为 Prompt 约束块

**不负责：**
- 不写入向量数据（入库由 `index_code_files()` 负责）
- 不做 Query Rewrite（当前直接用原始需求文本做 embedding）
- 不做 HyDE（假设答案检索），因为代码生成场景的查询已经足够具体
- Scalar filtering（Milvus Lite 不完全支持，Standalone 待 Schema 增强后启用）

**已知限制：**
- 并行检索受 Python GIL 影响有限（I/O 密集型，ThreadPoolExecutor 有效）
- 重排序新鲜度因子暂用固定值（Collection 无 `created_at` 字段）
- Lite 模式下不支持 Milvus scalar filter（filter 条件在路由表中定义但未生效）
- Standalone 模式下 gRPC 连接池未实现（每次 search 创建新连接）

---

## 十六、RAG 种子数据

### 16.1 设计思路

5 个 Collection 各司其职，种子数据按业务精准匹配：

| Collection | 种子数量 | 数据来源 | embedding 字段 |
|---|---|---|---|
| `framework_api` | 30 条 | Vue 3 18 API + Router 3 API + Pinia 2 API + Tailwind 1 条 | `example`（代码示例） |
| `component_library` | 10 条 | 自研组件骨架（DataTable/SearchFilter/Pagination/ModalDialog/CardGrid/PageHeader/Tabs/EmptyState/SkeletonLoader/ConfirmDialog） | `code_snippet`（完整代码） |
| `design_pattern` | 12 条 | 前端常见架构模式（响应式网格/无限滚动/搜索筛选/主从布局/多步表单/仪表盘/固定头+侧边栏/标签页切换/骨架屏/错误处理/乐观更新/防抖搜索） | `description`（模式描述） |
| `error_pattern` | 15 条 | 高频编译/运行时错误（路径别名/V-for key/ref解包/Props类型/空值访问/Tailwind类名/Pinia/路由匹配/defineProps未定义等） | `fix_code`（修复方案） |
| `code_store` | 0 条（预留） | 构建成功后自动填充 | — |

### 16.2 入库流程

```bash
PYTHONPATH=. .venv/Scripts/python.exe rag/seed_milvus.py
```

- 读出 seed_data.py 中的数据列表
- 用 embedding_service.embed() 对 text_field 做向量化
- 通过 milvus_store.insert_one() 写入 Milvus
- 67 条数据全部入库成功

### 16.3 检索效果验证

查询："做一个电商商品列表页，支持分页搜索和分类筛选，点击商品进入详情"

```
通道 A（意图定向）: 10 条结果 → 命中 component_library + framework_api + code_store
通道 B（全局向量）: 20 条结果 → 命中全部 5 个 Collection
去重: 30 → 20 条
重排序: Top 8 条
格式化: 3778 字符的约束 Prompt
```

检索到：SearchFilter、Pagination、DataTable、CardGrid 组件 + v-model、v-for、ref、computed、defineProps API — 与查询需求高度相关。

### 16.4 能力边界

**负责：**
- 种子数据维护（seed_data.py 作为唯一数据源）
- 入库脚本（seed_milvus.py 负责 embed + insert）
- 数据可随时扩充（添加条目到 seed_data.py 后重新运行即可）

**不负责：**
- code_store Collection 的种子数据（由构建成功后自动填充）
- 增量更新（当前为全量覆盖式入库）
- 数据版本管理（无 rollback 机制）
- 入库数据的人工审核（信任种子数据质量）

---

## 十七、FastAPI 服务层 SSE 真流式改造

### 17.1 问题诊断

原有 SSE 实现存在根本缺陷：

```python
# 旧代码：工作流全部执行完才发事件
loop.run_in_executor(pool, run_workflow, ...)  # 阻塞等待
# ↓ 全部完成后 ↓
for phase in phases: yield event  # 一次性涌入
```

前端表现为：长时间空白 → 瞬间所有事件涌入。这违背了 SSE 的设计初衷。

### 17.2 解决方案

用 LangGraph `astream()` 替代 `invoke()`——`astream()` 是异步生成器，每个 superstep（Agent 节点）完成后 yield 一次 state 快照。

```
astream yield #1 → state.phase="prd_done"   → SSE: phase_complete(pm)
astream yield #2 → state.phase="arch_done"  → SSE: phase_complete(arch)
astream yield #3 → state.phase="code_done"  → SSE: code_file×N + phase_complete(code)
astream yield #4 → state.phase="review_done" → SSE: review_issue×N + phase_complete(review)
astream yield #5 → state.phase="build_done" → SSE: phase_complete(build)
astream yield #6 → state.phase="completed"  → SSE: done
```

### 17.3 代码变更

**code_gen_workflow.py** — 新增 `async def run_workflow_async()`:
- 使用 `compiled.astream(initial, config)` 替代 `compiled.invoke()`
- 每个节点完成时 yield 中间 state 快照
- 保留原 `run_workflow()` 供同步场景使用

**sse_stream.py** — 全面重写:
- 消费 `run_workflow_async()` 异步生成器
- `seen_phases` 集合跟踪已处理阶段，避免重试回路重复事件
- `prev_retry_count` 检测重试，发送 `code_retry` 阶段事件
- 逐文件 yield `code_file` 事件（Coder 完成后立即推送）
- 逐 issue yield `review_issue` 事件

**server/main.py** — 增强:
- 添加 CORS 中间件（允许跨域）
- 添加请求日志中间件
- 健康检查返回更多信息（chat_model, milvus_mode）
- 启动日志打印模型和 Milvus 配置

### 17.4 验证结果

```bash
# 健康检查 → OK
curl http://localhost:8000/api/health
# {"status":"ok","model":"deepseek-v4-pro","milvus_connected":true,...}

# SSE 流式测试 → 事件逐步到达
curl -X POST http://localhost:8000/api/generate-code -d '{"prompt":"做一个登录页面"}'
# data: {"type":"workflow_start",...}       ← 立即
# data: {"type":"phase_start","phase":"pm",...} ← 立即
# : ping ...                                ← 每15秒保活
# data: {"type":"phase_complete","phase":"pm",...} ← PM完成后
# ...
```

关键改进：事件不再"一次性涌入"，而是**随 Agent 完成逐步到达**。`sse-starlette` 的 `: ping` 机制保证连接在长 LLM 调用期间不超时断开。

### 17.5 能力边界

**负责：**
- SSE 流式事件推送（节点级实时进度）
- 重试可见性（`code_retry` 阶段 + `retry` 计数器）
- 连接保活（sse-starlette 自动 `: ping` 每 15 秒）
- Java 后端透传兼容（标准 `text/event-stream` 格式）

**不负责：**
- 不实现 `code_chunk` 级别的流式（Coder Agent 的 LLM 调用仍是原子的，完成后一次性发送全部文件）
- 不做断点续传或连接恢复（断开后需重新请求）
- 不像 OpenAI 的 token 级流式输出（LangGraph `astream()` 的粒度是 superstep 而非 token）
- 不处理并发限流（依赖 Java 侧的 `@RateLimit` 注解）

**已知限制：**
- LangGraph `astream()` 在 superstep 粒度 yield，Coder Agent 内部 1 次 LLM 调用耗时最长（20~50 秒），这期间只有 ping 没有业务事件
- 工作流在 `astream()` 中执行且发生异常时，异常在 SSE 层捕获并转为 `error` 事件，不会让连接断开
- `MemorySaver` 检查点存储是内存级别，服务重启后丢失

---

## 十八、全量调试（2026-05-24）

### 18.1 发现与修复清单

对 31 个 .py 文件进行全面静态分析 + 16 模块导入测试，发现 11 个 bug：

| # | 严重度 | 文件 | 问题 | 修复 |
|---|---|---|---|---|
| 1 | Critical | `rag/retrieval_engine.py` | 语义去重完全无效 — `vector` 字段未填充 | 移除无效的语义去重步骤，保留 hash + source 两步去重 |
| 2 | Critical | `rag/retrieval_engine.py` | `RetrievalEngine.retrieve()` 每次做无用 embedding | 移除未使用的 `embedding_service.embed()` 调用 |
| 3 | Critical | `llm_factory.py` | `create_json_parser` 闭包直接修改传入的 messages 列表 | 改为 `list(messages)` shallow copy 后再修改 |
| 4 | Critical | `workflow/code_gen_workflow.py` | Lambda 节点不可 pickle | `lambda s: end_node(s)` → 直接引用 `end_node` |
| 5 | Performance | `rag/milvus_client.py` | `search_multi()` 每次调用创建新线程池 | 改用 `self._executor` |
| 6 | Resource | `rag/milvus_client.py` + `server/main.py` | 线程池永不关闭 | 添加 `__del__` + FastAPI shutdown 事件 |
| 7 | Import | `agents/coder_agent.py` | `@tool` 装饰器在 import 时注册全局副作用 | 移除 `@tool`，改为文档常量 `VUE_API_DOCS` |
| 8 | Formatting | `agents/architect_agent.py` | Feature interactions 渲染为 Python repr `['click']` | `", ".join(interactions)` |
| 9 | Logic | `agents/coder_agent.py` | 硬编码 `/tmp/ai-code-project` | 已随 BUG 7 移除 |
| 10 | Config | `server/main.py` | CORS `allow_credentials=True` + wildcard 冲突 | 移除 `allow_credentials` |
| 11 | Config | `rag/seed_milvus.py` | 统计部分硬编码 Standalone URI | 根据 `config.MILVUS_MODE` 选择连接方式 |

附加修复：
- `agents/architect_agent.py`: `Field(enum=[...])` → `Field(json_schema_extra={"enum": [...]})`（Pydantic V3 兼容）
- `rag/embedding_service.py`: `get_sentence_embedding_dimension()` → `get_embedding_dimension()`（FutureWarning 消除）

### 18.2 验证

- 16 模块全部 import 通过（零错误、零 DeprecationWarning）
- RAG 检索引擎功能正常（去重: 30→23, 重排序: top 8）
- 架构一致性：7 个 Agent 函数签名统一 `(CodeGenState) → CodeGenState`，无循环依赖

---

## 十九、Java 侧重构 —— Python Agent 集成

### 19.1 重构范围

| 文件 | 改动 | 说明 |
|---|---|---|
| `pom.xml` | 新增 `spring-boot-starter-webflux` | 仅引入 WebClient，不启用 WebFlux 服务器 |
| `application.yml` | 新增 `python.ai.base-url` | Python FastAPI 地址 |
| `core/python/PythonAiClient.java` | **新建** | WebClient 代理，调用 Python SSE 端点 |
| `core/AiCodeGeneratorFacade.java` | **重写** | 删除 LangChain4j 调用，改为 Python 代理 |
| `core/saver/CodeFileSaverExecutor.java` | 新增重载 | 支持 `List<CodeFileDto>` 直接写入 |
| `service/impl/AppServiceImpl.java` | 简化 | 移除 `StreamHandlerExecutor`，直接透传 SSE |

### 19.2 数据流变化

```
旧: Controller → AppServiceImpl → AiCodeGeneratorFacade
        → AiCodeGeneratorServiceFactory → LangChain4j → DeepSeek
        → TokenStream/Flux<String> → StreamHandler → 前端

新: Controller → AppServiceImpl → AiCodeGeneratorFacade
        → PythonAiClient (WebClient) → Python FastAPI SSE
        → Flux<String> 透传 → 前端
```

### 19.3 编译验证

```bash
JAVA_HOME="D:/Program Files/Java/jdk-23" mvn compile -DskipTests
# BUILD SUCCESS — 159 source files, 0 errors
```

### 19.4 能力边界

**负责：**
- SSE 流式透传（Python → Java → 前端）
- 从 `code_file` 事件提取文件并保存到磁盘
- 流完成后触发 `VueProjectBuilder.buildProject()`

**不负责：**
- 不解析 Python SSE 事件内容（仅提取 code_file 用于保存）
- 不做 failover（Python 不可用时直接报错，不回落 Java AI）
- 前端适配（SSE 事件格式从 `AiResponseMessage` 变为 Python 标准事件，前端需同步更新）
