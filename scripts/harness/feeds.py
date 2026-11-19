"""Feed declarations against Chainlink's directory and Base.

Usage: python3 -m harness.feeds

Runs cli/feed_check.py on Moonwell's registry, which must pass, and
on tests/feeds: two declarations that compile, one of which also passes every
check Dimension makes on chain. feed-check must reject both, for the pair.
Needs network access (BASE_RPC_URL overrides the public RPC). Writes
docs/results/feeds/<platform>.json.
"""

from __future__ import annotations

import json
import os
import sys

from harness.toolchain import ROOT, resolve

sys.path.insert(0, str(ROOT / "cli"))
import feed_check  # noqa: E402

REGISTRY = ROOT / "ingots" / "moonwell" / "src" / "registry.fe"
FIXTURE = ROOT / "tests" / "feeds"
SCHEMA = "dimension.feeds/v1"
# What Dimension itself checks on chain: decimals when a contract binds a feed,
# and a positive, fresh, in-band answer on every read.
ON_CHAIN = {"on-chain decimals", "on-chain answer", "on-chain freshness", "on-chain band"}


def failed(feed: dict) -> set[str]:
    return {c["check"] for c in feed["checks"] if not c["ok"]}


def detail(feed: dict, check: str) -> str:
    return next(c["detail"] for c in feed["checks"] if c["check"] == check)


def price(feed: dict) -> str:
    return detail(feed, "on-chain answer").split("(")[-1].rstrip(")")


def relative(feed: dict) -> dict:
    return {**feed, "source": str(os.path.relpath(feed["source"], ROOT))}


def main() -> int:
    fe = resolve()
    compiled = fe.run(["check"], FIXTURE)
    rpc = os.environ.get("BASE_RPC_URL")
    registry = feed_check.run([REGISTRY], "base", rpc, None, {})
    wrong = feed_check.run([FIXTURE / "src" / "lib.fe"], "base", rpc, None, {})
    mip, swapped = (next(f for f in wrong["feeds"] if f["name"] == n) for n in ("MIP_X43_CBETH_USD", "SWAPPED_ETH_USD"))
    eth_usd = next(f for f in registry["feeds"] if f["name"] == "ETH_USD")

    claims = [
        {
            "question": "Is every feed in Moonwell's registry the feed Chainlink lists at its address, as the chain reports it?",
            "holds": all(f["ok"] for f in registry["feeds"]),
            "evidence": "; ".join(
                f"{f['name']} is \"{f['listed_as']}\": {sum(c['ok'] for c in f['checks'])} of {len(f['checks'])} checks"
                for f in registry["feeds"]
            ),
        },
        {
            "question": "Is MIP-X43's declaration, the cbETH/ETH feed as cbETH/USD, rejected before deployment?",
            "holds": "pair" in failed(mip) and "0xd7818272B9e248357d13057AAb0B417aF31E817d" in (mip["suggestion"] or ""),
            "evidence": f"{detail(mip, 'pair')}. {mip['suggestion']}",
        },
        {
            "question": "Is a wrong feed rejected even when it compiles and passes every check Dimension makes on chain?",
            "holds": compiled.code == 0 and not failed(swapped) & ON_CHAIN and "pair" in failed(swapped),
            "evidence": f"the cbETH/USD feed declared as ETH/USD compiles"
            f"{'' if compiled.code == 0 else ' (it did not)'}, and on chain its decimals, answer, freshness and band "
            f"all pass: {price(swapped)}, while ETH/USD reads {price(eth_usd)}. feed-check: {detail(swapped, 'pair')}",
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "Is each declared feed the feed it is declared to be?",
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "directory": registry["directory"],
        "chain": registry["chain"],
        "checked_at": registry["checked_at"],
        "registry": [relative(f) for f in registry["feeds"]],
        "misdeclared": [relative(f) for f in wrong["feeds"]],
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "feeds"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")

    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    print(f"block {registry['chain']['block']:,}; report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
