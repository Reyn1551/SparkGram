"""
Unit & Integration Tests for SparkGram Features 2, 3, and 4:
- Feature 2: GitManager & Git Cockpit
- Feature 3: MacroManager & Developer Recipes
- Feature 4: FileExplorerService & State Cache
"""
import io
import os
import shutil
import tempfile
import pytest
from pathlib import Path

from sparkgram.core.git_manager import GitManager
from sparkgram.core.macro_manager import macro_manager, RECIPES
from sparkgram.engine.file_explorer import FileExplorerService, ExplorerStateCache, state_cache


# -------------------------------------------------------------
# 1. Tests for Feature 2: GitManager
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_git_manager_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        gm = GitManager(tmpdir)
        is_repo = await gm.is_git_repo()
        assert is_repo is False

        status = await gm.get_status_summary()
        assert status["is_repo"] is False

        ok, diff_text, stats = await gm.get_diff()
        assert ok is False


@pytest.mark.asyncio
async def test_git_manager_repo_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize a real git repo
        proc = await (await import_asyncio()).create_subprocess_exec(
            "git", "init", cwd=tmpdir,
            stdout=(await import_asyncio()).subprocess.PIPE,
            stderr=(await import_asyncio()).subprocess.PIPE
        )
        await proc.communicate()

        # Set dummy git user for commit
        await (await (await import_asyncio()).create_subprocess_exec("git", "config", "user.name", "TestUser", cwd=tmpdir)).communicate()
        await (await (await import_asyncio()).create_subprocess_exec("git", "config", "user.email", "test@test.com", cwd=tmpdir)).communicate()

        gm = GitManager(tmpdir)
        assert await gm.is_git_repo() is True

        # Create a test file
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("print('hello')", encoding="utf-8")

        status = await gm.get_status_summary()
        assert status["is_repo"] is True
        assert "test.py" in status["untracked"]

        # Stage all
        ok, msg = await gm.stage_all()
        assert ok is True

        status_after_stage = await gm.get_status_summary()
        assert "test.py" in status_after_stage["staged"]

        # AI Commit message generation
        ai_msg = gm.generate_ai_commit_message(status_after_stage)
        assert "test" in ai_msg.lower() or "feat" in ai_msg.lower()

        # Commit
        ok, c_msg = await gm.commit(ai_msg)
        assert ok is True
        assert "Commit berhasil" in c_msg

        # Modify file to test diff
        test_file.write_text("print('hello world!')\nprint('line 2')", encoding="utf-8")
        ok, diff_text, stats = await gm.get_diff(staged_only=False)
        assert ok is True
        assert "hello world!" in diff_text
        assert stats["added"] > 0

        # Unstage / Discard
        ok, d_msg = await gm.discard_all()
        assert ok is True


async def import_asyncio():
    import asyncio
    return asyncio


# -------------------------------------------------------------
# 2. Tests for Feature 3: MacroManager
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_macro_manager_recipes():
    recipes = macro_manager.list_recipes()
    assert len(recipes) >= 5
    ids = [r["id"] for r in recipes]
    assert "review" in ids
    assert "testgen" in ids
    assert "explain" in ids
    assert "refactor" in ids
    assert "doc" in ids


@pytest.mark.asyncio
async def test_macro_build_prompt():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create dummy source file
        dummy_file = Path(tmpdir) / "service.py"
        dummy_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        # Test testgen recipe
        ok, prompt, title = await macro_manager.build_macro_prompt(
            recipe_id="testgen",
            work_dir=tmpdir,
            target="service.py"
        )
        assert ok is True
        assert "def add(a, b):" in prompt
        assert "pytest" in prompt
        assert "Unit Test Generator" in title

        # Test explain recipe
        ok, prompt, title = await macro_manager.build_macro_prompt(
            recipe_id="explain",
            work_dir=tmpdir,
            target="service.py"
        )
        assert ok is True
        assert "alur data" in prompt or "arsitektur" in prompt

        # Test non-existent file
        ok, err, _ = await macro_manager.build_macro_prompt(
            recipe_id="testgen",
            work_dir=tmpdir,
            target="missing.py"
        )
        assert ok is False
        assert "tidak ditemukan" in err


# -------------------------------------------------------------
# 3. Tests for Feature 4: FileExplorerService & State Cache
# -------------------------------------------------------------
def test_explorer_state_cache():
    cache = ExplorerStateCache(max_items=10)
    tok1 = cache.register_path("src/core/models.py")
    tok2 = cache.register_path("src/bot/app.py")
    assert tok1 != tok2
    assert len(tok1) <= 6 # Very compact

    assert cache.get_path(tok1) == "src/core/models.py"
    assert cache.get_path(tok2) == "src/bot/app.py"

    # Same path returns same token
    assert cache.register_path("src/core/models.py") == tok1


def test_file_explorer_chroot_jail():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir).resolve()
        sub = base / "nested"
        sub.mkdir()
        file = sub / "app.py"
        file.write_text("code = 1", encoding="utf-8")

        # Valid safe resolve
        resolved = FileExplorerService.safe_resolve(tmpdir, "nested/app.py")
        assert resolved == file

        # Path Traversal attack -> should raise PermissionError
        with pytest.raises(PermissionError):
            FileExplorerService.safe_resolve(tmpdir, "../../Windows/System32")


def test_file_explorer_build_ui():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir).resolve()
        (base / "src").mkdir()
        (base / "README.md").write_text("# Test", encoding="utf-8")
        (base / "config.json").write_text("{}", encoding="utf-8")

        text, kb = FileExplorerService.build_file_tree_ui(tmpdir)
        assert "File Explorer" in text
        assert "README.md" in text
        assert len(kb.inline_keyboard) > 0


def test_file_explorer_read_preview():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir).resolve()
        f = base / "sample.py"
        f.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        ok, preview = FileExplorerService.read_file_preview(tmpdir, "sample.py")
        assert ok is True
        assert "sample.py" in preview
        assert "1 | line 1" in preview


def test_file_explorer_zip_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir).resolve()
        (base / "src").mkdir()
        (base / "src" / "main.py").write_text("print(1)", encoding="utf-8")
        (base / "node_modules").mkdir()
        (base / "node_modules" / "heavy.js").write_text("heavy", encoding="utf-8")

        ok, zip_bytes, zip_name = FileExplorerService.create_safe_zip(tmpdir)
        assert ok is True
        assert zip_name.endswith(".zip")
        assert len(zip_bytes) > 0

        # Verify excluded folders are NOT in zip
        import zipfile
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            assert any("src/main.py" in n or "src\\main.py" in n for n in names)
            assert not any("node_modules" in n for n in names)


def test_file_explorer_save_upload_and_backup():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir).resolve()
        test_file = base / "config.yaml"
        test_file.write_text("version: 1", encoding="utf-8")

        # Upload new content for existing file -> should create .bak
        ok, msg = FileExplorerService.save_uploaded_file(
            base_dir=tmpdir,
            filename="config.yaml",
            file_bytes=b"version: 2",
        )
        assert ok is True
        assert (base / "config.yaml").read_text(encoding="utf-8") == "version: 2"
        assert (base / "config.yaml.bak").exists()
        assert (base / "config.yaml.bak").read_text(encoding="utf-8") == "version: 1"
