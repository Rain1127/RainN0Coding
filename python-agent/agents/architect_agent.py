"""
Architect Agent —— 架构师

输入：PM Agent 产出的 PRD
输出：组件树 / 文件清单 / 数据流图 / 技术栈建议
行为：调用 LLM 1 次，手动 JSON 解析 + Pydantic validate
      关键约束——只设计结构，不写代码实现
"""
import json
import os
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from llm_factory import create_json_parser
from state.code_gen_state import CodeGenState
from config import LANGUAGE_CONFIGS, get_lang_config


# ============ Pydantic 输出模型 ============

class ComponentNode(BaseModel):
    """组件树中的一个节点"""
    name: str = Field(description="组件名称，如'ProductCard'，使用 PascalCase")
    description: str = Field(description="组件职责，一句话描述这个组件做什么")
    props: list[str] = Field(description="组件 Props 列表，如['title: string', 'items: Product[]']，包含类型")
    children: list[str] = Field(
        default_factory=list,
        description="子组件名称列表，引用 component_tree 中其他组件的 name"
    )


class FileSpec(BaseModel):
    """需要创建的文件规格"""
    path: str = Field(description="文件路径，如'src/components/ProductCard.vue'")
    description: str = Field(description="这个文件承担什么职责")
    file_type: str = Field(
        description="文件类型",
        json_schema_extra={"enum": ["component", "page", "store", "router", "util", "style", "config", "type"]}
    )
    component_name: str | None = Field(
        default=None,
        description="如果是组件文件，写组件名（与 component_tree 中的 name 对应）"
    )


class DataFlow(BaseModel):
    """组件间数据流向"""
    from_component: str = Field(description="数据来源组件名")
    to_component: str = Field(description="数据目标组件名")
    data_type: str = Field(description="传递的数据类型，如'Product[]' / 'UserInfo' / 'boolean: loading'")
    mechanism: str = Field(
        description="传递机制",
        json_schema_extra={"enum": ["props", "provide/inject", "pinia-store", "router-params", "emit-event"]}
    )


class Architecture(BaseModel):
    """架构方案"""
    tech_stack: dict = Field(
        description="技术栈。固定使用: {'framework': 'Vue 3', 'script': 'script setup lang=ts', "
                    "'css': 'Tailwind CSS', 'state': 'Pinia', 'router': 'Vue Router 4', 'build': 'Vite'}"
    )
    component_tree: list[ComponentNode] = Field(
        description="组件树。从页面根组件开始，逐层展开。至少包含根组件 + 3 个一级子组件"
    )
    file_list: list[FileSpec] = Field(
        description="文件清单。包含所有需要创建的文件：组件、页面、路由、store、工具函数、类型定义"
    )
    data_flow: list[DataFlow] = Field(
        description="数据流向。描述组件间如何传递数据，至少覆盖所有 high 优先级功能的交互链路"
    )


# ============ System Prompt（动态，根据语言生成）============

def _build_arch_prompt(code_gen_type: str | None) -> str:
    """根据代码生成类型构建 Architect Agent 的动态提示词。"""
    lc = get_lang_config(code_gen_type)
    is_frontend = lc.get("is_frontend", False)

    if is_frontend:
        return f"""你是一个资深{lc['arch_role']}。根据产品 PRD 设计{lc['label']}项目代码骨架。

## 技术栈（严格遵循）
- 框架: {lc['framework']}
- 语言: {lc['lang']}"""
        + (f"\n- CSS: {lc['css']}" if lc.get("css") else "")
        + (f"\n- 状态管理: {lc['state']}" if lc.get("state") else "")
        + (f"\n- 路由: {lc['router']}" if lc.get("router") else "")
        + (f"\n- 构建: {lc['build_tool']}" if lc.get("build_tool") else "")
        + f"""

## 设计规则
1. **组件树必须完整覆盖 PRD 功能清单**：根组件一般是 App.vue 或对应页面组件，每个 PRD 功能至少对应一个组件，组件粒度适中（不超过 200 行）
2. **每个组件必须标注 props**：写明组件需要接收什么数据，带上类型
3. **文件清单必须完整**：所有组件文件、路由配置、状态管理、类型定义、工具函数
4. **数据流要具体**：写明数据来源/流向/传递机制（props / store / provide-inject / emit）
5. **不要写代码实现**：只设计结构和接口
"""
    else:
        return f"""你是一个资深{lc['arch_role']}。根据需求设计{lc['label']}项目代码架构。

## 技术栈（严格遵循）
- 框架: {lc['framework']}
- 语言: {lc['lang']}"""
        + (f"\n- 构建工具: {lc['build_tool']}" if lc.get("build_tool") else "")
        + (f"\n- 包管理: {lc['pkg_manager']}" if lc.get("pkg_manager") else "")
        + (f"\n- 测试: {lc['test']}" if lc.get("test") else "")
        + f"""

## 设计规则
1. **component_tree 表示模块/类/函数的分层结构**：每个功能点对应一个模块或类
2. **遵循标准项目结构**：{lc['label']} 项目的标准目录布局（如 Spring Boot 的 controller/service/repository）
3. **file_list 必须完整**：所有源码文件、配置文件、依赖声明({lc.get('entry', 'main')})、测试文件
4. **data_flow 要具体**：模块间的调用关系、接口定义、数据传递方式
5. **不要写代码实现**：只设计结构和接口
"""


