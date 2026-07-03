"""Standalone tests for Python-side file tools."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import (
    create_file,
    delete_file,
    exit_tool,
    get_all_tools,
    get_tool_by_name,
    list_files,
    modify_file,
    read_file,
    set_tool_context,
)


pytestmark = [pytest.mark.integration, pytest.mark.harness]


def test_tool_registry():
    tools = get_all_tools()
    assert len(tools) == 6
    names = {t.name for t in tools}
    expected = {"create_file", "read_file", "modify_file", "delete_file", "list_files", "exit_tool"}
    assert names == expected

    for name in expected:
        assert get_tool_by_name(name) is not None


def test_create_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        result = create_file.invoke({"path": "src/App.vue", "content": "<template>\n  <div>Hello</div>\n</template>"})
        assert "成功" in result
        assert os.path.exists(os.path.join(tmpdir, "src", "App.vue"))

        content = read_file.invoke({"path": "src/App.vue"})
        assert "Hello" in content

        missing = read_file.invoke({"path": "nonexistent.txt"})
        assert "不存在" in missing


def test_modify_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        create_file.invoke({"path": "src/main.ts", "content": "import Vue from 'vue'\nVue.config.productionTip = false"})

        result = modify_file.invoke(
            {
                "path": "src/main.ts",
                "old_content": "import Vue from 'vue'",
                "new_content": "import { createApp } from 'vue'",
            }
        )
        assert "成功" in result

        content = read_file.invoke({"path": "src/main.ts"})
        assert "createApp" in content
        assert "import Vue from 'vue'" not in content

        missing = modify_file.invoke({"path": "no.ts", "old_content": "a", "new_content": "b"})
        assert "不存在" in missing

        not_found = modify_file.invoke({"path": "src/main.ts", "old_content": "this text does not exist", "new_content": "x"})
        assert "未找到" in not_found


def test_delete_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app", "admin")

        create_file.invoke({"path": "utils/helpers.ts", "content": "export const foo = 1"})
        result = delete_file.invoke({"path": "utils/helpers.ts"})
        assert "成功" in result
        assert not os.path.exists(os.path.join(tmpdir, "utils", "helpers.ts"))

        missing = delete_file.invoke({"path": "ghost.txt"})
        assert "不存在" in missing

        create_file.invoke({"path": "package.json", "content": "{}"})
        protected = delete_file.invoke({"path": "package.json"})
        assert "guardrail_blocked" in protected
        assert os.path.exists(os.path.join(tmpdir, "package.json"))

        create_file.invoke({"path": "vite.config.ts", "content": "export default {}"})
        protected_vite = delete_file.invoke({"path": "vite.config.ts"})
        assert "guardrail_blocked" in protected_vite


def test_list_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        create_file.invoke({"path": "src/App.vue", "content": "<template></template>"})
        create_file.invoke({"path": "src/components/Header.vue", "content": "<template>Header</template>"})
        create_file.invoke({"path": "src/components/Footer.vue", "content": "<template>Footer</template>"})
        create_file.invoke({"path": "src/main.ts", "content": "import App from './App.vue'"})

        result = list_files.invoke({"dir_path": ""})
        assert "App.vue" in result
        assert "Header.vue" in result
        assert "Footer.vue" in result
        assert "main.ts" in result

        subdir = list_files.invoke({"dir_path": "src/components"})
        assert "Header.vue" in subdir
        assert "Footer.vue" in subdir
        assert "App.vue" not in subdir

        missing = list_files.invoke({"dir_path": "ghost_dir"})
        assert "不存在" in missing


def test_exit_tool():
    result = exit_tool.invoke({})
    assert "不要继续调用工具" in result or "可以输出" in result


def test_path_safety():
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        result = create_file.invoke({"path": "../escaped.txt", "content": "evil"})
        assert "guardrail_blocked" in result or "禁止" in result or "失败" in result
        assert not os.path.exists(os.path.join(tmpdir, "..", "escaped.txt"))
