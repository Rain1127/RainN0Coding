"""
Builder Agent —— 构建验证

输入：code_files + images + project_dir
输出：{success, log, project_dir}
行为：零 LLM 调用 —— Coder 已通过工具写入文件，Builder 只补充脚手架 + 执行 npm build。
      本地无 Node.js 时自动降级为文件写入模式。

P0 质量门禁：Review 评分 >= 阈值 + 无 critical issue + 语法校验通过 → 才允许入库
反馈与入库在最终验收后由 workflow.validation_feedback 处理。
"""
import os
import json
import subprocess
import tempfile
import shutil
import glob as glob_mod
import shlex
from pathlib import Path
from agents.agent_logging import log_agent_fail, log_agent_ok, log_agent_start
from state.code_gen_state import CodeGenState
from config import get_lang_config, config
from workflow.build_status import build_result as make_build_result, verified


def _build_timeout(default=180):
    from workflow.budget import active_budget
    budget=active_budget.get()
    return min(default, budget.remaining_seconds()) if budget else default


def _source_snapshot(project_dir):
    import hashlib
    excluded = {'node_modules', '.git', '.venv', 'dist', 'build', 'target', '__pycache__'}
    metadata = {'prd.json', 'architecture.json', 'images.json', 'acceptance.json', 'review-coverage.json', '.generation-run-id'}
    result = {}
    for directory, dirs, names in os.walk(project_dir):
        dirs[:] = sorted(d for d in dirs if d not in excluded)
        for name in sorted(names):
            if name in metadata or name.endswith(('.pyc', '.log', '.tmp')):
                continue
            path = Path(directory, name)
            if path.is_symlink():
                raise ValueError('Source symlink is not supported')
            with path.open('rb') as handle:
                result[path.relative_to(project_dir).as_posix()] = hashlib.file_digest(handle, 'sha256').hexdigest()
    return result


def _syntax_command(template, *, files=(), **values):
    command=[]
    for part in shlex.split(template):
        if part == "{files}":
            command.extend(files)
        else:
            command.append(part.format(**values))
    return command


def _create_default_package_json(project_dir: str):
    """创建默认的 Vue 3 + Vite package.json"""
    pkg = {
        "name": "ai-generated-project",
        "version": "1.0.0",
        "private": True,
        "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
        "dependencies": {"vue": "^3.5.0", "vue-router": "^4.4.0", "pinia": "^2.2.0"},
        "devDependencies": {
            "@vitejs/plugin-vue": "^5.2.0", "typescript": "^5.6.0",
            "vite": "^6.0.0", "vue-tsc": "^2.2.0",
            "tailwindcss": "^3.4.0", "autoprefixer": "^10.4.0", "postcss": "^8.4.0",
        },
    }
    with open(os.path.join(project_dir, "package.json"), "w", encoding="utf-8") as f:
        json.dump(pkg, f, ensure_ascii=False, indent=2)


def _create_default_vite_config(project_dir: str):
    """创建默认 vite.config.ts"""
    config = """import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') }
  }
})
"""
    with open(os.path.join(project_dir, "vite.config.ts"), "w", encoding="utf-8") as f:
        f.write(config)


def _create_default_tailwind_config(project_dir: str):
    """创建默认 tailwind.config.js + postcss.config.js"""
    tailwind = """/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
"""
    postcss = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
