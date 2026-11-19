#!/usr/bin/env python3
"""Checks Dimension feed declarations against Chainlink's directory and the chain.

Usage:
    python3 scripts/feeds/feed_check.py REGISTRY.fe [...] --network base [--rpc URL] [--json OUT]

Dimension's types guarantee a `Feed<B, Q>` is only ever used as a B-in-Q
price, and its boundary checks decimals, freshness and band on chain. Neither
can see whether the address really is a B/Q feed: a feed with the right
decimals and a plausible answer passes every on-chain check. This review-time
check closes that gap for Chainlink feeds. For each `pub const NAME: Feed<B, Q>
= feed(...)` it requires that:

- Chainlink's published directory for the network lists the address, as a B/Q
  feed (the pair), with the declared decimals and a heartbeat within max_age;
- on chain, at one block, the proxy reports the listed decimals and
  description, points to the listed aggregator, and its answer is positive,
  fresh and inside the declared band.

A failure names what the address actually is, and where the directory lists
the declared pair. The directory is the feed operator's own record, so trust
in it is trust in Chainlink, as using its feeds already is. Exits 1 if any
check fails. Python 3.10+, standard library only.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import operator
import re
import ssl
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DIRECTORY = "https://reference-data-directory.vercel.app/feeds-{}.json"
NETWORKS = {
    "ethereum": ("mainnet", "https://eth.drpc.org"),
    "base": ("ethereum-mainnet-base-1", "https://mainnet.base.org"),
}
WAD = 10**18

_FEED = re.compile(
    r"pub\s+const\s+(?P<name>\w+)\s*:\s*Feed<\s*(?P<base>\w+)\s*,\s*(?P<quote>\w+)\s*>\s*=\s*feed\(\s*"
    r"Address::new\(\s*(?P<addr>0x[0-9a-fA-F]{40})\s*\)\s*,\s*"
    r"decimals:\s*(?P<decimals>[^,]+),\s*max_age:\s*(?P<max_age>[^,]+),\s*"
    r"min_wad:\s*(?P<min_wad>[^,]+),\s*max_wad:\s*(?P<max_wad>[^,)]+?)\s*,?\s*\)"
)
_CONST = re.compile(r"^\s*(?:pub\s+)?const\s+(\w+)\s*:\s*u\d+\s*=\s*(.+?)\s*$", re.MULTILINE)
_DECLARED = re.compile(r":\s*Feed<")
# Python from python.org on macOS starts with no trust store; fall back to the system's.
_TLS = ssl.create_default_context()
if not _TLS.get_ca_certs():
    for bundle in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if Path(bundle).exists():
            _TLS.load_verify_locations(bundle)
            break
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.floordiv, ast.Pow: operator.pow}


def evaluate(expr: str, consts: dict[str, int]) -> int:
    """Evaluates a Fe integer constant expression: literals, constants, + - * / **."""

    def go(node: ast.AST) -> int:
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name) and node.id in consts:
            return consts[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](go(node.left), go(node.right))
        raise ValueError(f"cannot evaluate `{expr}`")

    return go(ast.parse(expr.strip(), mode="eval").body)


@dataclass
class Declared:
    name: str
    base: str
    quote: str
    address: str
    decimals: int
    max_age: int
    min_wad: int
    max_wad: int
    source: str


def declarations(path: Path) -> list[Declared]:
    text = path.read_text()
    consts: dict[str, int] = {}
    for name, expr in _CONST.findall(text):
        try:
            consts[name] = evaluate(expr, consts)
        except (ValueError, SyntaxError):
            pass
    found = [
        Declared(
            name=m["name"],
            base=m["base"],
            quote=m["quote"],
            address=m["addr"],
            decimals=evaluate(m["decimals"], consts),
            max_age=evaluate(m["max_age"], consts),
            min_wad=evaluate(m["min_wad"], consts),
            max_wad=evaluate(m["max_wad"], consts),
            source=f"{path}:{text.count(chr(10), 0, m.start()) + 1}",
        )
        for m in _FEED.finditer(text)
    ]
    if len(found) != len(_DECLARED.findall(text)):
        raise SystemExit(f"{path}: {len(_DECLARED.findall(text))} Feed declarations, {len(found)} in the form `pub const N: Feed<B, Q> = feed(Address::new(0x..), decimals: .., max_age: .., min_wad: .., max_wad: ..)`")
    return found


class Chain:
    """Read-only calls, all at one block."""

    def __init__(self, rpc: str):
        self.rpc = rpc
        head = self._rpc("eth_getBlockByNumber", ["latest", False])
        self.block = int(head["number"], 16)
        self.timestamp = int(head["timestamp"], 16)

    def _rpc(self, method: str, params: list):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        request = urllib.request.Request(self.rpc, body, {"content-type": "application/json", "user-agent": "feed-check"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30, context=_TLS) as response:
                    reply = json.load(response)
                break
            except OSError:
                if attempt == 2:
                    raise
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply["result"]

    def call(self, to: str, selector: str) -> bytes:
        return bytes.fromhex(self._rpc("eth_call", [{"to": to, "data": selector}, hex(self.block)])[2:])


def word(data: bytes, i: int) -> int:
    return int.from_bytes(data[32 * i : 32 * i + 32], "big")


def text(data: bytes) -> str:
    offset = word(data, 0)
    length = int.from_bytes(data[offset : offset + 32], "big")
    return data[offset + 32 : offset + 32 + length].decode()


def pair_of(entry: dict) -> tuple[str, str]:
    docs = entry.get("docs") or {}
    if docs.get("baseAsset") and docs.get("quoteAsset"):
        return docs["baseAsset"].upper(), docs["quoteAsset"].upper()
    base, _, quote = entry.get("name", "").partition(" / ")
    return base.strip().upper(), quote.strip().upper()


@dataclass
class Report:
    feed: Declared
    listed_as: str | None = None
    checks: list[dict] = field(default_factory=list)
    suggestion: str | None = None

    def check(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append({"check": name, "ok": ok, "detail": detail})

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)


def check_feed(feed: Declared, directory: list[dict], chain: Chain, aliases: dict[str, str]) -> Report:
    report = Report(feed)
    declared = (aliases.get(feed.base, feed.base).upper(), aliases.get(feed.quote, feed.quote).upper())
    entry = next(
        (
            e
            for e in directory
            if feed.address.lower() in {(e.get("proxyAddress") or "").lower(), (e.get("secondaryProxyAddress") or "").lower()}
        ),
        None,
    )
    if entry is None:
        report.check("listed", False, f"{feed.address} is not in Chainlink's directory for this network")
    else:
        report.listed_as = entry["name"]
        listed = pair_of(entry)
        report.check("listed", True, f"Chainlink lists {feed.address} as \"{entry['name']}\"")
        report.check("pair", listed == declared, f"declared {declared[0]}/{declared[1]}, listed {listed[0]}/{listed[1]}")
        report.check(
            "decimals", entry["decimals"] == feed.decimals, f"declared {feed.decimals}, listed {entry['decimals']}"
        )
        heartbeat = int(entry.get("heartbeat") or 0)
        report.check(
            "heartbeat",
            0 < heartbeat <= feed.max_age,
            f"max_age {feed.max_age:,} s, heartbeat {heartbeat:,} s",
        )
        reported = word(chain.call(feed.address, "0x313ce567"), 0)
        report.check("on-chain decimals", reported == entry["decimals"], f"reported {reported}")
        description = text(chain.call(feed.address, "0x7284e416"))
        report.check("on-chain description", description == entry["name"], f"\"{description}\"")
        if entry.get("contractAddress"):
            aggregator = "0x" + chain.call(feed.address, "0x245a7bfc")[-20:].hex()
            report.check(
                "on-chain aggregator",
                aggregator.lower() == entry["contractAddress"].lower(),
                f"{aggregator}, listed {entry['contractAddress']}",
            )
        if listed != declared:
            matches = [e for e in directory if pair_of(e) == declared and e.get("proxyAddress")]
            report.suggestion = (
                f"Chainlink lists {declared[0]}/{declared[1]} at "
                + ", ".join(
                    f"{e['proxyAddress']} ({e['decimals']} decimals, heartbeat {int(e.get('heartbeat') or 0):,} s)"
                    for e in matches
                )
                if matches
                else f"Chainlink lists no {declared[0]}/{declared[1]} feed on this network"
            )

    data = chain.call(feed.address, "0xfeaf968c")
    answer = word(data, 1)
    answer = answer - (1 << 256) if answer >> 255 else answer
    age = chain.timestamp - word(data, 3)
    wad = answer * WAD // 10**feed.decimals if answer > 0 else 0
    report.check("on-chain answer", answer > 0, f"{answer} ({wad / WAD:,.6g} {declared[1]} per {declared[0]})")
    report.check("on-chain freshness", 0 <= age <= feed.max_age, f"{age:,} s old, max_age {feed.max_age:,} s")
    report.check(
        "on-chain band",
        feed.min_wad <= wad <= feed.max_wad,
        f"{wad / WAD:,.6g} within {feed.min_wad / WAD:,.6g} to {feed.max_wad / WAD:,.6g}",
    )
    return report


def fetch_directory(url: str) -> tuple[list[dict], str]:
    request = urllib.request.Request(url, headers={"user-agent": "feed-check"})
    with urllib.request.urlopen(request, timeout=60, context=_TLS) as response:
        raw = response.read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def run(paths: list[Path], network: str | None, rpc: str | None, directory_url: str | None, aliases: dict[str, str]) -> dict:
    slug, default_rpc = NETWORKS.get(network or "", (None, None))
    url = directory_url or (DIRECTORY.format(slug) if slug else None)
    if not url or not (rpc or default_rpc):
        raise SystemExit(f"give --network ({', '.join(NETWORKS)}), or --directory and --rpc")
    directory, digest = fetch_directory(url)
    chain = Chain(rpc or default_rpc)
    reports = [check_feed(feed, directory, chain, aliases) for path in paths for feed in declarations(path)]
    return {
        "directory": {"url": url, "sha256": digest, "entries": len(directory)},
        # The host only: RPC URLs often carry an API key.
        "chain": {"rpc_host": urllib.parse.urlsplit(chain.rpc).hostname, "block": chain.block, "timestamp": chain.timestamp},
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "feeds": [
            {
                "name": r.feed.name,
                "declared": f"Feed<{r.feed.base}, {r.feed.quote}>",
                "address": r.feed.address,
                "source": r.feed.source,
                "listed_as": r.listed_as,
                "ok": r.ok,
                "checks": r.checks,
                "suggestion": r.suggestion,
            }
            for r in reports
        ],
    }


def show(result: dict) -> None:
    chain = result["chain"]
    print(f"directory {result['directory']['url']} ({result['directory']['entries']} feeds)")
    print(f"chain     block {chain['block']:,} via {chain['rpc_host']}")
    for feed in result["feeds"]:
        print(f"\n{'ok  ' if feed['ok'] else 'FAIL'}  {feed['name']}: {feed['declared']} at {feed['address']}  ({feed['source']})")
        for c in feed["checks"]:
            print(f"      {'ok  ' if c['ok'] else 'FAIL'}  {c['check']:<22} {c['detail']}")
        if feed["suggestion"]:
            print(f"      hint  {feed['suggestion']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("registry", nargs="+", type=Path, help="Fe source files with Feed declarations")
    parser.add_argument("--network", choices=sorted(NETWORKS), help="selects the directory and a public RPC")
    parser.add_argument("--rpc", help="JSON-RPC URL (overrides the network's public one)")
    parser.add_argument("--directory", help="Chainlink directory JSON URL, for networks not listed")
    parser.add_argument("--alias", action="append", default=[], metavar="TYPE=SYMBOL", help="e.g. WETH=ETH")
    parser.add_argument("--json", type=Path, help="also write the result as JSON")
    args = parser.parse_args(argv)
    aliases = dict(a.split("=", 1) for a in args.alias)
    result = run(args.registry, args.network, args.rpc, args.directory, aliases)
    show(result)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if all(f["ok"] for f in result["feeds"]) else 1


if __name__ == "__main__":
    sys.exit(main())
