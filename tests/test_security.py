"""
V1 test coverage focuses on the two modules where a bug would be a
security bug: the path guard (filesystem sandbox escape) and the
permission manager (SAFE/MODERATE/DANGEROUS/BLOCKED routing).
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from security.path_guard import PathViolation, resolve_safe_path
from security.permissions import PermissionLevel, PermissionManager


@pytest.fixture
def sandbox_dir():
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_resolve_safe_path_allows_paths_inside_sandbox(sandbox_dir):
    (sandbox_dir / "sub").mkdir()
    resolved = resolve_safe_path("sub/file.txt", allowed_dirs=[sandbox_dir])
    assert resolved == (sandbox_dir / "sub" / "file.txt").resolve()


def test_resolve_safe_path_blocks_traversal(sandbox_dir):
    with pytest.raises(PathViolation):
        resolve_safe_path("../../etc/passwd", allowed_dirs=[sandbox_dir])


def test_resolve_safe_path_blocks_absolute_paths_outside_sandbox(sandbox_dir):
    with pytest.raises(PathViolation):
        resolve_safe_path("/etc/passwd", allowed_dirs=[sandbox_dir])


def test_safe_tool_executes_without_confirmation():
    pm = PermissionManager()
    decision = pm.evaluate("list_files", PermissionLevel.SAFE, {})
    assert decision.allowed is True
    assert decision.requires_confirmation is False


def test_moderate_tool_requires_confirmation():
    pm = PermissionManager()
    decision = pm.evaluate("delete_file", PermissionLevel.MODERATE, {"path": "x"})
    assert decision.allowed is False
    assert decision.requires_confirmation is True
    assert decision.pending is not None


def test_blocked_tool_is_never_allowed():
    pm = PermissionManager()
    decision = pm.evaluate("format_disk", PermissionLevel.BLOCKED, {})
    assert decision.allowed is False
    assert decision.requires_confirmation is False


def test_resolving_a_confirmation_removes_it_from_pending():
    pm = PermissionManager()
    decision = pm.evaluate("delete_file", PermissionLevel.DANGEROUS, {"path": "x"})
    conf_id = decision.pending.id
    assert pm.get_pending(conf_id) is not None
    pm.resolve(conf_id, approved=True)
    assert pm.get_pending(conf_id) is None
