"""Dimension on the other Fe release it supports.

Usage: python3 -m harness.compat

Installs Fe 26.7.0, pinned and checksum-verified like the main toolchain
(scripts/toolchain/fe-compat.lock). Then type-checks every ingot, runs every unit
suite on the backends it declares, and requires each compile-fail case to be
rejected with its expected code while its corrected twin passes. Diagnostics are
not compared with the goldens, whose exact text belongs to the pinned release.
Writes docs/results/compat/<platform>.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from harness.cases import SUITES, discover
from harness.toolchain import ROOT, host_platform

LOCK = ROOT / "scripts" / "toolchain" / "fe-compat.lock"
SCHEMA = "dimension.compat/v1"
_CODE = re.compile(r"^error\[([0-9]+-[0-9]+)\]", re.MULTILINE)


def run(fe: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(fe), "--color", "never", *args], cwd=cwd, capture_output=True, text=True)


def main() -> int:
    installed = subprocess.run([str(ROOT / "scripts" / "toolchain" / "install-fe.sh"), str(LOCK)], capture_output=True, text=True)
    if installed.returncode != 0:
        print(installed.stderr)
        return 1
    fe = Path(installed.stdout.strip().splitlines()[-1])
    version = run(fe, ["--version"], ROOT).stdout.strip()

    ingots = {str(i.parent.relative_to(ROOT)): run(fe, ["check"], i.parent).returncode == 0 for i in sorted((ROOT / "ingots").glob("*/fe.toml"))}

    suites: dict[str, int | None] = {}
    for case_dir in discover(SUITES["unit"]):
        spec = tomllib.loads((case_dir / "case.toml").read_text())
        for backend in spec.get("backends", ["sonatina"]):
            out = run(fe, ["test", "--backend", backend], case_dir)
            passed = re.search(r"test result: ok\. (\d+) passed; 0 failed", out.stdout + out.stderr)
            suites[f"{case_dir.relative_to(ROOT)} ({backend})"] = int(passed.group(1)) if out.returncode == 0 and passed else None

    cases: dict[str, bool] = {}
    for case_dir in discover(SUITES["compile-fail"]):
        spec = tomllib.loads((case_dir / "case.toml").read_text())
        bad = run(fe, ["check"], case_dir / spec.get("entry", "."))
        codes = set(_CODE.findall(bad.stdout + bad.stderr))
        allowed = {spec["expect_code"], *spec.get("consequential_codes", [])}
        rejected = bad.returncode != 0 and spec["expect_code"] in codes and codes <= allowed
        twin_ok = True
        if "twin" in spec:
            mode = spec.get("twin_run", "test")
            twin_ok = run(fe, ["test"] if mode == "test" else ["check"], case_dir / spec["twin"]).returncode == 0
        cases[case_dir.name] = rejected and twin_ok

    failing_suites = [name for name, n in suites.items() if n is None]
    claims = [
        {
            "question": f"On {version}, does every ingot type-check, and every unit suite pass on the backends it declares?",
            "holds": all(ingots.values()) and not failing_suites,
            "evidence": f"{sum(ingots.values())} of {len(ingots)} ingots type-check; "
            f"{len(suites) - len(failing_suites)} of {len(suites)} suite runs pass, {sum(n or 0 for n in suites.values())} tests"
            + (f"; failing: {', '.join(failing_suites)}" if failing_suites else ""),
        },
        {
            "question": f"On {version}, is every compile-fail case rejected with its expected code, and its corrected twin accepted?",
            "holds": all(cases.values()),
            "evidence": f"{sum(cases.values())} of {len(cases)} cases"
            + (f"; not: {', '.join(n for n, ok in cases.items() if not ok)}" if not all(cases.values()) else ""),
        },
    ]
    platform = host_platform()
    report = {
        "schema": SCHEMA,
        "question": "Does Dimension work, unchanged, on the other Fe release it supports?",
        "fe": {"reported": version, "lock": str(LOCK.relative_to(ROOT))},
        "platform": platform,
        "ingots": ingots,
        "suites": suites,
        "compile_fail": cases,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "compat"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
