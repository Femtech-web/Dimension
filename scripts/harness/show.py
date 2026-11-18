"""Shows one compile-fail case live: the bug, the compiler's verdict, the fix,
and the fixed code's result. Nothing is read from golden files.

Usage: python3 -m harness.show <case> [<case> ...]
"""

from __future__ import annotations

import re
import sys
import tomllib

from harness.cases import fix_diff
from harness.toolchain import ROOT, resolve

CASES = ROOT / "tests" / "compile_fail"
_HEADLINE = re.compile(r"^error\[[0-9-]+\]: .*$", re.MULTILINE)
_CARETS = re.compile(r"^[\s│]*\^+\s*")


def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if sys.stdout.isatty() else text


def show(fe, name: str) -> bool:
    case_dir = CASES / name
    spec = tomllib.loads((case_dir / "case.toml").read_text())
    print(bold(f"\n{name}"))
    if "incident" in spec:
        print(f"  incident:  {spec['incident']}")
    print(f"  mechanism: {spec['mechanism']}")

    rejected = fe.run(["check"], case_dir)
    headline = _HEADLINE.search(rejected.output)
    if rejected.code == 0 or not headline:
        print("  the bug:   COMPILED (it must not)")
        return False
    detail = [_CARETS.sub("", line) for line in rejected.output.splitlines() if "^" in line][:1]
    print(f"  the bug:   rejected by the compiler, {headline.group(0)}")
    for line in detail:
        print(f"             {line}")

    twin_dir = case_dir / spec["twin"]
    print("  the fix:")
    for line in fix_diff(case_dir / "src" / "lib.fe", twin_dir / "src" / "lib.fe") or ["+ fe.toml grants allow_unsafe"]:
        print(f"             {line}")
    if spec.get("twin_run", "test") == "test":
        fixed = fe.run(["test", "--backend", "sonatina"], twin_dir)
        verdicts = [l for l in fixed.output.splitlines() if l.startswith(("PASS", "FAIL"))]
        ok = fixed.code == 0 and bool(verdicts)
        print(f"  fixed:     compiles; {'; '.join(verdicts) if verdicts else 'no tests ran'}")
    else:
        fixed = fe.run(["check"], twin_dir)
        ok = fixed.code == 0
        print(f"  fixed:     {'compiles' if ok else 'DOES NOT COMPILE'}")
    return ok


def main() -> int:
    names = sys.argv[1:] or sorted(p.parent.name for p in CASES.glob("*/case.toml"))
    fe = resolve()
    results = [show(fe, name) for name in names]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
