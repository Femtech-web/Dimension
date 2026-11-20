"""The live demonstration on Base Sepolia: deploy it, rehearse it, check it.

Usage: python3 -m harness.live [check | rehearse | deploy]

  check     The default. Re-reads deployments/base-sepolia.json from the chain:
            each transaction's receipt, each contract's code against the code
            built here, the outcomes LiveRecorder logged against LivePlan's
            plan, and the oracle, the declarations and the vault at the latest
            block. Writes docs/results/live/<platform>.json.
  rehearse  Runs the whole deployment on a local anvil fork of Base Sepolia from
            anvil's own funded account, then checks it, reporting to
            contracts/reference/cache/. Needs no key.
  deploy    Broadcasts it to Base Sepolia from the key in .secrets/base-sepolia.json,
            writes deployments/base-sepolia.json, then checks it.

The key reaches forge only through its environment. BASE_SEPOLIA_RPC_URL
overrides the public RPC. Needs forge, cast and anvil.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from harness.evm import build
from harness.toolchain import ROOT, resolve

sys.path.insert(0, str(ROOT / "cli"))
import feed_check  # noqa: E402

REFERENCE = ROOT / "contracts" / "reference"
CACHE = REFERENCE / "cache"
PLAN = CACHE / "live-plan.json"
RECORD = ROOT / "deployments" / "base-sepolia.json"
REHEARSAL = CACHE / "live-rehearsal.json"
REHEARSAL_REPORT = CACHE / "live-rehearsal-report.json"
KEY = ROOT / ".secrets" / "base-sepolia.json"
REGISTRY = ROOT / "ingots" / "live" / "src" / "registry.fe"
NETWORK = "base-sepolia"
CHAIN_ID = 84532
DEFAULT_RPC = "https://sepolia.base.org"
EXPLORER = "https://sepolia.basescan.org"
SCHEMA = "dimension.live/v1"
RECORD_SCHEMA = "dimension.deployment/v1"
# anvil's first development account: its key is public, and funded only on the local fork.
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ANVIL_ACCOUNT = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
# The whole deployment costs well under this at Base Sepolia's gas prices.
MIN_BALANCE = 2 * 10**15
WAD = 10**18

# The Fe contracts as the script names them: (ingot, contract).
FE = {
    "FaithfulPool": ("balancer_v2", "FaithfulPool"),
    "TypedPool": ("balancer_v2", "TypedPool"),
    "GuardedPool": ("balancer_v2", "GuardedPool"),
    "CbethUsdOracle": ("live", "CbethUsdOracle"),
    "DeclaredCbethEthAsUsd": ("moonwell", "DeclaredCbethUsdFeed"),
    "DeclaredCbethUsd": ("moonwell", "DeclaredCbethUsdFeed"),
    "TypedVault": ("vault", "TypedVault"),
}
POOLS = ["FaithfulPool", "TypedPool", "GuardedPool"]
# MockRateProvider's rate: the osETH/wETH pool's, as in the fork tests.
RATE = 121 * 10**16
CALLS = [
    "initialize(uint256[2],uint256,uint256,uint256,uint256,uint256,address)",
    "attack(address,uint256,uint256[])",
    "probe(address,bytes)",
    "deploy(bytes)",
]
ERRORS = [
    "Error(string)",
    "ShareValueDecreased()",
    "WrongDecimals(address,uint8,uint8)",
    "NonPositiveAnswer(address)",
    "StaleAnswer(address,uint256,uint256)",
    "AnswerOutOfBand(address,uint256,uint256,uint256)",
]
EVENTS = {
    "Attack": "Attack(address,uint256,bool,uint256,uint256,bytes)",
    "Call": "Call(address,bytes,bool,bytes)",
    "Deployment": "Deployment(address,bytes32,bytes)",
}
PREVIEWS = ["previewDeposit", "previewMint", "previewWithdraw", "previewRedeem"]
# Vault states for the previews: empty, one share short of its assets, and a
# first depositor's single share after a donation of one token.
VAULT_STATES = [(0, 0), (1_000, 999), (WAD + 1, 1)]
VAULT_AMOUNTS = [7, WAD]


@functools.cache
def keccak(text: str) -> bytes:
    out = subprocess.run(["cast", "keccak", text], capture_output=True, text=True, check=True).stdout
    return bytes.fromhex(out.strip()[2:])


def selector(signature: str) -> bytes:
    return keccak(signature)[:4]


def word(data: bytes, i: int) -> int:
    return feed_check.word(data, i)


def dynamic(data: bytes, i: int) -> bytes:
    """The `bytes` whose offset is word `i`."""
    offset = word(data, i)
    return data[offset + 32 : offset + 32 + int.from_bytes(data[offset : offset + 32], "big")]


def words(*values: int) -> bytes:
    return b"".join(v.to_bytes(32, "big") for v in values)


def same(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def short(value: str) -> str:
    return f"{value[:6]}…{value[-4:]}"


def usd(wad: int) -> str:
    return f"{wad / WAD:,.2f} USD"


def decode_error(data: bytes) -> tuple:
    """Revert data as (error name, arguments), addresses as lower-case hex."""
    for signature in ERRORS:
        if data[:4] == selector(signature):
            name, params = signature[:-1].split("(")
            if name == "Error":
                return name, (feed_check.text(data[4:]),)
            types = params.split(",") if params else []
            return name, tuple(
                f"0x{word(data[4:], i):040x}" if t == "address" else word(data[4:], i) for i, t in enumerate(types)
            )
    return "unknown", ("0x" + data.hex(),)


def show_error(error: tuple) -> str:
    name, args = error
    if name == "Error":
        return f'Error("{args[0]}")'
    if name == "AnswerOutOfBand":
        feed, wad, low, high = args
        return f"AnswerOutOfBand({short(feed)}: {wad / WAD:,.4f}, outside {low / WAD:,.0f} to {high / WAD:,.0f})"
    if name == "StaleAnswer":
        feed, updated_at, now = args
        return f"StaleAnswer({short(feed)}: updated {now - updated_at:,} s before)"
    return f"{name}({', '.join(short(a) if isinstance(a, str) else str(a) for a in args)})"


class Chain(feed_check.Chain):
    """Reads at one block: the latest when it is created."""

    def request(self, method: str, *params):
        return self._rpc(method, list(params))

    def outcome(self, to: str, data: bytes) -> tuple[bool, bytes]:
        """An eth_call at the pinned block: (True, return data) or (False, revert data)."""
        try:
            out = self._rpc("eth_call", [{"to": to, "data": "0x" + data.hex()}, hex(self.block)])
        except feed_check.RpcError as e:
            data = e.error.get("data")
            if isinstance(data, dict):
                data = data.get("data")
            if not isinstance(data, str) or not data.startswith("0x"):
                raise
            return False, bytes.fromhex(data[2:])
        return True, bytes.fromhex(out[2:])

    def code(self, address: str) -> bytes:
        return bytes.fromhex(self._rpc("eth_getCode", [address, hex(self.block)])[2:])


def read(chain: Chain, feed) -> int | tuple:
    """A feed read as dimension::value::oracle::read does it: its WAD, or the error it reverts with."""
    _, data = chain.outcome(feed.address, selector("latestRoundData()"))
    answer = word(data, 1)
    answer -= 2**256 if answer >= 2**255 else 0
    updated_at = word(data, 3)
    addr = feed.address.lower()
    if answer <= 0:
        return "NonPositiveAnswer", (addr,)
    if updated_at > chain.timestamp or chain.timestamp - updated_at > feed.max_age:
        return "StaleAnswer", (addr, updated_at, chain.timestamp)
    wad = answer * WAD // 10**feed.decimals
    if not feed.min_wad <= wad <= feed.max_wad:
        return "AnswerOutOfBand", (addr, wad, feed.min_wad, feed.max_wad)
    return wad


def price(chain: Chain, address: str) -> int | tuple:
    """A deployed oracle's usdPrice() at the pinned block: its WAD, or the error it reverts with."""
    ok, data = chain.outcome(address, selector("usdPrice()"))
    return word(data, 0) if ok else decode_error(data)


