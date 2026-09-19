"""
OGGY configuration.

OGGY can access the user's normal filesystem, but protected/noisy
system locations are excluded from filesystem traversal.

Read/list/search:
    Allowed filesystem locations except blocked directories.

Write/edit/delete/move/rename:
    Still controlled by the permission layer.
"""

import os
from pathlib import Path


# ======================================================================
# Environment
# ======================================================================

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:

    # ==================================================================
    # LLM
    # ==================================================================

    LLM_PROVIDER = os.getenv(
        "OGGY_LLM_PROVIDER",
        "anthropic",
    )

    ANTHROPIC_API_KEY = os.getenv(
        "ANTHROPIC_API_KEY",
        "",
    )

    ANTHROPIC_MODEL = os.getenv(
        "OGGY_MODEL",
        "claude-sonnet-5",
    )

    GEMINI_API_KEY = os.getenv(
        "GEMINI_API_KEY",
        "",
    )

    GEMINI_MODEL = os.getenv(
        "OGGY_GEMINI_MODEL",
        "gemini-3.7-flash",
    )

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("OGGY_GROQ_MODEL", "llama-3.3-70b-versatile")
    QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
    QWEN_MODEL = os.getenv("OGGY_QWEN_MODEL", "qwen-plus")
    PROVIDER_ORDER = [
        name.strip().lower()
        for name in os.getenv("OGGY_PROVIDER_ORDER", "").split(",")
        if name.strip()
    ]

    MAX_TOKENS = int(
        os.getenv(
            "OGGY_MAX_TOKENS",
            "2048",
        )
    )

    PROVIDER_TIMEOUT_SECONDS = int(
        os.getenv(
            "OGGY_PROVIDER_TIMEOUT_SECONDS",
            "20",
        )
    )


    # ==================================================================
    # Filesystem
    # ==================================================================

    FULL_FILESYSTEM_ACCESS = (
        os.getenv(
            "OGGY_FULL_FILESYSTEM_ACCESS",
            "false",
        ).strip().lower()
        in ("1", "true", "yes", "on")
    )

    # --------------------------------------------------------------
    # OGGY project root
    #
    # config.py is located inside the OGGY project.
    # This gives OGGY a reliable default workspace.
    # --------------------------------------------------------------

    PROJECT_ROOT = Path(__file__).resolve().parent


    # --------------------------------------------------------------
    # Default workspace
    #
    # "." will resolve to this directory.
    # --------------------------------------------------------------

    DEFAULT_WORKSPACE = PROJECT_ROOT


    # --------------------------------------------------------------
    # Filesystem roots
    # --------------------------------------------------------------

    _default_workspace = (
        Path.home() / "oggy_workspace"
    )


    if FULL_FILESYSTEM_ACCESS:

        if os.name == "nt":

            ALLOWED_DIRS = []

            for drive_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":

                drive = Path(
                    f"{drive_letter}:\\"
                )

                try:

                    if drive.exists():
                        ALLOWED_DIRS.append(
                            drive.resolve()
                        )

                except OSError:
                    continue

        else:

            ALLOWED_DIRS = [
                Path("/").resolve()
            ]

    else:

        ALLOWED_DIRS = [
            Path(path).expanduser().resolve()

            for path in os.getenv(
                "OGGY_ALLOWED_DIRS",
                str(_default_workspace),
            ).split(",")

            if path.strip()
        ]


    # ==================================================================
    # Filesystem exclusions
    # ==================================================================
    #
    # These directories are NEVER traversed by OGGY filesystem tools.
    #
    # Most importantly:
    #
    #     $Recycle.Bin
    #
    # is completely invisible to OGGY.
    #
    # ==================================================================

    BLOCKED_DIRECTORY_NAMES = {
        "$RECYCLE.BIN",
        "SYSTEM VOLUME INFORMATION",
    }


    # --------------------------------------------------------------
    # Search exclusions
    #
    # These aren't necessarily forbidden paths. They are simply
    # skipped during broad recursive searches to prevent OGGY from
    # crawling enormous system/application directories.
    # --------------------------------------------------------------

    SEARCH_EXCLUDED_DIRECTORY_NAMES = {
        "$RECYCLE.BIN",
        "SYSTEM VOLUME INFORMATION",

        # Windows system locations
        "WINDOWS",
        "PROGRAM FILES",
        "PROGRAM FILES (X86)",
        "PROGRAMDATA",
        "RECOVERY",
        "CONFIG.MSI",
        "$SYSRESET",

        # Common development noise
        "NODE_MODULES",
        ".GIT",
        ".VENVS",
        "__PYCACHE__",
    }


    # ==================================================================
    # Commands
    # ==================================================================

    ALLOWED_COMMANDS = {
        command.strip()

        for command in os.getenv(
            "OGGY_ALLOWED_COMMANDS",
            "python,python3,pip,pip3,"
            "git,node,npm,ls,pytest,explorer",
        ).split(",")

        if command.strip()
    }


    COMMAND_TIMEOUT_SECONDS = int(
        os.getenv(
            "OGGY_COMMAND_TIMEOUT",
            "30",
        )
    )


    # ==================================================================
    # Storage
    # ==================================================================

    DATA_DIR = Path(
        os.getenv(
            "OGGY_DATA_DIR",
            str(
                Path(__file__).parent / "data"
            ),
        )
    )

    MEMORY_DB_PATH = (
        DATA_DIR / "memory.sqlite3"
    )

    LOG_DIR = (
        DATA_DIR / "logs"
    )


    # ==================================================================
    # Agent safety
    # ==================================================================

    MAX_AGENT_STEPS = int(
        os.getenv(
            "OGGY_MAX_AGENT_STEPS",
            "8",
        )
    )


    # ==================================================================
    # Flask
    # ==================================================================

    DEBUG = (
        os.getenv(
            "OGGY_DEBUG",
            "false",
        ).strip().lower()
        in ("1", "true", "yes", "on")
    )

    HOST = os.getenv(
        "OGGY_HOST",
        "127.0.0.1",
    )

    PORT = int(
        os.getenv(
            "OGGY_PORT",
            "5050",
        )
    )


    # ==================================================================
    # Directory initialization
    # ==================================================================

    @classmethod
    def ensure_dirs(cls):

        cls.DATA_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        cls.LOG_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not cls.FULL_FILESYSTEM_ACCESS:

            for directory in cls.ALLOWED_DIRS:

                directory.mkdir(
                    parents=True,
                    exist_ok=True,
                )


# ======================================================================
# Global instance
# ======================================================================

config = Config()