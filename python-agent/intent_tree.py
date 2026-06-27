"""
三层意图分类树（基于 docs/intent_recognition_tree.md）

结构:
  一级意图(10个) → 二级意图(~30个) → 三级意图(60+个)

每个叶子节点包含: path(路径), description(定义), keywords(典型关键词), required_slots(必填槽位)
"""
from dataclasses import dataclass, field


@dataclass
class IntentNode:
    """意图树节点"""
    id: str                              # 唯一标识, 如 "code_gen.backend.api"
    name: str                            # 显示名称, 如 "生成 API"
    description: str = ""                # 定义说明
    keywords: list[str] = field(default_factory=list)
    required_slots: list[str] = field(default_factory=list)
    children: list["IntentNode"] = field(default_factory=list)

    def find(self, node_id: str) -> "IntentNode | None":
        if self.id == node_id:
            return self
        for c in self.children:
            r = c.find(node_id)
            if r:
                return r
        return None

    def all_leaf_paths(self, prefix: str = "") -> list[str]:
        if not self.children:
            return [f"{prefix}{self.name}" if prefix else self.name]
        paths = []
        for c in self.children:
            paths.extend(c.all_leaf_paths(f"{prefix}{self.name} / "))
        return paths


# ---- 树定义 ----
INTENT_ROOT = IntentNode(
    id="root",
    name="用户输入意图",
    description="用户自然语言输入的意图分类根节点",
    children=[
        # ======== 1. 需求理解 ========
        IntentNode(
            id="requirement",
            name="需求理解",
            description="用户在描述想法、目标、业务规则，需要系统理解并拆解",
            keywords=["我想做", "需求", "功能设计", "拆解", "分析"],
            children=[
                IntentNode(id="req.breakdown", name="需求拆解",
                    description="提取功能点、业务规则、边界条件",
                    keywords=["功能点", "业务规则", "拆解需求", "边界条件"],
                    required_slots=["target_object", "desired_outcome"]),
                IntentNode(id="req.clarify", name="需求澄清",
                    description="目标/范围/约束不明确时主动澄清",
                    keywords=["不明确", "需要澄清", "确定目标"],
                    required_slots=["desired_outcome"]),
                IntentNode(id="req.compare", name="方案对比",
                    description="多方案选择、优缺点分析、实施路径建议",
                    keywords=["哪个方案好", "对比", "优缺点", "如何选择"],
                    required_slots=["target_object"]),
            ]
        ),
        # ======== 2. 代码生成 ========
        IntentNode(
            id="code_gen",
            name="代码生成",
            description="用户希望生成新代码、组件、接口、脚本、配置等",
            keywords=["生成", "创建", "做一个", "写一个", "新建"],
            children=[
                IntentNode(id="code_gen.frontend", name="前端代码生成",
                    description="生成页面、组件、表单、图表、交互逻辑",
                    keywords=["页面", "组件", "表单", "前端", "Vue", "React", "UI"],
                    children=[
                        IntentNode(id="code_gen.frontend.page", name="生成页面",
                            keywords=["页面", "首页", "列表页", "详情页"],
                            required_slots=["tech_stack", "target_function"]),
                        IntentNode(id="code_gen.frontend.component", name="生成组件",
                            keywords=["组件", "弹窗", "表格", "卡片"],
                            required_slots=["tech_stack", "target_function"]),
                        IntentNode(id="code_gen.frontend.form", name="生成表单",
                            keywords=["表单", "输入框", "登录", "注册"],
                            required_slots=["tech_stack", "target_function"]),
                        IntentNode(id="code_gen.frontend.chart", name="生成图表",
                            keywords=["图表", "折线图", "柱状图", "饼图"],
                            required_slots=["tech_stack"]),
                        IntentNode(id="code_gen.frontend.interaction", name="生成交互逻辑",
                            keywords=["交互", "动画", "拖拽", "滚动"],
                            required_slots=["tech_stack", "target_function"]),
                    ]),
                IntentNode(id="code_gen.backend", name="后端代码生成",
                    description="生成 API、数据库模型、服务层逻辑、权限逻辑",
                    keywords=["后端", "服务端", "接口", "数据库", "API"],
                    children=[
                        IntentNode(id="code_gen.backend.api", name="生成 API",
                            keywords=["API", "接口", "REST", "RESTful", "端点", "endpoint"],
                            required_slots=["tech_stack", "target_function"]),
                        IntentNode(id="code_gen.backend.db", name="生成数据库模型",
                            keywords=["数据库", "模型", "表结构", "ORM", "Entity"],
                            required_slots=["tech_stack"]),
                        IntentNode(id="code_gen.backend.service", name="生成服务层逻辑",
                            keywords=["Service", "业务逻辑", "服务层"],
                            required_slots=["tech_stack", "target_function"]),
                        IntentNode(id="code_gen.backend.auth", name="生成权限逻辑",
                            keywords=["权限", "认证", "登录", "JWT", "鉴权"],
                            required_slots=["tech_stack"]),
                    ]),
                IntentNode(id="code_gen.script", name="脚本生成",
                    description="数据处理脚本、文件处理脚本、自动化脚本",
                    keywords=["脚本", "自动化", "批处理", "定时任务"],
                    required_slots=["target_function"]),
                IntentNode(id="code_gen.config", name="配置生成",
                    description="构建配置、部署配置、环境变量模板",
                    keywords=["配置", "yml", "Dockerfile", "docker-compose", "环境变量"],
                    required_slots=["tech_stack"]),
            ]
        ),
        # ======== 3. 代码修改 ========
        IntentNode(
            id="code_modify",
            name="代码修改",
            description="用户希望修改已有代码、修复问题、调整逻辑",
            keywords=["修改", "改", "修复", "调整", "优化", "重构"],
            children=[
                IntentNode(id="code_modify.enhance", name="功能增强",
                    description="增加新功能、扩展已有功能、调整业务规则",
                    keywords=["增加", "加一个", "扩展", "增强", "调整规则"],
                    required_slots=["target_object", "desired_outcome"]),
                IntentNode(id="code_modify.bugfix", name="Bug 修复",
                    description="修复编译/运行时/逻辑/边界错误",
                    keywords=["报错", "错误", "bug", "崩溃", "不对", "异常"],
                    children=[
                        IntentNode(id="code_modify.bugfix.compile", name="修复编译错误",
                            keywords=["编译", "不通过", "syntax error"]),
                        IntentNode(id="code_modify.bugfix.runtime", name="修复运行时报错",
                            keywords=["500", "报错", "运行时", "异常", "Exception"],
                            required_slots=["error_info"]),
                        IntentNode(id="code_modify.bugfix.logic", name="修复逻辑错误",
                            keywords=["逻辑", "不对", "结果错", "不符合预期"],
                            required_slots=["desired_outcome"]),
                        IntentNode(id="code_modify.bugfix.edge", name="修复边界情况",
                            keywords=["边界", "空指针", "空值", "undefined", "null"]),
                    ]),
                IntentNode(id="code_modify.refactor", name="重构优化",
                    description="拆分模块、降低复杂度、提升可读性",
                    keywords=["重构", "拆分", "可读", "模块化", "解耦"],
                    required_slots=["target_object"]),
                IntentNode(id="code_modify.perf", name="性能优化",
                    description="优化查询、减少渲染、降低内存消耗",
                    keywords=["太慢", "卡", "性能", "优化速度", "内存", "响应慢"],
                    required_slots=["target_object"]),
            ]
        ),
        # ======== 4. 代码解释 ========
        IntentNode(
            id="code_explain",
            name="代码解释",
            description="用户希望解释已有代码、架构、流程或错误原因",
            keywords=["解释", "什么意思", "这段代码", "说明", "干嘛的"],
            children=[
                IntentNode(id="code_explain.local", name="局部代码解释",
                    description="函数/类/配置解释",
                    children=[
                        IntentNode(id="code_explain.local.func", name="函数解释", keywords=["函数", "方法"]),
                        IntentNode(id="code_explain.local.class", name="类解释", keywords=["类", "class"]),
                        IntentNode(id="code_explain.local.config", name="配置解释", keywords=["配置", "config"]),
                    ]),
                IntentNode(id="code_explain.flow", name="流程解释",
                    description="调用链/数据流/状态流转解释",
                    keywords=["流程", "调用链", "数据流", "状态"]),
                IntentNode(id="code_explain.arch", name="架构解释",
                    description="模块职责/依赖关系/设计意图解释",
                    keywords=["架构", "模块", "依赖", "设计"]),
            ]
        ),
        # ======== 5. 问题排查 ========
        IntentNode(
            id="troubleshoot",
            name="问题排查",
            description="用户遇到报错、异常、性能问题或行为不符合预期",
            keywords=["报错", "不工作", "出问题", "怎么回事", "帮我看看"],
            children=[
                IntentNode(id="troubleshoot.error", name="报错定位",
                    description="编译/运行时/类型/依赖错误",
                    keywords=["报错", "error", "错误信息", "traceback", "stack trace"],
                    required_slots=["error_info"]),
                IntentNode(id="troubleshoot.behavior", name="行为异常",
                    description="输出/显示/接口返回不符合预期",
                    keywords=["不符合预期", "显示异常", "返回不对"],
                    required_slots=["desired_outcome"]),
                IntentNode(id="troubleshoot.perf", name="性能问题",
                    description="响应慢/卡顿/内存泄漏/请求过多",
                    keywords=["太慢", "卡顿", "泄漏", "高延迟"],
                    required_slots=["target_object"]),
                IntentNode(id="troubleshoot.env", name="环境问题",
                    description="依赖/构建/部署/配置失败",
                    keywords=["安装失败", "构建失败", "部署", "依赖", "环境"]),
            ]
        ),
        # ======== 6. 文档生成 ========
        IntentNode(
            id="doc_gen",
            name="文档生成",
            description="用户希望生成 README、接口文档、注释、方案文档等",
            keywords=["文档", "README", "注释", "说明文档", "接口文档"],
            children=[
                IntentNode(id="doc_gen.project", name="项目文档",
                    keywords=["README", "使用说明", "部署说明"]),
                IntentNode(id="doc_gen.api", name="接口文档",
                    keywords=["API文档", "接口说明", "Swagger"]),
                IntentNode(id="doc_gen.code", name="代码文档",
                    keywords=["注释", "docstring", "Javadoc"]),
                IntentNode(id="doc_gen.solution", name="方案文档",
                    keywords=["技术方案", "架构方案", "优化方案"]),
            ]
        ),
        # ======== 7. 测试相关 ========
        IntentNode(
            id="test",
            name="测试相关",
            description="用户希望生成测试、补充用例、定位测试失败",
            keywords=["测试", "test", "用例", "单元测试", "集成测试"],
            children=[
                IntentNode(id="test.generate", name="测试生成",
                    description="生成单元/集成/端到端测试",
                    keywords=["生成测试", "写测试", "加测试"],
                    required_slots=["target_object", "tech_stack"]),
                IntentNode(id="test.fix", name="测试修复",
                    description="测试失败定位/断言修复/Mock修复",
                    keywords=["测试失败", "断言", "mock", "通不过"]),
                IntentNode(id="test.complete", name="测试补全",
                    description="补充边界/异常/回归用例",
                    keywords=["补全", "补充用例", "边界", "异常"]),
            ]
        ),
        # ======== 8. 架构设计 ========
        IntentNode(
            id="arch_design",
            name="架构设计",
            description="用户希望获得技术方案、模块划分、系统设计建议",
            keywords=["架构", "设计", "方案", "选型", "模块划分"],
            children=[
                IntentNode(id="arch_design.module", name="模块设计",
                    description="单模块/多模块/分层架构设计",
                    keywords=["模块", "分层", "微服务"]),
                IntentNode(id="arch_design.tech", name="技术选型",
                    description="框架/数据库/检索方案/部署方案选择",
                    keywords=["选型", "框架", "数据库", "哪个好"]),
                IntentNode(id="arch_design.flow", name="流程设计",
                    description="用户流程/数据流程/Agent流程/RAG流程设计",
                    keywords=["流程", "数据流", "Pipeline"]),
            ]
        ),
        # ======== 9. 环境配置 ========
        IntentNode(
            id="env_config",
            name="环境配置",
            description="用户希望配置依赖、部署、构建、CI/CD、运行环境",
            keywords=["配置", "安装", "部署", "环境", "docker", "k8s"],
            children=[
                IntentNode(id="env_config.local", name="本地开发环境",
                    keywords=["开发环境", "本地", "IDE", "调试"]),
                IntentNode(id="env_config.build", name="构建环境",
                    keywords=["构建", "打包", "build", "静态资源"]),
                IntentNode(id="env_config.deploy", name="部署环境",
                    keywords=["部署", "docker", "k8s", "CI/CD", "容器"]),
                IntentNode(id="env_config.runtime", name="运行配置",
                    keywords=["环境变量", "权限", "日志", "Nginx"]),
            ]
        ),
        # ======== 10. 不明确 ========
        IntentNode(
            id="unclear",
            name="不明确",
            description="无法可靠判断用户意图",
            keywords=["这个", "那个", "处理一下", "优化一下", "看一下", "帮我弄"],
            children=[
                IntentNode(id="unclear.reference", name="指代不清",
                    keywords=["这个", "那个", "上面的", "刚才的"],
                    required_slots=["target_object"]),
                IntentNode(id="unclear.goal", name="目标不清",
                    keywords=["处理一下", "优化一下", "看一下", "弄一下"],
                    required_slots=["desired_outcome"]),
                IntentNode(id="unclear.insufficient", name="信息不足",
                    keywords=["缺少", "没有"],
                    required_slots=["desired_outcome"]),
            ]
        ),
    ]
)


# ===== 辅助函数 =====

def find_intent(node_id: str) -> IntentNode | None:
    return INTENT_ROOT.find(node_id)


def get_leaf_nodes(root: IntentNode = INTENT_ROOT) -> list[IntentNode]:
    """获取所有叶子节点"""
    if not root.children:
        return [root]
    leaves = []
    for c in root.children:
        leaves.extend(get_leaf_nodes(c))
    return leaves


def format_intent_tree_flat(root: IntentNode = INTENT_ROOT, indent: int = 0) -> str:
    """将意图树格式化为扁平列表（供 LLM prompt 使用）"""
    prefix = "  " * indent
    if not root.children:
        kw = ", ".join(root.keywords[:5]) if root.keywords else ""
        slots = ", ".join(root.required_slots) if root.required_slots else "无"
        return (f"{prefix}- [{root.id}] {root.name}: {root.description}\n"
                f"{prefix}  关键词: {kw}\n"
                f"{prefix}  必填槽位: {slots}")

    lines = [f"{prefix}# {root.name} ({root.id})" + (f" — {root.description}" if root.description else "")]
    for c in root.children:
        lines.append(format_intent_tree_flat(c, indent + 1))
    return "\n".join(lines)
