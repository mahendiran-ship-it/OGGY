"""
OGGY filesystem tools.

Filesystem access model:

    list_files
        SAFE

    read_file
        SAFE

    search_files
        SAFE

    create_file
        MODERATE

    edit_file
        MODERATE

    create_folder
        MODERATE

    rename_file
        MODERATE

    move_file
        MODERATE

    delete_file
        DANGEROUS

All paths pass through security.path_guard.
"""

import os
import shutil
from pathlib import Path
from config import config
from security.path_guard import (
    PathViolation,
    resolve_safe_path,
)

from security.permissions import PermissionLevel

from tools.registry import (
    Tool,
    ToolError,
    ToolResult,
    registry,
)


# ======================================================================
# Limits
# ======================================================================

MAX_READ_BYTES = 200_000

MAX_SEARCH_RESULTS = 200

MAX_EDIT_BYTES = 500_000


# ======================================================================
# Path helper
# ======================================================================

def _safe(raw_path: str) -> Path:

    try:

        return resolve_safe_path(
            raw_path
        )

    except PathViolation as exc:

        raise ToolError(
            str(exc)
        )


# ======================================================================
# Directory traversal helper
# ======================================================================

def _clean_walk(root: Path):

    """
    Walk a directory while skipping protected/noisy directories.

    Recycle Bin is never traversed.
    """

    excluded = {
    name.upper()
    for name in config.SEARCH_EXCLUDED_DIRECTORY_NAMES
    }

    for current, directories, files in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):

        # ----------------------------------------------------------
        # Remove excluded directories BEFORE os.walk enters them.
        # ----------------------------------------------------------

        directories[:] = [
            directory
            for directory in directories
            if directory.upper() not in excluded
        ]

        yield (
            Path(current),
            directories,
            files,
        )


# ======================================================================
# LIST FILES
# ======================================================================

def list_files(
    path: str = ".",
) -> ToolResult:

    target = _safe(path)


    if not target.exists():

        raise ToolError(
            f"Path does not exist: {path}"
        )


    if not target.is_dir():

        raise ToolError(
            f"Path is not a directory: {path}"
        )


    entries = []


    try:

        for child in sorted(
            target.iterdir(),
            key=lambda p: p.name.lower(),
        ):

            # Never expose Recycle Bin.
            if (
                child.name.upper()
                in config_blocked_names()
            ):
                continue


            try:

                if child.is_file():

                    size = child.stat().st_size

                else:

                    size = None

            except OSError:

                size = None


            entries.append(
                {
                    "name": child.name,
                    "type": (
                        "dir"
                        if child.is_dir()
                        else "file"
                    ),
                    "size": size,
                }
            )


    except OSError as exc:

        raise ToolError(
            f"Unable to list directory: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "path": str(target),
            "entries": entries,
        },
    )


# ======================================================================
# READ FILE
# ======================================================================

def read_file(
    path: str,
) -> ToolResult:

    target = _safe(path)


    if not target.exists() or not target.is_file():

        raise ToolError(
            f"File does not exist: {path}"
        )


    size = target.stat().st_size


    if size > MAX_READ_BYTES:

        raise ToolError(
            f"File is too large to read directly "
            f"({size} bytes)."
        )


    try:

        content = target.read_text(
            encoding="utf-8"
        )

    except UnicodeDecodeError:

        raise ToolError(
            f"File is not a text file: {path}"
        )

    except OSError as exc:

        raise ToolError(
            f"Unable to read file: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "path": str(target),
            "content": content,
        },
    )


# ======================================================================
# SEARCH FILES
# ======================================================================

