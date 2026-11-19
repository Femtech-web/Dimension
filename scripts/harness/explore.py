"""Native exploration of the faithful and typed Balancer V2 kernels.

Usage: python3 -m harness.explore

Builds ingots/balancer_explorer as a native program with the pinned compiler,
runs its exhaustive search and greedy attacks, checks the claims the project
makes about them, and writes docs/results/exploration/<platform>.json.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from harness.toolchain import ROOT, resolve

INGOT = ROOT / "ingots" / "balancer_explorer"
SCHEMA = "dimension.exploration/v1"


def ops(kernel: dict, name: str) -> dict:
    return kernel["by_operation"][name]


KINDS = ("swapGivenIn", "swapGivenOut", "exitGivenIn", "exitGivenOut", "joinGivenIn", "joinGivenOut")


def claims(report: dict) -> list[dict]:
    faithful = report["kernels"]["faithful"]
    typed = report["kernels"]["typed"]
    guarded = report["kernels"]["guarded"]
    exits_f = ops(faithful, "exitGivenOut")["value_per_bpt_losses"]
    exits_t = ops(typed, "exitGivenOut")["value_per_bpt_losses"]
    swaps_t = ops(typed, "swapGivenOut")["value_per_bpt_losses"]
    unchanged = all(
        ops(faithful, k)[field] == ops(typed, k)[field]
        for k in ("swapGivenIn", "exitGivenIn", "joinGivenIn", "joinGivenOut")
        for field in ("value_per_bpt_losses", "stored_invariant_violations")
    )
    guarded_clean = all(
        ops(guarded, k)["value_per_bpt_losses"] == 0 and ops(guarded, k)["stored_invariant_violations"] == 0 for k in KINDS
    )
    rejections = {k: ops(guarded, k)["reverted"] - ops(typed, k)["reverted"] for k in KINDS}
    exact_guard = all(rejections[k] == ops(typed, k)["value_per_bpt_losses"] for k in KINDS)
    attacks = report["greedy_attacks"]
    return [
        {
            "question": "Does the faithful port lose value per BPT on GIVEN_OUT exits, as Balancer V2 did?",
            "holds": exits_f > 0,
            "evidence": f"{exits_f} losing exits, worst {ops(faithful, 'exitGivenOut')['worst_loss']['ppb'] / 1e7:.4f}%",
        },
        {
            "question": "Do the types alone remove the losses at Balancer's two _upscale sites?",
            "holds": swaps_t == 0 and exits_t * 1000 < exits_f,
            "evidence": f"swapGivenOut {ops(faithful, 'swapGivenOut')['value_per_bpt_losses']} -> {swaps_t}; exitGivenOut {exits_f} -> {exits_t}",
        },
        {
            "question": "Are the operations the types do not change identical with and without them?",
            "holds": unchanged,
            "evidence": "swapGivenIn, exitGivenIn, joinGivenIn and joinGivenOut counts match between faithful and typed",
        },
        {
            "question": "With the runtime guard added, does any operation lose value per BPT or store an invariant its balances do not back?",
            "holds": guarded_clean,
            "evidence": "guarded: 0 losses and 0 stored-invariant violations in every operation kind",
        },
        {
            "question": "Does the guard reject exactly the operations that would have lost value, and nothing else?",
            "holds": exact_guard,
            "evidence": ", ".join(f"{k} {rejections[k]}" for k in KINDS if rejections[k]) + " rejected; each equals the typed losses",
        },
        {
            "question": "Can a repeated-exit attacker gain against the faithful kernel, and is it always a loss with Dimension?",
            "holds": any(a["faithful"]["attacker_gain_wad"] > 0 for a in attacks)
            and all(a[k]["attacker_gain_wad"] < 0 for a in attacks for k in ("typed", "guarded")),
            "evidence": "; ".join(
                f"pool {a['b0']}/{a['b1']}: faithful {a['faithful']['attacker_gain_wad'] / 1e18:+.3f} D, "
                f"typed {a['typed']['attacker_gain_wad'] / 1e18:+.3f} D, guarded {a['guarded']['attacker_gain_wad'] / 1e18:+.3f} D"
                for a in attacks
            ),
        },
    ]


def main() -> int:
    fe = resolve()
    if not fe.native:
        print(f"skipped: Fe {fe.version} builds no native executables on {fe.platform}")
        return 0
    shutil.rmtree(INGOT / "out", ignore_errors=True)
    built = fe.run(["build", "--backend", "native"], INGOT)
    if built.code != 0:
        raise SystemExit(f"explorer failed to build:\n{built.output}")
    run = subprocess.run([str(INGOT / "out" / "balancer_explorer")], capture_output=True, text=True, timeout=3600)
    if run.returncode != 0:
        raise SystemExit(f"explorer failed:\n{run.stderr}")
    report = json.loads(run.stdout)

    checked = claims(report)
    document = {
        "schema": SCHEMA,
        "question": "Does typing the scaling boundary remove the value loss behind the November 2025 Balancer V2 exploit?",
        "fidelity": "faithful port of StableMath (differentially verified) and of the pool's swap, join and exit paths; "
        "single two-token pool, zero protocol fees, no Vault batching: a representative model, not the full exploit",
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "claims": checked,
        **report,
    }
    out = ROOT / "docs" / "results" / "exploration"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(document, indent=2) + "\n")

    for claim in checked:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    print(f"{report['states']} pool states; report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in checked) else 1


if __name__ == "__main__":
    sys.exit(main())
