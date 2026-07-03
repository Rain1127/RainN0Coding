"""
Builder Agent —— 构建验证

输入：code_files + images + project_dir
输出：{success, log, project_dir}
行为：零 LLM 调用 —— Coder 已通过工具写入文件，Builder 只补充脚手架 + 执行 npm build。
      本地无 Node.js 时自动降级为文件写入模式。

P0 质量门禁：Review 评分 >= 阈值 + 无 critical issue + 语法校验通过 → 才允许入库
P2 反馈闭环：构建完成后根据结果更新检索过的 code_store 条目质量分
"""
import os
import json
import subprocess
import tempfile
import shutil
import glob as glob_mod
from agents.agent_logging import log_agent_fail, log_agent_ok, log_agent_start
from state.code_gen_state import CodeGenState
from config import get_lang_config, config
from rag.rag_builder import index_code_files


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

    工具不可用时降级通过（passed=True, tool_available=False）。

    Returns:
        {passed, log, tool_available}
    """
    if not lang_config.get("needs_syntax_check"):
        return {"passed": True, "log": "[no syntax check needed]", "tool_available": True}

    cmd_template = lang_config.get("syntax_check_cmd", "")
    if not cmd_template:
        return {"passed": True, "log": "[no syntax check cmd configured]", "tool_available": True}

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
            return {"passed": True, "log": "[no matching files for syntax check]", "tool_available": True}

        # 检查工具是否可用
        tool_name = cmd_template.split()[0]
        if not shutil.which(tool_name):
            return {
                "passed": True,
                "log": f"[{tool_name} not installed, syntax check skipped]",
                "tool_available": False,
            }

        all_errors = []
        for fpath in matching_files:
            cmd = cmd_template.format(file=fpath, project_dir=project_dir)
            try:
                result = subprocess.run(
                    cmd, shell=True, cwd=os.path.dirname(fpath) or project_dir,
                    capture_output=True, text=True, timeout=timeout,
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
        # 检查工具是否可用
        tool_name = cmd_template.split()[0]
        if not shutil.which(tool_name):
            return {
                "passed": True,
                "log": f"[{tool_name} not installed, compile check skipped]",
                "tool_available": False,
            }

        tmpdir = tempfile.mkdtemp(prefix="syntax_check_")
        try:
            # 收集文件路径用于需要一次性传入所有文件的命令（如 javac）
            files_str = ""
            if file_glob:
                matching = glob_mod.glob(
                    os.path.join(project_dir, "**", file_glob), recursive=True)
                files_str = " ".join(f'"{f}"' for f in matching) if matching else ""

            cmd = cmd_template.format(
                project_dir=project_dir, files=files_str, tmpdir=tmpdir)
            result = subprocess.run(
                cmd, shell=True, cwd=project_dir,
                capture_output=True, text=True, timeout=timeout,
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
                "passed": True,
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
        log_agent_fail("Builder Agent", "缺少 code_files，无法执行构建")
        return state

    if not project_dir or not os.path.isdir(project_dir):
        state["error"] = f"project_dir 不存在: {project_dir}"
        state["phase"] = "error"
        log_agent_fail("Builder Agent", f"project_dir 不存在，无法执行构建: {project_dir}")
        return state

    try:
        # 1. 写入图片 URL 映射
        if images:
            with open(os.path.join(project_dir, "images.json"), "w", encoding="utf-8") as fh:
                json.dump(images, fh, ensure_ascii=False, indent=2)

        lc = get_lang_config(code_gen_type)

        # 2. 前端项目补充脚手架文件（Coder 可能未生成配置文件）
        if lc.get("is_frontend"):
            if not os.path.exists(os.path.join(project_dir, "package.json")):
                _create_default_package_json(project_dir)
            if not os.path.exists(os.path.join(project_dir, "vite.config.ts")) and \
               not os.path.exists(os.path.join(project_dir, "vite.config.js")):
                _create_default_vite_config(project_dir)
            if not os.path.exists(os.path.join(project_dir, "tailwind.config.js")):
                _create_default_tailwind_config(project_dir)
            if not os.path.exists(os.path.join(project_dir, "index.html")):
                _create_default_index_html(project_dir)

        # 3. 仅需要对 npm build 的项目执行构建
        build_success = True
        build_log = ""
        build_log_mode = "unknown"
        if lc.get("needs_npm_build"):
            try:
                result = subprocess.run(
                    ["npm", "install"], cwd=project_dir,
                    capture_output=True, text=True, timeout=180,
                )
                if result.returncode != 0:
                    build_success = False
                    build_log = "npm install failed:\n" + result.stderr[-2000:]
                    build_log_mode = "npm_install_failed"
                else:
                    result = subprocess.run(
                        ["npm", "run", "build"], cwd=project_dir,
                        capture_output=True, text=True, timeout=180,
                    )
                    if result.returncode != 0:
                        build_success = False
                        build_log = "npm run build failed:\n" + result.stderr[-2000:]
                        build_log_mode = "npm_build_failed"
                    else:
                        build_log = result.stdout[-1000:]
                        build_log_mode = "npm_build"
            except FileNotFoundError:
                build_log = "[本地无 Node.js，跳过实际构建。代码文件已写入磁盘。]"
                build_success = True
                build_log_mode = "node_missing"
            except subprocess.TimeoutExpired:
                build_log = "构建超时（超过 180 秒）"
                build_success = False
                build_log_mode = "build_timeout"
        else:
            build_log = f"[{code_gen_type} 项目无需 npm build，文件已就绪]"
            build_log_mode = "no_npm_build"

        state["build_result"] = {
            "success": build_success,
            "log": build_log,
            "project_dir": project_dir,
        }
        state["phase"] = "build_done"
        log_agent_ok(
            "Builder Agent",
            f"构建阶段完成，build_success={'yes' if build_success else 'no'} log_mode={build_log_mode}",
        )

        # === 3.5 质量门禁 (P0) ===
        lc = get_lang_config(code_gen_type)

        review_gate = _check_review_quality_gate(state, config.QUALITY_SCORE_THRESHOLD)
        syntax_result = _run_syntax_check(project_dir, code_files, lc)

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

        # === 4. 索引代码到 RAG 知识库（检索闭环 + 质量门禁） ===
        review_score = state.get("review", {}).get("score", 0)

        if app_id and code_files and build_success and quality_gate_passed:
            try:
                index_code_files(code_files, app_id, code_gen_type,
                                 review_score=review_score)
                state["indexing_result"] = {
                    "success": True,
                    "message": "代码已索引到 RAG 知识库",
                    "indexed_count": len(code_files),
                    "total_count": len(code_files),
                }
                log_agent_ok("Builder Agent", f"索引完成，files={len(code_files)} app_id={app_id}")
            except Exception as e:
                state["indexing_result"] = {
                    "success": False,
                    "message": f"索引失败（构建不受影响）: {e}",
                    "indexed_count": 0,
                    "total_count": len(code_files),
                }
                log_agent_fail("Builder Agent", f"索引失败，但不影响构建，原因={e}")
        elif not app_id:
            state["indexing_result"] = {
                "success": False,
                "message": "跳过索引: app_id 缺失",
                "indexed_count": 0,
                "total_count": len(code_files),
            }
            log_agent_ok("Builder Agent", "跳过索引，reason=app_id missing")
        elif not build_success:
            state["indexing_result"] = {
                "success": False,
                "message": "跳过索引: build_success=False",
                "indexed_count": 0,
                "total_count": len(code_files),
            }
            log_agent_ok("Builder Agent", "跳过索引，reason=build_success false")
        else:
            # quality_gate_passed == False
            reason = state.get("quality_gate_result", {}).get("reason", "质量门禁未通过")
            state["indexing_result"] = {
                "success": False,
                "message": f"跳过索引: {reason}",
                "indexed_count": 0,
                "total_count": len(code_files),
            }
            log_agent_ok("Builder Agent", f"跳过索引，reason={reason}")

        # === 5. 反馈闭环 (P2)：根据构建结果更新检索过的条目质量分 ===
        if app_id:
            try:
                from rag.feedback_tracker import feedback_tracker
                feedback_tracker.apply_feedback(app_id, build_success)
            except Exception as e:
                log_agent_fail("Builder Agent", f"反馈更新失败，但不影响构建，原因={e}")

        log_agent_ok(
            "Builder Agent",
            f"构建结束，build_success={'yes' if build_success else 'no'} "
            f"quality_gate={'passed' if state.get('quality_gate_result', {}).get('passed') else 'failed'} "
            f"files={len(code_files)} project_dir={project_dir}",
        )
        return state

    except Exception as e:
        state["build_result"] = {"success": False, "log": str(e), "project_dir": project_dir}
        state["phase"] = "build_done"
        state["error"] = str(e)
        log_agent_fail("Builder Agent", f"构建异常，原因={e}")
        return state
