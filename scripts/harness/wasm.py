"""The Balancer kernels on a third target: WebAssembly, in the browser.

Usage: python3 -m harness.wasm

Builds the Fe compiler with its WebAssembly backend at the pinned commit
(scripts/toolchain/build-fe-wasm.sh). Bundles interop/kernels.fe with Dimension,
the Balancer kernels and the batch LivePlan plans into one file, which that
backend requires, and compiles it to web/public/kernels.wasm, twice, to show
the build reproduces. Runs the module in Node.js and requires the value per
BPT after every exit, on every kernel, to equal forge's run of the deployed
contracts on the EVM, and each failing exit to fail the same check. Then runs
the unit suites on the WebAssembly backend. Writes docs/results/wasm/<platform>.json.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.live import PLAN, prepare
from harness.toolchain import ROOT, resolve, sha256_file

EXPORTS = ROOT / "interop" / "kernels.fe"
CHECK = ROOT / "interop" / "check.mjs"
PUBLIC = ROOT / "web" / "public"
INGOTS = ["dimension", "balancer_v2"]
EVM_ONLY = '#![cfg(target = "evm")]'
POOLS = {"faithful": "FaithfulPool", "typed": "TypedPool", "guarded": "GuardedPool"}
SUITES = ["examples/quickstart", "tests/core", "tests/vault", "tests/explorer"]
# Fe's WebAssembly backend builds no test that uses the EVM's test attributes.
UNSUPPORTED = "cannot use EVM `should_revert` or `balance` attributes"
SCHEMA = "dimension.wasm/v1"


def source(path: Path, ingot: str) -> str | None:
    """A source file as the body of an inline module; None for an EVM-only file."""
    text = path.read_text()
    if EVM_ONLY in text:
        return None
    # An inline module cannot hold inner doc comments.
    text = "\n".join(line for line in text.splitlines() if not line.startswith("//!"))
    if ingot != "dimension":
        text = re.sub(r"(?<![\w:])dimension::", "ingot::dimension::", text)
    return text


def modules(directory: Path, ingot: str) -> str:
    """Each file of `directory` as a module, holding the modules of its directory, as Fe nests them."""
    parts = []
    for path in sorted(directory.glob("*.fe")):
        body = source(path, ingot) if path.name != "lib.fe" else None
        if body is None:
            continue
        children = modules(directory / path.stem, ingot) if (directory / path.stem).is_dir() else ""
        parts.append(f"pub mod {path.stem} {{\n{body}\n{children}}}\n")
    return "\n".join(parts)


def bundle(plan: dict) -> str:
    """The export file, each ingot as a module, and the batch as `ingot::plan`."""
    exits = ", ".join(str(a) for a in plan["exits"])
    parts = [
        EXPORTS.read_text(),
        "pub mod plan {\n"
        "    // From contracts/reference/test/LivePlan.t.sol, as scripts/harness/wasm.py bundles it.\n"
        f"    pub const SUPPLY: u256 = {plan['supply']}\n"
        f"    pub const COUNT: usize = {len(plan['exits'])}\n"
        f"    pub const EXITS: [u256; {len(plan['exits'])}] = [{exits}]\n"
        "}\n",
    ]
    for ingot in INGOTS:
        src = ROOT / "ingots" / ingot / "src"
        parts.append(f"pub mod {ingot} {{\n{source(src / 'lib.fe', ingot)}\n{modules(src, ingot)}}}\n")
    return "\n".join(parts)


def compare(plan: dict, kernels: dict) -> tuple[int, list[str]]:
    """The values per BPT compared with forge's run of the deployed contracts,
    and the kernels, or their failing checks, that differ from it."""
    steps, mismatches = 0, []
    for kernel, pool in POOLS.items():
        evm = [str(plan[pool]["start"])] + [str(v) for v in plan[pool]["rates"]]
        steps += len(evm)
        if kernels[kernel]["values"] != evm:
            mismatches.append(kernel)
        # The EVM reverts the failing exit with Error("BAL#xyz"); the kernels report xyz.
        reason = bytes.fromhex(plan[pool]["reason"][2:])
        evm_code = int(reason[68 : 68 + int.from_bytes(reason[36:68], "big")].decode()[4:]) if reason else None
        if kernels[kernel]["failure"] != evm_code:
            mismatches.append(f"{kernel} failure")
    return steps, mismatches


def build(fe_wasm: str, text: str, out: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="dimension-wasm-") as tmp:
        src = Path(tmp) / "kernels.fe"
        src.write_text(text)
        built = subprocess.run(
            [fe_wasm, "--color", "never", "build", "--backend", "wasm", "-O", "2", "--out-dir", str(out), str(src)],
            capture_output=True, text=True,
        )
    if built.returncode != 0:
        raise SystemExit(f"the bundle does not build for WebAssembly:\n{built.stdout}{built.stderr}")
    return out / "kernels.wasm"


def suites(fe_wasm: str) -> dict:
    """Each unit suite on the WebAssembly backend: tests passed, failed, and the
    ones the backend cannot build."""
    results = {}
    for suite in SUITES:
        run = subprocess.run(
            [fe_wasm, "--color", "never", "test", "--backend", "wasm"], cwd=ROOT / suite, capture_output=True, text=True
        )
        lines = (run.stdout + run.stderr).splitlines()
        passed = sorted({m[1] for l in lines if (m := re.match(r"PASS\s+\[[^]]*\]\s+(\S+)", l))})
        failed = sorted({m[1] for l in lines if (m := re.match(r"FAIL\s+\[[^]]*\]\s+(\S+)", l))})
        unsupported = sorted({f for f in failed if any(f in l and UNSUPPORTED in l for l in lines)})
        results[suite] = {"passed": len(passed), "failed": [f for f in failed if f not in unsupported], "unsupported": unsupported}
    return results


def main() -> int:
    fe = resolve()
    fe_wasm = subprocess.run(
        [str(ROOT / "scripts" / "toolchain" / "build-fe-wasm.sh")], capture_output=True, text=True
    )
    if fe_wasm.returncode != 0:
        print(fe_wasm.stderr[-3000:])
        return 1
    fe_wasm = fe_wasm.stdout.strip()
    version = subprocess.run([fe_wasm, "--version"], capture_output=True, text=True).stdout.strip()

    prepare()
    plan = json.loads(PLAN.read_text())
    text = bundle(plan)
    with tempfile.TemporaryDirectory(prefix="dimension-wasm-out-") as tmp:
        first = build(fe_wasm, text, Path(tmp) / "a")
        second = build(fe_wasm, text, Path(tmp) / "b")
        reproducible = first.read_bytes() == second.read_bytes()
        served = PUBLIC / "kernels.wasm"
        updated = not served.exists() or served.read_bytes() != first.read_bytes()
        shutil.copy(first, served)
        shutil.copy(first.with_name("kernels.manifest.json"), PUBLIC / "kernels.manifest.json")

    ran = subprocess.run(["node", str(CHECK), str(served)], capture_output=True, text=True)
    if ran.returncode != 0:
        print(ran.stdout, ran.stderr)
        return 1
    wasm = json.loads(ran.stdout)

    steps, mismatches = compare(plan, wasm["kernels"])
    faithful, typed = wasm["kernels"]["faithful"], wasm["kernels"]["typed"]
    tests = suites(fe_wasm)
    ran_tests = sum(s["passed"] for s in tests.values())
    skipped = [t for s in tests.values() for t in s["unsupported"]]
    failing = [t for s in tests.values() for t in s["failed"]]

    claims = [
        {
            "question": "Compiled to WebAssembly from the same source, do the kernels compute every step of the batch exactly as the deployed contracts do on the EVM?",
            "holds": not mismatches,
            "evidence": (
                f"{steps} values per BPT, the start and after each exit on each kernel, equal to forge's run of the "
                f"same contracts to the wei; faithful {int(faithful['values'][0]) / 1e18:.4f} to "
                f"{int(faithful['values'][-1]) / 1e18:.4f}; typed and guarded fail exit {len(typed['values'])} with "
                f"BAL#{typed['failure']:03d}, as on the EVM"
            ) if not mismatches else f"differs: {', '.join(mismatches)}",
        },
        {
            "question": "Is the module reproducible, and is it the one the site serves?",
            "holds": reproducible,
            "evidence": f"two builds byte-identical: {served.stat().st_size:,} bytes, sha256 {sha256_file(served)[:16]}…, "
                        f"{'updated' if updated else 'unchanged'} in web/public",
        },
        {
            "question": "Do the unit suites run on the WebAssembly backend?",
            "holds": not failing,
            "evidence": f"{ran_tests} tests pass in {len(SUITES)} suites; "
                        + (f"{len(skipped)} not built: {', '.join(skipped)}, which uses the EVM's `should_revert`" if skipped else "none skipped")
                        + (f"; failing: {', '.join(failing)}" if failing else ""),
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "Do Dimension's Balancer kernels compute the same results in WebAssembly as on the EVM?",
        "fe": {"version": fe.version, "commit": fe.commit, "wasm_compiler": version},
        "platform": fe.platform,
        "module": {"file": "web/public/kernels.wasm", "bytes": served.stat().st_size, "sha256": sha256_file(served)},
        "exits": wasm["exits"],
        "milliseconds": wasm["milliseconds"],
        "kernels": wasm["kernels"],
        "suites": tests,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "wasm"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{fe.platform}.json").write_text(json.dumps(report, indent=2) + "\n")
    for c in claims:
        print(f"{'holds' if c['holds'] else 'FAILS'}  {c['question']}\n       {c['evidence']}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
