import os
import pytest

if __name__ != "__main__" and os.getenv("RUN_LIVE_LLM_TESTS") != "1":
    pytest.skip("manual live LLM script; set RUN_LIVE_LLM_TESTS=1 to collect", allow_module_level=True)

from workflow.code_gen_workflow import run_workflow

result = run_workflow(
    user_request="做一个个人博客网页",
    user_id="rain",
    app_id="demo",
    code_gen_type="html"
)

print(result)

