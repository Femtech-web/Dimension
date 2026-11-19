"""The November 2025 exploit, step by step, through the three Fe kernels.

Usage: python3 -m harness.replay

Runs contracts/reference/test/AttackReplay.t.sol: for each of the attacker's
three transactions on the osETH/wETH pool, a mainnet fork at that transaction
loads the pool's real state into the faithful, typed and guarded Fe kernels and
replays the transaction's own swaps from fixtures/balancer-v2-exploit/. The
faithful kernel must compute every step exactly as Balancer's Vault did and end
where the pool ended once the real transaction runs. Needs an archive RPC:
MAINNET_RPC_URL, or a public default. Writes docs/results/replay/<platform>.json.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

from harness.evm import build
from harness.toolchain import ROOT, resolve

REFERENCE = ROOT / "contracts" / "reference"
RESULTS = REFERENCE / "cache" / "attack-replay.csv"
DEFAULT_RPC = "https://eth.drpc.org"
SCHEMA = "dimension.replay/v1"
WAD = 10**18
ATTACKS = {
    1: (23_717_397, "0x6ed07db1a9fe5c0794d44cd36081d6a6df103fab868cdd75d581e3bd23bc9742"),
    2: (23_717_398, "0x1dc60f917e4d841f281e827cf82f93c7355e08f5855e9ae5b0a1764b38ed4b87"),
    3: (23_717_399, "0xe1d5f36f0aa6f6a07865ac4feaae5bda839f489372eb3ece7d53fb10100a1eb1"),
}
KERNELS = ("faithful", "typed", "guarded")


def main() -> int:
    fe = resolve()
    build()
    env = dict(os.environ)
    env["MAINNET_RPC_URL"] = os.environ.get("MAINNET_RPC_URL") or DEFAULT_RPC
    RESULTS.unlink(missing_ok=True)
    for _ in range(2):
        proc = subprocess.run(
            ["forge", "test", "--match-contract", "AttackReplay"], cwd=REFERENCE, env=env, capture_output=True, text=True, timeout=3600
        )
        # Public RPCs drop connections; try again once before reporting a failure.
        if "could not instantiate forked environment" not in proc.stdout + proc.stderr:
            break

    if proc.returncode != 0:
        print(proc.stdout[-4000:], proc.stderr[-2000:])
        return 1

    steps: dict[tuple[int, str], list[dict]] = {}
    ends: dict[tuple[int, str], dict] = {}
    real: dict[int, dict] = {}
    with RESULTS.open() as f:
        for row in csv.reader(f):
            if row[0] == "step":
                _, n, kernel, i, kind, given, computed_real, result, rate = row
                steps.setdefault((int(n), kernel), []).append({
                    "step": int(i),
                    "kind": kind,
                    "given": int(given),
                    "balancer": int(computed_real),
                    "result": result,
                    "value_per_bpt_wad": int(rate),
                })
            elif row[0] == "end":
                _, n, kernel, done, total, matched, start, end, b0, b1, supply = row
                ends[(int(n), kernel)] = {
                    "steps_completed": int(done),
                    "steps": int(total),
                    "steps_equal_to_balancer": int(matched),
                    "value_per_bpt_start_wad": int(start),
                    "value_per_bpt_end_wad": int(end),
                    "balances": [int(b0), int(b1)],
                    "supply": int(supply),
                }
            else:
                _, n, b0, b1, supply = row
                real[int(n)] = {"balances": [int(b0), int(b1)], "supply": int(supply)}

    attacks = []
    for n, (block, tx) in ATTACKS.items():
        entry = {"attack": n, "block": block, "transaction": tx, "real_end_state": real.get(n)}
        for kernel in KERNELS:
            e = dict(ends.get((n, kernel), {}))
            rows = steps.get((n, kernel), [])
            diverged = next((r for r in rows if r["result"] != str(r["balancer"])), None)
            if diverged:
                e["first_difference"] = diverged
            # The value per BPT after each completed step, for charting the attack.
            e["value_per_bpt_by_step_wad"] = [r["value_per_bpt_wad"] for r in rows if r["result"].isdigit()]
            e["kinds_by_step"] = [r["kind"] for r in rows]
            entry[kernel] = e
        attacks.append(entry)

    faithful = [a["faithful"] for a in attacks]
    total = sum(f.get("steps", 0) for f in faithful)
    exact = sum(f.get("steps_equal_to_balancer", 0) for f in faithful)
    same_end = all(
        a["real_end_state"] and a["faithful"].get("balances") == a["real_end_state"]["balances"]
        and a["faithful"].get("supply") == a["real_end_state"]["supply"]
        for a in attacks
    )
    first = attacks[0]
    claims = [
        {
            "question": "Does the Fe port compute every step of the real exploit exactly as Balancer's Vault did?",
            "holds": proc.returncode == 0 and total > 0 and exact == total,
            "evidence": f"{exact} of {total} steps across the three attack transaction"
            f"s ({', '.join(str(f.get('steps')) for f in faithful)}): every amount equal",
        },
        {
            "question": "After each attack transaction, does the faithful kernel hold exactly what the real pool held?",
            "holds": proc.returncode == 0 and same_end,
            "evidence": "WETH and osETH balances and BPT supply equal after each transaction; value per BPT "
            + " -> ".join(f"{f['value_per_bpt_start_wad'] / WAD:.6g}" for f in faithful)
            + f" -> {faithful[-1]['value_per_bpt_end_wad'] / WAD:.6g}",
        },
        {
            "question": "Do the typed and guarded kernels stop the attacker's own sequence?",
            "holds": all(a[k]["steps_completed"] < a[k]["steps"] for a in attacks for k in ("typed", "guarded")),
            "evidence": "yes: "
            + "; ".join(
                f"transaction {a['attack']} reverts at step {a['typed']['steps_completed']} with "
                f"{steps[(a['attack'], 'typed')][-1]['result']}"
                for a in attacks
            )
            + f". Before that, value per BPT on the typed kernel rose from {first['typed']['value_per_bpt_start_wad'] / WAD:.4f} "
            f"to {first['typed']['value_per_bpt_end_wad'] / WAD:.4f}",
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "Does the Fe port reproduce the real exploit step by step, and what do the same steps do to the typed kernels?",
        "pool": "0xDACf5Fa19b1f720111609043ac67A9818262850c (osETH/wETH ComposableStablePool)",
        "fixtures": "fixtures/balancer-v2-exploit/attack-{1,2,3}.csv, from the transactions' Swap events",
        "state_loaded": "at each transaction: Vault balances, amplification, swap and protocol swap fees, actual supply "
        "(protocol fees due paid), the current invariant as the stored one, and the osETH rate after refreshing its cache",
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "attacks": attacks,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "replay"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    for a in attacks:
        f = a["faithful"]
        print(f"attack {a['attack']} (block {a['block']:,}): faithful {f['steps_equal_to_balancer']}/{f['steps']} steps equal, "
              f"value per BPT {f['value_per_bpt_start_wad'] / WAD:.6g} -> {f['value_per_bpt_end_wad'] / WAD:.6g}; "
              f"typed stops at step {a['typed']['steps_completed']}, guarded at {a['guarded']['steps_completed']}")
    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