def oz_preview(name: str, assets: int, shares: int, amount: int) -> int:
    """OpenZeppelin's ERC4626 with a decimals offset of 0."""
    def div(a: int, b: int, up: bool) -> int:
        return -(-a // b) if up else a // b

    return {
        "previewDeposit": div(amount * (shares + 1), assets + 1, False),
        "previewMint": div(amount * (assets + 1), shares + 1, True),
        "previewWithdraw": div(amount * (shares + 1), assets + 1, True),
        "previewRedeem": div(amount * (assets + 1), shares + 1, False),
    }[name]


# ---- deploying ----


def prepare() -> dict:
    """Builds every contract with the pinned Fe, and plans the attacker's batch."""
    for ingot in sorted({i for i, _ in FE.values()}):
        build(ROOT / "ingots" / ingot, {c: c for i, c in FE.values() if i == ingot})
    PLAN.unlink(missing_ok=True)
    proc = subprocess.run(
        ["forge", "test", "--match-contract", "LivePlan"], cwd=REFERENCE, capture_output=True, text=True, timeout=3600
    )
    if proc.returncode != 0:
        print(proc.stdout[-4000:], proc.stderr[-2000:])
        raise SystemExit(1)
    return json.loads(PLAN.read_text())


def broadcast(rpc: str, key: str, out: Path, resume: bool = False) -> None:
    """Runs script/Live.s.sol and sends its transactions in order, each after the
    last confirms. `resume` sends only those a stopped run did not, as its
    broadcast log records them."""
    env = {**os.environ, "LIVE_KEY": key, "FOUNDRY_BROADCAST": str(out)}
    proc = subprocess.run(
        ["forge", "script", "script/Live.s.sol:Live", "--rpc-url", rpc, "--broadcast", "--slow", *(["--resume"] if resume else [])],
        cwd=REFERENCE, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3600,
    )
    if proc.returncode != 0:
        print(proc.stdout[-6000:], proc.stderr[-3000:])
        raise SystemExit(
            "forge script stopped before every transaction confirmed; nothing is recorded yet. Public RPCs drop "
            "transactions and receipts: send the rest with `make live-deploy RESUME=1`"
        )


def created(t: dict) -> str:
    """Which contract a creation transaction deploys: forge names the Solidity ones;
    a Fe contract's creation code starts with its built code, and the two declared
    feeds, built from one contract, differ in the feed their constructor names."""
    if t.get("contractName"):
        return t["contractName"]
    code = t["transaction"]["input"][2:].lower()
    for name, (ingot, built) in FE.items():
        prefix = (ROOT / "ingots" / ingot / "out" / f"{built}.bin").read_text().strip().lower()
        if code.startswith(prefix):
            if built != "DeclaredCbethUsdFeed":
                return name
            feed = f"0x{word(bytes.fromhex(code[len(prefix):]), 0):040x}"
            cbeth_eth = next(d.address for d in feed_check.declarations(REGISTRY) if d.name == "CBETH_ETH")
            return "DeclaredCbethEthAsUsd" if same(feed, cbeth_eth) else "DeclaredCbethUsd"
    raise SystemExit(f"{t['hash']} deploys code built from none of the contracts")


def record(out: Path, deployer: str) -> dict:
    """The deployment record from forge's broadcast log: each contract and each transaction."""
    run = json.loads((out / "Live.s.sol" / str(CHAIN_ID) / "run-latest.json").read_text())
    names = {t["contractAddress"].lower(): created(t) for t in run["transactions"] if t["transactionType"] == "CREATE"}
    calls = {selector(s): s.split("(")[0] for s in CALLS}
    receipts = {r["transactionHash"]: r for r in run["receipts"]}
    contracts, transactions = {}, []
    for t in run["transactions"]:
        receipt = receipts[t["hash"]]
        block = int(receipt["blockNumber"], 16)
        if t["transactionType"] == "CREATE":
            name = names[t["contractAddress"].lower()]
            contracts[name] = {"address": t["contractAddress"], "tx": t["hash"], "block": block}
            action = f"deploy {name}"
        else:
            data = bytes.fromhex(t["transaction"]["input"][2:])
            call = calls[data[:4]]
            if call == "initialize":
                action = f"initialize {names[t['transaction']['to'].lower()]}"
            elif call == "deploy":
                action = "deploy DeclaredCbethUsdFeed through LiveRecorder"
            elif call == "attack":
                action = f"attack {names[f'0x{word(data[4:], 0):040x}']} ({word(data[4:], 3)} exits)"
            else:
                action = f"probe {names[f'0x{word(data[4:], 0):040x}']}"
        transactions.append({"action": action, "hash": t["hash"], "block": block, "gas_used": int(receipt["gasUsed"], 16)})
    fe = resolve()
    return {
        "schema": RECORD_SCHEMA,
        "network": NETWORK,
        "chain_id": CHAIN_ID,
        "explorer": EXPLORER,
        "deployer": deployer,
        "fe": {"version": fe.version, "commit": fe.commit},
        "contracts": contracts,
        "transactions": transactions,
    }


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rpc_url() -> str:
    return os.environ.get("BASE_SEPOLIA_RPC_URL") or DEFAULT_RPC


def rehearse() -> int:
    prepare()
    port = free_port()
    anvil = subprocess.Popen(
        ["anvil", "--fork-url", rpc_url(), "--port", str(port), "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                Chain(url)
                break
            except OSError:
                time.sleep(0.5)
        broadcast(url, ANVIL_KEY, CACHE / "rehearsal-broadcast")
        REHEARSAL.write_text(json.dumps(record(CACHE / "rehearsal-broadcast", ANVIL_ACCOUNT), indent=2) + "\n")
        print(f"rehearsed on a fork of Base Sepolia; record in {REHEARSAL.relative_to(ROOT)}")
        return check(REHEARSAL, url, prepared=True, write=False)
    finally:
        anvil.terminate()
        anvil.wait()


def deploy(again: bool, resume: bool) -> int:
    if RECORD.exists() and not again:
        raise SystemExit(f"{RECORD.relative_to(ROOT)} exists: this would deploy a second time (--again to do so)")
    entry = json.loads(KEY.read_text())[0]
    chain = Chain(rpc_url())
    if int(chain.request("eth_chainId"), 16) != CHAIN_ID:
        raise SystemExit(f"{rpc_url()} is not Base Sepolia")
    balance = int(chain.request("eth_getBalance", entry["address"], "latest"), 16)
    if balance < MIN_BALANCE:
        raise SystemExit(f"{entry['address']} holds {balance / WAD:.6f} ETH on Base Sepolia; fund it with at least {MIN_BALANCE / WAD} first")
    prepare()
    log = CACHE / "broadcast" / "Live.s.sol" / str(CHAIN_ID) / "run-latest.json"
    run = json.loads(log.read_text()) if resume and log.exists() else None
    # A stopped run whose every transaction has since confirmed has nothing left to send.
    if not (run and not run.get("pending") and len(run["receipts"]) == len(run["transactions"])):
        broadcast(rpc_url(), entry["private_key"], CACHE / "broadcast", resume)
    RECORD.parent.mkdir(exist_ok=True)
    RECORD.write_text(json.dumps(record(CACHE / "broadcast", entry["address"]), indent=2) + "\n")
    print(f"deployed; record in {RECORD.relative_to(ROOT)}")
    return check(RECORD, rpc_url(), prepared=True, write=True)


# ---- checking ----


def logs(chain: Chain, rec: dict) -> dict[str, list]:
    """Every event LiveRecorder logged in the recorded transactions, by event name."""
    recorder = rec["contracts"]["LiveRecorder"]["address"]
    topics = {"0x" + keccak(s).hex(): n for n, s in EVENTS.items()}
    found: dict[str, list] = {n: [] for n in EVENTS}
    for tx in rec["transactions"]:
        receipt = chain.request("eth_getTransactionReceipt", tx["hash"])
        tx["receipt"] = receipt
        for log in receipt["logs"]:
            if same(log["address"], recorder) and log["topics"][0] in topics:
                found[topics[log["topics"][0]]].append(
                    {"tx": tx["hash"], "block": tx["block"], "topics": log["topics"], "data": bytes.fromhex(log["data"][2:])}
                )
    return found


def without_metadata(code: bytes) -> bytes:
    """Solidity code without its CBOR metadata trailer, whose length is the last two bytes."""
    return code[: -(int.from_bytes(code[-2:], "big") + 2)]


def code_matches(name: str, onchain: bytes) -> bool:
    """Fe code must be byte-identical. Solidity code must be identical apart from
    its metadata hash, which hashes the compile's settings, remappings among them,
    and forge passes only the remappings each compile uses."""
    if name in FE:
        ingot, built = FE[name]
        return onchain == bytes.fromhex((ROOT / "ingots" / ingot / "out" / f"{built}.runtime.bin").read_text().strip())
    artifact = json.loads((REFERENCE / "out" / f"{name}.sol" / f"{name}.json").read_text())["deployedBytecode"]
    code = bytearray.fromhex(artifact["object"][2:])
    # Solidity writes immutables into the code at deployment: MockRateProvider's rate.
    for refs in artifact.get("immutableReferences", {}).values():
        for ref in refs:
            code[ref["start"] : ref["start"] + ref["length"]] = RATE.to_bytes(ref["length"], "big")
    return len(onchain) == len(code) and without_metadata(onchain) == without_metadata(bytes(code))


def check(path: Path, rpc: str, prepared: bool = False, write: bool = True) -> int:
    plan = json.loads(PLAN.read_text()) if prepared else prepare()
    rec = json.loads(path.read_text())
    chain = Chain(rpc)
    if int(chain.request("eth_chainId"), 16) != rec["chain_id"]:
        raise SystemExit(f"{rpc} is not chain {rec['chain_id']}")
    c = {n: v["address"] for n, v in rec["contracts"].items()}
    by_address = {a.lower(): n for n, a in c.items()}
    feeds = {d.name: d for d in feed_check.declarations(REGISTRY)}
    claims = []

    def claim(question: str, holds: bool, evidence: str) -> None:
        claims.append({"question": question, "holds": bool(holds), "evidence": evidence})

    events = logs(chain, rec)
    txs = rec["transactions"]
    ok = all(int(t["receipt"]["status"], 16) == 1 and int(t["receipt"]["blockNumber"], 16) == t["block"] for t in txs)
    blocks = [t["block"] for t in txs]
    claim(
        "Did every recorded transaction succeed, in the block the record gives?",
        ok,
        f"{len(txs)} transactions from {rec['deployer']}, blocks {min(blocks):,} to {max(blocks):,}",
    )

    mismatched = [n for n, a in c.items() if not code_matches(n, chain.code(a))]
    fe = rec["fe"]
    claim(
        "Is each contract's code on chain exactly the code this repository builds?",
        not mismatched,
        (f"{sum(n in FE for n in c)} Fe contracts byte-identical to fe build with Fe {fe['version']}; "
         f"LiveRecorder and MockRateProvider (rate {RATE / WAD}) identical to forge's build apart from "
         "Solidity's metadata hash")
        if not mismatched else f"differs: {', '.join(mismatched)}",
    )

    exits = plan["exits"]
    attacks = []
    for e in events["Attack"]:
        d = e["data"]
        data = bytes.fromhex(chain.request("eth_getTransactionByHash", e["tx"])["input"][2:])
        attacks.append({
            "pool": by_address[f"0x{int(e['topics'][1], 16):040x}"], "tx": e["tx"], "block": e["block"],
            "exits": word(d, 0), "batch": [word(data[4:], 4 + i) for i in range(word(data[4:], 3))],
            "succeeded": bool(word(d, 1)), "rate_before": word(d, 2), "rate_after": word(d, 3),
            "reason": "0x" + dynamic(d, 4).hex(),
        })

    def attack(pool: str, batch: list[int]) -> dict:
        found = [a for a in attacks if a["pool"] == pool and a["batch"] == batch]
        return found[0] if len(found) == 1 else {"succeeded": None, "rate_before": 0, "rate_after": 0, "reason": "0x", "tx": "", "block": 0}

    f, planned = attack("FaithfulPool", exits), plan["FaithfulPool"]
    loss = (f["rate_before"] - f["rate_after"]) / max(f["rate_before"], 1)
    claim(
        "On chain, does the attacker's planned batch lower the value behind each share of the pool that rounds as Balancer V2?",
        f["succeeded"] is True and f["rate_after"] < f["rate_before"]
        and (f["rate_before"], f["rate_after"]) == (planned["start"], planned["end"]),
        f"{len(exits)} exits in one transaction ({short(f['tx'])}, block {f['block']:,}): "
        f"{f['rate_before'] / WAD:.4f} to {f['rate_after'] / WAD:.4f} per BPT (-{loss:.2%}), "
        "equal to the wei to LivePlan's run of the same batch",
    )
    typed = ("TypedPool", "GuardedPool")
    full = {p: attack(p, exits) for p in typed}
    claim(
        "Do the typed and guarded pools reject the same batch on chain, keeping the value behind each share?",
        all(a["succeeded"] is False and a["rate_before"] == a["rate_after"] == plan[p]["start"]
            and a["reason"] == plan[p]["reason"] and plan[p]["stopped_at"] < len(exits) for p, a in full.items()),
        "; ".join(f"{p}: reverted {show_error(decode_error(bytes.fromhex(a['reason'][2:])))} at exit "
                  f"{plan[p]['stopped_at'] + 1} of {len(exits)}, as LivePlan finds; {a['rate_before'] / WAD:.4f} per BPT unchanged"
                  for p, a in full.items()),
    )
    prefix = {p: attack(p, exits[: plan[p]["stopped_at"]]) for p in typed}
    claim(
        "Without the exit they reject, does the same batch raise the value behind each typed and guarded share instead?",
        all(a["succeeded"] is True and a["rate_after"] > a["rate_before"] == plan[p]["start"]
            and a["rate_after"] == plan[p]["rate_at_stop"] for p, a in prefix.items()),
        "; ".join(f"{p}: {plan[p]['stopped_at']} exits, {a['rate_before'] / WAD:.4f} to {a['rate_after'] / WAD:.4f} per BPT "
                  f"(+{(a['rate_after'] - a['rate_before']) / max(a['rate_before'], 1):.2%})" for p, a in prefix.items())
        + ", equal to the wei to LivePlan",
    )
    for a in attacks:
        a["reason"] = show_error(decode_error(bytes.fromhex(a["reason"][2:]))) if a["reason"] != "0x" else None
        del a["batch"]

    calls = {}
    for e in events["Call"]:
        target = by_address[f"0x{int(e['topics'][1], 16):040x}"]
        d = e["data"]
        result = dynamic(d, 2)
        calls[target] = {"tx": e["tx"], "block": e["block"], "succeeded": bool(word(d, 1)),
                         "result": word(result, 0) if word(d, 1) else decode_error(result)}

    leg, eth_usd = read(chain, feeds["CBETH_ETH"]), read(chain, feeds["ETH_USD"])
    composite = next((r for r in (leg, eth_usd) if isinstance(r, tuple)), None) or leg * eth_usd // WAD
    live = price(chain, c["CbethUsdOracle"])
    recorded = calls["CbethUsdOracle"]
    claim(
        "Does the oracle price cbETH as cbETH/ETH times ETH/USD, read from Chainlink's Base Sepolia feeds with every check?",
        recorded["succeeded"] and live == composite,
        (f"block {chain.block:,}: {usd(live)}, equal to the wei to the product of the feeds' answers"
         if isinstance(live, int) else f"block {chain.block:,}: reverts {show_error(live)}, as a stale feed must")
        + f"; recorded on chain at deployment: {usd(recorded['result'])} (block {recorded['block']:,})",
    )

    deployments = events["Deployment"]
    bind = decode_error(dynamic(deployments[0]["data"], 2)) if len(deployments) == 1 else None
    cbeth_eth = feeds["CBETH_ETH"].address.lower()
    claim(
        "Declared as an 8-decimal USD feed, is cbETH/ETH rejected when the contract binding it is deployed?",
        bind == ("WrongDecimals", (cbeth_eth, 8, 18)) and word(deployments[0]["data"], 0) == 0,
        f"{show_error(bind)} in {short(deployments[0]['tx'])}, block {deployments[0]['block']:,}" if bind else "not recorded",
    )

    declared = calls["DeclaredCbethEthAsUsd"]
    misdeclared = deployed_feed(chain, rec, "DeclaredCbethEthAsUsd")
    now = price(chain, c["DeclaredCbethEthAsUsd"])
    claim(
        "Declared with its real 18 decimals, does it deploy, and is every read of it rejected?",
        not declared["succeeded"] and declared["result"][0] == "AnswerOutOfBand"
        and same(misdeclared.address, feeds["CBETH_ETH"].address) and now == read(chain, misdeclared),
        f"deployed at {short(c['DeclaredCbethEthAsUsd'])}; its read reverted {show_error(declared['result'])} "
        f"in {short(declared['tx'])}, and {show_error(now) if isinstance(now, tuple) else 'did not'} at block {chain.block:,}",
    )

    correct = calls["DeclaredCbethUsd"]
    cbeth_usd_feed = deployed_feed(chain, rec, "DeclaredCbethUsd")
    direct = price(chain, c["DeclaredCbethUsd"])
    gap = abs(composite - direct) / direct if isinstance(composite, int) and isinstance(direct, int) else None
    claim(
        "Declared correctly, does Chainlink's own cbETH/USD feed read through the same contract?",
        correct["succeeded"] and direct == read(chain, cbeth_usd_feed),
        (f"block {chain.block:,}: {usd(direct)}, its answer to the wei" if isinstance(direct, int) else show_error(direct))
        + (f"; the oracle's price through ETH is {gap:.2%} from it" if gap is not None else ""),
    )

    previews = 0
    for assets, shares in VAULT_STATES:
        for amount in VAULT_AMOUNTS:
            for name in PREVIEWS:
                ok, data = chain.outcome(c["TypedVault"], selector(f"{name}(uint256,uint256,uint256)") + words(assets, shares, amount))
                previews += ok and word(data, 0) == oz_preview(name, assets, shares, amount)
    total = len(VAULT_STATES) * len(VAULT_AMOUNTS) * len(PREVIEWS)
    claim(
        "Does the deployed typed vault preview as OpenZeppelin's ERC4626?",
        previews == total,
        f"{previews} of {total} previews equal OpenZeppelin's formulas, in {len(VAULT_STATES)} states "
        "including a first deposit after a one-token donation",
    )

    report = {
        "schema": SCHEMA,
        "question": "Does the deployment on Base Sepolia do on chain what the tests say it does?",
        "network": rec["network"],
        "chain_id": rec["chain_id"],
        "explorer": rec["explorer"],
        "checked_at": {"block": chain.block, "timestamp": chain.timestamp},
        "deployer": rec["deployer"],
        "fe": rec["fe"],
        "contracts": rec["contracts"],
        "transactions": [{k: v for k, v in t.items() if k != "receipt"} for t in txs],
        "plan": {"exits": exits, "supply": plan["supply"]},
        "attacks": attacks,
        "oracle": {"recorded": recorded["result"], "recorded_block": recorded["block"], "price": live,
                   "feeds": {n: d.address for n, d in feeds.items()}},
        "declarations": {
            "bind": {"error": show_error(bind) if bind else None, "tx": deployments[0]["tx"] if deployments else None},
            "read": {"error": show_error(declared["result"]), "tx": declared["tx"]},
            "correct": {"price": direct, "recorded": correct["result"], "tx": correct["tx"], "feed": cbeth_usd_feed.address},
        },
        "claims": claims,
    }
    report["platform"] = resolve().platform
    out = ROOT / "docs" / "results" / "live" / f"{report['platform']}.json" if write else REHEARSAL_REPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    for cl in claims:
        print(f"{'holds' if cl['holds'] else 'FAILS'}  {cl['question']}\n       {cl['evidence']}")
    return 0 if all(cl["holds"] for cl in claims) else 1


def deployed_feed(chain: Chain, rec: dict, name: str) -> feed_check.Declared:
    """A DeclaredCbethUsdFeed's declaration, from the constructor arguments in its creation transaction."""
    data = bytes.fromhex(chain.request("eth_getTransactionByHash", rec["contracts"][name]["tx"])["input"][2:])
    args = data[-5 * 32 :]
    return feed_check.Declared(name, "CBETH", "USD", f"0x{word(args, 0):040x}", word(args, 1), word(args, 2),
                               word(args, 3), word(args, 4), "")


def main() -> int:
    parser = argparse.ArgumentParser(prog="harness.live", description=__doc__.split("\n")[0])
    parser.add_argument("command", nargs="?", default="check", choices=["check", "rehearse", "deploy"])
    parser.add_argument("--again", action="store_true", help="deploy even though a record exists")
    parser.add_argument("--resume", action="store_true", help="send the transactions a stopped deployment did not")
    args = parser.parse_args()
    if args.command == "rehearse":
        return rehearse()
    if args.command == "deploy":
        return deploy(args.again, args.resume)
    if not RECORD.exists():
        raise SystemExit(f"no {RECORD.relative_to(ROOT)}: nothing is deployed yet (python3 -m harness.live rehearse)")
    return check(RECORD, rpc_url())


if __name__ == "__main__":
    sys.exit(main())