"""
    with open(os.path.join(project_dir, "tailwind.config.js"), "w", encoding="utf-8") as f:
        f.write(tailwind)
    with open(os.path.join(project_dir, "postcss.config.js"), "w", encoding="utf-8") as f:
        f.write(postcss)


def _create_default_index_html(project_dir: str):
    """创建默认 index.html"""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Generated App</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
"""
    with open(os.path.join(project_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


# ========== P0 质量门禁 ==========

def _check_review_quality_gate(state: CodeGenState, threshold: int = 80) -> dict:
    """检查 Review 质量门禁。

    三个条件必须全部满足：
      1. review.passed == True
      2. review.score >= threshold
      3. 无 severity == "critical" 的 issue

    Returns:
        {passed, score, has_critical, reason}
    """
    review = state.get("review") or {}
    score = review.get("score", 0)
    passed = review.get("passed", False)
    issues = review.get("issues", [])

    has_critical = any(
        issue.get("severity") == "critical"
        for issue in issues
    )

    if not passed:
        return {
            "passed": False, "score": score, "has_critical": has_critical,
            "reason": f"review.passed=False (score={score})",
        }
    if not isinstance(score, (int, float)):
        return {
            "passed": False, "score": score, "has_critical": has_critical,
            "reason": "review score unavailable",
        }
    if score < threshold:
        return {
            "passed": False, "score": score, "has_critical": has_critical,
            "reason": f"review.score={score} < threshold={threshold}",
        }
    if has_critical:
        return {
            "passed": False, "score": score, "has_critical": True,
            "reason": "exist critical issues",
        }
    return {
        "passed": True, "score": score, "has_critical": False,
        "reason": "ok",
    }


def _run_syntax_check(project_dir: str, code_files: list, lang_config: dict) -> dict:
    """对非 npm 项目运行语言特定的语法/编译检查。

    支持两种模式：
      - 逐文件检查（如 Python py_compile）：逐个文件运行语法检查
      - 项目级检查（如 Java javac、Go vet）：在项目根目录运行编译命令

    工具不可用时返回 passed=False、tool_available=False，由 Builder 标记未验证。

    Returns:
        {passed, log, tool_available}
    """
    if not lang_config.get("needs_syntax_check"):
        return {"passed": True, "log": "[no syntax check needed]", "tool_available": True}

    cmd_template = lang_config.get("syntax_check_cmd", "")
    if not cmd_template:
        return {"passed": False, "log": "[no syntax check cmd configured]", "tool_available": False}

    per_file = lang_config.get("syntax_check_per_file", False)
    file_glob = lang_config.get("syntax_check_file_glob", None)
    timeout = lang_config.get("syntax_check_timeout", 60)

    if per_file:
        # === 逐文件检查模式 ===
        matching_files = []
        if file_glob:
            pattern = os.path.join(project_dir, "**", file_glob)
            matching_files = glob_mod.glob(pattern, recursive=True)
        else:
            for cf in code_files:
                fpath = os.path.join(project_dir, cf.get("path", ""))
                if os.path.isfile(fpath):
                    matching_files.append(fpath)

        if not matching_files:
            return {"passed": False, "log": "[no matching files for syntax check]", "tool_available": True}

        # 检查工具是否可用
        tool_name = cmd_template.split()[0]
        if not shutil.which(tool_name):
            return {
                "passed": False,
                "log": f"[{tool_name} not installed, syntax check skipped]",
                "tool_available": False,
            }

        all_errors = []
        for fpath in matching_files:
            cmd = _syntax_command(cmd_template, file=fpath, project_dir=project_dir)
            try:
                result = subprocess.run(
                    cmd, cwd=os.path.dirname(fpath) or project_dir,
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_build_timeout(timeout),
                )
                if result.returncode != 0:
                    all_errors.append(
                        f"FAIL {os.path.basename(fpath)}: "
                        f"{(result.stderr or result.stdout)[:300]}"
                    )
            except subprocess.TimeoutExpired:
                all_errors.append(f"TIMEOUT {os.path.basename(fpath)} ({timeout}s)")

        if all_errors:
            return {"passed": False, "log": "\n".join(all_errors), "tool_available": True}
        return {
            "passed": True,
            "log": f"[syntax check passed: {len(matching_files)} files]",
            "tool_available": True,
        }

    else:
        # === 项目级检查模式 ===
        tool_name = cmd_template.split()[0]
        if not shutil.which(tool_name):
            return {"passed": False, "log": f"[{tool_name} not installed]", "tool_available": False}
        tmpdir = tempfile.mkdtemp(prefix="syntax_check_")
        try:
            # 收集文件路径用于需要一次性传入所有文件的命令（如 javac）
            matching = []
            if file_glob:
                matching = glob_mod.glob(
                    os.path.join(project_dir, "**", file_glob), recursive=True)
                if not matching:
                    return {"passed": False, "log": "[no matching files for compile check]", "tool_available": True}
            cmd = _syntax_command(cmd_template, project_dir=project_dir, files=matching, tmpdir=tmpdir)
            result = subprocess.run(
                cmd, cwd=project_dir,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_build_timeout(timeout),
            )
            if result.returncode != 0:
                return {
                    "passed": False,
                    "log": f"compile failed:\n{(result.stderr or result.stdout)[:1000]}",
                    "tool_available": True,
                }
            return {
                "passed": True,
                "log": (result.stdout or "[compile passed]")[:500],
                "tool_available": True,
            }
        except FileNotFoundError:
            tool_name = cmd_template.split()[0]
            return {
                "passed": False,
                "log": f"[{tool_name} not installed, compile check skipped]",
                "tool_available": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "log": f"compile timeout ({timeout}s)",
                "tool_available": True,
            }
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def builder_agent(state: CodeGenState) -> CodeGenState:
    # ========== Builder Agent 主逻辑 ==========
    """Builder Agent 主逻辑 —— 补充脚手架 + 尝试构建。Coder 已通过工具写完文件。"""
    code_files = state.get("code_files", [])
    images = state.get("images", [])
    code_gen_type = state.get("code_gen_type", "vue_project")
    project_dir = state.get("project_dir", "")
    app_id = state.get("app_id", "")

    log_agent_start(
        "Builder Agent",
        f"正在构建项目，code_gen_type={code_gen_type} file_count={len(code_files)} project_dir={project_dir}",
    )

    if not code_files:
        state["error"] = "code_files 为空，Builder 无文件可构建"
        state["phase"] = "error"
        state["build_result"] = make_build_result("failed", state["error"], project_dir, "code")
        log_agent_fail("Builder Agent", "缺少 code_files，无法执行构建")
        return state

    if not project_dir or not os.path.isdir(project_dir):
        state["error"] = f"project_dir 不存在: {project_dir}"
        state["phase"] = "error"
        state["build_result"] = make_build_result("unverified", state["error"], project_dir, "environment")
        log_agent_fail("Builder Agent", f"project_dir 不存在，无法执行构建: {project_dir}")
        return state

    if code_gen_type == "html" and state.get("mode", "new") != "modify":
        entry = os.path.join(project_dir, "index.html")
        has_entry = any(
            f.get("path") == "index.html" and f.get("content", "").strip()
            for f in code_files
        )
        entry_ready = False
        if has_entry:
            try:
                with open(entry, encoding="utf-8-sig") as fh:
                    entry_ready = bool(fh.read().strip())
            except (OSError, UnicodeError):
                pass
        if not entry_ready:
            state["error"] = "HTML 构建缺少非空的根目录 index.html"
            state["phase"] = "error"
            state["build_result"] = make_build_result("failed", state["error"], project_dir, "code")
            log_agent_fail("Builder Agent", state["error"])
            return state

    try:
        from workflow.harness_policy import enabled
        strict_modify = enabled(state, 'editing') and state.get('mode') == 'modify'
        source_before_build = _source_snapshot(project_dir) if strict_modify else None
        if enabled(state, 'editing'):
            import hashlib
            from tools.path_guard import resolve_project_path
            for path, expected in state.get('coder_file_hashes', {}).items():
                full = Path(resolve_project_path(project_dir, path))
                if not full.is_file() or hashlib.sha256(full.read_bytes()).hexdigest() != expected:
                    state['build_result'] = make_build_result('unverified', '候选文件在审查后发生变更，请重新读取并审查：' + path, project_dir, 'conflict')
                    state['phase'] = 'build_done'
                    return state
        # 1. 写入图片 URL 映射
        if images:
            with open(os.path.join(project_dir, "images.json"), "w", encoding="utf-8") as fh:
                json.dump(images, fh, ensure_ascii=False, indent=2)

        lc = get_lang_config(code_gen_type)

        # Static HTML needs no Vue shell: a root scaffold would shadow src/index.html.
        # Only frontend projects that actually build with npm need these defaults.
        if lc.get("is_frontend") and lc.get("needs_npm_build"):
            if enabled(state, 'editing') and state.get('mode') == 'modify':
                required = ['package.json', 'index.html']
                if not any(os.path.exists(os.path.join(project_dir, name)) for name in ('vite.config.ts', 'vite.config.js')):
                    required.append('vite.config.ts')
                missing = [name for name in required if not os.path.isfile(os.path.join(project_dir, name))]
                if missing:
                    state['build_result'] = make_build_result('unverified', '待确认：修改模式缺少构建配置，需要先扩展修改计划：' + ','.join(missing), project_dir, 'specification')
                    state['phase'] = 'build_done'
                    return state
            if not os.path.exists(os.path.join(project_dir, "package.json")):
                _create_default_package_json(project_dir)
            if not os.path.exists(os.path.join(project_dir, "vite.config.ts")) and \
               not os.path.exists(os.path.join(project_dir, "vite.config.js")):
                _create_default_vite_config(project_dir)
            if not os.path.exists(os.path.join(project_dir, "tailwind.config.js")) and not (enabled(state, 'editing') and state.get('mode') == 'modify'):
                _create_default_tailwind_config(project_dir)
            if not os.path.exists(os.path.join(project_dir, "index.html")):
                _create_default_index_html(project_dir)

        # 3. 仅需要对 npm build 的项目执行构建
        build_status = "not_required"
        failure_kind = None
        build_log = ""
        build_log_mode = "unknown"
        if lc.get("needs_npm_build"):
            from workflow.execution import execution_request, executor
            build_status = "succeeded"
            backend = executor(state)
            install_profile = 'npm-install'
            if strict_modify:
                install_profile = ('npm-install-locked' if os.path.isfile(os.path.join(project_dir, 'package-lock.json'))
                                   else 'npm-install-preserve')
            result = backend.run(execution_request(state, install_profile, _build_timeout()))
            build_log_mode = "npm_install_failed"
            if result.status == 'succeeded':
                # Vite assets must resolve under the app's preview/publish directory.
                profile = 'vite-build' if lc.get('is_frontend') else 'npm-build'
                result = backend.run(execution_request(state, profile, _build_timeout()))
                build_log_mode = 'npm_build' if result.status == 'succeeded' else 'npm_build_failed'
            build_status = 'failed' if result.status == 'cancelled' else result.status
            failure_kind = result.failure_kind
            build_log = result.log[-1000:] if result.status == 'succeeded' else result.log[-8000:]
            if not build_log:
                build_log = f'[{result.backend}: {result.status}, {result.failure_kind or build_log_mode}]'
        else:
            build_log = f"[{code_gen_type} 项目无需 npm build，文件已就绪]"
            build_log_mode = "no_npm_build"

        state["build_result"] = make_build_result(build_status, build_log, project_dir, failure_kind)
        state["phase"] = "build_done"
        log_agent_ok(
            "Builder Agent",
            f"构建阶段完成，status={build_status} log_mode={build_log_mode}",
        )

        # === 3.5 质量门禁 (P0) ===
        lc = get_lang_config(code_gen_type)

        review_gate = _check_review_quality_gate(state, config.QUALITY_SCORE_THRESHOLD)
        isolated_syntax = enabled(state, 'executor') and lc.get('needs_syntax_check')
        if isolated_syntax:
            from workflow.execution import execution_request, executor
            syntax = executor(state).run(execution_request(state, f'{code_gen_type}-syntax', lc.get('syntax_check_timeout', 60)))
            syntax_result = {'passed': syntax.status == 'succeeded', 'log': syntax.log, 'tool_available': syntax.status != 'unverified'}
        else:
            syntax_result = _run_syntax_check(project_dir, code_files, lc)

        if lc.get("needs_syntax_check") and not lc.get("needs_npm_build"):
            build_status = ("unverified" if not syntax_result["tool_available"] else
                            "succeeded" if syntax_result["passed"] else "failed")
            failure_kind = ("environment" if not syntax_result["tool_available"] else
                            "timeout" if "TIMEOUT" in syntax_result["log"] or "timeout" in syntax_result["log"] else
                            "code" if not syntax_result["passed"] else None)
            if isolated_syntax:
                failure_kind = syntax.failure_kind
            state["build_result"] = make_build_result(build_status, syntax_result["log"], project_dir, failure_kind)
        if source_before_build is not None:
            after = _source_snapshot(project_dir)
            changed = sorted(p for p in source_before_build.keys() | after.keys() if source_before_build.get(p) != after.get(p))
            allowed = set((state.get('change_plan') or {}).get('files', []))
            unexpected = [path for path in changed if path not in allowed]
            state['build_scope_result'] = {'changed': changed, 'unexpected': unexpected}
            if unexpected:
                state['build_result'] = make_build_result('unverified', '构建改动了计划外源文件，候选已保留：' + ','.join(unexpected), project_dir, 'conflict')
                return state
        build_success = verified(state["build_result"])

        quality_gate_passed = review_gate["passed"] and syntax_result["passed"]

        gate_reason_parts = []
        if not review_gate["passed"]:
            gate_reason_parts.append(review_gate["reason"])
        if not syntax_result["passed"]:
            gate_reason_parts.append(
                f"syntax: {syntax_result['log'][:150]}")
        elif not syntax_result["tool_available"]:
            gate_reason_parts.append(
                f"syntax tool unavailable: {syntax_result['log'][:100]}")

        state["quality_gate_result"] = {
            "passed": quality_gate_passed,
            "review_score": review_gate["score"],
            "has_critical_issues": review_gate["has_critical"],
            "syntax_check_passed": syntax_result["passed"],
            "syntax_log": syntax_result["log"][:500],
            "reason": "; ".join(gate_reason_parts) if gate_reason_parts else "ok",
        }
        if quality_gate_passed:
            log_agent_ok(
                "Builder Agent",
                f"质量门禁通过，review_score={review_gate['score']} "
                f"syntax_passed={'yes' if syntax_result['passed'] else 'no'} "
                f"reason={state['quality_gate_result']['reason']}",
            )
        else:
            log_agent_fail(
                "Builder Agent",
                f"质量门禁未通过，review_score={review_gate['score']} "
                f"syntax_passed={'yes' if syntax_result['passed'] else 'no'} "
                f"reason={state['quality_gate_result']['reason']}",
            )

        # Publication and RAG evidence are handled after runtime acceptance.
        state["indexing_result"] = {"success": False, "message": "等待最终验收与版本发布",
                                    "indexed_count": 0, "total_count": len(code_files)}

        log_agent_ok(
            "Builder Agent",
            f"构建结束，build_success={'yes' if build_success else 'no'} "
            f"quality_gate={'passed' if state.get('quality_gate_result', {}).get('passed') else 'failed'} "
            f"files={len(code_files)} project_dir={project_dir}",
        )
        return state

    except Exception as e:
        state["build_result"] = make_build_result("failed", str(e), project_dir, "environment")
        state["phase"] = "build_done"
        state["error"] = str(e)
        log_agent_fail("Builder Agent", f"构建异常，原因={e}")
        return state
