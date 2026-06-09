
from workflow.code_gen_workflow import run_workflow

result = run_workflow(
    user_request="做一个个人博客网页",
    user_id="rain",
    app_id="demo",
    code_gen_type="html"
)

print(result)

