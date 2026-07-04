"""Environment and dotenv helpers."""

from __future__ import annotations

import os
from pathlib import Path


def load_secret(name: str, env_path: Path) -> str | None:
    """Load a secret from the process environment or a dotenv file.

    Args:
        name: Environment variable name.
        env_path: Dotenv file path used as a fallback.

    Returns:
        Secret value when configured.
    """

    return os.environ.get(name) or load_dotenv_value(env_path, name)


def load_dotenv_value(env_path: Path, name: str) -> str | None:
    """Read one variable from a simple dotenv file.

    Args:
        env_path: Dotenv file path.
        name: Variable name to read.

    Returns:
        Dotenv value when present.
    """

    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        if key.strip() != name:
            continue

        return strip_env_quotes(value.strip())
    return None


def strip_env_quotes(value: str) -> str:
    """Remove matching single or double quotes from an env value.

    Args:
        value: Raw environment value.

    Returns:
        Value without matching surrounding quotes.
    """

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
