"""
Git Manager for SparkGram.
Provides async Git operations, status summary, diff inspection, and 1-tap AI commit formatting.
"""
import os
import html
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

log = logging.getLogger(__name__)


class GitManager:
    """Async safe Git operations engine for SparkGram."""

    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir).resolve()

    async def _run_git(self, *args: str) -> Tuple[int, str, str]:
        """Executes a git command using argument vector (safe from shell injection)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(self.work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except FileNotFoundError:
            return -1, "", "Git binary not found on host system."
        except Exception as e:
            return -1, "", str(e)

    async def is_git_repo(self) -> bool:
        """Checks if work_dir is a valid Git repository."""
        code, out, _ = await self._run_git("rev-parse", "--is-inside-work-tree")
        return code == 0 and out.strip() == "true"

    async def get_status_summary(self) -> Dict[str, Any]:
        """Returns structured summary of git status (branch, staged, unstaged, untracked)."""
        if not await self.is_git_repo():
            return {
                "is_repo": False,
                "branch": "not-a-repo",
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "stats": {"added": 0, "deleted": 0},
            }

        code, out, err = await self._run_git("status", "--porcelain=v1", "-b")
        if code != 0:
            return {
                "is_repo": True,
                "branch": "error",
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "error": err,
            }

        lines = out.splitlines()
        branch_line = lines[0].replace("## ", "") if lines else "unknown"
        # Parse branch name (e.g. main...origin/main [ahead 1])
        branch_name = branch_line.split("...")[0].split()[0] if branch_line else "unknown"

        staged: List[str] = []
        unstaged: List[str] = []
        untracked: List[str] = []

        for line in lines[1:]:
            if len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]
            filepath = line[3:].strip().strip('"')

            if index_status in ("M", "A", "D", "R", "C"):
                staged.append(filepath)
            if worktree_status in ("M", "D"):
                unstaged.append(filepath)
            elif index_status == "?" and worktree_status == "?":
                untracked.append(filepath)

        # Get diff stats (+lines, -lines)
        diff_code, numstat_out, _ = await self._run_git("diff", "--numstat", "HEAD")
        added_lines = 0
        deleted_lines = 0
        if diff_code == 0 and numstat_out:
            for n_line in numstat_out.splitlines():
                parts = n_line.split()
                if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                    added_lines += int(parts[0])
                    deleted_lines += int(parts[1])

        return {
            "is_repo": True,
            "branch": branch_name,
            "branch_full": branch_line,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "stats": {"added": added_lines, "deleted": deleted_lines},
        }

    async def get_diff(self, staged_only: bool = False, max_chars: int = 3500) -> Tuple[bool, str, Dict[str, int]]:
        """Returns unified diff text with stats and HTML-safe formatted content."""
        if not await self.is_git_repo():
            return False, "Bukan repositori Git.", {"added": 0, "deleted": 0, "files_count": 0}

        args = ["diff", "--no-color", "-U3"]
        if staged_only:
            args.append("--staged")

        code, stdout, stderr = await self._run_git(*args)
        if code != 0:
            return False, f"Git diff error: {stderr}", {"added": 0, "deleted": 0, "files_count": 0}

        diff_text = stdout.strip()
        if not diff_text:
            return True, "", {"added": 0, "deleted": 0, "files_count": 0}

        added = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deleted = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))
        files_count = sum(1 for line in diff_text.splitlines() if line.startswith("diff --git"))

        return True, diff_text, {"added": added, "deleted": deleted, "files_count": files_count}

    async def stage_all(self) -> Tuple[bool, str]:
        """Stages all changes (git add -A)."""
        code, out, err = await self._run_git("add", "-A")
        if code == 0:
            return True, "Semua perubahan berhasil di-stage (git add -A)."
        return False, f"Gagal staging: {err or out}"

    async def stage_file(self, filepath: str) -> Tuple[bool, str]:
        """Stages a specific file (git add <filepath>)."""
        code, out, err = await self._run_git("add", filepath)
        if code == 0:
            return True, f"File <code>{html.escape(filepath)}</code> berhasil di-stage."
        return False, f"Gagal staging file: {err or out}"

    async def unstage_all(self) -> Tuple[bool, str]:
        """Unstages all files (git restore --staged .)."""
        code, out, err = await self._run_git("restore", "--staged", ".")
        if code == 0:
            return True, "Semua staged changes berhasil di-unstage."
        return False, f"Gagal unstage: {err or out}"

    async def discard_all(self) -> Tuple[bool, str]:
        """Discards all unstaged modifications (git restore .)."""
        code, out, err = await self._run_git("restore", ".")
        if code == 0:
            return True, "Semua perubahan unstaged berhasil di-revert."
        return False, f"Gagal discard: {err or out}"

    async def commit(self, message: str) -> Tuple[bool, str]:
        """Commits staged changes with the provided message."""
        clean_msg = message.strip()
        if not clean_msg:
            return False, "Pesan commit tidak boleh kosong."

        code, out, err = await self._run_git("commit", "-m", clean_msg)
        if code == 0:
            return True, f"Commit berhasil: <b>{html.escape(clean_msg)}</b>\n<code>{html.escape(out.strip())}</code>"
        return False, f"Gagal commit: {err or out}"

    async def push(self, remote: str = "origin", branch: Optional[str] = None) -> Tuple[bool, str]:
        """Pushes current branch to remote repository."""
        args = ["push", remote]
        if branch:
            args.append(branch)
        code, out, err = await self._run_git(*args)
        if code == 0:
            return True, f"Push ke <code>{html.escape(remote)}</code> berhasil!\n<code>{html.escape(out.strip() or 'Up-to-date')}</code>"
        return False, f"Gagal push: {err or out}"

    def generate_ai_commit_message(self, status_info: Dict[str, Any], diff_snippet: str = "") -> str:
        """Generates high-quality Conventional Commit message based on staged files & diff."""
        staged = status_info.get("staged", [])
        if not staged:
            return "chore: update codebase"

        # Check typical paths for semantic prefix
        has_tests = any("test" in f.lower() for f in staged)
        has_docs = any(f.endswith((".md", ".rst", ".txt")) or "doc" in f.lower() for f in staged)
        has_core = any("core" in f.lower() or "engine" in f.lower() for f in staged)
        has_bot = any("bot" in f.lower() or "handler" in f.lower() for f in staged)
        has_config = any(f in (".env", "config.py", "pyproject.toml", "settings.py") for f in staged)

        scope = "bot" if has_bot else ("core" if has_core else ("tests" if has_tests else "code"))
        
        # Determine prefix
        if has_tests and len(staged) == 1:
            prefix = "test"
        elif has_docs and len(staged) == 1:
            prefix = "docs"
        elif has_config:
            prefix = "chore"
        else:
            prefix = "feat"

        sample_file = Path(staged[0]).stem
        if len(staged) == 1:
            return f"{prefix}({scope}): update {sample_file}"
        return f"{prefix}({scope}): update {sample_file} and {len(staged)-1} other files"
