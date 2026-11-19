"""Differential test: Balancer V2's Solidity StableMath against the Fe port.

Usage: python3 -m harness.differential [--runs N]

Builds the Fe harness contract with the pinned compiler, runs the Foundry
suite in contracts/reference (identical calldata to both, byte-identical
results required), and writes docs/results/differential/<platform>.json with
how many vectors each function saw and how they ended.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib

from harness.toolchain import ROOT, host_platform, resolve

REFERENCE = ROOT / "contracts" / "reference"
FE_INGOT = ROOT / "ingots" / "balancer_v2"
OUTCOMES = REFERENCE / "cache" / "differential-outcomes.csv"
BALANCER_COMMIT = "e91a2b643a49856f51a648d175667c1b48cf3377"
SCHEMA = "dimension.differential/v1"

_TEST_NAME = re.compile(r"testFuzz_(\w+)\(")


def build_fe_harness() -> None:
    fe = resolve()
    shutil.rmtree(FE_INGOT / "out", ignore_errors=True)
    outcome = fe.run(["build", "--emit", "bytecode"], FE_INGOT)
    if outcome.code != 0:
        raise SystemExit(f"Fe harness failed to build:\n{outcome.output}")


def run_forge(runs: int | None) -> dict:
    env = dict(os.environ)
    if runs:
        env["FOUNDRY_FUZZ_RUNS"] = str(runs)
    OUTCOMES.unlink(missing_ok=True)
    # Foundry replays previously failing inputs first; clear them so every run
    # executes exactly the configured vectors.
    shutil.rmtree(REFERENCE / "cache" / "fuzz", ignore_errors=True)
    proc = subprocess.run(
        ["forge", "test", "--json", "--match-contract", "StableMathDifferential"], cwd=REFERENCE, env=env, capture_output=True, text=True, timeout=3600
    )
    try:
        return json.loads(proc.stdout[proc.stdout.index("{"):])
    except ValueError:
        raise SystemExit(f"forge test produced no JSON:\n{proc.stdout}\n{proc.stderr}")


def tool_version(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, help="fuzz runs per function (default: foundry.toml)")
    args = parser.parse_args()

    fe = resolve()
    build_fe_harness()
    results = run_forge(args.runs)

    outcomes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    with OUTCOMES.open() as f:
        for function, outcome in csv.reader(f):
            outcomes[function][outcome] += 1

    functions = {}
    failed = []
    for suite in results.values():
        for test, result in suite["test_results"].items():
            name = _TEST_NAME.match(test).group(1)
            if result["status"] != "Success":
                failed.append(name)
            seen = outcomes[name]
            functions[name] = {
                "passed": result["status"] == "Success",
                "vectors": sum(seen.values()),
                "both_succeeded": seen["ok"],
                "both_reverted": {k: v for k, v in sorted(seen.items()) if k != "ok"},
            }

    config = tomllib.loads((REFERENCE / "foundry.toml").read_text())
    total = sum(f["vectors"] for f in functions.values())
    succeeded = sum(f["both_succeeded"] for f in functions.values())
    report = {
        "schema": SCHEMA,
        "question": "Does the Fe port compute exactly what Balancer V2's Solidity computes, reverts included?",
        "comparison": "identical calldata to both; equal success flag and byte-identical return data required",
        "reference": {"repository": "balancer/balancer-v2-monorepo", "commit": BALANCER_COMMIT, "solc": "0.7.6"},
        "fe": {"version": fe.version, "commit": fe.commit},
        "forge": tool_version(["forge", "--version"]),
        "fuzz": {"seed": config["fuzz"]["seed"], "runs_per_function": args.runs or config["fuzz"]["runs"]},
        "platform": host_platform(),
        "summary": {
            "functions": len(functions),
            "vectors": total,
            "both_succeeded": succeeded,
            "both_reverted": total - succeeded,
            "mismatches": len(failed),
        },
        "functions": dict(sorted(functions.items())),
    }
    out = ROOT / "docs" / "results" / "differential"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{host_platform()}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    print(f"{len(functions)} functions, {total} vectors: {succeeded} succeeded identically, "
          f"{total - succeeded} reverted identically, {len(failed)} mismatched")
    print(f"report: {path.relative_to(ROOT)}")
    if failed:
        print("mismatched:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
