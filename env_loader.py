"""Load environment variables from ``.env`` files.

The bot reads its configuration from environment variables, but it is very
common (and handy) to keep them in a ``.env`` file instead of exporting them in
the shell or in the service unit.  This module implements a tiny ``.env``
loader, so no external dependency (python-dotenv) is needed.

Rules:

* Real environment variables always win: a value already present in
  ``os.environ`` is never overridden.
* Among the files, the first one that defines a variable wins.  Files are
  searched in this order: ``$CONFIG_DIR/.env``, ``./.env``, the ``.env`` next to
  the code, ``$HOME/.env`` and ``$HOME/.simplebot/.env``.
* Supported syntax: ``KEY=value``, ``export KEY=value``, blank lines and
  ``#`` comments, values quoted with ``'`` or ``"`` (quotes are removed) and
  trailing ``# comments`` in unquoted values.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Dict, Iterable, List, Optional

HOME = Path.home()

#: files loaded by the last call to :func:`load_env_files`
loaded_files: List[str] = []

#: files that were looked for (useful for diagnostics)
searched_files: List[str] = []


def parse_env_file(path) -> Dict[str, str]:
    """Parse the given ``.env`` file and return a dict with its variables."""
    values: Dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not (key[0].isalpha() or key[0] == "_"):
            continue
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif "#" in value:
            # strip trailing comment of unquoted values: KEY=value # comment
            head, _, comment = value.partition("#")
            if comment and (head.endswith(" ") or head.endswith("\t") or head == ""):
                value = head.rstrip()
            elif not comment:
                value = head.rstrip()
        values[key] = value
    return values


def env_dirs() -> List[Path]:
    """Return the folders where a ``.env`` file is searched for."""
    dirs: List[Path] = []
    config_dir = os.environ.get("CONFIG_DIR")
    if config_dir:
        dirs.append(Path(config_dir))
    dirs.append(Path.cwd())
    dirs.append(Path(__file__).resolve().parent)
    dirs.append(HOME)
    dirs.append(HOME / ".simplebot")
    return dirs


def load_env_files(paths: Optional[Iterable] = None) -> List[str]:
    """Load the ``.env`` files, without overriding existing variables.

    Return the list of files that were actually used.
    """
    if paths is None:
        paths = [folder / ".env" for folder in env_dirs()]
    #mutate the lists in place, so importers keep seeing the same object
    loaded_files.clear()
    searched_files.clear()
    for path in paths:
        path = Path(path)
        name = str(path)
        if name in searched_files:
            continue
        searched_files.append(name)
        if not path.is_file():
            continue
        values = parse_env_file(path)
        used = False
        for key, value in values.items():
            if key in os.environ:
                continue  # real environment variables win
            os.environ[key] = value
            used = True
        if used or values:
            loaded_files.append(name)
    return loaded_files


def export_shell(paths: Optional[Iterable] = None) -> str:
    """Return ``export`` statements for the values of the ``.env`` files.

    Used by ``start.sh`` to load the same configuration as the bot, without
    sourcing the file directly (which breaks with values containing spaces).
    """
    if paths is None:
        paths = [folder / ".env" for folder in env_dirs()]
    values: Dict[str, str] = {}
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        for key, value in parse_env_file(path).items():
            if key in os.environ or key in values:
                continue
            values[key] = value
    return "\n".join(f"export {key}={shlex.quote(value)}" for key, value in values.items())


if __name__ == "__main__":
    import sys

    if "--export" in sys.argv:
        print(export_shell())
    else:
        print("Cargando " + ", ".join(load_env_files() or ["(ningun .env encontrado)"]))
