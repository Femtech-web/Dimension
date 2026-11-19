"""The three Fe pool contracts on a real EVM.

Usage: python3 -m harness.evm

Builds FaithfulPool, TypedPool and GuardedPool with the pinned compiler, runs
contracts/reference/test/PoolAttack.t.sol (a greedy attacker repeating the
November 2025 exit against each deployed contract, and gas per operation on a
pool the size of the osETH/wETH pool), checks the claims made about them, and
writes docs/results/evm/<platform>.json.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

from harness.toolchain import ROOT, resolve

REFERENCE = ROOT / "contracts" / "reference"
INGOT = ROOT / "ingots" / "balancer_v2"
RESULTS = REFERENCE / "cache" / "pool-attack.csv"
CONTRACTS = {"faithful": "FaithfulPool", "typed": "TypedPool", "guarded": "GuardedPool"}
SCHEMA = "dimension.evm/v1"


def build(ingot: Path = INGOT, contracts: dict[str, str] = CONTRACTS) -> dict[str, int]:
    """Builds an ingot's contracts; returns each one's runtime bytecode size."""
    fe = resolve()
    shutil.rmtree(ingot / "out", ignore_errors=True)
    built = fe.run(["build", "--emit", "bytecode,runtime-bytecode"], ingot)
    if built.code != 0:
        raise SystemExit(f"Fe contracts failed to build:\n{built.output}")
    return {k: len(bytes.fromhex((ingot / "out" / f"{c}.runtime.bin").read_text().strip())) for k, c in contracts.items()}


def pct(value: int, base: int) -> str:
    return f"{(value - base) / base * 100:+.1f}%"


def main() -> int:
    fe = resolve()
    sizes = build()
    RESULTS.unlink(missing_ok=True)
    proc = subprocess.run(
        ["forge", "test", "--match-contract", "PoolAttack"], cwd=REFERENCE, capture_output=True, text=True, timeout=3600
    )
    if proc.returncode != 0:
        print(proc.stdout[-4000:], proc.stderr[-2000:])
        return 1

    attacks, gas = {}, {}
    with RESULTS.open() as f:
        for row in csv.reader(f):
            if row[0] == "attack":
                _, kernel, steps, start, end, loss = row
                attacks[kernel] = {
                    "exits": int(steps),
                    "value_per_bpt_start_wad": int(start),
                    "value_per_bpt_end_wad": int(end),
                    "value_per_bpt_change": f"{(int(end) - int(start)) / int(start) * 100:+.2f}%",
                    "holder_loss_wad": int(loss) // 10**18,
                }
            else:
                _, kernel, swap, exit_ = row
                gas[kernel] = {"swapGivenOut": int(swap), "exitGivenOut": int(exit_)}

    base = gas["faithful"]
    claims = [
        {
            "question": "Deployed on an EVM, does the faithful pool let a repeated-exit attacker take value from LPs?",
            "holds": attacks["faithful"]["holder_loss_wad"] > 0,
            "evidence": f"value per BPT {attacks['faithful']['value_per_bpt_change']} over {attacks['faithful']['exits']} exits",
        },
        {
            "question": "Do the typed and guarded pools keep the value behind each BPT under the same attack?",
            "holds": all(attacks[k]["value_per_bpt_end_wad"] >= attacks[k]["value_per_bpt_start_wad"] for k in ("typed", "guarded")),
            "evidence": f"typed {attacks['typed']['value_per_bpt_change']}, guarded {attacks['guarded']['value_per_bpt_change']}",
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "What do Dimension's layers do, and cost, in contracts deployed on a real EVM?",
        "fe": {"version": fe.version, "commit": fe.commit},
        "forge": subprocess.run(["forge", "--version"], capture_output=True, text=True).stdout.splitlines()[0],
        "platform": fe.platform,
        "attack": {"setup": "1,000 wei of each token, rate 1.21, amp 200, no fees; greedy GIVEN_OUT exits of the rated token", **attacks},
        "gas": {
            "setup": "osETH/wETH pool balances before the exploit (4,922.36 WETH, 6,851.58 osETH), amp 200, fee 0.01%, 10 tokens out",
            "per_operation": gas,
            "relative_to_faithful": {
                k: {op: pct(v[op], base[op]) for op in v} for k, v in gas.items() if k != "faithful"
            },
        },
        "runtime_bytecode_bytes": sizes,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "evm"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    for k, v in gas.items():
        print(f"gas {k:9s} swapGivenOut {v['swapGivenOut']:6d}  exitGivenOut {v['exitGivenOut']:6d}  bytecode {sizes[k]} B")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
