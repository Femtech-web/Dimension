"""Runs a suite of Fe cases against the pinned compiler and golden files.

Usage: python3 -m harness.cases <suite> [--update]

A case is any directory holding a `case.toml`. --update rewrites the golden
files from the current compiler output. Review the diff before keeping it: a
changed golden means the compiler's behaviour or the code under test changed.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from harness.toolchain import ROOT, Fe, resolve

SUITES = {
    "probes": [ROOT / "tests" / "probes"],
    "compile-fail": [ROOT / "tests" / "compile_fail"],
    "unit": [ROOT / "tests" / "core", ROOT / "tests" / "oracle", ROOT / "tests" / "explorer", ROOT / "tests" / "vault"],
}
TESTS = ROOT / "tests"
SCHEMA = "dimension.cases/v1"

_ERROR_CODE = re.compile(r"^error\[([0-9]+-[0-9]+)\]: (.*)$", re.MULTILINE)
_SUMMARY = re.compile(r"test result: \w+\. (\d+) passed; (\d+) failed")


@dataclass
class Result:
    id: str
    kind: str
    layer: str
    mechanism: str
    incident: str | None = None
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    observed: dict = field(default_factory=dict)

    def fail(self, problem: str) -> None:
        self.ok = False
        self.problems.append(problem)


def golden(path: Path, actual: str, update: bool, result: Result) -> None:
    if update:
        path.write_text(actual)
    elif not path.exists():
        result.fail(f"missing golden {path.relative_to(ROOT)}; run with --update")
    elif path.read_text() != actual:
        result.fail(f"output differs from {path.relative_to(ROOT)}")


def sorted_test_output(output: str) -> str:
    """Tests run in parallel, so their PASS/FAIL lines arrive in any order."""
    lines = output.splitlines()
    verdicts = sorted(line for line in lines if line.startswith(("PASS", "FAIL")))
    rest = [line for line in lines if not line.startswith(("PASS", "FAIL"))]
    return "\n".join(verdicts + rest) + "\n"


def check_compile_fail(fe: Fe, case_dir: Path, spec: dict, result: Result, update: bool) -> None:
    outcome = fe.run(["check"], case_dir / spec.get("entry", "."))
    errors = _ERROR_CODE.findall(outcome.output)
    if outcome.code == 0 or not errors:
        result.fail("compiled, but it must be rejected")
        return
    intended = [(c, m) for c, m in errors if c == spec["expect_code"]]
    code, message = (intended or errors)[0]
    result.observed = {
        "error_code": code,
        "message": message,
        "diagnostics_sha256": hashlib.sha256(outcome.output.encode()).hexdigest(),
    }
    if not intended:
        result.fail(f"rejected, but not with {spec['expect_code']}")
    # Every error must be the intended one; a stray error elsewhere in the
    # case would mean it fails for a reason other than the mechanism it names.
    # `consequential_codes` lists errors the same mistake also triggers.
    allowed = {spec["expect_code"], *spec.get("consequential_codes", [])}
    unexpected = sorted({c for c, _ in errors if c not in allowed})
    if unexpected:
        result.fail(f"expected only {', '.join(sorted(allowed))}, also got {', '.join(unexpected)}")
    golden(case_dir / "expected.diagnostics", outcome.output, update, result)
    if "twin" in spec:
        check_twin(fe, case_dir, spec, result, update)


def fix_diff(unsafe: Path, fixed: Path) -> list[str]:
    """The lines the fix changes, without diff headers."""
    lines = difflib.unified_diff(unsafe.read_text().splitlines(), fixed.read_text().splitlines(), lineterm="", n=0)
    return [line for line in lines if line[:1] in "+-" and not line.startswith(("+++", "---"))]


def check_twin(fe: Fe, case_dir: Path, spec: dict, result: Result, update: bool) -> None:
    """A rejection only means something if the corrected code is accepted and
    computes the right result; the twin is that corrected code."""
    twin_dir = case_dir / spec["twin"]
    mode = spec.get("twin_run", "test")
    twin = {"mode": mode, "fix": fix_diff(case_dir / "src" / "lib.fe", twin_dir / "src" / "lib.fe")}
    if "allow_unsafe = true" in (twin_dir / "fe.toml").read_text() and not twin["fix"]:
        twin["fix"] = ["+fe.toml: dimension = { ..., allow_unsafe = true }"]
    if mode == "test":
        outcome = fe.run(["test", "--backend", "sonatina"], twin_dir)
        output = sorted_test_output(outcome.output)
        summary = _SUMMARY.search(output)
        twin["passed"] = int(summary.group(1)) if summary else 0
        if outcome.code != 0 or not summary or summary.group(2) != "0" or twin["passed"] == 0:
            result.fail("the corrected twin does not pass its tests")
        golden(twin_dir / "expected.sonatina.txt", output, update, result)
    else:
        outcome = fe.run(["check"], twin_dir)
        if outcome.code != 0:
            result.fail(f"the corrected twin does not compile:\n{outcome.output}")
    twin["ok"] = result.ok
    result.observed["twin"] = twin


def check_compile_pass(fe: Fe, case_dir: Path, result: Result) -> None:
    outcome = fe.run(["check"], case_dir)
    result.observed = {"compiles": outcome.code == 0}
    if outcome.code != 0:
        result.fail("expected to compile")


def check_tests(fe: Fe, case_dir: Path, spec: dict, result: Result, update: bool) -> None:
    for backend in spec["backends"]:
        if backend == "native" and not fe.native:
            result.observed[backend] = "skipped: no native executables on this platform"
            continue
        outcome = fe.run(["test", "--backend", backend], case_dir)
        output = sorted_test_output(outcome.output)
        summary = _SUMMARY.search(output)
        if outcome.code != 0 or not summary or summary.group(2) != "0":
            result.fail(f"{backend} tests failed")
        passed = int(summary.group(1)) if summary else 0
        result.observed[backend] = {"passed": passed}
        golden(case_dir / f"expected.{backend}.txt", output, update, result)


def runtime_bytecode(fe: Fe, ingot: Path, contract: str, level: str) -> bytes:
    shutil.rmtree(ingot / "out", ignore_errors=True)
    outcome = fe.run(["build", "-O", level, "--emit", "runtime-bytecode"], ingot)
    if outcome.code != 0:
        raise RuntimeError(f"build failed in {ingot}: {outcome.output}")
    code = bytes.fromhex((ingot / "out" / f"{contract}.runtime.bin").read_text().strip())
    shutil.rmtree(ingot / "out", ignore_errors=True)
    return code


def check_bytecode(fe: Fe, case_dir: Path, spec: dict, result: Result, update: bool) -> None:
    table: dict[str, dict] = {}
    for level in spec["levels"]:
        row = {}
        for variant in ("typed", "raw"):
            code = runtime_bytecode(fe, case_dir / variant, spec["contract"], level)
            row[variant] = {"bytes": len(code), "sha256": hashlib.sha256(code).hexdigest()}
        row["identical"] = row["typed"]["sha256"] == row["raw"]["sha256"]
        table[f"O{level}"] = row
    result.observed = {"question": spec["question"], "levels": table}
    for level in spec["identical_at"]:
        if not table[f"O{level}"]["identical"]:
            result.fail(f"typed and raw bytecode differ at -O{level}")
    golden(case_dir / "expected.json", json.dumps(table, indent=2) + "\n", update, result)


def discover(roots: list[Path]) -> list[Path]:
    return sorted(path.parent for root in roots for path in root.rglob("case.toml"))


def run(fe: Fe, roots: list[Path], update: bool) -> list[Result]:
    results = []
    for case_dir in discover(roots):
        spec = tomllib.loads((case_dir / "case.toml").read_text())
        result = Result(
            id=str(case_dir.relative_to(TESTS)),
            kind=spec["kind"],
            layer=spec.get("layer", "cost"),
            mechanism=spec.get("mechanism", spec.get("question", "")),
            incident=spec.get("incident"),
        )
        match spec["kind"]:
            case "compile_fail":
                check_compile_fail(fe, case_dir, spec, result, update)
            case "compile_pass":
                check_compile_pass(fe, case_dir, result)
            case "test":
                check_tests(fe, case_dir, spec, result, update)
            case "bytecode":
                check_bytecode(fe, case_dir, spec, result, update)
            case other:
                result.fail(f"unknown kind {other}")
        status = "ok  " if result.ok else "FAIL"
        print(f"{status} {result.id}" + "".join(f"\n     {p}" for p in result.problems))
        results.append(result)
    return results


def write_report(fe: Fe, suite: str, results: list[Result]) -> Path:
    reports = ROOT / "docs" / "results" / suite
    reports.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": SCHEMA,
        "suite": suite,
        "fe": {"version": fe.version, "commit": fe.commit, "binary_sha256": fe.binary_sha256},
        "platform": fe.platform,
        "summary": {
            "cases": len(results),
            "ok": sum(r.ok for r in results),
            "by_kind": {k: sum(r.kind == k for r in results) for k in sorted({r.kind for r in results})},
        },
        "cases": [
            {
                "id": r.id,
                "kind": r.kind,
                "layer": r.layer,
                "mechanism": r.mechanism,
                **({"incident": r.incident} if r.incident else {}),
                "ok": r.ok,
                "problems": r.problems,
                "observed": r.observed,
            }
            for r in results
        ],
    }
    path = reports / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("suite", choices=sorted(SUITES))
    parser.add_argument("--update", action="store_true", help="rewrite golden files")
    args = parser.parse_args()

    fe = resolve()
    print(f"{args.suite}: fe {fe.version} ({fe.commit[:7]}) on {fe.platform}")
    results = run(fe, SUITES[args.suite], args.update)
    report = write_report(fe, args.suite, results)
    failed = [r.id for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} cases ok; report: {report.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
