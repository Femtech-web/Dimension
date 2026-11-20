// Read-only calls to Base Sepolia from the visitor's browser, through its public
// RPC. Every read on a page is made at one block, so the numbers agree.
import { wad } from "@/lib/format";

export const RPC = "https://sepolia.base.org";

// `cast sig` of each signature.
export const SELECTOR = {
  usdPrice: "0x6619aa86",
  getRate: "0x679aefce",
  latestRoundData: "0xfeaf968c",
  previewDeposit: "0x224fe64d",
  previewMint: "0x1740e545",
  previewWithdraw: "0x7f0e8030",
  previewRedeem: "0x80827299",
} as const;

const ERRORS: Record<string, { name: string; args: number }> = {
  "0x63b64fb7": { name: "AnswerOutOfBand", args: 4 },
  "0xfac0852b": { name: "StaleAnswer", args: 3 },
  "0x828c8880": { name: "NonPositiveAnswer", args: 1 },
  "0x04f9e16b": { name: "WrongDecimals", args: 3 },
  "0xa97825b3": { name: "ShareValueDecreased", args: 0 },
};

export type Outcome = { ok: true; data: string } | { ok: false; data: string };

type Reply = { id: number; result?: string; error?: { message: string; data?: unknown } };

// Public RPCs drop or rate-limit requests now and then, so each is tried twice.
async function post<T>(body: unknown): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(RPC, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`RPC answered ${response.status}`);
      return await response.json();
    } catch (e) {
      if (attempt === 1) throw e;
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  }
}

/** A recent block that every node behind the public RPC already has: two below
 * the head one node reports, since the next request may reach a node behind it. */
export async function readBlock(): Promise<bigint> {
  const reply = await post<Reply>({ jsonrpc: "2.0", id: 0, method: "eth_blockNumber", params: [] });
  if (reply.result === undefined) throw new Error(reply.error?.message ?? "no block number");
  return BigInt(reply.result) - 2n;
}

/** eth_calls at `block`, in one batched request: each one's return data, or the data it reverts with. */
export async function callAll(calls: { to: string; data: string }[], block: bigint, attempt = 0): Promise<Outcome[]> {
  const tag = `0x${block.toString(16)}`;
  const replies = await post<Reply[]>(
    calls.map((c, id) => ({ jsonrpc: "2.0", id, method: "eth_call", params: [{ to: c.to, data: c.data }, tag] })),
  );
  const outcomes: (Outcome | null)[] = calls.map((_, id) => {
    const reply = replies.find((r) => r.id === id);
    if (reply?.result !== undefined) return { ok: true, data: reply.result };
    const revert = reply?.error?.data;
    return typeof revert === "string" && revert.startsWith("0x") ? { ok: false, data: revert } : null;
  });
  // An error without revert data is the node's, not the contract's: ask again once.
  if (outcomes.every((o) => o !== null)) return outcomes as Outcome[];
  if (attempt === 1) throw new Error("the RPC could not run every call");
  await new Promise((resolve) => setTimeout(resolve, 700));
  return callAll(calls, block, 1);
}

export function word(data: string, i: number): bigint {
  return BigInt(`0x${data.slice(2 + 64 * i, 2 + 64 * (i + 1)) || "0"}`);
}

export function encode(...values: bigint[]): string {
  return values.map((v) => v.toString(16).padStart(64, "0")).join("");
}

/** Revert data as a sentence: Dimension's typed errors, and Balancer's `BAL#` reasons. */
export function revertReason(data: string): string {
  const selector = data.slice(0, 10);
  const body = `0x${data.slice(10)}`;
  if (selector === "0x08c379a0") {
    const length = Number(word(body, 1));
    const bytes = body.slice(2 + 128, 2 + 128 + 2 * length);
    return `Error("${new TextDecoder().decode(Uint8Array.from(bytes.match(/../g) ?? [], (h) => parseInt(h, 16)))}")`;
  }
  const error = ERRORS[selector];
  if (!error) return data === "0x" ? "reverts without data" : `reverts with ${selector}`;
  const args = Array.from({ length: error.args }, (_, i) => word(body, i));
  if (error.name === "AnswerOutOfBand") {
    return `AnswerOutOfBand: ${wad(args[1], 4)} is outside ${wad(args[2], 0)} to ${wad(args[3], 0)}`;
  }
  if (error.name === "StaleAnswer") return `StaleAnswer: last updated ${(args[2] - args[1]).toLocaleString("en-US")} s before`;
  return error.name;
}
