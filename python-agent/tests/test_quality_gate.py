"""单元测试：P0 质量门禁"""
import pytest
import os
import tempfile
import sys

# Ensure python-agent root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.builder_agent import _check_review_quality_gate, _run_syntax_check


# ========== _check_review_quality_gate ==========

class TestCheckReviewQualityGate:

    def test_passes_high_score(self):
        """高评分 + passed=True + 无 critical → 通过"""
        state = {
            "review": {
                "passed": True,
                "score": 90,
                "issues": [{"severity": "warn", "category": "style", "description": "indent"}],
            }
        }
        result = _check_review_quality_gate(state, threshold=80)
        assert result["passed"] is True
        assert result["score"] == 90
        assert result["has_critical"] is False
        assert result["reason"] == "ok"

    def test_fails_low_score(self):
        """低评分 → 失败"""
        state = {
            "review": {
                "passed": False,
                "score": 65,
                "issues": [],
            }
        }
        result = _check_review_quality_gate(state, threshold=80)
        assert result["passed"] is False
        assert "review.passed=False" in result["reason"]

    def test_fails_passed_false_even_high_score(self):
        """passed=False 即使 score >= 80 也失败"""
        state = {
            "review": {
                "passed": False,
                "score": 85,
                "issues": [],
            }
        }
        result = _check_review_quality_gate(state, threshold=80)
        assert result["passed"] is False
        assert "review.passed=False" in result["reason"]

    def test_fails_critical_issue(self):
        """存在 critical issue → 失败"""
        state = {
            "review": {
                "passed": True,
                "score": 90,
                "issues": [
                    {"severity": "critical", "category": "security", "description": "XSS"},
                ],
            }
        }
        result = _check_review_quality_gate(state, threshold=80)
        assert result["passed"] is False
        assert result["has_critical"] is True
        assert "critical" in result["reason"]

    def test_fails_score_below_threshold(self):
        """score < threshold，但 passed=True → 失败（硬阈值）"""
        state = {
            "review": {
                "passed": True,
                "score": 78,
                "issues": [],
            }
        }
        result = _check_review_quality_gate(state, threshold=80)
        assert result["passed"] is False
        assert "score=78 < threshold=80" in result["reason"]

    def test_empty_review_defaults_to_fail(self):
        """review 为空 → 失败"""
        state = {}
        result = _check_review_quality_gate(state, threshold=80)
        assert result["passed"] is False
        assert result["score"] == 0

    def test_no_issues_field(self):
        """review 有 passed+score 但无 issues 字段 → 通过"""
        state = {
            "review": {"passed": True, "score": 88}
        }
        result = _check_review_quality_gate(state, threshold=80)
        assert result["passed"] is True

    def test_custom_threshold(self):
        """自定义阈值"""
        state = {
            "review": {"passed": True, "score": 75, "issues": []}
        }
        assert _check_review_quality_gate(state, threshold=70)["passed"] is True
        assert _check_review_quality_gate(state, threshold=80)["passed"] is False


# ========== _run_syntax_check ==========

class TestRunSyntaxCheck:

    def test_skip_when_needs_syntax_check_false(self):
        """不需要语法检查时跳过"""
        lang_config = {"needs_syntax_check": False}
        result = _run_syntax_check("/tmp/test", [], lang_config)
        assert result["passed"] is True
        assert "no syntax check" in result["log"]

    def test_skip_when_no_cmd(self):
        """未配置命令时跳过"""
        lang_config = {"needs_syntax_check": True, "syntax_check_cmd": ""}
        result = _run_syntax_check("/tmp/test", [], lang_config)
        assert result["passed"] is True

    def test_per_file_syntax_pass(self):
        """逐文件模式 — Python 语法通过"""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_py = os.path.join(tmpdir, "hello.py")
            with open(valid_py, "w") as f:
                f.write("print('hello')\n")

            lang_config = {
                "needs_syntax_check": True,
                "syntax_check_cmd": 'python -m py_compile "{file}"',
                "syntax_check_file_glob": "*.py",
                "syntax_check_per_file": True,
                "syntax_check_timeout": 30,
            }
            result = _run_syntax_check(tmpdir, [], lang_config)
            assert result["passed"] is True
            assert "syntax check passed" in result["log"]

    def test_per_file_syntax_fail(self):
        """逐文件模式 — Python 语法失败"""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_py = os.path.join(tmpdir, "bad.py")
            with open(invalid_py, "w") as f:
                f.write("if True\n    pass\n")  # 缺少冒号 → SyntaxError

            lang_config = {
                "needs_syntax_check": True,
                "syntax_check_cmd": 'python -m py_compile "{file}"',
                "syntax_check_file_glob": "*.py",
                "syntax_check_per_file": True,
                "syntax_check_timeout": 30,
            }
            result = _run_syntax_check(tmpdir, [], lang_config)
            assert result["passed"] is False
            assert "FAIL" in result["log"]

    def test_tool_not_installed_graceful_degrade(self):
        """工具未安装 → 降级通过"""
        lang_config = {
            "needs_syntax_check": True,
            "syntax_check_cmd": 'nonexistent_tool_xyz "{file}"',
            "syntax_check_file_glob": "*.py",
            "syntax_check_per_file": True,
            "syntax_check_timeout": 10,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_py = os.path.join(tmpdir, "dummy.py")
            with open(dummy_py, "w") as f:
                f.write("# dummy\n")
            result = _run_syntax_check(tmpdir, [], lang_config)
            assert result["passed"] is True
            assert result["tool_available"] is False
            assert "not installed" in result["log"]

    def test_no_matching_files(self):
        """无匹配文件时通过"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lang_config = {
                "needs_syntax_check": True,
                "syntax_check_cmd": 'python -m py_compile "{file}"',
                "syntax_check_file_glob": "*.py",
                "syntax_check_per_file": True,
                "syntax_check_timeout": 10,
            }
            result = _run_syntax_check(tmpdir, [], lang_config)
            assert result["passed"] is True
            assert "no matching files" in result["log"]

    def test_project_level_go_vet(self):
        """项目级模式 — Go 语法检查命令格式正确"""
        lang_config = {
            "needs_syntax_check": True,
            "syntax_check_cmd": 'go vet ./...',
            "syntax_check_file_glob": None,
            "syntax_check_per_file": False,
            "syntax_check_timeout": 10,
        }
        # go vet 在非 Go 项目目录下会失败，这里只验证逻辑不抛异常
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_syntax_check(tmpdir, [], lang_config)
            # go vet 可能返回 passed=True (工具未安装) 或 passed=False (目录非 Go 项目)
            # 只要不抛异常即可
            assert isinstance(result["passed"], bool)
            assert "log" in result
            assert "tool_available" in result