def search_files(
    query: str,
    path: str = ".",
    max_results: int = 50,
) -> ToolResult:

    root = _safe(path)


    if not root.exists() or not root.is_dir():

        raise ToolError(
            f"Path is not a directory: {path}"
        )


    max_results = max(
        1,
        min(
            int(max_results),
            MAX_SEARCH_RESULTS,
        ),
    )


    query_lower = query.lower()

    matches = []


    # --------------------------------------------------------------
    # Recursive search.
    #
    # _clean_walk() prevents Recycle Bin traversal.
    # --------------------------------------------------------------

    for current, directories, files in _clean_walk(
        root
    ):

        if len(matches) >= max_results:
            break


        for filename in files:

            if len(matches) >= max_results:
                break


            file_path = current / filename


            # ------------------------------------------------------
            # Filename match
            # ------------------------------------------------------

            if query_lower in filename.lower():

                matches.append(
                    {
                        "path": str(file_path),
                        "match_type": "filename",
                    }
                )

                continue


            # ------------------------------------------------------
            # Content search for reasonably small files.
            # ------------------------------------------------------

            try:

                if (
                    file_path.stat().st_size
                    > MAX_READ_BYTES
                ):
                    continue


                text = file_path.read_text(
                    encoding="utf-8"
                )


                if query_lower in text.lower():

                    matches.append(
                        {
                            "path": str(file_path),
                            "match_type": "content",
                        }
                    )


            except (
                UnicodeDecodeError,
                OSError,
                PermissionError,
            ):

                continue


    return ToolResult(
        success=True,
        data={
            "query": query,
            "root": str(root),
            "matches": matches,
        },
    )


# ======================================================================
# CREATE FILE
# ======================================================================

def create_file(
    path: str,
    content: str = "",
) -> ToolResult:

    target = _safe(path)


    if target.exists():

        raise ToolError(
            f"File already exists: {path}"
        )


    try:

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_text(
            content,
            encoding="utf-8",
        )

    except OSError as exc:

        raise ToolError(
            f"Unable to create file: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "path": str(target),
            "created": True,
        },
    )


# ======================================================================
# EDIT FILE
# ======================================================================

def edit_file(
    path: str,
    content: str,
) -> ToolResult:

    target = _safe(path)


    if not target.exists():

        raise ToolError(
            f"File does not exist: {path}"
        )


    if not target.is_file():

        raise ToolError(
            f"Path is not a file: {path}"
        )


    if len(content.encode("utf-8")) > MAX_EDIT_BYTES:

        raise ToolError(
            "New file content is too large."
        )


    try:

        target.write_text(
            content,
            encoding="utf-8",
        )

    except OSError as exc:

        raise ToolError(
            f"Unable to edit file: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "path": str(target),
            "edited": True,
        },
    )


# ======================================================================
# CREATE FOLDER
# ======================================================================

def create_folder(
    path: str,
) -> ToolResult:

    target = _safe(path)


    if target.exists():

        raise ToolError(
            f"Path already exists: {path}"
        )


    try:

        target.mkdir(
            parents=True,
            exist_ok=False,
        )

    except OSError as exc:

        raise ToolError(
            f"Unable to create folder: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "path": str(target),
            "created": True,
        },
    )


# ======================================================================
# DELETE
# ======================================================================

def delete_file(
    path: str,
) -> ToolResult:

    target = _safe(path)


    if not target.exists():

        raise ToolError(
            f"Path does not exist: {path}"
        )


    try:

        if target.is_dir():

            shutil.rmtree(target)

        else:

            target.unlink()

    except OSError as exc:

        raise ToolError(
            f"Unable to delete: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "path": str(target),
            "deleted": True,
        },
    )


# ======================================================================
# RENAME
# ======================================================================

def rename_file(
    path: str,
    new_name: str,
) -> ToolResult:

    target = _safe(path)


    if not target.exists():

        raise ToolError(
            f"Path does not exist: {path}"
        )


    if not new_name or new_name in (".", ".."):

        raise ToolError(
            "Invalid new filename."
        )


    destination = target.parent / new_name


    # Validate destination through path guard.
    destination = _safe(
        str(destination)
    )


    try:

        target.rename(destination)

    except OSError as exc:

        raise ToolError(
            f"Unable to rename: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "old_path": str(target),
            "new_path": str(destination),
        },
    )


# ======================================================================
# MOVE
# ======================================================================

def move_file(
    path: str,
    destination: str,
) -> ToolResult:

    source = _safe(path)

    dest = _safe(destination)


    if not source.exists():

        raise ToolError(
            f"Path does not exist: {path}"
        )


    try:

        dest.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.move(
            str(source),
            str(dest),
        )

    except OSError as exc:

        raise ToolError(
            f"Unable to move: {exc}"
        )


    return ToolResult(
        success=True,
        data={
            "old_path": str(source),
            "new_path": str(dest),
        },
    )


