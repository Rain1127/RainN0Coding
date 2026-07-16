"""端到端测试：完整 7 Agent 工作流"""
import sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__" and os.getenv("RUN_LIVE_LLM_TESTS") != "1":
    pytest.skip("manual live LLM script; set RUN_LIVE_LLM_TESTS=1 to collect", allow_module_level=True)

from workflow.code_gen_workflow import run_workflow

print("=" * 60)
print("Starting full workflow: PM -> Arch -> Coder+Images -> Reviewer -> Builder")
print("=" * 60)

result = run_workflow("做一个简单的登录页面，包含用户名、密码输入框和登录按钮", "demo", "e2e-test")

print("\n" + "=" * 60)
print("FULL WORKFLOW COMPLETE")
print("=" * 60)

# PRD
prd = result.get("prd") or {}
print(f"\n[PM]     {prd.get('page_name', '?')}, {len(prd.get('features', []))} features")

# Arch
arch = result.get("architecture") or {}
print(f"[Arch]   {len(arch.get('component_tree', []))} components, {len(arch.get('file_list', []))} files")

# Code
files = result.get("code_files", [])
print(f"[Coder]  {len(files)} files generated")
for f in files:
    print(f"         {f.get('path', '?')} ({len(f.get('content', '').split(chr(10)))} lines)")

# Images
imgs = result.get("images", [])
print(f"[Images] {len(imgs)} images collected")

# Review
review = result.get("review") or {}
status = "PASS" if review.get("passed") else "FAIL"
print(f"[Review] {review.get('score', '?')}/100 {status}, retry={result.get('retry_count', '?')}")

# Build
build = result.get("build_result") or {}
bstatus = "OK" if build.get("success") else "FAIL"
print(f"[Build]  {bstatus}")

# Final
final = result.get("final_result") or {}
phase = result.get("phase", "?")
error = result.get("error")
print(f"\n[Final]  phase={phase}, error={error}")

if final.get("review_passed"):
    print("RESULT: Code passed review and built successfully!")
elif result.get("retry_count", 0) >= result.get("max_retries", 3):
    print(f"RESULT: Max retries ({result.get('max_retries')}) reached, human intervention needed")
else:
    print(f"RESULT: Workflow ended at phase={phase}")
