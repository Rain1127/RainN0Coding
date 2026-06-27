"""
Mode Detector —— 双重信号路由（零 LLM 调用）

在 Intent Agent 之前运行。通过文件系统状态 + 用户语言信号双重判断，
决定本次请求是"新需求"还是"修改上一次需求"。

路由逻辑：
  有历史产物（project_dir 存在且有文件）？
  ├── 没有 → mode = "new"（完整流程）
  └── 有
      ├── 用户明确说"改/加/换/修复/继续" → mode = "modify"（跳过 PM + Architect）
      ├── 用户说"重新/重来/换方案" → mode = "rebuild"（等同于 new，走完整流程）
      └── 模糊（如"优化一下"）→ mode = "modify"（默认修改）
"""
import json
import os
from state.code_gen_state import CodeGenState


# ============ 语言信号关键词（优先级：rebuild > new > modify）============

_REBUILD_KEYWORDS = [
    "重新生成", "重做", "换方案", "不用这个", "覆盖",
    "重新", "重来", "从头开始", "推倒重来", "换个方案",
]

_NEW_KEYWORDS = [
    "新建", "做一个", "从头", "创建", "搭建", "生成一个",
    "生成", "做一个新的", "新建一个", "创建一个",
]

_MODIFY_KEYWORDS = [
    "改一下", "改一改", "改成", "换成", "换掉", "调整", "加一个",
    "继续", "修复", "增加", "添加", "删除", "删掉",
    "更新", "优化", "替换", "修改", "改", "加上",
    "去掉", "移除", "变更", "修正", "调整一下",
]


# ============ Helper 函数 ============

def _detect_language_signal(user_request: str) -> str:
    """从用户输入中检测语言信号：rebuild / new / modify / ambiguous。

    优先级：rebuild > new > modify（rebuild 是最强信号）。
    多字关键词优先匹配（如"重新生成"在"生成"之前检查）。
    """
    text = user_request

    for kw in _REBUILD_KEYWORDS:
        if kw in text:
            return "rebuild"

    for kw in _NEW_KEYWORDS:
        if kw in text:
            return "new"

    for kw in _MODIFY_KEYWORDS:
        if kw in text:
            return "modify"

    return "ambiguous"


def _has_files_in_dir(project_dir: str) -> bool:
    """检查目录是否存在且包含至少一个非目录条目。"""
    if not project_dir or not os.path.isdir(project_dir):
        return False
    try:
        with os.scandir(project_dir) as entries:
            for _ in entries:
                return True
    except OSError:
        return False
    return False


def _load_json_if_exists(path: str) -> dict | None:
    """读取并解析 JSON 文件，不存在或解析失败则返回 None。"""
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _collect_code_files(project_dir: str) -> list[dict]:
    """从项目目录收集所有代码文件快照（排除 node_modules 等）。"""
    code_files = []
    if not project_dir or not os.path.isdir(project_dir):
        return code_files
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in
                   {"node_modules", ".git", "__pycache__", ".venv", "dist", "build"}]
        for name in files:
            if name.endswith((".pyc", ".log", ".lock", ".tmp", ".json")):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, project_dir).replace("\\", "/")
            try:
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
                code_files.append({"path": rel, "content": content})
            except Exception:
                pass
    return code_files


# ============ LangGraph 节点 ============

def mode_detector(state: CodeGenState) -> CodeGenState:
    """在 Intent Agent 之前检测运行模式。

    读取 state["project_dir"] 和 state["user_request"]，
    设置 state["mode"]、state["has_existing_code"]，
    以及（modify 模式下）加载历史产物。
    """
    project_dir = state.get("project_dir", "")
    user_request = state.get("user_request", "")

    # 1. 状态信号：检查是否有历史产物
    has_existing_code = _has_files_in_dir(project_dir)
    state["has_existing_code"] = has_existing_code

    # 2. 语言信号：用户说了什么
    language_signal = _detect_language_signal(user_request)

    # 3. 双重信号合并 → 决定 mode
    if not has_existing_code:
        # 没有历史产物 → 一定是新需求
        mode = "new"
    else:
        # 有历史产物 → 结合语言信号判断
        if language_signal == "rebuild":
            mode = "rebuild"
        elif language_signal == "new":
            mode = "new"
        elif language_signal == "modify":
            mode = "modify"
        else:
            # ambiguous → 有产物默认走修改
            mode = "modify"

    state["mode"] = mode

    # 4. modify 模式：加载历史产物
    if mode == "modify":
        state["existing_prd"] = _load_json_if_exists(
            os.path.join(project_dir, "prd.json"))
        state["existing_architecture"] = _load_json_if_exists(
            os.path.join(project_dir, "architecture.json"))
        state["existing_code_files"] = _collect_code_files(project_dir)

    # 5. rebuild 模式：可选择性清理旧产物（非关键，失败不阻塞）
    if mode == "rebuild":
        import shutil
        try:
            if os.path.isdir(project_dir):
                shutil.rmtree(project_dir)
        except Exception:
            pass  # 清理失败不影响流程

    state["phase"] = "mode_detected"

    print(f"[Mode Detector] mode={mode}, has_existing_code={has_existing_code}, "
          f"language_signal={language_signal}, "
          f"existing_files={len(state.get('existing_code_files', []))}")
    return state
