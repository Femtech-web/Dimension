"""The Balancer kernels as a native library, called from C.

Usage: python3 -m harness.native

Bundles interop/kernels.fe with Dimension, the Balancer kernels and the batch
LivePlan plans, as `make wasm` does, and marks its three functions
`#[unsafe(export)]`, as a native library exports them. Builds the bundle with
the pinned Fe into a static library (`fe build --backend native --emit
staticlib`), links interop/check.c against it with the system C compiler, and
requires the value per BPT after every exit, on every kernel, to equal forge's
run of the deployed contracts on the EVM, and each failing exit to fail the
same check. Writes docs/results/native/<platform>.json.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.live import prepare
from harness.toolchain import ROOT, Fe, resolve
from harness.wasm import bundle, compare

CHECK = ROOT / "interop" / "check.c"
EXPORTED = ("exits", "value_after", "failure")
SCHEMA = "dimension.native/v1"


def exported(text: str) -> str:
    """The bundle with the kernels' functions marked as a native library's exports."""
    names = "|".join(EXPORTED)
    marked, count = re.subn(rf"^pub fn ({names})\(", r"#[unsafe(export)]\npub fn \1(", text, flags=re.M)
    if count != len(EXPORTED):
        raise SystemExit(f"interop/kernels.fe should define {len(EXPORTED)} exported functions; found {count}")
    return marked


def build(fe: Fe, text: str, out: Path) -> Path:
    out.mkdir(parents=True)
    (out / "kernels.fe").write_text(text)
    built = fe.run(["build", "--backend", "native", "--emit", "staticlib", "-O", "2", "--out-dir", ".", "kernels.fe"], out)
    if built.code != 0:
        raise SystemExit(f"the bundle does not build as a native library:\n{built.output}")
    return out / "libkernels.a"


def main() -> int:
    fe = resolve()
    if not fe.native:
        print(f"skipped: Fe {fe.version} builds no native libraries on {fe.platform}")
        return 0
    cc = os.environ.get("CC", "cc")
    if not shutil.which(cc):
        raise SystemExit(f"no C compiler: {cc} is not on PATH (set CC to use another)")
    compiler = subprocess.run([cc, "--version"], capture_output=True, text=True).stdout.splitlines()[0]

    plan = prepare()
    text = exported(bundle(plan))
    with tempfile.TemporaryDirectory(prefix="dimension-native-") as tmp:
        library = build(fe, text, Path(tmp) / "lib")
        size = library.stat().st_size
        program = Path(tmp) / "check"
        linked = subprocess.run([cc, "-O2", str(CHECK), str(library), "-o", str(program)], capture_output=True, text=True)
        if linked.returncode != 0:
            raise SystemExit(f"interop/check.c does not link against the library:\n{linked.stderr}")
        ran = subprocess.run([str(program)], capture_output=True, text=True, timeout=600)
    if ran.returncode != 0:
        raise SystemExit(f"the C program failed:\n{ran.stdout}{ran.stderr}")
    native = json.loads(ran.stdout)

    steps, mismatches = compare(plan, native["kernels"])
    faithful, typed = native["kernels"]["faithful"], native["kernels"]["typed"]
    claims = [
        {
            "question": "Built as a native static library and called from C, do the kernels compute every step of the batch exactly as the deployed contracts do on the EVM?",
            "holds": not mismatches,
            "evidence": (
                f"{steps} values per BPT, the start and after each exit on each kernel, equal to forge's run of the "
                f"same contracts to the wei; faithful {int(faithful['values'][0]) / 1e18:.4f} to "
                f"{int(faithful['values'][-1]) / 1e18:.4f}; typed and guarded fail exit {len(typed['values'])} with "
                f"BAL#{typed['failure']:03d}, as on the EVM"
            ) if not mismatches else f"differs: {', '.join(mismatches)}",
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "Do Dimension's Balancer kernels compute the same results as a native library, called from C, as on the EVM?",
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "library": {"source": "interop/kernels.fe", "caller": "interop/check.c", "bytes": size, "c_compiler": compiler},
        "exits": native["exits"],
        "milliseconds": native["milliseconds"],
        "kernels": native["kernels"],
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "native"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{fe.platform}.json").write_text(json.dumps(report, indent=2) + "\n")
    for c in claims:
        print(f"{'holds' if c['holds'] else 'FAILS'}  {c['question']}\n       {c['evidence']}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
