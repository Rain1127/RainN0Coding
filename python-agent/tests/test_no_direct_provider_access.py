from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = [
    path for path in ROOT.rglob("*.py") if "tests" not in path.parts
]


def test_python_agent_has_no_provider_credentials_or_urls():
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in PRODUCTION_FILES
    )
    for forbidden in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "ZHIPU_API_KEY",
        "ZHIPU_BASE_URL",
        "api.deepseek.com",
        "open.bigmodel.cn",
    ):
        assert forbidden not in combined