# ======================================================================
# Config helper
# ======================================================================

def config_blocked_names():

    from config import config

    return {
        name.upper()
        for name in config.BLOCKED_DIRECTORY_NAMES
    }


# ======================================================================
# Tool registration
# ======================================================================

def register_filesystem_tools():

    registry.register(
        Tool(
            name="list_files",

            description=(
                "List files and folders. "
                "The default path '.' means the OGGY project folder. "
                "Protected system locations such as the Windows "
                "Recycle Bin are hidden."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": (
                        "Directory path. Relative paths start "
                        "from the OGGY project folder."
                    ),
                },
            },

            risk_level=PermissionLevel.SAFE,

            handler=list_files,
        )
    )


    registry.register(
        Tool(
            name="read_file",

            description=(
                "Read a text file from the accessible filesystem. "
                "Protected directories are blocked."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": (
                        "File path. Relative paths start "
                        "from the OGGY project folder."
                    ),
                },
            },

            risk_level=PermissionLevel.SAFE,

            handler=read_file,

            required=["path"],
        )
    )


    registry.register(
        Tool(
            name="search_files",

            description=(
                "Search filenames and text content recursively. "
                "Search automatically skips the Windows Recycle Bin, "
                "system directories, and common development noise."
            ),

            parameters={
                "query": {
                    "type": "string",
                    "description": "Text to search for.",
                },

                "path": {
                    "type": "string",
                    "description": (
                        "Directory to search. "
                        "Defaults to the OGGY project."
                    ),
                },

                "max_results": {
                    "type": "integer",
                    "description": (
                        "Maximum number of results."
                    ),
                },
            },

            risk_level=PermissionLevel.SAFE,

            handler=search_files,

            required=["query"],
        )
    )


    registry.register(
        Tool(
            name="create_file",

            description=(
                "Create a new file. "
                "Requires user confirmation."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": "File path.",
                },

                "content": {
                    "type": "string",
                    "description": "Initial file content.",
                },
            },

            risk_level=PermissionLevel.MODERATE,

            handler=create_file,

            required=["path"],
        )
    )


    registry.register(
        Tool(
            name="edit_file",

            description=(
                "Replace the contents of an existing text file. "
                "Requires user confirmation."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": "File to edit.",
                },

                "content": {
                    "type": "string",
                    "description": "Complete new file content.",
                },
            },

            risk_level=PermissionLevel.MODERATE,

            handler=edit_file,

            required=[
                "path",
                "content",
            ],
        )
    )


    registry.register(
        Tool(
            name="create_folder",

            description=(
                "Create a new folder. "
                "Requires user confirmation."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": "Folder path.",
                },
            },

            risk_level=PermissionLevel.MODERATE,

            handler=create_folder,

            required=["path"],
        )
    )


    registry.register(
        Tool(
            name="delete_file",

            description=(
                "Delete a file or folder. "
                "Dangerous and requires explicit confirmation."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": "Path to delete.",
                },
            },

            risk_level=PermissionLevel.DANGEROUS,

            handler=delete_file,

            required=["path"],
        )
    )


    registry.register(
        Tool(
            name="rename_file",

            description=(
                "Rename a file or folder. "
                "Requires user confirmation."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": "Path to rename.",
                },

                "new_name": {
                    "type": "string",
                    "description": "New filename.",
                },
            },

            risk_level=PermissionLevel.MODERATE,

            handler=rename_file,

            required=[
                "path",
                "new_name",
            ],
        )
    )


    registry.register(
        Tool(
            name="move_file",

            description=(
                "Move a file or folder. "
                "Requires user confirmation."
            ),

            parameters={
                "path": {
                    "type": "string",
                    "description": "Source path.",
                },

                "destination": {
                    "type": "string",
                    "description": "Destination path.",
                },
            },

            risk_level=PermissionLevel.MODERATE,

            handler=move_file,

            required=[
                "path",
                "destination",
            ],
        )
    )