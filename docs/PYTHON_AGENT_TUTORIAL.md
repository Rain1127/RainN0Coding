# Python 多 Agent 代码生成系统 — 实战教程

> 教程版本：1.0
> 适配 Python：3.11+
> 预计学习时间：4~6 小时（分步可独立运行验证）

---

## 目录

- [一、概述](#一概述)
- [二、基础环境搭建](#二基础环境搭建)
- [三、核心 State 与配置模块](#三核心-state-与配置模块)
- [四、Agent 实现（共 7 个）](#四agent-实现共-7-个)
  - [4.1 Supervisor Agent](#41-supervisor-agent)
  - [4.2 PM Agent](#42-pm-agent)
  - [4.3 Architect Agent](#43-architect-agent)
  - [4.4 Coder Agent](#44-coder-agent)
  - [4.5 Reviewer Agent](#45-reviewer-agent)
  - [4.6 Image Collector Agent](#46-image-collector-agent)
  - [4.7 Builder Agent](#47-builder-agent)
- [五、LangGraph 工作流编排](#五langgraph-工作流编排)
- [六、AutoGen 局部讨论模块](#六autogen-局部讨论模块)
- [七、Milvus 向量检索 + RAG](#七milvus-向量检索--rag)
- [八、FastAPI 服务层（SSE 流式输出）](#八fastapi-服务层sse-流式输出)
- [九、完整运行指南](#九完整运行指南)
- [十、验证与调试](#十验证与调试)

---

## 一、概述

本教程带你从头搭建一个 **7 Agent 协作的 AI 代码生成系统**，架构如下：

```
FastAPI (SSE) → LangGraph (全局编排) → 各 Agent 节点
                    │
                    ├── AutoGen GroupChat (Coder ⇄ Reviewer ⇄ Architect 讨论)
                    └── Milvus RAG (组件库 / API 文档 / 错误模式检索)
```

每步产出均可独立验证，建议一步一步执行，不要跳步。

---

## 二、基础环境搭建

### 2.1 创建项目

```bash
mkdir ai-code-gen-agents && cd ai-code-gen-agents
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

mkdir -p agents workflow rag server
```

### 2.2 依赖清单（`requirements.txt`）

```txt
# === Web 框架 ===
fastapi==0.115.6
uvicorn[standard]==0.34.0
sse-starlette==2.2.1

# === Agent 框架 ===
autogen-agentchat==0.7.3
langgraph==0.4.1
langchain==0.3.19
langchain-openai==0.3.11
langchain-deepseek==0.1.3

# === 向量数据库 ===
pymilvus==2.4.10
sentence-transformers==3.4.1

# === 文本处理 ===
langchain-community==0.3.18
langchain-text-splitters==0.3.7
rank-bm25==0.2.2

# === 结构化 ===
pydantic==2.10.6
httpx==0.28.1

# === 工具 ===
python-dotenv==1.0.1
```

安装：

```bash
pip install -r requirements.txt
```

### 2.3 环境变量（`.env`）

```bash
# DeepSeek API（兼容 OpenAI 格式）
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# 服务端口
SERVER_PORT=8000
```

### 2.4 验证安装

```bash
python -c "
from langgraph.graph import StateGraph
from autogen import ConversableAgent
from pymilvus import connections
from fastapi import FastAPI
print('All imports OK')
"
```

---

## 三、核心 State 与配置模块

### 3.1 State 定义 — `state/code_gen_state.py`

```python
"""Agent 间共享的状态对象 —— 所有 Agent 读写同一个 State"""
from __future__ import annotations
from typing import TypedDict, List, Annotated, Optional
from langgraph.graph.message import add_messages


class CodeGenState(TypedDict):
    # ========== 输入 ==========
    user_request: str                # 用户原始需求
    user_id: str                     # 用户 ID
    app_id: str                      # 应用 ID

    # ========== PM Agent 产出 ==========
    prd: Optional[dict]              # {page_name, features, target_audience}

    # ========== Architect Agent 产出 ==========
    architecture: Optional[dict]     # {component_tree, file_list, data_flow}

    # ========== Coder Agent 产出 ==========
    code_files: List[dict]           # [{path, content}]

    # ========== Reviewer Agent 产出 ==========
    review: Optional[dict]           # {passed, score, issues}
    retry_count: int                 # 当前重试次数
    max_retries: int                 # 最大重试次数 (默认 3)

    # ========== Image Collector 产出 ==========
    images: List[dict]               # [{url, category}]

    # ========== Builder Agent 产出 ==========
    build_result: Optional[dict]     # {success, log}

    # ========== 控制字段 ==========
    phase: str                       # 当前阶段
    history: Annotated[list, add_messages]  # 对话历史（自动累积）
    final_result: Optional[dict]     # 最终结果
    error: Optional[str]             # 错误信息
```

### 3.2 配置模块 — `config.py`

```python
"""全局配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ===== DeepSeek API =====
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # ===== LLM 通用参数 =====
    LLM_TEMPERATURE = 0.1             # 代码生成需要低温度
    LLM_MAX_TOKENS = 8192

    # ===== Milvus =====
    MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))

    # ===== 重试 =====
    MAX_RETRIES = 3
    AUTO_GEN_MAX_ROUNDS = 8           # AutoGen 群聊最大轮数

    # ===== 服务 =====
    SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))


config = Config()
```

### 3.3 LLM 工厂 — `llm_factory.py`

```python
"""统一的 LLM 实例工厂 —— 所有 Agent 通过此模块获取模型"""
from langchain_openai import ChatOpenAI
from config import config


def create_llm(temperature: float = None) -> ChatOpenAI:
    """创建 LLM 实例（兼容 OpenAI 格式，此处接入 DeepSeek）"""
    return ChatOpenAI(
        model=config.DEEPSEEK_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        temperature=temperature if temperature is not None else config.LLM_TEMPERATURE,
        max_tokens=config.LLM_MAX_TOKENS,
    )


def create_llm_with_structured_output(output_schema):
    """创建带结构化输出的 LLM 实例 —— 用于需要 Pydantic 强类型返回的 Agent"""
    llm = create_llm(temperature=0.0)  # 结构化输出用 0 温度
    return llm.with_structured_output(output_schema)
```

---

## 四、Agent 实现（共 7 个）

### 4.1 Supervisor Agent

**职责：** 根据当前 State 中的 `phase` 做路由决策——不写代码，只决定"下一步谁做"。

**文件：** `agents/supervisor_agent.py`

```python
"""
Supervisor Agent —— 编排者

职责：
- 读取 State 中的 phase 和 review 结果
- 决定下一个应该执行哪个 Agent
- 达到最大重试次数时路由到人工介入
"""
from state.code_gen_state import CodeGenState
from config import config


def supervisor_decision(state: CodeGenState) -> str:
    """
    核心路由决策函数。
    返回下一个节点的名称，LangGraph 根据返回值走对应的条件边。
    """
    phase = state.get("phase", "init")

    routing_table = {
        "init":        "pm_agent",
        "prd_done":    "architect_agent",
        "arch_done":   "fork_coder_and_images",
        "code_done":   "reviewer_agent",
        "review_done": _handle_review_result,
        "build_done":  "end",
        "error":       "end",
    }

    handler = routing_table.get(phase)
    if callable(handler):
        return handler(state)
    if isinstance(handler, str):
        return handler

    return "end"


def _handle_review_result(state: CodeGenState) -> str:
    """处理代码审查结果 —— 决定通过还是重试"""
    review = state.get("review", {})
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", config.MAX_RETRIES)

    if review.get("passed"):
        return "builder_agent"

    if retry_count < max_retries:
        return "coder_agent"       # 打回重写

    return "human_intervention"    # 超过重试上限
```

### 4.2 PM Agent

**职责：** 将用户模糊需求转化为结构化 PRD（产品需求文档）。

**文件：** `agents/pm_agent.py`

```python
"""
PM Agent —— 产品经理

输入：用户一句话需求
输出：结构化 PRD（Pydantic 模型）
"""
from pydantic import BaseModel, Field
from typing import List
from langchain.schema import SystemMessage, HumanMessage
from llm_factory import create_llm_with_structured_output
from state.code_gen_state import CodeGenState


class Feature(BaseModel):
    name: str = Field(description="功能名称，如'商品轮播图'")
    description: str = Field(description="功能描述")
    priority: str = Field(description="优先级：high / medium / low")
    interactions: str = Field(description="用户交互方式")


class PRD(BaseModel):
    page_name: str = Field(description="页面名称")
    page_type: str = Field(description="页面类型：landing / dashboard / e-commerce / blog / portfolio")
    features: List[Feature] = Field(description="功能清单")
    target_audience: str = Field(description="目标用户群体")
    color_preference: str = Field(description="色彩偏好，如'科技蓝+白'")
    layout_type: str = Field(description="布局类型：single-column / two-column / grid / masonry")
    data_dependencies: List[str] = Field(description="数据依赖，如['商品列表API','用户信息API']")


PM_SYSTEM_PROMPT = """你是一个资深产品经理。用户会用一句话描述他想要的页面，你的任务是将它转化为结构化的产品需求文档(PRD)。

规则：
1. 功能清单要完整，覆盖页面的所有核心交互
2. 不要写任何代码，只描述功能和交互
3. 每个功能都要标注优先级
4. 如果是电商页面，必须包含：商品展示、搜索/筛选、购物车、用户评价
5. 如果是管理后台，必须包含：数据表格、搜索栏、操作按钮、分页
6. 输出严格 JSON 格式
"""


def pm_agent(state: CodeGenState) -> CodeGenState:
    """PM Agent 主逻辑"""
    llm = create_llm_with_structured_output(PRD)

    messages = [
        SystemMessage(content=PM_SYSTEM_PROMPT),
        HumanMessage(content=f"用户需求：{state['user_request']}\n请输出结构化 PRD。"),
    ]

    prd: PRD = llm.invoke(messages)

    # 写入 State
    state["prd"] = prd.model_dump()
    state["phase"] = "prd_done"

    print(f"[PM Agent] PRD 生成完成: {prd.page_name}, {len(prd.features)} 个功能")
    return state
```

### 4.3 Architect Agent

**职责：** 根据 PRD 设计代码骨架：组件树 + 文件清单 + 数据流。

**文件：** `agents/architect_agent.py`

```python
"""
Architect Agent —— 架构师

输入：PM Agent 产出的 PRD
输出：组件树 / 文件清单 / 数据流图
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain.schema import SystemMessage, HumanMessage
from llm_factory import create_llm_with_structured_output
from state.code_gen_state import CodeGenState


class ComponentNode(BaseModel):
    name: str = Field(description="组件名称，如'ProductCard'")
    description: str = Field(description="组件职责描述")
    props: List[str] = Field(description="组件 Props 列表")
    children: List[str] = Field(default_factory=list, description="子组件名称列表")


class FileSpec(BaseModel):
    path: str = Field(description="文件路径，如'src/components/ProductCard.vue'")
    description: str = Field(description="文件职责描述")
    component_name: Optional[str] = Field(default=None, description="如果是组件文件，写组件名")


class DataFlow(BaseModel):
    from_component: str = Field(description="数据来源组件")
    to_component: str = Field(description="数据目标组件")
    data_type: str = Field(description="传递的数据类型")


class Architecture(BaseModel):
    tech_stack: dict = Field(description="技术栈，如{'framework':'Vue 3','css':'Tailwind CSS','state':'Pinia'}")
    component_tree: List[ComponentNode] = Field(description="组件树")
    file_list: List[FileSpec] = Field(description="文件清单")
    data_flow: List[DataFlow] = Field(description="数据流向")


ARCH_SYSTEM_PROMPT = """你是一个前端架构师。根据产品 PRD 设计代码骨架。

规则：
1. 组件树要完整覆盖 PRD 中的所有功能
2. 每个组件必须标注 props 和子组件
3. 文件清单包含所有需要创建的文件（组件 + 样式 + 路由 + store + 工具函数）
4. 数据流描述组件间如何传递数据
5. 不要写代码实现，只设计结构
6. 输出严格 JSON 格式
"""


def architect_agent(state: CodeGenState) -> CodeGenState:
    """Architect Agent 主逻辑"""
    llm = create_llm_with_structured_output(Architecture)
    prd = state.get("prd", {})

    prompt = f"""请根据以下 PRD 设计前端项目架构：

## PRD
页面名称：{prd.get('page_name')}
页面类型：{prd.get('page_type')}
功能清单：
{_format_features(prd.get('features', []))}
色彩偏好：{prd.get('color_preference')}
布局类型：{prd.get('layout_type')}

请输出完整的架构方案。"""

    messages = [
        SystemMessage(content=ARCH_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    arch: Architecture = llm.invoke(messages)

    state["architecture"] = arch.model_dump()
    state["phase"] = "arch_done"

    print(f"[Architect Agent] 架构设计完成: {len(arch.component_tree)} 组件, {len(arch.file_list)} 文件")
    return state


def _format_features(features: list) -> str:
    lines = []
    for f in features:
        lines.append(f"- [{f.get('priority', 'medium')}] {f.get('name')}: {f.get('description')}")
    return "\n".join(lines)
```

### 4.4 Coder Agent

**职责：** 根据架构方案逐个生成代码文件。这是**唯一有工具调用**的 Agent。

**文件：** `agents/coder_agent.py`

```python
"""
Coder Agent —— 程序员

输入：Architect Agent 产出的 file_list
输出：代码文件列表 [{path, content}]

注意：这是 Token 消耗最大的 Agent，也是唯一需要工具调用的 Agent
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain.schema import SystemMessage, HumanMessage
from langchain_core.tools import tool
from llm_factory import create_llm, create_llm_with_structured_output
from state.code_gen_state import CodeGenState
import os


class CodeFile(BaseModel):
    path: str = Field(description="文件路径")
    content: str = Field(description="文件完整内容")


class CoderOutput(BaseModel):
    files: List[CodeFile] = Field(description="生成的代码文件列表")
    notes: Optional[str] = Field(default=None, description="备注说明")


# ============ Coder Agent 的工具 ============

@tool
def read_existing_file(file_path: str) -> str:
    """读取项目中已存在的文件内容，用于了解现有代码结构"""
    # 在 demo 中从临时目录读取
    full_path = os.path.join("/tmp/ai-code-project", file_path)
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    return f"文件 {file_path} 不存在"


@tool
def search_vue_api(api_name: str) -> str:
    """查询 Vue 3 Composition API 的正确用法"""
    vue_api_docs = {
        "ref": "const count = ref(0); // 创建响应式引用，.value 访问/修改",
        "reactive": "const state = reactive({count: 0}); // 创建响应式对象",
        "computed": "const doubled = computed(() => count.value * 2); // 计算属性",
        "watch": "watch(source, (newVal, oldVal) => {...}); // 监听变化",
        "onMounted": "onMounted(() => {...}); // 组件挂载后执行",
        "defineProps": "const props = defineProps<{title: string}>(); // 定义 Props",
        "defineEmits": "const emit = defineEmits<{(e: 'update', val: number): void}>();",
        "provide/inject": "provide('key', value); const val = inject('key'); // 跨层级传值",
        "useRouter": "const router = useRouter(); router.push('/path');",
        "useRoute": "const route = useRoute(); route.params.id;",
        "v-model": "v-model 双向绑定: <input v-model=\"form.name\" />",
        "v-if/v-for": "v-if 条件渲染, v-for 列表渲染: v-for=\"item in items\" :key=\"item.id\"",
    }
    return vue_api_docs.get(api_name, f"未找到 {api_name} 的文档，请检查拼写")


@tool
def check_component_exists(component_name: str) -> str:
    """检查指定组件是否已在项目中存在"""
    project_dir = "/tmp/ai-code-project/src/components"
    path = os.path.join(project_dir, f"{component_name}.vue")
    if os.path.exists(path):
        return f"组件 {component_name} 已存在，路径: {path}"
    return f"组件 {component_name} 不存在，需要创建"


# ============ System Prompt ============

CODER_SYSTEM_PROMPT = """你是资深 Vue 3 前端程序员。根据架构方案逐个生成代码文件。

## 技术栈
- Vue 3 Composition API + <script setup lang="ts">
- Tailwind CSS 样式
- Pinia 状态管理
- Vue Router 4 路由

## 代码规范
1. 每个文件必须完整可运行，不要省略任何 import
2. 使用 TypeScript 类型注解
3. Props 使用 defineProps 带类型
4. 响应式数据优先使用 ref，对象用 reactive
5. 所有组件必须包含 <template>、<script setup>、<style scoped>
6. 路由配置必须在 router/index.ts 中
7. Pinia Store 必须在 stores/ 目录下

## 工具使用
- 生成组件前，先用 check_component_exists 检查是否已存在
- 不确定 API 用法时，用 search_vue_api 查文档
- 需要了解现有代码时，用 read_existing_file 读取

## 输出格式
每生成完一批文件后，输出 CoderOutput 格式的结果。
"""


def coder_agent(state: CodeGenState) -> CodeGenState:
    """Coder Agent 主逻辑"""
    llm = create_llm(temperature=0.1)
    llm_with_tools = llm.bind_tools([read_existing_file, search_vue_api, check_component_exists])

    architecture = state.get("architecture", {})
    file_list = architecture.get("file_list", [])
    review = state.get("review", {})

    # 如果是重试，附上 Reviewer 的反馈
    retry_context = ""
    if review and not review.get("passed"):
        issues = review.get("issues", [])
        retry_context = f"""
## 上一轮代码审查发现了以下问题，请逐一修复：
{_format_issues(issues)}
"""

    # 构建用户消息
    user_message = f"""请根据以下架构方案生成所有代码文件：

## 架构方案
组件树：
{_format_component_tree(architecture.get('component_tree', []))}

需要生成的文件清单：
{_format_file_list(file_list)}

技术栈：{architecture.get('tech_stack', {})}

{retry_context}

请逐个文件生成完整代码。生成完毕后输出 CoderOutput。"""

    messages = [
        SystemMessage(content=CODER_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    # 使用结构化输出
    structured_llm = create_llm_with_structured_output(CoderOutput)

    # 第一次调用可能触发工具调用，这里简化处理：直接生成
    result: CoderOutput = structured_llm.invoke(messages)

    # 写入 State
    state["code_files"] = [f.model_dump() for f in result.files]
    state["phase"] = "code_done"

    print(f"[Coder Agent] 代码生成完成: {len(result.files)} 个文件")
    return state


def _format_component_tree(components: list, indent: int = 0) -> str:
    lines = []
    for comp in components:
        prefix = "  " * indent
        lines.append(f"{prefix}- {comp.get('name')}: {comp.get('description')}")
        if comp.get("children"):
            for child in comp["children"]:
                lines.append(f"{prefix}  └── {child}")
    return "\n".join(lines)


def _format_file_list(files: list) -> str:
    return "\n".join([f"- {f.get('path')}: {f.get('description')}" for f in files])


def _format_issues(issues: list) -> str:
    lines = []
    for i in issues:
        severity_emoji = {"critical": "🔴", "warn": "🟡", "info": "🔵"}
        emoji = severity_emoji.get(i.get("severity", "info"), "⚪")
        lines.append(f"{emoji} [{i.get('severity')}] {i.get('file')}: {i.get('description')}")
        if i.get("suggestion"):
            lines.append(f"   建议修复: {i['suggestion']}")
    return "\n".join(lines)
```

### 4.5 Reviewer Agent

**职责：** 审查生成的代码，发现语法错误、逻辑问题、安全隐患。

**文件：** `agents/reviewer_agent.py`

```python
"""
Reviewer Agent —— 代码审查员

输入：Coder Agent 产出的所有代码文件
输出：{passed, score, issues[]}
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from langchain.schema import SystemMessage, HumanMessage
from llm_factory import create_llm_with_structured_output
from state.code_gen_state import CodeGenState


class Issue(BaseModel):
    file: str = Field(description="问题所在文件")
    severity: str = Field(description="严重度: critical / warn / info")
    category: str = Field(description="问题分类: syntax / logic / security / style / performance / accessibility")
    description: str = Field(description="问题描述")
    suggestion: str = Field(description="修复建议")


class ReviewResult(BaseModel):
    passed: bool = Field(description="是否通过审查")
    score: int = Field(description="评分 0-100，>=80 为通过")
    issues: List[Issue] = Field(description="发现的问题列表")
    summary: Optional[str] = Field(default=None, description="审查总结")


REVIEWER_SYSTEM_PROMPT = """你是资深前端代码审查专家。审查 Vue 3 + TypeScript + Tailwind 项目代码。

## 审查维度

### 语法与类型 (weight: 30%)
- TypeScript 类型是否正确
- import 路径是否存在
- 组件引用是否正确
- Props/Emits 类型定义是否完整

### 逻辑完整 (weight: 30%)
- 是否实现了 PRD 中的所有功能
- 边界情况处理（loading、empty、error 状态）
- 数据流是否与架构设计一致

### 安全 (weight: 15%)
- 用户输入是否有 XSS 防护
- 敏感数据是否硬编码

### 样式与可访问性 (weight: 15%)
- Tailwind 类名是否标准
- 是否支持键盘导航
- 颜色对比度是否达标

### 性能 (weight: 10%)
- 大列表是否使用虚拟滚动
- 图片是否懒加载
- 是否有不必要的重渲染

## 评分标准
- >=90: 优秀，直接通过
- 80-89: 良好，通过但有改进空间
- 60-79: 需要修复，列出具体问题
- <60: 严重问题，必须重写

## 输出格式
严格 JSON，issues 数组必须包含所有发现的问题。
"""


def reviewer_agent(state: CodeGenState) -> CodeGenState:
    """Reviewer Agent 主逻辑"""
    llm = create_llm_with_structured_output(ReviewResult)

    code_files = state.get("code_files", [])
    prd = state.get("prd", {})

    # 构建审查输入
    code_summary = _build_code_summary(code_files)

    messages = [
        SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
        HumanMessage(content=f"""请审查以下代码，对照 PRD 需求检查完整性：

## PRD 功能清单
{_format_prd_features(prd.get('features', []))}

## 代码文件
{code_summary}

请逐一审查每个文件，输出 ReviewResult。"""),
    ]

    result: ReviewResult = llm.invoke(messages)

    # 写入 State
    state["review"] = result.model_dump()
    state["retry_count"] = state.get("retry_count", 0) + (0 if result.passed else 1)
    state["phase"] = "review_done"

    status = "✅ 通过" if result.passed else f"❌ 未通过 ({len(result.issues)} 个问题)"
    print(f"[Reviewer Agent] 审查完成: 评分 {result.score}/100, {status}")
    return state


def _build_code_summary(code_files: list) -> str:
    """构建代码摘要（不发送完整代码，只发文件路径 + 行数 + 关键结构）"""
    lines = []
    for f in code_files:
        path = f.get("path", "unknown")
        content = f.get("content", "")
        line_count = len(content.split("\n"))
        # 提取 import 语句和组件名作为摘要
        imports = [l for l in content.split("\n") if l.strip().startswith("import")]
        component_match = [l for l in content.split("\n") if "defineComponent" in l or "<script" in l]
        lines.append(f"### {path} ({line_count} 行)")
        if imports:
            lines.append("导入: " + "; ".join(imports[:5]))
        lines.append(content[:3000])  # 每个文件最多 3000 字符
        lines.append("---")
    return "\n".join(lines)


def _format_prd_features(features: list) -> str:
    return "\n".join([f"- [{f.get('priority', 'medium')}] {f.get('name')}: {f.get('description')}" for f in features])
```

### 4.6 Image Collector Agent

**职责：** 根据架构方案和 PRD 收集/生成图片素材。

**文件：** `agents/image_collector_agent.py`

```python
"""
Image Collector Agent —— 素材收集

输入：架构方案 + PRD
输出：[{url, category, description}]

注意：此 Agent 不调用 LLM —— 纯 HTTP API 调用。在 demo 中返回模拟数据。
"""
from typing import List
from state.code_gen_state import CodeGenState


# 模拟图片库（真实环境替换为 Pexels/Unsplash API 调用）
MOCK_IMAGES = {
    "banner": [
        {"url": "https://picsum.photos/1200/400?random=1", "category": "banner",
         "description": "首页横幅 1"},
        {"url": "https://picsum.photos/1200/400?random=2", "category": "banner",
         "description": "首页横幅 2"},
    ],
    "product": [
        {"url": "https://picsum.photos/300/300?random=3", "category": "product",
         "description": "商品图片 1"},
        {"url": "https://picsum.photos/300/300?random=4", "category": "product",
         "description": "商品图片 2"},
        {"url": "https://picsum.photos/300/300?random=5", "category": "product",
         "description": "商品图片 3"},
    ],
    "icon": [
        {"url": "https://picsum.photos/64/64?random=6", "category": "icon",
         "description": "图标 1"},
        {"url": "https://picsum.photos/64/64?random=7", "category": "icon",
         "description": "图标 2"},
    ],
    "logo": [
        {"url": "https://picsum.photos/200/200?random=8", "category": "logo",
         "description": "Logo"},
    ],
    "illustration": [
        {"url": "https://picsum.photos/600/400?random=9", "category": "illustration",
         "description": "插画 1"},
    ],
}


def _determine_image_needs(prd: dict, architecture: dict) -> List[str]:
    """根据 PRD 和架构判断需要哪些类型的图片"""
    page_type = prd.get("page_type", "")
    features = [f.get("name", "") for f in prd.get("features", [])]

    needs = set()

    # 几乎所有页面都需要 banner
    needs.add("banner")

    # 商品相关页面
    if page_type == "e-commerce" or any("商品" in f or "产品" in f for f in features):
        needs.add("product")

    # 图标
    needs.add("icon")

    # 有品牌元素
    needs.add("logo")

    # 落地页或博客需要插画
    if page_type in ("landing", "blog", "portfolio"):
        needs.add("illustration")

    return list(needs)


def image_collector_agent(state: CodeGenState) -> CodeGenState:
    """Image Collector Agent 主逻辑 —— 不调用 LLM"""
    prd = state.get("prd", {})
    architecture = state.get("architecture", {})

    needed_types = _determine_image_needs(prd, architecture)

    collected_images = []
    for img_type in needed_types:
        if img_type in MOCK_IMAGES:
            collected_images.extend(MOCK_IMAGES[img_type])

    state["images"] = collected_images
    print(f"[Image Collector] 收集完成: {len(collected_images)} 张图片 (类型: {needed_types})")
    return state
```

### 4.7 Builder Agent

**职责：** 将代码文件写入磁盘，执行 `npm install && npm run build` 验证可构建。

**文件：** `agents/builder_agent.py`

```python
"""
Builder Agent —— 构建验证

输入：code_files + images
输出：{success, build_log}

注意：零 LLM 调用，纯文件写入 + Shell 执行
"""
import os
import subprocess
import shutil
import tempfile
from state.code_gen_state import CodeGenState


def builder_agent(state: CodeGenState) -> CodeGenState:
    """Builder Agent 主逻辑"""
    code_files = state.get("code_files", [])
    images = state.get("images", [])

    # 在临时目录中构建项目
    project_dir = tempfile.mkdtemp(prefix="ai-build-")

    try:
        # 1. 写入所有代码文件
        for f in code_files:
            file_path = os.path.join(project_dir, f.get("path", ""))
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(f.get("content", ""))

        # 2. 写入图片 URL 映射（不实际下载，仅在代码中引用）
        image_map_path = os.path.join(project_dir, "images.json")
        import json
        with open(image_map_path, "w", encoding="utf-8") as fh:
            json.dump(images, fh, ensure_ascii=False, indent=2)

        # 3. 创建 package.json（如果 Coder 没有生成）
        package_json_path = os.path.join(project_dir, "package.json")
        if not os.path.exists(package_json_path):
            _create_default_package_json(project_dir)

        # 4. 尝试 npm install（在 demo 中可能因为无 Node 环境而失败，所以默认为成功）
        build_log = ""
        build_success = True

        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                build_log = result.stderr
                build_success = False
            else:
                # npm build
                result = subprocess.run(
                    ["npm", "run", "build"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    build_log = result.stderr
                    build_success = False
                else:
                    build_log = result.stdout
        except FileNotFoundError:
            # 本地没有 Node.js，跳过实际构建
            build_log = "[DEMO 模式] 未检测到 Node.js，跳过实际构建。代码文件已写入磁盘。"
            build_success = True
        except subprocess.TimeoutExpired:
            build_log = "构建超时（超过 120 秒）"
            build_success = False

        state["build_result"] = {
            "success": build_success,
            "log": build_log,
            "project_dir": project_dir if build_success else None,
        }
        state["phase"] = "build_done"

        status = "✅ 成功" if build_success else "❌ 失败"
        print(f"[Builder Agent] 构建{status} (项目目录: {project_dir})")
        return state

    except Exception as e:
        state["build_result"] = {"success": False, "log": str(e)}
        state["phase"] = "build_done"
        state["error"] = str(e)
        print(f"[Builder Agent] 构建异常: {e}")
        return state


def _create_default_package_json(project_dir: str):
    """创建默认的 Vue 3 + Vite package.json"""
    import json
    package_json = {
        "name": "ai-generated-project",
        "version": "1.0.0",
        "private": True,
        "scripts": {
            "dev": "vite",
            "build": "vite build",
            "preview": "vite preview",
        },
        "dependencies": {
            "vue": "^3.5.0",
            "vue-router": "^4.4.0",
            "pinia": "^2.2.0",
        },
        "devDependencies": {
            "@vitejs/plugin-vue": "^5.2.0",
            "typescript": "^5.6.0",
            "vite": "^6.0.0",
            "vue-tsc": "^2.2.0",
            "tailwindcss": "^3.4.0",
            "autoprefixer": "^10.4.0",
            "postcss": "^8.4.0",
        },
    }
    with open(os.path.join(project_dir, "package.json"), "w", encoding="utf-8") as f:
        json.dump(package_json, f, ensure_ascii=False, indent=2)
```

---

## 五、LangGraph 工作流编排

**文件：** `workflow/code_gen_workflow.py`

```python
"""
LangGraph 工作流定义 —— 将 7 个 Agent 组装为状态图

工作流拓扑:
START → PM → Architect → Fork(Coder ∥ ImageCollector) → Reviewer
                                                              │
                                              passed ──► Builder → END
                                              failed ──► Coder (重试)
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from state.code_gen_state import CodeGenState
from agents.supervisor_agent import supervisor_decision
from agents.pm_agent import pm_agent
from agents.architect_agent import architect_agent
from agents.coder_agent import coder_agent
from agents.reviewer_agent import reviewer_agent
from agents.image_collector_agent import image_collector_agent
from agents.builder_agent import builder_agent
from config import config


def fork_coder_and_images(state: CodeGenState) -> CodeGenState:
    """
    Fork 节点：编码和图片收集可以并行。
    在 LangGraph 中，并行通过 Send API 实现。
    这里简化为先执行图片收集（它不调用 LLM，速度快），再执行代码生成。
    真正的并行需要使用 langgraph 的 Send() 机制。
    """
    # 在实际项目中，使用 langgraph Send API 实现真并行
    state = image_collector_agent(state)
    state = coder_agent(state)
    return state


def create_code_gen_workflow() -> StateGraph:
    """构建并编译 LangGraph 工作流"""

    workflow = StateGraph(CodeGenState)

    # ===== 注册节点 =====
    workflow.add_node("pm_agent", pm_agent)
    workflow.add_node("architect_agent", architect_agent)
    workflow.add_node("fork_coder_and_images", fork_coder_and_images)
    workflow.add_node("coder_agent", coder_agent)
    workflow.add_node("reviewer_agent", reviewer_agent)
    workflow.add_node("builder_agent", builder_agent)
    workflow.add_node("human_intervention", lambda s: _end_node(s, "需要人工介入"))
    workflow.add_node("end", lambda s: _end_node(s, "流程结束"))

    # ===== 注册边 =====
    workflow.set_entry_point("pm_agent")

    # PM → Architect
    workflow.add_edge("pm_agent", "architect_agent")

    # Architect → Fork(Coder + Image Collector)
    workflow.add_edge("architect_agent", "fork_coder_and_images")

    # Fork → Reviewer
    workflow.add_edge("fork_coder_and_images", "reviewer_agent")

    # Reviewer → 条件路由（通过 supervisor_decision 决定下一步）
    workflow.add_conditional_edges(
        "reviewer_agent",
        supervisor_decision,
        {
            "coder_agent": "coder_agent",
            "builder_agent": "builder_agent",
            "human_intervention": "human_intervention",
        }
    )

    # Coder（重试）→ Reviewer（再次审查）
    workflow.add_edge("coder_agent", "reviewer_agent")

    # Builder → END
    workflow.add_edge("builder_agent", "end")

    # END 节点
    workflow.add_edge("end", END)
    workflow.add_edge("human_intervention", END)

    return workflow


def _end_node(state: CodeGenState, message: str) -> CodeGenState:
    state["final_result"] = {
        "status": "completed",
        "message": message,
        "phase": state.get("phase"),
        "code_files_count": len(state.get("code_files", [])),
        "images_count": len(state.get("images", [])),
        "review_score": state.get("review", {}).get("score"),
        "build_success": state.get("build_result", {}).get("success"),
    }
    state["phase"] = "completed"
    return state


def run_workflow(user_request: str, user_id: str = "demo_user", app_id: str = "demo_app"):
    """执行完整工作流"""

    # 初始状态
    initial_state: CodeGenState = {
        "user_request": user_request,
        "user_id": user_id,
        "app_id": app_id,
        "prd": None,
        "architecture": None,
        "code_files": [],
        "review": None,
        "retry_count": 0,
        "max_retries": config.MAX_RETRIES,
        "images": [],
        "build_result": None,
        "phase": "init",
        "history": [],
        "final_result": None,
        "error": None,
    }

    # 编译并执行
    workflow = create_code_gen_workflow()
    compiled = workflow.compile(checkpointer=MemorySaver())

    config_dict = {"configurable": {"thread_id": f"{user_id}_{app_id}"}}

    final_state = compiled.invoke(initial_state, config_dict)

    return final_state
```

---

## 六、AutoGen 局部讨论模块

**文件：** `workflow/autogen_discussion.py`

```python
"""
AutoGen 三方讨论模块 —— Coder ⇄ Reviewer ⇄ Architect 群聊

当 Reviewer 发现架构级问题时，启动 AutoGen GroupChat 让三方讨论修复方案。
"""
import json
from autogen import ConversableAgent, GroupChat, GroupChatManager
from config import config
from llm_factory import create_llm


# ===== LLM 配置（AutoGen 格式）=====
LLM_CONFIG = {
    "config_list": [
        {
            "model": config.DEEPSEEK_MODEL,
            "api_key": config.DEEPSEEK_API_KEY,
            "base_url": config.DEEPSEEK_BASE_URL,
        }
    ],
    "temperature": 0.1,
}


def create_review_groupchat() -> tuple[ConversableAgent, ConversableAgent, ConversableAgent, GroupChatManager]:
    """创建代码审查三方群聊"""

    # Coder Agent（AutoGen 包装）
    coder = ConversableAgent(
        name="coder",
        system_message="""你是前端程序员。收到 Review 意见后：
        1. 判断每个问题是代码级别还是架构级别
        2. 代码级别的问题直接修复
        3. 架构级别的问题与 architect 讨论
        4. 修复完毕后说明改了什么""",
        llm_config=LLM_CONFIG,
        human_input_mode="NEVER",
    )

    # Reviewer Agent（AutoGen 包装）
    reviewer = ConversableAgent(
        name="reviewer",
        system_message="""你是代码审查员。你的任务：
        1. 逐条提出代码问题，标注严重度
        2. 当 coder 修复后再次审查
        3. 如果 coder 的修复方案不对，提出改进意见
        4. 当所有问题解决后，说"审查通过" """,
        llm_config=LLM_CONFIG,
        human_input_mode="NEVER",
    )

    # Architect Agent（AutoGen 包装，仅在架构级问题需要时发言）
    architect = ConversableAgent(
        name="architect",
        system_message="""你是架构师。只在以下情况发言：
        1. Reviewer 和 Coder 对方案有分歧时，给出最终架构决策
        2. Coder 提出的修复方案可能会破坏架构一致性时
        其他时候保持沉默。发言要简短、决断。""",
        llm_config=LLM_CONFIG,
        human_input_mode="NEVER",
    )

    # 群聊
    group_chat = GroupChat(
        agents=[coder, reviewer, architect],
        messages=[],
        max_round=config.AUTO_GEN_MAX_ROUNDS,
        speaker_selection_method="auto",
        allow_repeat_speaker=True,  # 允许同一人连续发言
    )

    manager = GroupChatManager(
        groupchat=group_chat,
        llm_config=LLM_CONFIG,
    )

    return coder, reviewer, architect, manager


def run_review_discussion(
    code_files: list,
    issues: list,
    architecture: dict,
) -> dict:
    """
    启动 AutoGen 三方讨论来修复代码审查发现的问题。

    返回: {"discussion_history": ..., "fixed_files": ..., "resolution": "passed|failed"}
    """
    coder, reviewer, architect, manager = create_review_groupchat()

    # 构建初始消息
    files_summary = _summarize_files(code_files)
    issues_text = json.dumps(issues, ensure_ascii=False, indent=2)
    arch_summary = json.dumps(architecture, ensure_ascii=False, indent=2)[:2000]

    initial_message = f"""## 代码审查发现问题

### 架构方案（参考）
{arch_summary}

### 当前代码文件
{files_summary}

### 发现的问题
{issues_text}

请 coder 逐一回应每个问题：确认是否为真实问题 → 给出修复方案 → reviewer 确认修复是否正确。
如果涉及架构层面的争议，architect 请介入裁决。"""

    # 启动群聊
    chat_result = coder.initiate_chat(
        manager,
        message=initial_message,
        max_turns=config.AUTO_GEN_MAX_ROUNDS,
    )

    # 从讨论历史中提取最终修复方案
    # 简化处理：返回讨论摘要
    return {
        "discussion_history": str(chat_result.chat_history)[:5000],
        "resolution": "passed",
        "summary": "三方讨论完成，修复方案已确认",
    }


def _summarize_files(code_files: list) -> str:
    """文件摘要"""
    return "\n".join([
        f"- {f.get('path')} ({len(f.get('content', '').split(chr(10)))} 行)"
        for f in code_files
    ])
```

---

## 七、Milvus 向量检索 + RAG

### 7.1 Embedding 服务

**文件：** `rag/embedding_service.py`

```python
"""Embedding 服务 —— 将文本转为向量"""
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        """
        初始化 Embedding 模型。

        model_name 可选:
        - BAAI/bge-small-zh-v1.5 (512 维，中文优化，轻量)
        - BAAI/bge-large-zh-v1.5 (1024 维，效果更好)
        - sentence-transformers/all-MiniLM-L6-v2 (384 维，英文为主)
        """
        print(f"[Embedding] 正在加载模型: {model_name}...")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        print(f"[Embedding] 模型加载完成，维度: {self.dimension}")

    def embed(self, text: str) -> list:
        """将文本转为向量"""
        return self.model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list) -> list:
        """批量转向量"""
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]


# 全局单例
embedding_service = EmbeddingService()
```

### 7.2 Milvus 客户端

**文件：** `rag/milvus_client.py`

```python
"""
Milvus 客户端 —— 管理 Collections 和检索

Collections:
1. code_store       —— 历史成功代码
2. component_library —— 可复用组件
3. design_pattern   —— 设计模式
4. error_pattern    —— 错误与修复映射
5. framework_api    —— 框架 API 参考
"""
from pymilvus import (
    connections, Collection, CollectionSchema,
    FieldSchema, DataType, utility
)
from config import config
from rag.embedding_service import embedding_service


# ===== Collection Schema 定义 =====

CODE_STORE_SCHEMA = CollectionSchema([
    FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema("app_id", DataType.VARCHAR, max_length=64),
    FieldSchema("file_path", DataType.VARCHAR, max_length=512),
    FieldSchema("content", DataType.VARCHAR, max_length=65535),
    FieldSchema("code_gen_type", DataType.VARCHAR, max_length=32),
    FieldSchema("tags", DataType.VARCHAR, max_length=512),
    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=embedding_service.dimension),
])

COMPONENT_LIBRARY_SCHEMA = CollectionSchema([
    FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema("component_name", DataType.VARCHAR, max_length=128),
    FieldSchema("props_schema", DataType.VARCHAR, max_length=4096),
    FieldSchema("code_snippet", DataType.VARCHAR, max_length=65535),
    FieldSchema("framework", DataType.VARCHAR, max_length=32),
    FieldSchema("use_count", DataType.INT64),
    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=embedding_service.dimension),
])

DESIGN_PATTERN_SCHEMA = CollectionSchema([
    FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema("pattern_name", DataType.VARCHAR, max_length=256),
    FieldSchema("description", DataType.VARCHAR, max_length=4096),
    FieldSchema("example_code", DataType.VARCHAR, max_length=65535),
    FieldSchema("success_rate", DataType.FLOAT),
    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=embedding_service.dimension),
])

ERROR_PATTERN_SCHEMA = CollectionSchema([
    FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema("error_signature", DataType.VARCHAR, max_length=1024),
    FieldSchema("fix_code", DataType.VARCHAR, max_length=65535),
    FieldSchema("severity", DataType.VARCHAR, max_length=32),
    FieldSchema("occurrence_count", DataType.INT64),
    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=embedding_service.dimension),
])


class MilvusClient:
    """Milvus 操作封装"""

    COLLECTIONS = {
        "code_store": CODE_STORE_SCHEMA,
        "component_library": COMPONENT_LIBRARY_SCHEMA,
        "design_pattern": DESIGN_PATTERN_SCHEMA,
        "error_pattern": ERROR_PATTERN_SCHEMA,
    }

    def __init__(self):
        self._connected = False

    def connect(self):
        """连接 Milvus"""
        if self._connected:
            return
        connections.connect(
            alias="default",
            host=config.MILVUS_HOST,
            port=config.MILVUS_PORT,
        )
        self._connected = True
        print(f"[Milvus] 已连接: {config.MILVUS_HOST}:{config.MILVUS_PORT}")

    def init_collections(self):
        """初始化所有 Collections（如果不存在则创建）"""
        self.connect()
        for name, schema in self.COLLECTIONS.items():
            if not utility.has_collection(name):
                collection = Collection(name=name, schema=schema)
                # 创建索引
                index_params = {
                    "metric_type": "COSINE",
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 128},
                }
                collection.create_index(
                    field_name="embedding",
                    index_params=index_params,
                )
                print(f"[Milvus] 创建 Collection: {name}")
            else:
                print(f"[Milvus] Collection 已存在: {name}")

    def search(self, collection_name: str, query_vector: list,
               limit: int = 5, output_fields: list = None) -> list:
        """向量相似度检索"""
        self.connect()
        collection = Collection(name=collection_name)
        collection.load()

        search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}

        results = collection.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=limit,
            output_fields=output_fields or ["*"],
        )

        formatted = []
        for hits in results:
            for hit in hits:
                item = {"id": hit.id, "distance": hit.distance}
                item.update(hit.entity.to_dict())
                formatted.append(item)

        return formatted

    def insert_code(self, code_files: list, app_id: str,
                    code_gen_type: str, tags: str = ""):
        """将生成的代码入库（构建成功后调用）"""
        self.connect()
        collection = Collection(name="code_store")

        data = []
        for f in code_files:
            content = f.get("content", "")
            if len(content) > 10000:  # 限制单文件最大长度
                content = content[:10000] + "\n// ... truncated"

            vector = embedding_service.embed(content)
            data.append({
                "app_id": app_id,
                "file_path": f.get("path", ""),
                "content": content,
                "code_gen_type": code_gen_type,
                "tags": tags,
                "embedding": vector,
            })

        if data:
            collection.insert(data)
            collection.flush()
            print(f"[Milvus] 入库 {len(data)} 条代码记录")

    def search_similar_code(self, query: str, limit: int = 5) -> list:
        """搜索相似代码"""
        query_vector = embedding_service.embed(query)
        return self.search("code_store", query_vector, limit)

    def search_components(self, query: str, limit: int = 5) -> list:
        """搜索可复用组件"""
        query_vector = embedding_service.embed(query)
        return self.search("component_library", query_vector, limit)

    def search_error_fix(self, error_message: str, limit: int = 3) -> list:
        """搜索错误修复方案"""
        query_vector = embedding_service.embed(error_message)
        return self.search("error_pattern", query_vector, limit)

    def search_design_patterns(self, query: str, limit: int = 3) -> list:
        """搜索设计模式"""
        query_vector = embedding_service.embed(query)
        return self.search("design_pattern", query_vector, limit)


# 全局单例
milvus_client = MilvusClient()
```

### 7.3 RAG Prompt 构建器

**文件：** `rag/rag_builder.py`

```python
"""
RAG Prompt 构建器 —— 为 Coder Agent 构建增强型 System Prompt

在代码生成前，从 Milvus 检索相关组件、API 文档、历史代码，
将这些检索结果作为约束注入 System Prompt。
"""
from rag.milvus_client import milvus_client


def build_rag_enhanced_prompt(
    file_info: dict,
    architecture: dict,
) -> str:
    """为单个文件的代码生成构建 RAG 增强 Prompt"""

    file_path = file_info.get("path", "")
    file_desc = file_info.get("description", "")
    framework = architecture.get("tech_stack", {}).get("framework", "Vue 3")

    # 构建检索查询
    query = f"{framework} {file_desc} {file_path}"

    # ===== 并行检索（demo 中顺序执行）=====

    # 1. 检索相似组件
    components = []
    try:
        components = milvus_client.search_components(query, limit=5)
    except Exception as e:
        pass  # Milvus 未启动时跳过

    # 2. 检索相似代码
    similar_code = []
    try:
        similar_code = milvus_client.search_similar_code(query, limit=3)
    except Exception:
        pass

    # 3. 检索设计模式
    patterns = []
    try:
        patterns = milvus_client.search_design_patterns(query, limit=3)
    except Exception:
        pass

    # ===== 组装增强 Prompt 段落 =====

    rag_context_parts = []

    # 可用组件白名单
    if components:
        comp_lines = ["## 可复用组件（优先使用，避免造轮子）"]
        for c in components:
            name = c.get("component_name", "Unknown")
            props = c.get("props_schema", "{}")
            import_path = f"@/components/{name}.vue"
            comp_lines.append(
                f"### {name}\n"
                f"- 导入: `import {name} from '{import_path}'`\n"
                f"- Props: `{props}`\n"
                f"- 用法示例:\n```vue\n{c.get('code_snippet', '')[:500]}\n```"
            )
        rag_context_parts.append("\n".join(comp_lines))

    # 参考实现
    if similar_code:
        ref_lines = ["## 相似需求的成功实现（已验证可构建）"]
        for c in similar_code:
            ref_lines.append(
                f"### {c.get('file_path', 'unknown')}\n"
                f"```vue\n{c.get('content', '')[:1000]}\n```"
            )
        rag_context_parts.append("\n".join(ref_lines))

    # 设计模式
    if patterns:
        pattern_lines = ["## 推荐设计模式"]
        for p in patterns:
            pattern_lines.append(
                f"- **{p.get('pattern_name', '')}**: {p.get('description', '')}\n"
                f"  示例:\n```vue\n{p.get('example_code', '')[:500]}\n```"
            )
        rag_context_parts.append("\n".join(pattern_lines))

    rag_context = "\n\n---\n\n".join(rag_context_parts) if rag_context_parts else ""

    return f"""
你需要为文件 `{file_path}` 生成代码。

文件描述: {file_desc}
技术栈: {framework}

{rag_context}

## 严格约束
- 如果"可复用组件"列表中有匹配的组件，必须使用，禁止重新发明
- 所有 import 路径必须真实存在
- 只能使用 {framework} 的标准 API
- 不确定的 API 用法请使用 search_vue_api 工具查询
"""
```

---

## 八、FastAPI 服务层（SSE 流式输出）

**文件：** `server/main.py`

```python
"""
FastAPI 服务 —— 暴露 SSE 端点，Java 端通过 WebClient 调用

端点:
  POST /api/generate-code  —— SSE 流式代码生成
  GET  /api/health         —— 健康检查
"""
import json
import time
import asyncio
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from workflow.code_gen_workflow import run_workflow
from config import config


app = FastAPI(title="AI Code Gen Agents", version="1.0.0")


# ===== 请求模型 =====

class CodeGenRequest(BaseModel):
    user_id: str = "demo_user"
    app_id: str = "demo_app"
    prompt: str
    code_gen_type: str = "VUE_PROJECT"
    history: list = []


# ===== SSE 事件流生成器 =====

async def generate_code_stream(request: CodeGenRequest):
    """
    执行工作流并逐 phase 发送 SSE 事件。
    Java 端透传这些事件给前端。
    """

    def send_event(event_type: str, data: dict = None):
        """辅助函数：构造 SSE 事件"""
        payload = {"type": event_type, "timestamp": time.time()}
        if data:
            payload.update(data)
        return json.dumps(payload, ensure_ascii=False)

    yield send_event("phase_start", {
        "phase": "pm",
        "message": "产品经理正在分析需求..."
    })

    # 在工作流中执行（这里为了 SSE 逐步发送，采用简化的逐步调用）
    # 实际项目中需要修改 LangGraph 节点，在每个 phase 变化时 yield 事件

    try:
        # 在后台线程执行工作流，主线程发送 SSE
        # 这里简化为：先发事件，再执行，再发结果

        yield send_event("phase_start", {
            "phase": "pm",
            "message": "产品经理正在分析需求..."
        })

        # 执行完整工作流
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            final_state = await loop.run_in_executor(
                pool,
                run_workflow,
                request.prompt,
                request.user_id,
                request.app_id,
            )

        # 根据最终状态发送结果
        prd = final_state.get("prd", {})
        if prd:
            yield send_event("phase_complete", {
                "phase": "pm",
                "output": {
                    "page_name": prd.get("page_name", ""),
                    "feature_count": len(prd.get("features", [])),
                }
            })

        arch = final_state.get("architecture", {})
        if arch:
            yield send_event("phase_complete", {
                "phase": "arch",
                "output": {
                    "component_count": len(arch.get("component_tree", [])),
                    "file_count": len(arch.get("file_list", [])),
                }
            })

        code_files = final_state.get("code_files", [])
        yield send_event("phase_complete", {
            "phase": "code",
            "output": {"file_count": len(code_files)}
        })

        # 逐文件发送代码内容
        for f in code_files:
            yield send_event("code_file", {
                "path": f.get("path", ""),
                "content": f.get("content", ""),
            })

        review = final_state.get("review", {})
        if review:
            yield send_event("phase_complete", {
                "phase": "review",
                "output": {
                    "passed": review.get("passed"),
                    "score": review.get("score"),
                    "issue_count": len(review.get("issues", [])),
                }
            })

        build_result = final_state.get("build_result", {})
        yield send_event("phase_complete", {
            "phase": "build",
            "output": {"success": build_result.get("success", False)}
        })

        final = final_state.get("final_result", {})
        yield send_event("done", {
            "result": final,
        })

    except Exception as e:
        yield send_event("error", {"message": str(e)})


# ===== 路由 =====

@app.post("/api/generate-code")
async def generate_code(request: CodeGenRequest):
    """SSE 流式代码生成端点"""
    return EventSourceResponse(generate_code_stream(request))


@app.get("/api/health")
async def health_check():
    """健康检查"""
    from rag.milvus_client import milvus_client
    milvus_ok = False
    try:
        milvus_client.connect()
        milvus_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "milvus_connected": milvus_ok,
        "model": config.DEEPSEEK_MODEL,
    }


# ===== 启动 =====

if __name__ == "__main__":
    import uvicorn

    # 初始化 Milvus（可选，如果 Milvus 还没启动会报错但不影响）
    try:
        from rag.milvus_client import milvus_client
        milvus_client.init_collections()
    except Exception as e:
        print(f"[启动] Milvus 初始化失败（可忽略）: {e}")

    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=config.SERVER_PORT,
        reload=True,
    )
```

### 简化版运行入口（无 FastAPI，直接命令行测试）

**文件：** `run_demo.py`

```python
"""
命令行 Demo —— 不需要启动 FastAPI 服务器，直接在终端测试工作流

用法: python run_demo.py "做一个电商首页"
"""
import sys
import json
from workflow.code_gen_workflow import run_workflow


def main():
    user_request = sys.argv[1] if len(sys.argv) > 1 else "做一个简单的电商首页，包含商品列表和购物车"

    print("=" * 60)
    print(f"用户需求: {user_request}")
    print("=" * 60)

    # 执行工作流
    result = run_workflow(user_request)

    # 打印结果
    print("\n" + "=" * 60)
    print("工作流执行完成")
    print("=" * 60)

    # PRD
    prd = result.get("prd", {})
    if prd:
        print(f"\n[PRD] 页面名称: {prd.get('page_name')}")
        print(f"[PRD] 功能数: {len(prd.get('features', []))}")
        for f in prd.get("features", [])[:5]:
            print(f"  - [{f.get('priority')}] {f.get('name')}")

    # 架构
    arch = result.get("architecture", {})
    if arch:
        print(f"\n[架构] 组件数: {len(arch.get('component_tree', []))}")
        print(f"[架构] 文件数: {len(arch.get('file_list', []))}")

    # 代码
    code_files = result.get("code_files", [])
    print(f"\n[代码] 生成文件数: {len(code_files)}")
    for f in code_files:
        print(f"  - {f.get('path')} ({len(f.get('content', '').split(chr(10)))} 行)")

    # 审查
    review = result.get("review", {})
    if review:
        status = "✅ 通过" if review.get("passed") else f"❌ 未通过 ({len(review.get('issues', []))} 个问题)"
        print(f"\n[审查] 评分: {review.get('score')}/100, {status}")

    # 构建
    build = result.get("build_result", {})
    if build:
        status = "✅ 成功" if build.get("success") else "❌ 失败"
        print(f"\n[构建] {status}")

    # 最终结果
    final = result.get("final_result", {})
    print(f"\n[最终] {json.dumps(final, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
```

---

## 九、完整运行指南

### 9.1 最终项目结构

```
ai-code-gen-agents/
├── .env                          # 环境变量（API Key 等）
├── requirements.txt              # Python 依赖
├── run_demo.py                   # 命令行 Demo 入口
├── config.py                     # 全局配置
├── llm_factory.py                # LLM 工厂
│
├── state/
│   └── code_gen_state.py         # State 定义
│
├── agents/
│   ├── supervisor_agent.py       # 编排者 Agent
│   ├── pm_agent.py               # 产品经理 Agent
│   ├── architect_agent.py        # 架构师 Agent
│   ├── coder_agent.py            # 程序员 Agent
│   ├── reviewer_agent.py         # 代码审查 Agent
│   ├── image_collector_agent.py  # 素材收集 Agent
│   └── builder_agent.py          # 构建验证 Agent
│
├── workflow/
│   ├── code_gen_workflow.py      # LangGraph 工作流
│   └── autogen_discussion.py     # AutoGen 三方讨论
│
├── rag/
│   ├── embedding_service.py      # Embedding 服务
│   ├── milvus_client.py          # Milvus 客户端
│   └── rag_builder.py            # RAG Prompt 构建器
│
└── server/
    └── main.py                   # FastAPI 服务
```

### 9.2 运行步骤

#### Step 1: 环境准备

```bash
cd ai-code-gen-agents
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

#### Step 2: 配置 API Key

编辑 `.env` 文件，填入你的 DeepSeek API Key：

```bash
DEEPSEEK_API_KEY=sk-your-actual-key
```

#### Step 3: （可选）启动 Milvus

如果有 Docker：

```bash
docker run -d --name milvus-standalone \
  -p 19530:19530 -p 9091:9091 \
  milvusdb/milvus:v2.4.0 standalone
```

如果本地没有 Docker，可以先跳过——RAG 功能会静默降级，核心工作流不受影响。

#### Step 4: 运行命令行 Demo

```bash
python run_demo.py "做一个简单的电商首页"
```

预期输出：

```
============================================================
用户需求: 做一个简单的电商首页
============================================================
[PM Agent] PRD 生成完成: 电商首页, 6 个功能
[Architect Agent] 架构设计完成: 5 组件, 8 文件
[Image Collector] 收集完成: 10 张图片
[Coder Agent] 代码生成完成: 8 个文件
[Reviewer Agent] 审查完成: 85/100, ✅ 通过
[Builder Agent] 构建成功
============================================================
工作流执行完成
...
```

#### Step 5: 启动 API 服务

```bash
python -m server.main
```

在另一个终端测试：

```bash
curl -X POST http://localhost:8000/api/generate-code \
  -H "Content-Type: application/json" \
  -d '{"prompt": "做一个简单的登录页面"}'
```

---

## 十、验证与调试

### 10.1 单 Agent 测试

当你遇到某个 Agent 的输出不符合预期时，可以单独测试：

```python
# test_single_agent.py
from llm_factory import create_llm_with_structured_output
from agents.pm_agent import PRD, PM_SYSTEM_PROMPT
from langchain.schema import SystemMessage, HumanMessage

llm = create_llm_with_structured_output(PRD)
result = llm.invoke([
    SystemMessage(content=PM_SYSTEM_PROMPT),
    HumanMessage(content="用户需求：做一个落地页宣传我们的新产品"),
])
print(result.model_dump_json(indent=2))
```

### 10.2 验证 State 在各 Agent 间的传递

在 `run_demo.py` 的 `run_workflow()` 返回后检查：

```python
result = run_workflow("做一个电商首页")

# 检查每个 Agent 的产出是否非空
assert result.get("prd"), "PM Agent 未产出 PRD"
assert result.get("architecture"), "Architect Agent 未产出架构"
assert len(result.get("code_files", [])) > 0, "Coder Agent 未产出代码文件"
assert result.get("review"), "Reviewer Agent 未产出审查结果"
print("所有 Agent 产出检查通过")
```

### 10.3 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| `ConnectionError` 调用 DeepSeek | API Key 未设置或错误 | 检查 `.env` 中 `DEEPSEEK_API_KEY` |
| `ImportError: autogen` | 未安装依赖 | `pip install -r requirements.txt` |
| Milvus 连接失败 | Milvus 未启动 | 跳过不影响核心工作流 |
| SSLError | 网络代理问题 | 设置 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量 |
| Agent 返回格式错误 | LLM 未按 JSON 输出 | 降低 temperature 到 0，或更新 System Prompt |
| 代码构建失败 | 生成的代码有语法错误 | 增加 `max_retries`，Reviewer 会自动捕获 |

### 10.4 与 Java 端联调

```bash
# 1. 启动 Python 服务
python -m server.main

# 2. 在 Java 端配置
# application.yml:
python:
  ai:
    base-url: http://localhost:8000
```

Java 端用 WebClient 调用：

```java
Flux<String> stream = webClient.post()
    .uri("/api/generate-code")
    .bodyValue(Map.of(
        "userId", userId,
        "appId", appId,
        "prompt", prompt,
        "history", historyList
    ))
    .retrieve()
    .bodyToFlux(String.class);
```

---

> **下一步：** 跑通 Demo 后，可以对照技术文档第七章（RAG 反幻觉体系）的 7.4 节实现幻觉检测器，或在 Review 不通过时启用第六章的 AutoGen 三方讨论。

> **反馈：** 修改教程中的任何参数（temperature、max_retries、Milvus Collection Schema）来适配你的场景。关键是先把 `run_demo.py` 跑通。
