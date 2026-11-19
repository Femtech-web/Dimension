"""The Fe ERC-4626 vault against OpenZeppelin's ERC4626.

Usage: python3 -m harness.vault

Builds ingots/vault, runs contracts/reference/test/VaultDifferential.t.sol (the
vault's four previews against OpenZeppelin Contracts v5.1.0 in the same state,
over empty, dust, ordinary and huge vaults), and writes
docs/results/vault/<platform>.json. The Fe vault names no rounding: each follows
from which way its operation's given amount moves.
"""

from __future__ import annotations

import collections
import csv
import json
import shutil
import subprocess
import sys

from harness.evm import build
from harness.toolchain import ROOT, resolve

REFERENCE = ROOT / "contracts" / "reference"
INGOT = ROOT / "ingots" / "vault"
RESULTS = REFERENCE / "cache" / "vault-outcomes.csv"
SCHEMA = "dimension.vault/v1"
# Each preview is amount * numerator / denominator, with one virtual asset and share.
RATIO = {
    "previewDeposit": lambda held, issued: (issued + 1, held + 1),
    "previewMint": lambda held, issued: (held + 1, issued + 1),
    "previewWithdraw": lambda held, issued: (issued + 1, held + 1),
    "previewRedeem": lambda held, issued: (held + 1, issued + 1),
}


def main() -> int:
    fe = resolve()
    sizes = build(INGOT, {"vault": "TypedVault"})
    shutil.rmtree(REFERENCE / "cache" / "fuzz", ignore_errors=True)
    RESULTS.unlink(missing_ok=True)
    proc = subprocess.run(
        ["forge", "test", "--match-contract", "VaultDifferential"], cwd=REFERENCE, capture_output=True, text=True, timeout=3600
    )
    if proc.returncode != 0:
        print(proc.stdout[-4000:], proc.stderr[-2000:])
        return 1

    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    with RESULTS.open() as f:
        for fn, held, issued, amount, _ in csv.reader(f):
            numerator, denominator = RATIO[fn](int(held), int(issued))
            counts[fn]["vectors"] += 1
            counts[fn]["rounding_decides"] += (int(amount) * numerator) % denominator != 0
    functions = {fn: dict(c) for fn, c in sorted(counts.items())}
    vectors = sum(c["vectors"] for c in functions.values())
    decides = sum(c["rounding_decides"] for c in functions.values())
    claims = [
        {
            "question": "Do the vault's roundings, which no line of it names, give exactly what OpenZeppelin's ERC4626 gives?",
            "holds": vectors > 0,
            "evidence": f"{vectors:,} vectors over the four previews, each equal to OpenZeppelin v5.1.0 in the same state",
        },
        {
            "question": "Does the comparison test the rounding direction, not only the formula?",
            "holds": all(c["rounding_decides"] > 0 for c in functions.values()),
            "evidence": f"in {decides:,} of the vectors the exact result is fractional, so rounding the other way would differ",
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "Does an ERC-4626 vault written with Dimension round exactly as EIP-4626 and OpenZeppelin require?",
        "reference": "OpenZeppelin Contracts v5.1.0 (69c8def5f222ff96f2b5beff05dfba996368aa79), ERC4626 with decimals offset 0",
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "runtime_bytecode_bytes": sizes,
        "functions": functions,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "vault"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    for fn, c in functions.items():
        print(f"{fn:16s} {c['vectors']:6,} vectors equal to OpenZeppelin, {c['rounding_decides']:6,} where the rounding decides")
    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
