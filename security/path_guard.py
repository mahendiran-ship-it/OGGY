"""
OGGY filesystem path guard.

Responsibilities:

1. Resolve relative paths against OGGY's project root.
2. Allow access to configured filesystem roots.
3. Completely block protected directories.
4. Prevent path traversal.
5. Prevent symlink/junction escapes into blocked locations.
"""

from pathlib import Path
from typing import List, Optional

from config import config


class PathViolation(Exception):
    """Raised when a filesystem path is not allowed."""


# ======================================================================
# Helpers
# ======================================================================

def _normalise_name(path: Path) -> str:
    return path.name.strip().upper()


def _contains_blocked_directory(path: Path) -> Optional[Path]:
    """
    Check every component of a resolved path.

    Example:

        C:\\$Recycle.Bin\\something.txt

    is rejected even if the user supplied an absolute path.
    """

    for part in path.parts:

        if part.strip().upper() in config.BLOCKED_DIRECTORY_NAMES:
            return Path(part)

    return None


def _is_within(path: Path, base: Path) -> bool:

    try:
        path.relative_to(base)
        return True

    except ValueError:
        return False


# ======================================================================
# Main path resolver
# ======================================================================

def resolve_safe_path(
    raw_path: str,
    allowed_dirs: List[Path] = None,
) -> Path:

    if not raw_path:
        raise PathViolation(
            "Empty filesystem path."
        )

    allowed_dirs = (
        allowed_dirs
        if allowed_dirs is not None
        else config.ALLOWED_DIRS
    )

    if not allowed_dirs:
        raise PathViolation(
            "No allowed directories are configured."
        )


    # --------------------------------------------------------------
    # Relative path
    #
    # "." / "config.py" / "security/path_guard.py"
    #
    # resolve relative to OGGY itself.
    # --------------------------------------------------------------

    candidate = Path(raw_path)

    if not candidate.is_absolute():
        # Callers such as tests and future scoped tools may provide a
        # temporary allowed root. Relative paths belong to that root.
        relative_root = Path(allowed_dirs[0])
        candidate = relative_root / candidate


    # --------------------------------------------------------------
    # Resolve absolute path.
    #
    # resolve() also normalises:
    #
    #   ..
    #   .
    #   symlinks/junctions where possible
    # --------------------------------------------------------------

    try:

        resolved = candidate.resolve()

    except OSError as exc:

        raise PathViolation(
            f"Unable to resolve path '{raw_path}': {exc}"
        )


    # --------------------------------------------------------------
    # Block protected directories.
    # --------------------------------------------------------------

    blocked = _contains_blocked_directory(
        resolved
    )

    if blocked is not None:

        raise PathViolation(
            f"Access to protected directory "
            f"'{blocked.name}' is blocked."
        )


    # --------------------------------------------------------------
    # Verify filesystem root.
    # --------------------------------------------------------------

    for base in allowed_dirs:

        try:

            base_resolved = base.resolve()

        except OSError:
            continue


        if _is_within(
            resolved,
            base_resolved,
        ):

            return resolved


    raise PathViolation(
        f"Path '{raw_path}' is outside the "
        f"allowed OGGY filesystem."
    )


# ======================================================================
# Boolean helper
# ======================================================================

def is_within_allowed(
    path: Path,
    allowed_dirs: List[Path] = None,
) -> bool:

    try:

        resolve_safe_path(
            str(path),
            allowed_dirs,
        )

        return True

    except PathViolation:

        return False