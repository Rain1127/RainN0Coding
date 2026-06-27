"""工具集独立测试 —— 验证 6 个工具的基本功能"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import (
    create_file, read_file, modify_file, delete_file,
    list_files, exit_tool, set_tool_context, get_all_tools, get_tool_by_name,
)


def test_tool_registry():
    """验证工具注册"""
    tools = get_all_tools()
    assert len(tools) == 6, f"期望 6 个工具，实际 {len(tools)}"
    names = {t.name for t in tools}
    expected = {"create_file", "read_file", "modify_file", "delete_file", "list_files", "exit_tool"}
    assert names == expected, f"工具名不匹配: {names}"

    for name in expected:
        t = get_tool_by_name(name)
        assert t is not None, f"按名查找失败: {name}"

    print("[PASS] test_tool_registry")


def test_create_and_read():
    """验证创建 + 读取文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        # 创建
        r = create_file.invoke({"path": "src/App.vue", "content": "<template>\n  <div>Hello</div>\n</template>"})
        assert "成功" in r, f"创建失败: {r}"
        assert os.path.exists(os.path.join(tmpdir, "src", "App.vue"))

        # 读取
        content = read_file.invoke({"path": "src/App.vue"})
        assert "Hello" in content, f"读取内容不正确: {content}"

        # 读取不存在的文件
        r2 = read_file.invoke({"path": "nonexistent.txt"})
        assert "不存在" in r2, f"应该报不存在: {r2}"

    print("[PASS] test_create_and_read")


def test_modify_file():
    """验证文件修改"""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        create_file.invoke({"path": "src/main.ts", "content": "import Vue from 'vue'\nVue.config.productionTip = false"})

        # 正常修改
        r = modify_file.invoke({
            "path": "src/main.ts",
            "old_content": "import Vue from 'vue'",
            "new_content": "import { createApp } from 'vue'",
        })
        assert "成功" in r, f"修改失败: {r}"

        content = read_file.invoke({"path": "src/main.ts"})
        assert "createApp" in content
        assert "import Vue from 'vue'" not in content

        # 修改不存在的文件
        r2 = modify_file.invoke({"path": "no.txt", "old_content": "a", "new_content": "b"})
        assert "不存在" in r2, f"应该报不存在: {r2}"

        # 旧内容未找到
        r3 = modify_file.invoke({"path": "src/main.ts", "old_content": "this text does not exist", "new_content": "x"})
        assert "未找到" in r3, f"应该报未找到: {r3}"

    print("[PASS] test_modify_file")


def test_delete_file():
    """验证文件删除 + 重要文件保护"""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        # 创建普通文件并删除
        create_file.invoke({"path": "utils/helpers.ts", "content": "export const foo = 1"})
        r = delete_file.invoke({"path": "utils/helpers.ts"})
        assert "成功" in r, f"删除失败: {r}"
        assert not os.path.exists(os.path.join(tmpdir, "utils", "helpers.ts"))

        # 删除不存在的文件
        r2 = delete_file.invoke({"path": "ghost.txt"})
        assert "不存在" in r2, f"应该报不存在: {r2}"

        # 保护 package.json
        create_file.invoke({"path": "package.json", "content": "{}"})
        r3 = delete_file.invoke({"path": "package.json"})
        assert "不允许删除重要文件" in r3, f"应该被保护: {r3}"
        assert os.path.exists(os.path.join(tmpdir, "package.json"))

        # 保护 vite.config.ts
        create_file.invoke({"path": "vite.config.ts", "content": "export default {}"})
        r4 = delete_file.invoke({"path": "vite.config.ts"})
        assert "不允许删除重要文件" in r4, f"应该被保护: {r4}"

    print("[PASS] test_delete_file")


def test_list_files():
    """验证目录列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        # 创建文件结构
        create_file.invoke({"path": "src/App.vue", "content": "<template></template>"})
        create_file.invoke({"path": "src/components/Header.vue", "content": "<template>Header</template>"})
        create_file.invoke({"path": "src/components/Footer.vue", "content": "<template>Footer</template>"})
        create_file.invoke({"path": "src/main.ts", "content": "import App from './App.vue'"})

        r = list_files.invoke({"dir_path": ""})
        assert "App.vue" in r, f"应该包含 App.vue: {r}"
        assert "Header.vue" in r, f"应该包含 Header.vue: {r}"
        assert "Footer.vue" in r, f"应该包含 Footer.vue: {r}"
        assert "main.ts" in r, f"应该包含 main.ts: {r}"

        # 子目录
        r2 = list_files.invoke({"dir_path": "src/components"})
        assert "Header.vue" in r2
        assert "Footer.vue" in r2
        assert "App.vue" not in r2  # 不在这个子目录

        # 不存在的目录
        r3 = list_files.invoke({"dir_path": "ghost_dir"})
        assert "不存在" in r3, f"应该报不存在: {r3}"

    print("[PASS] test_list_files")


def test_exit_tool():
    """验证退出工具"""
    r = exit_tool.invoke({})
    assert "不要继续调用工具" in r or "可以输出" in r, f"退出消息不正确: {r}"
    print("[PASS] test_exit_tool")


def test_path_safety():
    """验证路径安全：禁止逃逸工作目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        set_tool_context(tmpdir, "test_app")

        # 尝试用 .. 逃逸
        r = create_file.invoke({"path": "../escaped.txt", "content": "evil"})
        assert "禁止" in r or "失败" in r, f"路径逃逸应该被阻止: {r}"
        assert not os.path.exists(os.path.join(tmpdir, "..", "escaped.txt"))

    print("[PASS] test_path_safety")


if __name__ == "__main__":
    test_tool_registry()
    test_create_and_read()
    test_modify_file()
    test_delete_file()
    test_list_files()
    test_exit_tool()
    test_path_safety()
    print("\n全部工具测试通过！")