ARCH_FIELD_SPEC = """Output ONLY a valid JSON object with these EXACT field names:
{
  "tech_stack": {"framework": "string", "lang": "string", "build": "string", "test": "string or null"},
  "component_tree": [
    {"name": "string", "description": "string", "props": ["string"], "children": ["string"]}
  ],
  "file_list": [
    {"path": "string", "description": "string", "file_type": "src|config|test|doc|build", "component_name": "string or null"}
  ],
  "data_flow": [
    {"from_component": "string", "to_component": "string", "data_type": "string", "mechanism": "function_call|http|db|queue|file|rpc"}
  ]
}
Output ONLY the JSON, no markdown, no explanation."""


# ============ Agent 主函数 ============

def architect_agent(state: CodeGenState) -> CodeGenState:
    """Architect Agent 主逻辑 —— 调用 LLM 将 PRD 转为架构方案"""
    parser = create_json_parser(Architecture, ARCH_FIELD_SPEC, group="structured", agent_name="architect_agent")

    prd = state.get("prd")
    if not prd:
        state["error"] = "PRD 为空，Architect Agent 无法设计架构"
        state["phase"] = "error"
        return state

    code_gen_type = state.get("code_gen_type", "vue_project")
    system_prompt = _build_arch_prompt(code_gen_type)

    # 构造 HumanMessage：从 PRD 提取关键信息
    user_prompt = f"""请根据以下需求设计{get_lang_config(code_gen_type)['label']}项目架构：

## 产品需求
- 页面名称：{prd.get('page_name', '')}
- 页面类型：{prd.get('page_type', '')}
- 目标用户：{prd.get('target_audience', '')}
- 色彩偏好：{prd.get('color_preference', '')}
- 布局类型：{prd.get('layout_type', '')}

## 功能清单
{_format_features(prd.get('features', []))}

## 数据依赖
{_format_list(prd.get('data_dependencies', []))}

请输出完整的架构方案（组件树 + 文件清单 + 数据流 + 技术栈）。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        arch: Architecture = parser(messages, user_id=state.get("user_id"))
    except Exception as e:
        state["error"] = f"Architect Agent LLM 调用失败: {e}"
        state["phase"] = "error"
        return state

    if arch is None:
        state["error"] = "Architect Agent 失败：所有模型候选不可用（全部已熔断或调用失败）"
        state["phase"] = "error"
        return state

    # 写入 State
    state["architecture"] = arch.model_dump()

    # 持久化架构方案到磁盘，供后续修改模式加载复用
    _persist_architecture(state)

    state["phase"] = "arch_done"

    component_names = [c.name for c in arch.component_tree]
    print(f"[Architect Agent] 完成: {len(arch.component_tree)} 组件, "
          f"{len(arch.file_list)} 文件, "
          f"{len(arch.data_flow)} 条数据流, "
          f"根组件: {component_names[0] if component_names else 'N/A'}")

    return state


def _persist_architecture(state: CodeGenState) -> None:
    """将架构方案持久化到项目目录，供后续修改模式加载复用。"""
    project_dir = state.get("project_dir", "")
    if not project_dir:
        return
    try:
        os.makedirs(project_dir, exist_ok=True)
        arch_path = os.path.join(project_dir, "architecture.json")
        with open(arch_path, "w", encoding="utf-8") as f:
            json.dump(state["architecture"], f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 持久化非关键，失败不影响流程


# ============ 格式化辅助函数 ============

def _format_features(features: list) -> str:
    """将 PRD features 列表格式化为 Markdown 清单"""
    if not features:
        return "(无)"
    lines = []
    for f in features:
        priority = f.get("priority", "medium")
        name = f.get("name", "未命名")
        desc = f.get("description", "")
        interactions = f.get("interactions", [])
        detail = f"{desc}"
        if interactions:
            detail += f"（交互：{', '.join(interactions)}）"
        lines.append(f"- [{priority.upper()}] **{name}**: {detail}")
    return "\n".join(lines)


def _format_list(items: list) -> str:
    """格式化字符串列表"""
    if not items:
        return "(无)"
    return "\n".join(f"- {item}" for item in items)
