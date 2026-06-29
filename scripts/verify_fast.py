"""Fast verification checks that do not require heavy ML dependencies."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]

COMPILE_TARGETS = ("app", "scripts", "tests")
UNITTEST_TARGETS = (
    "tests.test_message_metadata",
    "tests.test_practice_mode",
    "tests.test_rag_eval",
    "tests.test_session_metadata",
    "tests.test_session_security",
    "tests.test_runtime_safety",
    "tests.test_verify_fast",
)
SECRET_SCAN_FILES = (
    "README.md",
    ".env.example",
    "docker-compose.yml",
    "docs/ARCHITECTURE.md",
    "docs/UPGRADE_ROADMAP.md",
)
FORBIDDEN_PATTERNS = (
    "sk-",
    "interviewagent123",
    "change-me-in-production",
)


@dataclass(frozen=True)
class ForbiddenTextMatch:
    path: Path
    line_number: int
    pattern: str
    line: str


def find_forbidden_text(
    root: Path,
    files: Iterable[Path],
    patterns: Sequence[str],
) -> list[ForbiddenTextMatch]:
    matches: list[ForbiddenTextMatch] = []
    for path in files:
        full_path = path if path.is_absolute() else root / path
        if not full_path.exists():
            continue
        try:
            lines = full_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for pattern in patterns:
                if pattern in line:
                    matches.append(
                        ForbiddenTextMatch(
                            path=full_path.relative_to(root),
                            line_number=line_number,
                            pattern=pattern,
                            line=line.strip(),
                        )
                    )
    return matches


def run_command(args: Sequence[str], cwd: Path = PROJECT_ROOT) -> int:
    print(f"$ {' '.join(args)}")
    completed = subprocess.run(args, cwd=str(cwd), check=False)
    return completed.returncode


def check_compile() -> int:
    return run_command([sys.executable, "-m", "compileall", "-q", *COMPILE_TARGETS])


def check_unittest() -> int:
    return run_command([sys.executable, "-m", "unittest", *UNITTEST_TARGETS, "-v"])


def check_forbidden_text() -> int:
    files = [Path(p) for p in SECRET_SCAN_FILES]
    matches = find_forbidden_text(PROJECT_ROOT, files, FORBIDDEN_PATTERNS)
    if not matches:
        print("Secret scan: no forbidden text found")
        return 0

    print("Secret scan failed:")
    for match in matches:
        print(f"  {match.path}:{match.line_number}: matched {match.pattern!r}")
    return 1


def main() -> int:
    checks = (
        ("compile", check_compile),
        ("unittest", check_unittest),
        ("secret-scan", check_forbidden_text),
    )

    failed: list[str] = []
    for name, check in checks:
        print(f"\n== {name} ==")
        if check() != 0:
            failed.append(name)

    if failed:
        print(f"\nFast verification failed: {', '.join(failed)}")
        return 1

    print("\nFast verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
