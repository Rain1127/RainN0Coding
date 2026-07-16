import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import workflow.code_gen_workflow as workflow_module


def test_run_workflow_uses_async_graph_api(monkeypatch):
    expected = {"phase": "completed", "final_status": "success"}

    class FakeCompiled:
        async def ainvoke(self, initial, config):
            assert initial["user_request"] == "hello"
            assert config["configurable"]["thread_id"] == "user_app"
            return expected

        def invoke(self, *_args, **_kwargs):
            raise AssertionError("sync graph API must not be used for async nodes")

    class FakeWorkflow:
        def compile(self, checkpointer):
            assert checkpointer is not None
            return FakeCompiled()

    monkeypatch.setattr(workflow_module, "create_code_gen_workflow", lambda: FakeWorkflow())

    result = workflow_module.run_workflow("hello", user_id="user", app_id="app")

    assert result == expected
