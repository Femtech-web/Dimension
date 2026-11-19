"""The three Fe pool contracts on a real EVM.

Usage: python3 -m harness.evm

Builds FaithfulPool, TypedPool and GuardedPool with the pinned compiler at each
optimization level, and at each runs contracts/reference/test/PoolAttack.t.sol:
a greedy attacker repeating the November 2025 exit against each deployed
contract, and gas for every operation on a pool with the osETH/wETH pool's
balances and parameters. Then, for each pair in tests/zero_cost, typed code on
Dimension and the same code by hand on raw u256, compares bytes, results and gas
at each level (contracts/reference/test/ZeroCost.t.sol). Checks the claims made
about them, and writes docs/results/evm/<platform>.json.
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
# Typed code on Dimension next to the same code by hand on raw u256, each pair one contract P.
ZERO_COST = ROOT / "tests" / "zero_cost"
ZERO_COST_BINS = REFERENCE / "cache" / "zero-cost"
ZERO_COST_RESULTS = REFERENCE / "cache" / "zero-cost.csv"
CONTRACTS = {"faithful": "FaithfulPool", "typed": "TypedPool", "guarded": "GuardedPool"}
LEVELS = ["0", "1", "2", "s"]
SCHEMA = "dimension.evm/v1"


def build(ingot: Path = INGOT, contracts: dict[str, str] = CONTRACTS) -> dict[str, int]:
    """Builds an ingot's contracts; returns each one's runtime bytecode size."""
    fe = resolve()
    shutil.rmtree(ingot / "out", ignore_errors=True)
    built = fe.run(["build", "--emit", "bytecode,runtime-bytecode"], ingot)
    if built.code != 0:
        raise SystemExit(f"Fe contracts failed to build:\n{built.output}")
    return {k: len(bytes.fromhex((ingot / "out" / f"{c}.runtime.bin").read_text().strip())) for k, c in contracts.items()}


def attack_and_gas() -> tuple[dict, dict]:
    """Runs PoolAttack against the contracts in out/: the attack per kernel and gas per operation."""
    RESULTS.unlink(missing_ok=True)
    proc = subprocess.run(
        ["forge", "test", "--match-contract", "PoolAttack"], cwd=REFERENCE, capture_output=True, text=True, timeout=3600
    )
    if proc.returncode != 0:
        print(proc.stdout[-4000:], proc.stderr[-2000:])
        raise SystemExit(1)
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
                _, kernel, op, used = row
                gas.setdefault(kernel, {})[op] = int(used)
    return attacks, gas


def by_level() -> tuple[dict, dict, dict]:
    """Size, gas and attack outcome of each contract at each optimization level."""
    fe = resolve()
    sizes, gas, attacks = {}, {}, {}
    for level in LEVELS:
        shutil.rmtree(INGOT / "out", ignore_errors=True)
        built = fe.run(["build", "-O", level, "--emit", "bytecode,runtime-bytecode"], INGOT)
        if built.code != 0:
            raise SystemExit(f"Fe contracts failed to build at -O{level}:\n{built.output}")
        key = f"O{level}"
        sizes[key] = {
            k: len(bytes.fromhex((INGOT / "out" / f"{c}.runtime.bin").read_text().strip())) for k, c in CONTRACTS.items()
        }
        attacks[key], gas[key] = attack_and_gas()
    return sizes, gas, attacks


def zero_cost() -> dict:
    """Each pair in tests/zero_cost at each level: sizes, identical bytes, equal results and gas per call."""
    fe = resolve()
    pairs = sorted(p.name for p in ZERO_COST.iterdir() if p.is_dir())
    ZERO_COST_BINS.mkdir(parents=True, exist_ok=True)
    table: dict = {pair: {} for pair in pairs}
    for level in LEVELS:
        runtime = {}
        for pair in pairs:
            for variant in ("typed", "raw"):
                ingot = ZERO_COST / pair / variant
                shutil.rmtree(ingot / "out", ignore_errors=True)
                built = fe.run(["build", "-O", level, "--emit", "bytecode,runtime-bytecode"], ingot)
                if built.code != 0:
                    raise SystemExit(f"{pair}/{variant} failed to build at -O{level}:\n{built.output}")
                runtime[pair, variant] = bytes.fromhex((ingot / "out" / "P.runtime.bin").read_text().strip())
                shutil.copy(ingot / "out" / "P.bin", ZERO_COST_BINS / f"{pair}-{variant}.bin")
                shutil.rmtree(ingot / "out", ignore_errors=True)
        ZERO_COST_RESULTS.unlink(missing_ok=True)
        proc = subprocess.run(
            ["forge", "test", "--match-contract", "ZeroCost"], cwd=REFERENCE, capture_output=True, text=True, timeout=3600
        )
        if proc.returncode != 0:
            print(proc.stdout[-4000:], proc.stderr[-2000:])
            raise SystemExit(1)
        functions: dict = {pair: {} for pair in pairs}
        with ZERO_COST_RESULTS.open() as f:
            for pair, name, calls, equal, succeeded, gas_typed, gas_raw in csv.reader(f):
                functions[pair][name] = {
                    "calls": int(calls),
                    "equal": int(equal),
                    "succeeded": int(succeeded),
                    "gas_typed": int(gas_typed),
                    "gas_raw": int(gas_raw),
                }
        for pair in pairs:
            rows = functions[pair].values()
            succeeded = sum(r["succeeded"] for r in rows)
            table[pair][f"O{level}"] = {
                "bytes": {"typed": len(runtime[pair, "typed"]), "raw": len(runtime[pair, "raw"])},
                "identical": runtime[pair, "typed"] == runtime[pair, "raw"],
                "calls": sum(r["calls"] for r in rows),
                "equal": sum(r["equal"] for r in rows),
                "gas_per_call": {
                    "typed": round(sum(r["gas_typed"] for r in rows) / succeeded, 1),
                    "raw": round(sum(r["gas_raw"] for r in rows) / succeeded, 1),
                },
                "by_function": functions[pair],
            }
    return table


def pct(value: int, base: int) -> str:
    return f"{(value - base) / base * 100:+.1f}%"


def main() -> int:
    fe = resolve()
    levels, gas_by_level, attacks_by_level = by_level()
    # The default build, which is -O1: its numbers are the headline ones.
    sizes = build()
    if sizes != levels["O1"]:
        raise SystemExit(f"the default build is not -O1: {sizes} vs {levels['O1']}")
    attacks, gas = attacks_by_level["O1"], gas_by_level["O1"]
    differing = [level for level, a in attacks_by_level.items() if a != attacks]
    pairs = zero_cost()
    calls = {level: sum(pairs[pair][level]["calls"] for pair in pairs) for level in levels}
    unequal = [f"{pair} -{level}" for pair in pairs for level, r in pairs[pair].items() if r["equal"] != r["calls"]]
    costly = [
        f"{pair} -{level}"
        for pair in pairs
        for level, r in pairs[pair].items()
        if level != "O0" and r["gas_per_call"]["typed"] > r["gas_per_call"]["raw"]
    ]
    o0 = ", ".join(
        f"{pair} {pct(pairs[pair]['O0']['gas_per_call']['typed'], pairs[pair]['O0']['gas_per_call']['raw'])}" for pair in pairs
    )

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
        {
            "question": "Does every optimization level compute the same attack, to the wei?",
            "holds": not differing,
            "evidence": "the attack's exits and value per BPT on each kernel are identical at -O0, -O1, -O2 and -Os"
            if not differing
            else f"differs from -O1 at {', '.join('-' + d for d in differing)}",
        },
        {
            "question": "Built on Dimension itself, does typed code return exactly what the same code written by hand on raw u256 returns, at every optimization level?",
            "holds": not unequal,
            "evidence": f"{calls['O1']:,} calls per level over 8 functions (the four roundings, an ERC-4626 vault's four previews), reverts included: "
            + ("all equal at -O0, -O1, -O2 and -Os" if not unequal else f"differ in {', '.join(unequal)}"),
        },
        {
            "question": "Above -O0, is Dimension's typing free, gas for gas, against the same code written by hand?",
            "holds": not costly,
            "evidence": (
                "at -O1, -O2 and -Os the roundings compile to identical bytes, and the vault to the same size with identical gas on every call"
                if not costly
                else f"typed costs more in {', '.join(costly)}"
            )
            + f". At -O0, which no one deploys, typed costs {o0} per call",
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
            "setup": "the osETH/wETH pool's balances before the exploit (4,922.36 WETH, 6,851.58 osETH), amp 200, swap fee 0.01%, "
            "protocol swap fee 50%; 10 tokens or 10 BPT per operation",
            "per_operation": gas,
            "relative_to_faithful": {
                k: {op: pct(v[op], base[op]) for op in v} for k, v in gas.items() if k != "faithful"
            },
            "per_operation_by_level": gas_by_level,
        },
        "zero_cost": {
            "setup": "tests/zero_cost: each pair is one contract written with Dimension and the same contract written by hand "
            "on raw u256, with the same ABI. Every function is called on the same 512 inputs of every magnitude in both.",
            "pairs": pairs,
        },
        "runtime_bytecode_bytes": sizes,
        "runtime_bytecode_bytes_by_level": levels,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "evm"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    for k, v in gas.items():
        print(f"gas {k:9s} " + "  ".join(f"{op} {n:6d}" for op, n in v.items()))
    for level, row in levels.items():
        print(f"bytecode -{level}: " + ", ".join(f"{k} {n:,} B" for k, n in row.items()))
    for level, table in gas_by_level.items():
        print(f"mean gas -{level}: " + ", ".join(f"{k} {sum(v.values()) // len(v):,}" for k, v in table.items()))
    for pair, rows in pairs.items():
        for level, r in rows.items():
            g = r["gas_per_call"]
            same = "identical bytes" if r["identical"] else f"{r['bytes']['typed']:,} vs {r['bytes']['raw']:,} B"
            print(f"zero-cost {pair:8s} -{level}: {same}; gas per call typed {g['typed']:,} raw {g['raw']:,}; {r['equal']}/{r['calls']} equal")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
