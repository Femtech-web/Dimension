"""Moonwell's cbETH market on Base forks, before, during and after MIP-X43.

Usage: python3 -m harness.moonwell

Builds the Fe oracle contracts, runs contracts/reference/test/MoonwellFork.t.sol
on Base forks (BASE_RPC_URL, or a public default), checks the compile-time case
written against the same registry, and writes docs/results/moonwell/<platform>.json
with the layer at which each form of the misconfiguration is stopped.
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
INGOT = ROOT / "ingots" / "moonwell"
RESULTS = REFERENCE / "cache" / "moonwell-fork.csv"
CASE = ROOT / "tests" / "compile_fail" / "moonwell_component_feed_in_usd_market"
CONTRACTS = {"oracle": "CbethUsdOracle", "declared": "DeclaredCbethUsdFeed"}
DEFAULT_RPC = "https://mainnet.base.org"
SCHEMA = "dimension.moonwell/v1"
WAD = 10**18


def usd(wad: int) -> str:
    return f"{wad / WAD:,.4f} USD"


def main() -> int:
    fe = resolve()
    sizes = build(INGOT, CONTRACTS)
    env = dict(os.environ)
    env["BASE_RPC_URL"] = os.environ.get("BASE_RPC_URL") or DEFAULT_RPC
    RESULTS.unlink(missing_ok=True)
    for _ in range(2):
        proc = subprocess.run(
            ["forge", "test", "--match-contract", "MoonwellFork"], cwd=REFERENCE, env=env, capture_output=True, text=True, timeout=3600
        )
        # Public RPCs drop connections; try again once before reporting a failure.
        if "could not instantiate forked environment" not in proc.stdout + proc.stderr:
            break
    if proc.returncode != 0:
        print(proc.stdout[-4000:], proc.stderr[-2000:])
        return 1

    prices, rejections, checks = [], [], []
    with RESULTS.open() as f:
        for row in csv.reader(f):
            if row[0] == "price":
                _, block, timestamp, regime, moonwell, mine = row
                prices.append({
                    "block": int(block),
                    "timestamp": int(timestamp),
                    "moonwell_oracle": regime,
                    "moonwell_wad": int(moonwell),
                    "fe_wad": int(mine),
                })
            else:
                kind, layer, declaration, error = row
                (rejections if kind == "reject" else checks).append({"layer": layer, "case": declaration, "error": error})
    prices.sort(key=lambda p: p["block"])
    rejections.sort(key=lambda r: ["bind", "read"].index(r["layer"]))
    window = [p for p in prices if p["moonwell_oracle"] == "mip-x43"]
    outside = [p for p in prices if p["moonwell_oracle"] == "composite"]

    compiled = fe.run(["check"], CASE)
    compile_rejects = compiled.code != 0 and "8-0000" in compiled.output
    layers = [
        {"layer": "compile", "case": "the cbETH/ETH feed used as cbETH's USD feed", "error": "8-0000 type mismatch",
         "rejected": compile_rejects},
        *[{**r, "rejected": True} for r in rejections],
        {"layer": "external assumption", "case": "a wrong feed declared with the decimals it reports and a band its answer falls in",
         "rejected": False, "note": "every on-chain check accepts it; make feeds rejects it before deployment"},
    ]
    claims = [
        {
            "question": "Did Moonwell's deployed oracle price cbETH at the bare exchange rate throughout MIP-X43's window?",
            "holds": bool(window) and all(p["moonwell_wad"] < 2 * WAD for p in window),
            "evidence": f"{len(window)} blocks from {window[0]['block']:,} to {window[-1]['block']:,}: "
            f"{usd(min(p['moonwell_wad'] for p in window))} to {usd(max(p['moonwell_wad'] for p in window))}",
        },
        {
            "question": "At the same blocks, does the Fe oracle price cbETH as cbETH/ETH times ETH/USD from the same feeds?",
            "holds": True,
            "evidence": f"{usd(min(p['fe_wad'] for p in window))} to {usd(max(p['fe_wad'] for p in window))}, "
            "asserted equal at every block to the product of the two feeds' answers",
        },
        {
            "question": "Where Moonwell's oracle was right, is the Fe price identical to it?",
            "holds": bool(outside) and all(p["fe_wad"] == p["moonwell_wad"] for p in outside),
            "evidence": ", ".join(f"block {p['block']:,}: {p['fe_wad']} wad" for p in outside) + ", identical",
        },
        {
            "question": "Is MIP-X43's misconfiguration rejected in each form it can take, and at which layer?",
            "holds": all(l["rejected"] for l in layers if l["layer"] != "external assumption"),
            "evidence": "; ".join(f"{l['layer']}: {l['error']}" for l in layers if l["rejected"]),
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "Would Dimension have priced Moonwell's cbETH market correctly through MIP-X43, and where does it stop the mistake?",
        "reference": {
            "chain": "base",
            "last_correct_block": 42_194_662,
            "mip_x43_block": 42_194_663,
            "mip_x43_tx": "0xd26baf29dcba7bf66db4be17b46a49bb4dacca41ace968c98c8a5b09a03ae812",
            "fixed_block": 42_538_949,
            "fix_tx": "0xd1c363dec8e159b5db38799fed885ad5a157aa1e237ccc74b312df7fad8043c5",
            "moonwell_oracle": "0xEC942bE8A8114bFD0396A5052c36027f2cA6a9d0",
            "cbeth_market": "0x3bf93770f2d4a794c3d9EBEfBAeBAE2a8f09A5E5",
            "feeds": {
                "cbETH/ETH": "0x806b4Ac04501c29769051e42783cF04dCE41440b",
                "ETH/USD": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
            },
        },
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "runtime_bytecode_bytes": sizes,
        "prices": prices,
        "layers": layers,
        "boundary_checks": checks,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "moonwell"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    for p in prices:
        print(f"block {p['block']:,}  Moonwell {usd(p['moonwell_wad']):>18s}  Fe {usd(p['fe_wad']):>18s}  ({p['moonwell_oracle']})")
    for l in layers:
        print(f"{'rejected' if l['rejected'] else 'passes  '}  {l['layer']:19s} {l['case']}")
    for c in checks:
        print(f"rejected  {c['layer']:19s} {c['case']} ({c['error']})")
    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
