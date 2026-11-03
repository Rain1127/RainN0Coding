import pytest

from workflow.runtime_validation import validate_page, acceptance_contract


def run(tmp_path, html, contract=None):
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text(html, encoding="utf-8")
    result = validate_page(root, contract or acceptance_contract("页面"), report_dir=tmp_path / "report", timeout_ms=1500)
    if result["status"] == "unverified":
        pytest.fail("Browser infrastructure unavailable: " + result["log"])
    return result


@pytest.mark.parametrize("html,expected", [
    ("<html><body></body></html>", "Blank page"),
    ("<h1>Hello</h1><script>throw Error('critical script')</script>", "critical script"),
    ('<h1>Hello</h1><script src="/missing.js"></script>', "HTTP 404"),
])
def test_runtime_failures_are_not_passes(tmp_path, html, expected):
    result = run(tmp_path, html)
    assert result["status"] == "failed"
    assert expected in result["log"]
    assert result["screenshot"].endswith("failure.png")


def test_dead_button_fails(tmp_path):
    contract = {"version": "button-v1", "steps": [{"action": "click_change", "selector": "button"}]}
    result = run(tmp_path, "<h1>Hello</h1><button>Save</button>", contract)
    assert result["status"] == "failed"
    assert result["interaction_status"] == "unverified"


def test_interaction_success(tmp_path):
    contract = {"version": "button-v1", "steps": [{"action": "click_change", "selector": "button"}]}
    result = run(tmp_path, '<h1>Hello</h1><button onclick="this.textContent=\'Saved\'">Save</button>', contract)
    assert result["status"] == "succeeded"
    assert result["interaction_status"] == "passed"


def test_real_vue_bundle_loads_and_interacts(tmp_path):
    import json
    import os
    import subprocess
    from pathlib import Path
    repo=Path(__file__).resolve().parents[2]
    vite=repo / "RainN0Coding-frontend/node_modules/vite/bin/vite.js"
    if not vite.is_file():
        pytest.skip("frontend node_modules not installed")
    project=tmp_path / "vue"
    project.mkdir()
    vue=repo / "RainN0Coding-frontend/node_modules/vue/dist/vue.runtime.esm-bundler.js"
    relative=os.path.relpath(vue, project).replace("\\", "/")
    (project / "index.html").write_text('<div id="app"></div><script type="module" src="./main.js"></script>')
    (project / "main.js").write_text("import {createApp,h,ref} from " + json.dumps(relative) + ";createApp({setup(){const n=ref(0);return()=>h('button',{onClick:()=>n.value++},'Count '+n.value)}}).mount('#app')")
    build=subprocess.run(["node",str(vite),"build",str(project),"--base=./"],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30)
    assert build.returncode==0, build.stderr
    result=validate_page(project / "dist", {"version":"vue-counter-v1","steps":[{"action":"click_change","selector":"button"}]},
                         report_dir=tmp_path / "vue-report")
    assert result["status"]=="succeeded", result["log"]
