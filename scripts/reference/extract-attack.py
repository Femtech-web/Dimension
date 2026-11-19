"""Extracts the Balancer V2 exploit's swaps on the osETH/wETH pool into fixtures.

Usage: python3 scripts/reference/extract-attack.py   (needs `cast` and an archive RPC)

The attacker drained the pool in three transactions. For each, this reads the
receipt and writes, in execution order, every swap the Vault performed on this
pool, from its `Swap` events: token in, token out, amount in, amount out. The
batch was GIVEN_OUT throughout, so the amount out of each step is the one the
attacker named and the amount in is what Balancer computed. Fixtures go to
fixtures/balancer-v2-exploit/; the replay test reads them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fixtures" / "balancer-v2-exploit"
RPC = os.environ.get("MAINNET_RPC_URL") or "https://eth.drpc.org"
VAULT = "0xba12222222228d8ba445958a75a0704d566bf2c8"
POOL_ID = "0xdacf5fa19b1f720111609043ac67a9818262850c000000000000000000000635"
SWAP = "0x2170c741c41531aec20e7c107c24eecfdd15e69c9bb0a8dd37b1840b9e0b207b"
TOKENS = {
    "c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "f1c9acdc66974dfb6decb12aa385b9cd01190e38": "osETH",
    "dacf5fa19b1f720111609043ac67a9818262850c": "BPT",
}
ATTACKS = [
    (23_717_397, "0x6ed07db1a9fe5c0794d44cd36081d6a6df103fab868cdd75d581e3bd23bc9742"),
    (23_717_398, "0x1dc60f917e4d841f281e827cf82f93c7355e08f5855e9ae5b0a1764b38ed4b87"),
    (23_717_399, "0xe1d5f36f0aa6f6a07865ac4feaae5bda839f489372eb3ece7d53fb10100a1eb1"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for n, (block, tx) in enumerate(ATTACKS, start=1):
        receipt = json.loads(
            subprocess.run(["cast", "receipt", tx, "--rpc-url", RPC, "--json"], capture_output=True, text=True, check=True).stdout
        )
        steps = []
        for log in sorted(receipt["logs"], key=lambda l: int(l["logIndex"], 16)):
            topics = log["topics"]
            if log["address"].lower() != VAULT or topics[0] != SWAP or topics[1] != POOL_ID:
                continue
            data = log["data"][2:]
            steps.append((TOKENS[topics[2][-40:]], TOKENS[topics[3][-40:]], int(data[:64], 16), int(data[64:128], 16)))
        lines = [
            f"# Balancer V2 exploit, attack transaction {n} of 3 on the osETH/wETH pool ({POOL_ID}).",
            f"# Transaction {tx}, block {block:,}.",
            "# Each line is one swap the Vault executed on this pool, in order, read from its Swap event:",
            "# token in, token out, amount in, amount out. The batch was GIVEN_OUT: the amount out is the one named.",
            *(f"{a},{b},{x},{y}" for a, b, x, y in steps),
        ]
        path = OUT / f"attack-{n}.csv"
        path.write_text("\n".join(lines) + "\n")
        print(f"{path.relative_to(ROOT)}: {len(steps)} steps from {tx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
