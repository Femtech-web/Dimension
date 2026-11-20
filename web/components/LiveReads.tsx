"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Status } from "@/components/Claims";
import { SELECTOR, callAll, encode, readBlock, revertReason, word } from "@/lib/chain";
import { n, wad } from "@/lib/format";
import styles from "./LiveReads.module.css";

export type LiveAddresses = {
  oracle: string;
  misdeclared: string;
  declared: string;
  vault: string;
  pools: [string, string][];
  cbethEth: string;
  ethUsd: string;
};

type Reading = { label: string; value: string; unit?: string; detail: string; holds: boolean; verdict: string };

const WAD = 10n ** 18n;

async function readAll(a: LiveAddresses, block: bigint): Promise<{ readings: Reading[]; rates: [string, bigint][] }> {
  const [oracle, leg, ethUsd, misdeclared, declared, ...rates] = await callAll(
    [
      { to: a.oracle, data: SELECTOR.usdPrice },
      { to: a.cbethEth, data: SELECTOR.latestRoundData },
      { to: a.ethUsd, data: SELECTOR.latestRoundData },
      { to: a.misdeclared, data: SELECTOR.usdPrice },
      { to: a.declared, data: SELECTOR.usdPrice },
      ...a.pools.map(([, address]) => ({ to: address, data: SELECTOR.getRate })),
    ],
    block,
  );
  // cbETH/ETH reports 18 decimals and ETH/USD 8, as the registry declares.
  const legWad = word(leg.data, 1);
  const ethUsdWad = word(ethUsd.data, 1) * 10n ** 10n;
  const product = (legWad * ethUsdWad) / WAD;
  const price = oracle.ok ? word(oracle.data, 0) : null;
  const direct = declared.ok ? word(declared.data, 0) : null;
  const gap = price !== null && direct !== null ? (Number(price - direct) / Number(direct)) * 100 : null;
  return {
    readings: [
      {
        label: "cbETH in USD, through ETH",
        value: price !== null ? wad(price, 2) : "reverts",
        unit: price !== null ? "USD" : undefined,
        detail: price !== null
          ? `cbETH/ETH ${wad(legWad, 4)} × ETH/USD ${wad(ethUsdWad, 2)}`
          : revertReason(oracle.data),
        holds: price === product,
        verdict: price === product ? "equal to the wei to the product of Chainlink's answers" : "differs from the product",
      },
      {
        label: "MIP-X43: cbETH/ETH declared as cbETH/USD",
        value: misdeclared.ok ? wad(word(misdeclared.data, 0), 2) : "reverts",
        unit: misdeclared.ok ? "USD" : undefined,
        detail: misdeclared.ok ? "the read went through" : revertReason(misdeclared.data),
        holds: !misdeclared.ok,
        verdict: misdeclared.ok ? "accepted" : "rejected on every read",
      },
      {
        label: "Chainlink's cbETH/USD, declared correctly",
        value: direct !== null ? wad(direct, 2) : "reverts",
        unit: direct !== null ? "USD" : undefined,
        detail: direct !== null ? "the same contract, the right feed" : revertReason(declared.data),
        holds: direct !== null,
        verdict: gap !== null ? `${Math.abs(gap).toFixed(2)}% from the price through ETH` : "no price",
      },
    ],
    rates: a.pools.map(([name], i) => [name, rates[i].ok ? word(rates[i].data, 0) : -1n]),
  };
}

// OpenZeppelin's ERC4626 with a decimals offset of 0.
function openZeppelin(op: string, assets: bigint, shares: bigint, amount: bigint): bigint {
  const div = (x: bigint, y: bigint, up: boolean) => (up ? (x + y - 1n) / y : x / y);
  if (op === "previewDeposit") return div(amount * (shares + 1n), assets + 1n, false);
  if (op === "previewMint") return div(amount * (assets + 1n), shares + 1n, true);
  if (op === "previewWithdraw") return div(amount * (shares + 1n), assets + 1n, true);
  return div(amount * (assets + 1n), shares + 1n, false);
}

const OPS = [
  ["previewDeposit", "deposit", "shares out", "down"],
  ["previewMint", "mint", "assets in", "up"],
  ["previewWithdraw", "withdraw", "shares in", "up"],
  ["previewRedeem", "redeem", "assets out", "down"],
] as const;

const STATES = [
  { name: "Empty vault", assets: "0", shares: "0", amount: "7" },
  { name: "One share short", assets: "1000", shares: "999", amount: "7" },
  { name: "After a 1-token donation", assets: "1000000000000000001", shares: "1", amount: "1000000000000000000" },
];

