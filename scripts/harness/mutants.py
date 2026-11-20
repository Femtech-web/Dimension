"""Mutation testing of Dimension's safety-critical code.

Usage: python3 -m harness.mutants [--forks] [--only id,id]

Each mutant is a realistic bug planted in one place: a rounding flipped, a
boundary check removed, Balancer's line put back. In a scratch copy of the
repository, every mutant is applied on its own and the check meant to catch it
is run. The mutant is caught only if that check fails for the reason expected
of it; a failure for any other reason (a network error, say) is inconclusive
and fails the run. `--forks` adds the mutants only a mainnet or Base fork can
catch. Writes docs/results/mutants/<platform>.json.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.toolchain import ROOT, resolve

SCHEMA = "dimension.mutants/v1"
FE = ".tools/fe-26.6.0/fe"
_EVIDENCE = re.compile(
    r"(error\[[0-9-]+\].*|^FAILS? .*|^\s+(missing|output differs|compiled, but|expected only).*|.*mismatched.*|.*\[FAIL.*"
    r"|unsafe code outside.*|a protocol ingot sets allow_unsafe)"
)

# What each check prints when it catches its mutant.
EXPECT = {
    "balancer-upscale-in-typed-pool": r"error\[8-0000\]",
    "out-admits-down": r"FAIL core",
    "in-settles-down": r"FAIL core",
    "exchange-keeps-direction": r"error\[8-0000\]",
    "feed-band-unchecked": r"FAIL oracle",
    "feed-age-unchecked": r"FAIL oracle",
    "feed-decimals-unchecked": r"FAIL oracle",
    "rate-band-unchecked": r"FAIL oracle",
    "guard-always-passes": r"FAILS\s+With the runtime guard added",
    "guard-off-on-exits": r"FAILS\s+With the runtime guard added",
    "bonus-predicate-dropped": r"FAIL compile_fail/liquidation_bonus_creates_bad_debt",
    "credit-takes-any-direction": r"FAIL compile_fail/vault_deposit_labeled_as_leaving",
    "internal-units-credited": r"FAIL compile_fail/internal_units_credited_to_balance",
    "credit-takes-any-token": r"FAIL compile_fail/deposit_credited_to_another_token",
    "supply-can-be-credited": r"FAIL compile_fail/share_supply_credited_as_held",
    "seal-key-public": r"FAIL compile_fail/custom_flow_through_the_seal",
    "port-drops-plus-one": r"[1-9][0-9]* mismatched",
    "port-mul-up-floors": r"[1-9][0-9]* mismatched",
    "vault-extra-virtual-share": r"FAIL: preview",
    "unsafe-in-protocol-ingot": r"unsafe code outside",
    "protocol-fee-skipped": r"every step must compute what Balancer computed|after the attack",
    "eth-usd-declared-18-decimals": r"the Fe oracle must bind the real feeds",
}

# id, layer, what the bug is, edits [(file, old, new)], the check meant to catch it, needs a fork
MUTANTS = [
    ("balancer-upscale-in-typed-pool", "compile time", "Balancer's _upscale put back into the typed pool's exit",
     [("ingots/balancer_v2/src/pool/typed.fe", "use super::faithful::upscaled\n", "use super::faithful::{upscale, upscaled}\n"),
      ("ingots/balancer_v2/src/pool/typed.fe", "    let scaled_out = admit(amount_out, factor)\n",
       "    let scaled_out = upscale(amount_out.value(), factor.value())\n")],
     [FE, "check", "ingots/balancer_v2"], False),
    ("out-admits-down", "types", "An amount leaving the protocol is admitted rounded down, as Balancer did",
     [("ingots/dimension/src/flow.fe", "impl Flow for Out {\n    type Admission = Ceil\n", "impl Flow for Out {\n    type Admission = Floor\n")],
     ["make", "unit"], False),
    ("in-settles-down", "types", "A charge is settled rounded down, in the caller's favour",
     [("ingots/dimension/src/flow.fe", "    type Admission = Floor\n    type Obligation = Ceil\n", "    type Admission = Floor\n    type Obligation = Floor\n")],
     ["make", "unit"], False),
    ("seal-key-public", "types", "The seal's key is made public, so code outside Dimension can implement the seal and add a flow",
     [("ingots/dimension/src/flow.fe", "\nstruct Key {}\n", "\npub struct Key {}\n")],
     ["make", "compile-fail"], False),
    ("exchange-keeps-direction", "types", "An exchange gives back value moving the same way as what it received",
     [("ingots/dimension/src/flow.fe", "    type Obligation = Floor\n    type Opposite = In\n", "    type Obligation = Floor\n    type Opposite = Out\n")],
     [FE, "check", "ingots/vault"], False),
    ("feed-band-unchecked", "read time", "A feed's answer is not checked against its band",
     [("ingots/dimension/src/value/oracle.fe", "    if wad < f.min_wad || wad > f.max_wad {\n", "    if false {\n")],
     ["make", "unit"], False),
    ("feed-age-unchecked", "read time", "A feed's answer is not checked for staleness",
     [("ingots/dimension/src/value/oracle.fe", "    if updated_at > now || now - updated_at > f.max_age {\n", "    if false {\n")],
     ["make", "unit"], False),
    ("feed-decimals-unchecked", "bind time", "A feed's reported decimals are not checked when it is bound",
     [("ingots/dimension/src/value/oracle.fe", "    if reported != f.decimals {\n", "    if false {\n")],
     ["make", "unit"], False),
    ("rate-band-unchecked", "read time", "A rate provider's answer is not checked against its band",
     [("ingots/dimension/src/value/oracle.fe", "    if wad < s.min_wad || wad > s.max_wad {\n", "    if false {\n")],
     ["make", "unit"], False),
    ("guard-always-passes", "runtime guard", "The share-value comparison always passes",
     [("ingots/dimension/src/invariant.fe", "    held_hi > owed_hi || (held_hi == owed_hi && held_lo >= owed_lo)\n", "    true\n")],
     ["make", "explore"], False),
    ("guard-off-on-exits", "runtime guard", "The guarded pool's exact-out exit runs without its guard",
     [("ingots/balancer_v2/src/pool/guarded.fe", "    typed::exit_given_out(mut pool, j, amount_out, factor, guard: true)\n",
       "    typed::exit_given_out(mut pool, j, amount_out, factor, guard: false)\n")],
     ["make", "explore"], False),
    ("bonus-predicate-dropped", "compile time", "A risk policy's bonus no longer has to avoid bad debt at the threshold",
     [("ingots/dimension/src/policy.fe", "    P::LTV_BPS < P::LIQUIDATION_THRESHOLD_BPS,\n    P::LIQUIDATION_THRESHOLD_BPS * (10_000 + P::LIQUIDATION_BONUS_BPS) <= 100_000_000\n",
       "    P::LTV_BPS < P::LIQUIDATION_THRESHOLD_BPS\n")],
     ["make", "compile-fail"], False),
    ("credit-takes-any-direction", "types", "A held balance can be credited with an amount labelled as leaving",
     [("ingots/dimension/src/value.fe", "    pub fn credit<S: TokenUnits>(self, _ q: Quantity<T, In, S>) -> Self {\n",
       "    pub fn credit<F, S: TokenUnits>(self, _ q: Quantity<T, F, S>) -> Self {\n")],
     ["make", "compile-fail"], False),
    ("internal-units-credited", "types", "An amount in internal 18-decimal units counts as token units",
     [("ingots/dimension/src/flow.fe", "impl TokenUnits for Settled {}\n", "impl TokenUnits for Settled {}\nimpl TokenUnits for Admitted {}\n")],
     ["make", "compile-fail"], False),
    ("credit-takes-any-token", "types", "A held balance can be credited with an amount of another token",
     [("ingots/dimension/src/value.fe", "    pub fn credit<S: TokenUnits>(self, _ q: Quantity<T, In, S>) -> Self {\n        Held { raw: self.raw + q.v }\n",
       "    pub fn credit<U, S: TokenUnits>(self, _ q: Quantity<U, In, S>) -> Self {\n        Held { raw: self.raw + q.v }\n")],
     ["make", "compile-fail"], False),
    ("supply-can-be-credited", "types", "A supply the protocol issues can be credited, as if the protocol held it",
     [("ingots/dimension/src/value.fe", "impl<T> Supply<T> {\n",
       "impl<T> Supply<T> {\n    pub fn credit<S: TokenUnits>(self, _ q: Quantity<T, In, S>) -> Self {\n        Supply { raw: self.raw + q.v }\n    }\n\n")],
     ["make", "compile-fail"], False),
    ("port-drops-plus-one", "port fidelity", "The port drops the + 1 Balancer adds in calc_in_given_out",
     [("ingots/balancer_v2/src/stable/stable_math.fe", "    fp::add(fp::sub(final_in, balances[index_in]), 1)\n", "    fp::sub(final_in, balances[index_in])\n")],
     ["make", "differential"], False),
    ("port-mul-up-floors", "port fidelity", "The port's mulUp rounds down",
     [("ingots/balancer_v2/src/stable/fixed_point.fe", "        (product - 1) / ONE + 1\n", "        product / ONE\n")],
     ["make", "differential"], False),
    ("vault-extra-virtual-share", "port fidelity", "The vault counts two virtual shares on deposit instead of one",
     [("ingots/vault/src/vault.fe", "        numerator: v.total_shares.raw() + 1,\n        denominator: v.total_assets.raw() + 1,\n    )\n}\n\n/// Assets that minting",
       "        numerator: v.total_shares.raw() + 2,\n        denominator: v.total_assets.raw() + 1,\n    )\n}\n\n/// Assets that minting")],
     ["make", "vault"], False),
    ("unsafe-in-protocol-ingot", "unsafe policy", "A protocol ingot gains an unsafe block",
     [("ingots/moonwell/src/registry.fe", "pub struct CBETH {}\n", "pub struct CBETH {}\n\nfn forge() {\n    unsafe {}\n}\n")],
     ["make", "unsafe-policy"], False),
    ("protocol-fee-skipped", "port fidelity", "Joins and exits stop minting the protocol's fee on their own swap fees",
     [("ingots/balancer_v2/src/pool/fees.fe",
       "        if percentage > 0 {\n            pool.supply = pool.supply + bpt_for_ownership(pool.supply, percentage)\n",
       "        if false {\n            pool.supply = pool.supply + bpt_for_ownership(pool.supply, percentage)\n")],
     ["make", "replay"], True),
    ("eth-usd-declared-18-decimals", "bind time", "The registry declares ETH/USD with 18 decimals",
     [("ingots/moonwell/src/registry.fe", "    decimals: 8,\n    max_age: 1_800,\n", "    decimals: 18,\n    max_age: 1_800,\n")],
     ["make", "moonwell"], True),
]


def copy_repo(dest: Path) -> None:
    ignore = shutil.ignore_patterns(".git", ".tools", "out", "cache", "lib", "private-notes", "__pycache__", "node_modules")
    shutil.copytree(ROOT, dest, ignore=ignore, dirs_exist_ok=True)
    (dest / ".tools").symlink_to(ROOT / ".tools")
    (dest / "contracts" / "reference" / "lib").symlink_to(ROOT / "contracts" / "reference" / "lib")


def main() -> int:
    fe = resolve()
    args = sys.argv[1:]
    forks = "--forks" in args
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else None
    results = []
    with tempfile.TemporaryDirectory(prefix="dimension-mutants-") as tmp:
        work = Path(tmp)
        copy_repo(work)
        for mid, layer, bug, edits, command, needs_fork in MUTANTS:
            if (needs_fork and not forks) or (only and mid not in only):
                continue
            originals = {}
            for file, old, new in edits:
                path = work / file
                originals.setdefault(path, path.read_text())
                text = path.read_text()
                if text.count(old) != 1:
                    raise SystemExit(f"mutant {mid} no longer applies to {file}")
                path.write_text(text.replace(old, new))
            proc = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=3600)
            for path, text in originals.items():
                path.write_text(text)
            output = proc.stdout + proc.stderr
            expected = re.compile(EXPECT[mid])
            lines = [m.group(0).strip() for m in map(_EVIDENCE.match, output.splitlines()) if m]
            # The line that shows the expected catch comes first.
            evidence = sorted(lines, key=lambda line: not expected.search(line))[:2]
            if proc.returncode == 0:
                outcome = "missed"
            elif expected.search(output):
                outcome = "caught"
            else:
                outcome = "inconclusive"
                evidence = [line for line in output.strip().splitlines() if line.strip()][-3:]
            results.append({
                "id": mid,
                "layer": layer,
                "bug": bug,
                "files": sorted({e[0] for e in edits}),
                "check": " ".join(command).replace(FE, "fe"),
                "caught": outcome == "caught",
                "outcome": outcome,
                "evidence": evidence,
            })
            print(f"{outcome:12s} {mid:32s} by {results[-1]['check']}: {evidence[0] if evidence else ''}")

    caught = sum(r["caught"] for r in results)
    layers = sorted({r["layer"] for r in results})
    inconclusive = sum(r["outcome"] == "inconclusive" for r in results)
    claims = [{
        "question": "Is every planted bug in the safety-critical code caught by the check meant to catch it?",
        "holds": caught == len(results) and len(results) > 0,
        "evidence": f"{caught} of {len(results)} mutants caught, each for the reason expected of it, across {len(layers)} layers: "
        + ", ".join(layers) + (f"; {inconclusive} inconclusive (rerun them)" if inconclusive else ""),
    }]
    report = {
        "schema": SCHEMA,
        "question": "Would the checks notice if the code they protect were wrong?",
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "fork_mutants_included": forks,
        "mutants": results,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "mutants"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'holds' if claims[0]['holds'] else 'FAILS'}  {claims[0]['question']}\n       {claims[0]['evidence']}")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if claims[0]["holds"] else 1


if __name__ == "__main__":
    sys.exit(main())
