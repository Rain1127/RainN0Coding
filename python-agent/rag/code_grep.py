"""
ripgrep 代码精确搜索 —— 在已验证代码库中按符号名/文件名搜索

用法：
    grep = CodeGrep()
    results = grep.search("UserController", max_files=5)
    results = grep.grep_content("JwtUtil", max_results=5)
"""

import os
import shutil
import subprocess
from pathlib import Path
from config import config


class CodeGrep:
    """用 ripgrep 在已验证代码文件中精确搜索符号/内容"""

    DEFAULT_CONTENT_LIMIT = 3000  # 单文件内容截断长度

    def __init__(self, store_dir: str | None = None):
        self.store_dir = Path(store_dir or config.CODE_STORE_DIR)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._rg_available: bool | None = None

    def search(self, symbol: str, max_files: int = 5) -> list[dict]:
        """
        按符号名搜索文件。
        symbol: 类名/函数名，如 "UserController", "PageResult"
        返回匹配文件列表，每个包含 file_path + content
        """
        if not self._check_rg():
            return self._fallback_search(symbol, max_files)

        try:
            result = subprocess.run(
                [
                    self._rg_path(),
                    "-l",                          # 只列文件名
                    "--max-count", str(max_files),
                    "--no-heading",
                    "-g", "!*.min.*",              # 跳过压缩文件
                    "-g", "!.git",                 # 跳过 .git 目录
                    "--",                          # 参数结束
                    symbol,
                    str(self.store_dir),
                ],
                capture_output=True, text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return self._fallback_search(symbol, max_files)

        return self._read_files(result.stdout, max_files)

    def grep_content(self, pattern: str, max_results: int = 5) -> list[dict]:
        """
        全文搜索代码内容。
        pattern: 任意文本，如 "export interface User", "@RestController"
        """
        if not self._check_rg():
            return self._fallback_search(pattern, max_results)

        try:
            result = subprocess.run(
                [
                    self._rg_path(),
                    "-l",
                    "--max-count", str(max_results),
                    "--no-heading",
                    "-g", "!*.min.*",
                    "-g", "!.git",
                    "-g", "!*.lock",
                    "--", pattern, str(self.store_dir),
                ],
                capture_output=True, text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return self._fallback_search(pattern, max_results)

        return self._read_files(result.stdout, max_results)

    def write_code(self, app_id: str, file_path: str, content: str):
        """将构建成功的代码写入文件系统"""
        dest = self.store_dir / app_id / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", errors="ignore")

    def delete_code(self, app_id: str, file_path: str = "") -> bool:
        """删除单个代码文件或整个 app 目录。

        Args:
            app_id: 应用 ID
            file_path: 文件相对路径。为空时删除整个 app 目录。

        Returns:
            是否成功删除
        """
        target = self.store_dir / app_id
        if file_path:
            target = target / file_path
        if not target.exists():
            return False
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        # 清理空的父目录（上溯到 store_dir）
        parent = target.parent
        while parent != self.store_dir:
            try:
                if not any(parent.iterdir()):
                    parent.rmdir()
                else:
                    break
            except OSError:
                break
            parent = parent.parent
        return True

    def get_file_count(self) -> int:
        """统计已验证代码库的文件数"""
        if not self.store_dir.exists():
            return 0
        return sum(1 for _ in self.store_dir.rglob("*") if _.is_file())

    # ========== 内部方法 ==========

    def _check_rg(self) -> bool:
        """检查 ripgrep 是否可用"""
        if self._rg_available is None:
            self._rg_available = shutil.which("rg") is not None
        return self._rg_available

    def _rg_path(self) -> str:
        return "rg"

    def _read_files(self, stdout: str, max_files: int) -> list[dict]:
        """读取 rg 输出的文件列表并返回内容"""
        files = [f.strip() for f in stdout.strip().split("\n") if f.strip()]
        results = []
        for fpath in files[:max_files]:
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            results.append({
                "file_path": fpath,
                "content": content[:self.DEFAULT_CONTENT_LIMIT],
            })
        return results

    def _fallback_search(self, symbol: str, max_files: int) -> list[dict]:
        """ripgrep 不可用时走文件系统遍历"""
        results = []
        if not self.store_dir.exists():
            return results
        for fpath in self.store_dir.rglob("*"):
            if not fpath.is_file():
                continue
            fname = fpath.name.lower()
            sym_lower = symbol.lower()
            # 文件名匹配或内容首行匹配
            if sym_lower in fname:
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                results.append({
                    "file_path": str(fpath),
                    "content": content[:self.DEFAULT_CONTENT_LIMIT],
                })
                if len(results) >= max_files:
                    break
        return results


# 全局单例
code_grep = CodeGrep()
