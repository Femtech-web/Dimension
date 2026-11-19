const WAD = 10n ** 18n;

/** A number with thousands separators. */
export function n(value: number | bigint): string {
  return value.toLocaleString("en-US");
}

/** A WAD-scaled integer as a decimal, `places` digits after the point. */
export function wad(value: number | string | bigint, places = 2): string {
  const v = BigInt(value);
  const scale = 10n ** BigInt(places);
  const scaled = (v * scale + WAD / 2n) / WAD;
  const whole = scaled / scale;
  const frac = (scaled % scale).toString().padStart(places, "0");
  return places > 0 ? `${n(whole)}.${frac}` : n(whole);
}

/** A WAD-scaled integer as a float, for charts. */
export function wadFloat(value: number | string | bigint): number {
  return Number(BigInt(value)) / 1e18;
}

export function pct(value: number, places = 2): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(places)}%`;
}

export function shortHash(hash: string): string {
  return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
}
