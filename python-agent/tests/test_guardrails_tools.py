import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import create_file, delete_file, modify_file, read_file


pytestmark = [pytest.mark.integration, pytest.mark.harness]


def test_create_file_blocks_project_escape(tool_context):
    with tool_context(app_id="app-1", user_role="user"):
        result = create_file.invoke({"path": "../escape.txt", "content": "bad"})
        assert "guardrail_blocked" in result


def test_delete_file_blocks_protected_package_json_for_admin(tool_context):
    with tool_context(app_id="app-2", user_role="admin"):
        create_file.invoke({"path": "package.json", "content": "{}"})
        result = delete_file.invoke({"path": "package.json"})
        assert "guardrail_blocked" in result


def test_modify_file_warns_for_entrypoint_change_but_continues(tool_context):
    with tool_context(app_id="app-3", user_role="user"):
        create_file.invoke({"path": "src/main.ts", "content": "console.log('a')"})
        result = modify_file.invoke(
            {
                "path": "src/main.ts",
                "old_content": "console.log('a')",
                "new_content": "console.log('b')",
            }
        )

        assert "成功" in result
        content = read_file.invoke({"path": "src/main.ts"})
        assert "console.log('b')" in content
