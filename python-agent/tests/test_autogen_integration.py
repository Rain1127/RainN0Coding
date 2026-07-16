"""AutoGen 三方讨论链路测试"""
import os, sys, json, asyncio
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv; load_dotenv()

if __name__ != "__main__" and os.getenv("RUN_LIVE_LLM_TESTS") != "1":
    pytest.skip("manual live LLM script; set RUN_LIVE_LLM_TESTS=1 to collect", allow_module_level=True)

# === 1. 测试 Supervisor 路由 ===
print("=" * 50)
print("1. Supervisor 路由测试")
print("=" * 50)

from agents.supervisor_agent import supervisor_decision, _has_architectural_issues

# 场景A: 架构级 issue → autogen_discussion
review_arch = {
    "passed": False,
    "score": 55,
    "issues": [
        {"file": "src/App.vue", "severity": "critical", "category": "architecture",
         "description": "组件树设计不合理，应将 ProductList 和 ProductForm 合并为一个 ProductManage 组件",
         "suggestion": "重构 component_tree，合并 ProductList 和 ProductForm，提取共享的 Pinia store"}
    ]
}
assert _has_architectural_issues(review_arch), "架构级 issue 应该被检测到"
state_a = {"phase": "review_done", "review": review_arch, "retry_count": 0, "max_retries": 3}
route_a = supervisor_decision(state_a)
assert route_a == "autogen_discussion", f"期望 autogen_discussion，实际 {route_a}"
print(f"  [PASS] 架构级 issue → {route_a}")

# 场景B: 代码级 issue → coder_agent
review_code = {
    "passed": False,
    "score": 65,
    "issues": [
        {"file": "src/ProductTable.vue", "severity": "warn", "category": "syntax",
         "description": "v-for 缺少 :key", "suggestion": "添加 :key=\"item.id\""}
    ]
}
assert not _has_architectural_issues(review_code), "代码级 issue 不应被检测为架构级"
state_b = {"phase": "review_done", "review": review_code, "retry_count": 0, "max_retries": 3}
route_b = supervisor_decision(state_b)
assert route_b == "coder_agent", f"期望 coder_agent，实际 {route_b}"
print(f"  [PASS] 代码级 issue → {route_b}")

# 场景C: passed → builder_agent
review_pass = {"passed": True, "score": 85, "issues": []}
state_c = {"phase": "review_done", "review": review_pass, "retry_count": 0, "max_retries": 3}
route_c = supervisor_decision(state_c)
assert route_c == "builder_agent", f"期望 builder_agent，实际 {route_c}"
print(f"  [PASS] 通过审查 → {route_c}")

# 场景D: retry>=3 → human_intervention
state_d = {"phase": "review_done", "review": review_code, "retry_count": 3, "max_retries": 3}
route_d = supervisor_decision(state_d)
assert route_d == "human_intervention", f"期望 human_intervention，实际 {route_d}"
print(f"  [PASS] 重试超限 → {route_d}")

# 场景E: 描述含架构关键词 → autogen_discussion
review_kw = {
    "passed": False,
    "score": 60,
    "issues": [
        {"file": "src/main.ts", "severity": "warn", "category": "logic",
         "description": "路由设计方案有问题",
         "suggestion": "需要重构路由设计，改为嵌套路由"}
    ]
}
assert _has_architectural_issues(review_kw), "含'路由设计'关键词应被检测为架构级"
state_e = {"phase": "review_done", "review": review_kw, "retry_count": 0, "max_retries": 3}
route_e = supervisor_decision(state_e)
assert route_e == "autogen_discussion", f"期望 autogen_discussion，实际 {route_e}"
print(f"  [PASS] 关键词检测 → {route_e}")

print()

# === 2. 测试 AutoGen 讨论节点 ===
print("=" * 50)
print("2. AutoGen Discussion 节点测试")
print("=" * 50)

from workflow.autogen_discussion import autogen_discussion_node

code_files = [
    {
        "path": "src/views/ProductManage.vue",
        "content": """<script setup lang="ts">
import { ref } from 'vue'
const products = ref([])
// TODO: 需要从 API 获取数据
</script>
<template>
  <div>
    <ProductList :products="products" />
    <ProductForm />
  </div>
</template>"""
    },
    {
        "path": "src/components/ProductList.vue",
        "content": """<script setup lang="ts">
defineProps<{ products: any[] }>()
</script>
<template>
  <div v-for="p in products">{{ p.name }}</div>
</template>"""
    }
]

issues = [
    {
        "file": "src/views/ProductManage.vue",
        "severity": "critical",
        "category": "architecture",
        "description": "ProductList 和 ProductForm 应该合并为一个组件，或者通过 Pinia store 共享状态",
        "suggestion": "1. 将 products 状态提升到 Pinia store\n2. ProductForm 通过 store 添加商品\n3. ProductList 通过 store 读取商品列表\n4. 避免 props drilling"
    },
    {
        "file": "src/components/ProductList.vue",
        "severity": "warn",
        "category": "syntax",
        "description": "v-for 缺少 :key",
        "suggestion": "添加 :key=\"p.id\""
    }
]

architecture = {
    "tech_stack": {"framework": "Vue 3", "lang": "TypeScript"},
    "component_tree": [
        {"name": "ProductManage", "children": ["ProductList", "ProductForm"]}
    ],
    "file_list": [
        {"path": "src/views/ProductManage.vue", "file_type": "page", "description": "商品管理页"},
        {"path": "src/components/ProductList.vue", "file_type": "component", "description": "商品列表"},
        {"path": "src/components/ProductForm.vue", "file_type": "component", "description": "商品表单"},
    ],
    "data_flow": [
        {"from_component": "ProductManage", "to_component": "ProductList", "data_type": "products", "mechanism": "props"},
        {"from_component": "ProductManage", "to_component": "ProductForm", "data_type": "callback", "mechanism": "emit-event"},
    ]
}

state = {
    "code_files": code_files,
    "review": {"passed": False, "score": 55, "issues": issues},
    "architecture": architecture,
    "retry_count": 1,
    "max_retries": 3,
}

print("启动 AutoGen 三方讨论 (Coder × Reviewer × Architect)...")
result = autogen_discussion_node(state)

# 验证结果
assert "autogen_discussion" in result, "缺少 autogen_discussion 字段"
discussion = result["autogen_discussion"]
print(f"  完成状态: {discussion.get('completed')}")
print(f"  摘要: {discussion.get('summary', '')[:100]}")

context = discussion.get("context", "")
print(f"  讨论上下文长度: {len(context)} 字符")
if context:
    print(f"  讨论片段: {context[:200]}...")

# 验证 context 注入了 review
assert "autogen_context" in result.get("review", {}), "缺少 autogen_context"
print(f"  review.autogen_context 长度: {len(result['review']['autogen_context'])} 字符")

print()
print("=" * 50)
print("全部测试通过！")
print("=" * 50)
