"""The Fe faithful kernel against the deployed Balancer V2 pool it ports.

Usage: python3 -m harness.fidelity

Forks Ethereum mainnet at block 23,717,399, the block before the osETH/wETH
pool was drained, loads that pool's real state into the Fe FaithfulPool, and
requires every quote to equal what Balancer's own Vault returns for the same
swap or exit. Needs an archive RPC: MAINNET_RPC_URL, or a public default.
Writes docs/results/fidelity/<platform>.json.
"""

from __future__ import annotations

import collections
import csv
import json
import os
import subprocess
import sys

from harness.evm import build
from harness.toolchain import ROOT, resolve

REFERENCE = ROOT / "contracts" / "reference"
RESULTS = REFERENCE / "cache" / "pool-fidelity.csv"
DEFAULT_RPC = "https://eth.drpc.org"
SCHEMA = "dimension.fidelity/v1"


def main() -> int:
    fe = resolve()
    build()
    env = dict(os.environ)
    env["MAINNET_RPC_URL"] = os.environ.get("MAINNET_RPC_URL") or DEFAULT_RPC
    RESULTS.unlink(missing_ok=True)
    proc = subprocess.run(
        ["forge", "test", "--match-contract", "PoolFidelity"], cwd=REFERENCE, env=env, capture_output=True, text=True, timeout=3600
    )

    tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    names = {"givenIn": "swapGivenIn", "givenOut": "swapGivenOut", "exitGivenOut": "exitGivenOut"}
    with RESULTS.open() as f:
        for kind, side, _amount, real, _mine, verdict in csv.reader(f):
            key = f"{names[kind]} {'WETH' if side == '0' else 'osETH'} {'out' if kind == 'exitGivenOut' else 'in'}"
            if verdict != "match":
                outcome = "mismatches"
            elif real == "revert":
                outcome = "identical_reverts"
            else:
                outcome = "identical_values"
            tally[key]["compared"] += 1
            tally[key][outcome] += 1

    operations = {k: dict(v) for k, v in sorted(tally.items())}
    compared = sum(v["compared"] for v in operations.values())
    mismatches = sum(v.get("mismatches", 0) for v in operations.values())
    values = sum(v.get("identical_values", 0) for v in operations.values())
    report = {
        "schema": SCHEMA,
        "question": "Does the Fe port compute what the deployed Balancer V2 pool computed, on its real state before the exploit?",
        "reference": {
            "chain": "ethereum mainnet",
            "block": 23_717_399,
            "pool": "0xDACf5Fa19b1f720111609043ac67A9818262850c (osETH/wETH ComposableStablePool v5)",
            "pool_id": "0xdacf5fa19b1f720111609043ac67a9818262850c000000000000000000000635",
            "drained_at_block": 23_717_400,
            "compared_with": "Vault.queryBatchSwap on the same fork",
        },
        "state_loaded": "Vault balances, amplification, swap fee, actual supply (including protocol fees due), "
        "last join/exit invariant, and the osETH rate the pool would use (cached, or refreshed if expired)",
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "summary": {
            "compared": compared,
            "identical_values": values,
            "identical_reverts": compared - values - mismatches,
            "mismatches": mismatches,
        },
        "operations": operations,
        "claims": [
            {
                "question": "Does the Fe port return exactly what the deployed pool returned, on its state the block before the exploit?",
                "holds": proc.returncode == 0 and mismatches == 0 and compared > 0,
                "evidence": f"{compared} quotes against Vault.queryBatchSwap at block 23,717,399: {values} identical values, "
                f"{compared - values - mismatches} identical reverts, {mismatches} mismatches",
            },
        ],
    }
    out = ROOT / "docs" / "results" / "fidelity"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    for key, v in operations.items():
        print(
            f"{key:24s} {v.get('identical_values', 0):4d} identical values, "
            f"{v.get('identical_reverts', 0):3d} identical reverts, {v.get('mismatches', 0)} mismatches"
        )
    print(f"{compared} quotes against the deployed pool at block 23,717,399: {mismatches} mismatches; report: {path.relative_to(ROOT)}")
    if proc.returncode != 0:
        print(proc.stdout[-3000:])
    return 0 if all(c["holds"] for c in report["claims"]) else 1


if __name__ == "__main__":
    sys.exit(main())
