"""逐个测试三个 LLM Agent 的完整调用链"""
import sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__" and os.getenv("RUN_LIVE_LLM_TESTS") != "1":
    pytest.skip("manual live LLM test; set RUN_LIVE_LLM_TESTS=1 to collect", allow_module_level=True)

def test_pm():
    from agents.pm_agent import pm_agent
    state = {"user_request": "做一个简单的电商首页，包含商品列表和购物车入口", "phase": "init"}
    result = pm_agent(state)
    assert result["phase"] != "error", f"PM failed: {result.get('error')}"
    prd = result["prd"]
    assert len(prd["features"]) >= 3
    assert prd["page_name"]
    print(f"PM OK: {prd['page_name']}, {len(prd['features'])} features, phase={result['phase']}")

def test_arch():
    from agents.architect_agent import architect_agent
    prd = {
        "page_name": "电商首页", "page_type": "e-commerce",
        "target_audience": "网购用户", "color_preference": "橙+白",
        "layout_type": "grid",
        "features": [
            {"name": "商品列表", "description": "展示商品", "priority": "high", "interactions": ["点击查看"]},
            {"name": "购物车", "description": "购物车入口", "priority": "high", "interactions": ["点击进入"]},
            {"name": "搜索栏", "description": "商品搜索", "priority": "medium", "interactions": ["输入搜索"]},
        ],
        "data_dependencies": ["商品列表API", "购物车API"],
    }
    state = {"prd": prd, "phase": "prd_done"}
    result = architect_agent(state)
    assert result["phase"] != "error", f"Arch failed: {result.get('error')}"
    arch = result["architecture"]
    assert len(arch["component_tree"]) >= 2
    assert len(arch["file_list"]) >= 5
    print(f"Arch OK: {len(arch['component_tree'])} components, {len(arch['file_list'])} files")

def test_coder():
    from agents.coder_agent import coder_agent
    arch = {
        "tech_stack": {"framework": "Vue 3"},
        "component_tree": [
            {"name": "App", "description": "根组件", "props": [], "children": ["Header", "ProductList"]},
            {"name": "Header", "description": "顶部导航", "props": ["title: string"], "children": []},
            {"name": "ProductList", "description": "商品列表", "props": ["products: Product[]"], "children": []},
        ],
        "file_list": [
            {"path": "src/App.vue", "description": "根组件", "file_type": "page"},
            {"path": "src/components/Header.vue", "description": "导航", "file_type": "component", "component_name": "Header"},
            {"path": "src/components/ProductList.vue", "description": "商品列表", "file_type": "component", "component_name": "ProductList"},
            {"path": "src/types/index.ts", "description": "类型定义", "file_type": "type"},
        ],
        "data_flow": [],
    }
    state = {"architecture": arch, "phase": "arch_done"}
    result = coder_agent(state)
    assert result["phase"] != "error", f"Coder failed: {result.get('error')}"
    files = result["code_files"]
    assert len(files) >= 2
    for f in files:
        assert f["path"]
        assert len(f["content"]) > 50
    total_lines = sum(len(f["content"].split("\n")) for f in files)
    print(f"Coder OK: {len(files)} files, {total_lines} lines total, phase={result['phase']}")

if __name__ == "__main__":
    print("=" * 40)
    test_pm()
    print("=" * 40)
    test_arch()
    print("=" * 40)
    test_coder()
    print("=" * 40)
    print("ALL 3 AGENTS PASSED")