function Vault({ address }: { address: string }) {
  const [form, setForm] = useState(STATES[1]);
  const [rows, setRows] = useState<{ op: string; chain: bigint | null; oz: bigint }[] | null>(null);
  const [error, setError] = useState("");

  const preview = useCallback(async (state: typeof form) => {
    setError("");
    let assets: bigint, shares: bigint, amount: bigint;
    try {
      [assets, shares, amount] = [BigInt(state.assets), BigInt(state.shares), BigInt(state.amount)];
      if (assets < 0n || shares < 0n || amount < 0n || [assets, shares, amount].some((v) => v >= 2n ** 120n)) throw 0;
    } catch {
      setError("Whole numbers from 0 to 2¹²⁰, in the token's smallest unit.");
      return;
    }
    try {
      const block = await readBlock();
      const results = await callAll(
        OPS.map(([op]) => ({ to: address, data: SELECTOR[op] + encode(assets, shares, amount) })),
        block,
      );
      setRows(OPS.map(([op], i) => ({
        op,
        chain: results[i].ok ? word(results[i].data, 0) : null,
        oz: openZeppelin(op, assets, shares, amount),
      })));
    } catch {
      setError("Base Sepolia's public RPC did not answer. Try again.");
    }
  }, []);

  useEffect(() => {
    preview(STATES[1]);
  }, [preview]);

  return (
    <div className={`panel ${styles.vault}`}>
      <div className={styles.vaultHead}>
        <div>
          <div className={styles.label}>The typed vault, any state</div>
          <p className="ink2" style={{ margin: "6px 0 0", fontSize: 14.5 }}>
            The deployed vault&apos;s four previews against OpenZeppelin&apos;s ERC4626, computed here in your browser.
          </p>
        </div>
        <div className={styles.presets}>
          {STATES.map((s) => (
            <button
              key={s.name}
              type="button"
              className={`button ghost ${styles.small}`}
              aria-pressed={form.name === s.name}
              onClick={() => {
                setForm(s);
                preview(s);
              }}
            >
              {s.name}
            </button>
          ))}
        </div>
      </div>
      <form
        className={styles.inputs}
        onSubmit={(e) => {
          e.preventDefault();
          preview(form);
        }}
      >
        {(["assets", "shares", "amount"] as const).map((k) => (
          <label key={k}>
            <span>{k === "assets" ? "Total assets" : k === "shares" ? "Total shares" : "Amount"}</span>
            <input
              className="num"
              inputMode="numeric"
              value={form[k]}
              onChange={(e) => setForm({ ...form, name: "", [k]: e.target.value.trim() })}
            />
          </label>
        ))}
        <button type="submit" className={`button ${styles.small}`}>
          Ask the chain
        </button>
      </form>
      {error && <p className={styles.error}>{error}</p>}
      {rows && (
        <div className="table-wrap" style={{ marginTop: 16 }}>
          <table>
            <thead>
              <tr>
                <th>Operation</th>
                <th className="n">On chain</th>
                <th className="n">OpenZeppelin</th>
                <th>Rounding</th>
                <th>Equal</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.op}>
                  <td>
                    {OPS[i][1]} <span className="muted">· {OPS[i][2]}</span>
                  </td>
                  <td className="n">{r.chain === null ? "reverts" : n(r.chain)}</td>
                  <td className="n">{n(r.oz)}</td>
                  <td className="num">{OPS[i][3]}</td>
                  <td>
                    <Status holds={r.chain === r.oz} yes="equal" no="differs" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function LiveReads({ addresses }: { addresses: LiveAddresses }) {
  const [state, setState] = useState<{ block: bigint; at: string; readings: Reading[]; rates: [string, bigint][] } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Only the newest read may update the page, however the reads finish.
  const latest = useRef(0);

  const refresh = useCallback(async () => {
    const run = ++latest.current;
    setBusy(true);
    setError("");
    try {
      const block = await readBlock();
      const read = await readAll(addresses, block);
      if (run === latest.current) setState({ block, at: new Date().toLocaleTimeString(), ...read });
    } catch {
      if (run === latest.current) setError("Base Sepolia's public RPC did not answer. Try again.");
    } finally {
      if (run === latest.current) setBusy(false);
    }
  }, [addresses]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className={styles.live}>
      <div className={styles.bar}>
        <span className="num">
          {state ? `Base Sepolia block ${n(state.block)}, read at ${state.at}` : busy ? "Reading Base Sepolia…" : ""}
        </span>
        <button type="button" className={`button ghost ${styles.small}`} onClick={refresh} disabled={busy}>
          {busy ? "Reading…" : "Read again"}
        </button>
      </div>
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.cards}>
        {(state?.readings ?? []).map((r) => (
          <div key={r.label} className={`panel ${styles.card}`}>
            <div className={styles.label}>{r.label}</div>
            <div className={styles.value}>
              {r.value}
              {r.unit && <span className={styles.unit}> {r.unit}</span>}
            </div>
            <div className={styles.detail}>{r.detail}</div>
            <div className={styles.verdict}>
              <Status holds={r.holds} yes={r.verdict} no={r.verdict} />
            </div>
          </div>
        ))}
        {state && (
          <div className={`panel ${styles.card}`}>
            <div className={styles.label}>Value per pool share, now</div>
            <table className={styles.rates}>
              <tbody>
                {state.rates.map(([name, rate]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td className="n">{rate < 0n ? "reverts" : wad(rate, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className={styles.detail}>Each started at 1.0000. The pools are open test contracts: anyone can call them.</div>
          </div>
        )}
      </div>
      <Vault address={addresses.vault} />
    </div>
  );
}
