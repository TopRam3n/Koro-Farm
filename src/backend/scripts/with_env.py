"""Run one command with variables from a local, gitignored env file. Works the same in PowerShell and bash.

  python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m src.backend.scripts.check_staging
  python -m src.backend.scripts.with_env src/backend/.env.staging.local -- python -m alembic -c src/backend/alembic.ini current

* Never prints a value; with --names it lists only the variable names it loaded.
* Refuses a file inside this repository that git would commit (it must match .gitignore, like .env.* does).
* Lines are KEY=VALUE; blank lines and # comments are ignored; surrounding quotes are removed. Nothing is expanded.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = LINE.match(raw)
        if not match:
            raise ValueError(f"line {number} is not KEY=VALUE")  # the line itself is not echoed: it may hold a secret
        key, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def committable(path: Path) -> bool:
    """True if the file is inside this repository and git would not ignore it."""
    try:
        path.resolve().relative_to(REPO)
    except ValueError:
        return False
    result = subprocess.run(["git", "check-ignore", "-q", str(path.resolve())], cwd=REPO, capture_output=True)
    return result.returncode == 1  # 0: ignored; 1: not ignored; 128: git unavailable (treated as not committable)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    names = "--names" in argv[: argv.index("--") if "--" in argv else len(argv)]
    if names:
        argv.remove("--names")
    if len(argv) < 3 or argv[1] != "--":
        print("usage: python -m src.backend.scripts.with_env [--names] ENV_FILE -- COMMAND ...", file=sys.stderr)
        return 2
    path, command = Path(argv[0]), argv[2:]
    if not path.is_file():
        print(f"{path} not found", file=sys.stderr)
        return 2
    if committable(path):
        print(f"refusing {path}: git would commit it; use a gitignored name such as .env.staging.local", file=sys.stderr)
        return 2
    try:
        values = parse(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 2
    if names:
        print(f"loaded: {', '.join(sorted(values))}", file=sys.stderr)
    return subprocess.run(command, env={**os.environ, **values}).returncode


if __name__ == "__main__":
    raise SystemExit(main())
