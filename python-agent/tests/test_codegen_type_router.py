import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.codegen_type_router import normalize_code_gen_type, route_code_gen_type


class DummyResult:
    def __init__(self, code_gen_type: str):
        self.code_gen_type = code_gen_type


def test_normalize_code_gen_type_supports_uppercase_enum_name():
    assert normalize_code_gen_type("VUE_PROJECT") == "vue_project"
    assert normalize_code_gen_type("MULTI_FILE") == "multi_file"


def test_normalize_code_gen_type_returns_none_for_unknown_value():
    assert normalize_code_gen_type("desktop_app") is None


def test_route_code_gen_type_normalizes_llm_output(monkeypatch):
    def fake_parser(messages, user_id=None):
        return DummyResult("HTML")

    monkeypatch.setattr("server.codegen_type_router._route_parser", fake_parser)

    assert route_code_gen_type("做一个简单落地页") == "html"


def test_route_code_gen_type_falls_back_to_vue_project_on_invalid_result(monkeypatch):
    def fake_parser(messages, user_id=None):
        return DummyResult("desktop_app")

    monkeypatch.setattr("server.codegen_type_router._route_parser", fake_parser)

    assert route_code_gen_type("做一个后台系统") == "vue_project"


def test_route_code_gen_type_falls_back_to_vue_project_on_exception(monkeypatch):
    def fake_parser(messages, user_id=None):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("server.codegen_type_router._route_parser", fake_parser)

    assert route_code_gen_type("做一个管理系统") == "vue_project"
