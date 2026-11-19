"""Renders docs/index.html, the verification page, from the saved reports.

Usage: python3 -m harness.page

Reads docs/results/<suite>/<platform>.json for this platform and writes one
self-contained page: every claim with its evidence, the Moonwell prices through
MIP-X43, the Balancer search, the costs, and the rejected constructions. It has
no network dependencies and works without JavaScript. Regenerate it after a run;
never edit it by hand.
"""

from __future__ import annotations

import datetime
import json
import sys
from html import escape

from harness.toolchain import ROOT, resolve

RESULTS = ROOT / "docs" / "results"
OUT = ROOT / "docs" / "index.html"
WAD = 10**18

SUITES = [
    ("differential", "Balancer's Solidity against the Fe port", "make differential"),
    ("fidelity", "The Fe port against the deployed pool", "make fidelity"),
    ("exploration", "Native search over the three kernels", "make explore"),
    ("evm", "The three contracts on an EVM", "make evm"),
    ("moonwell", "Moonwell's cbETH market on Base forks", "make moonwell"),
]


def load(suite: str, platform: str) -> dict | None:
    path = RESULTS / suite / f"{platform}.json"
    return json.loads(path.read_text()) if path.exists() else None


def num(n: int | float) -> str:
    return f"{n:,}"


def usd(wad: int, places: int = 2) -> str:
    return f"{wad / WAD:,.{places}f}"


def utc(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%b %d, %H:%M:%S")


def tile(label: str, value: str, detail: str) -> str:
    return (
        f'<div class="tile"><div class="tile-label">{escape(label)}</div>'
        f'<div class="tile-value">{escape(value)}</div><div class="tile-detail">{escape(detail)}</div></div>'
    )


def status(holds: bool) -> str:
    icon, word, cls = ("✓", "holds", "good") if holds else ("✕", "fails", "bad")
    return f'<span class="status"><span class="dot {cls}" aria-hidden="true">{icon}</span>{word}</span>'


def table(head: list[str], rows: list[list[str]], numeric_from: int = 1, nowrap_from: int = 99) -> str:
    def cls(i: int) -> str:
        names = ["n"] * (i >= numeric_from) + ["nw"] * (i >= nowrap_from)
        return f' class="{" ".join(names)}"' if names else ""

    cells = "".join(f"<th{cls(i)}>{h}</th>" for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="scroll"><table><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table></div>'


def missing(command: str) -> str:
    return f'<p class="missing">No report on this platform yet. Run <code>{escape(command)}</code>, then <code>make page</code>.</p>'


def claims_section(reports: dict) -> str:
    groups = []
    for suite, title, command in SUITES:
        r = reports.get(suite)
        if r is None:
            groups.append(f"<h3>{escape(title)}</h3>{missing(command)}")
            continue
        if suite == "differential":
            s = r["summary"]
            claims = [{
                "question": r["question"],
                "holds": s["mismatches"] == 0,
                "evidence": f"{num(s['vectors'])} vectors over {s['functions']} functions: {num(s['both_succeeded'])} identical "
                f"results, {num(s['both_reverted'])} identical reverts, {s['mismatches']} mismatches",
            }]
        else:
            claims = r["claims"]
        items = "".join(
            f'<li>{status(c["holds"])}<div><div class="q">{escape(c["question"])}</div>'
            f'<div class="ev">{escape(c["evidence"])}</div></div></li>'
            for c in claims
        )
        groups.append(f'<h3>{escape(title)} <code>{escape(command)}</code></h3><ul class="claims">{items}</ul>')
    return "".join(groups)


def price_chart(m: dict) -> str:
    prices = sorted(m["prices"], key=lambda p: p["timestamp"])
    w, h, left, right, top, bottom = 880, 320, 56, 24, 28, 36
    y_max = 3_000
    t0 = prices[0]["timestamp"] - 36_000
    t1 = prices[-1]["timestamp"] + 36_000

    def x(ts: int) -> float:
        return left + (w - left - right) * (ts - t0) / (t1 - t0)

    def y(v: float) -> float:
        return top + (h - top - bottom) * (1 - v / y_max)

    window = [p for p in prices if p["moonwell_oracle"] == "mip-x43"]
    start = window[0]["timestamp"]
    end = next(p["timestamp"] for p in prices if p["timestamp"] > window[-1]["timestamp"])
    parts = [
        f'<rect class="band" x="{x(start):.1f}" y="{top}" width="{x(end) - x(start):.1f}" height="{h - top - bottom}"/>',
        f'<text class="band-label" x="{x(start) + 8:.1f}" y="{top + 14}">MIP-X43 in effect</text>',
    ]
    for v in range(0, y_max + 1, 500):
        label = "0" if v == 0 else (f"{v // 1000}K" if v % 1000 == 0 else f"{v / 1000:.1f}K")
        parts.append(f'<line class="{"axis" if v == 0 else "grid"}" x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        parts.append(f'<text class="tick" x="{left - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{label}</text>')
    day = datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).replace(hour=0, minute=0, second=0) + datetime.timedelta(days=1)
    while day.timestamp() < t1:
        parts.append(f'<text class="tick" x="{x(day.timestamp()):.1f}" y="{h - 12}" text-anchor="middle">{day.strftime("%b %d")}</text>')
        day += datetime.timedelta(days=1)
    for key, cls in (("moonwell_wad", "s2"), ("fe_wad", "s1")):
        pts = " ".join(f"{x(p['timestamp']):.1f},{y(p[key] / WAD):.1f}" for p in prices)
        parts.append(f'<polyline class="line {cls}" points="{pts}"/>')
        parts += [f'<circle class="mark {cls}" cx="{x(p["timestamp"]):.1f}" cy="{y(p[key] / WAD):.1f}" r="4"/>' for p in prices]
    mid = window[len(window) // 2]["timestamp"]
    top_fe = max(p["fe_wad"] for p in window) / WAD
    parts.append(f'<text class="label" x="{x(mid):.1f}" y="{y(top_fe) - 12:.1f}" text-anchor="middle">Dimension, same feeds</text>')
    parts.append(f'<text class="label" x="{x(mid):.1f}" y="{y(0) - 10:.1f}" text-anchor="middle">Moonwell\'s oracle: about 1.12 USD</text>')
    parts.append(f'<line class="crosshair" x1="0" x2="0" y1="{top}" y2="{h - bottom}" visibility="hidden"/>')
    parts.append(f'<rect class="hit" x="{left}" y="{top}" width="{w - left - right}" height="{h - top - bottom}"/>')
    points = [
        {"x": round(x(p["timestamp"]), 1), "block": num(p["block"]), "time": utc(p["timestamp"]) + " UTC",
         "fe": usd(p["fe_wad"]), "moonwell": usd(p["moonwell_wad"])}
        for p in prices
    ]
    rows = [[num(p["block"]), utc(p["timestamp"]), usd(p["moonwell_wad"], 4), usd(p["fe_wad"], 4)] for p in prices]
    legend = (
        '<div class="legend"><span><i class="key s1"></i>Dimension (<code>CbethUsdOracle</code>)</span>'
        "<span><i class=\"key s2\"></i>Moonwell's deployed oracle</span></div>"
    )
    svg = (
        f'<svg id="chart" viewBox="0 0 {w} {h}" role="img" tabindex="0" aria-label="cbETH price in USD from both oracles, '
        f'block {num(prices[0]["block"])} to {num(prices[-1]["block"])}. A table of the same values follows.">{"".join(parts)}</svg>'
    )
    return (
        f'<figure><figcaption>cbETH price in USD, read at {len(prices)} Base blocks from the same two Chainlink feeds</figcaption>'
        f'{legend}<div class="chart">{svg}<div id="tip" class="tip" hidden></div></div>'
        f'<details><summary>Table of the same values</summary>'
        f'{table(["Block", "Time (UTC)", "Moonwell (USD)", "Dimension (USD)"], rows, numeric_from=2)}</details></figure>'
        f'<script type="application/json" id="points">{json.dumps(points)}</script>'
    )


def moonwell_section(m: dict | None) -> str:
    if m is None:
        return missing("make moonwell")
    ref = m["reference"]
    layers = [
        [escape(l["layer"]), escape(l["case"]), escape(l.get("error", l.get("note", ""))),
         "rejected" if l["rejected"] else "passes"]
        for l in m["layers"]
    ]
    return (
        "<p>MIP-X43 executed at Base block "
        f'{num(ref["mip_x43_block"])} and was undone at block {num(ref["fixed_block"])}. In between, Moonwell valued cbETH '
        "at the cbETH/ETH exchange rate. Dimension's oracle reads the same two feeds and multiplies them, as the types require."
        "</p>"
        + price_chart(m)
        + "<h3>Where each form of the mistake is stopped</h3>"
        + table(["Layer", "Declaration", "Result", "Outcome"], layers, numeric_from=9)
    )


def balancer_section(e: dict | None, evm: dict | None) -> str:
    out = []
    if e is None:
        out.append(missing("make explore"))
    else:
        ops = ["swapGivenOut", "exitGivenOut", "joinGivenIn", "joinGivenOut"]
        rows = []
        for op in ops:
            cells = [f"<code>{op}</code>"]
            for k in ("faithful", "typed", "guarded"):
                t = e["kernels"][k]["by_operation"][op]
                cells.append(f"{num(t['value_per_bpt_losses'])} / {num(t['stored_invariant_violations'])}")
            rows.append(cells)
        out.append(
            f"<p>Every single operation on {num(e['states'])} small pool states, amounts up to {e['amount_cap']}. "
            "Each cell: operations that lowered the value per share / operations that stored an invariant the "
            "balances do not support.</p>"
        )
        out.append(table(["Operation", "Faithful (Balancer)", "Typed", "Guarded"], rows))
    if evm is None:
        out.append(missing("make evm"))
    else:
        g, rel, size = evm["gas"]["per_operation"], evm["gas"]["relative_to_faithful"], evm["runtime_bytecode_bytes"]
        rows = [
            [k.capitalize(), num(g[k]["swapGivenOut"]) + (f" ({rel[k]['swapGivenOut']})" if k in rel else ""),
             num(g[k]["exitGivenOut"]) + (f" ({rel[k]['exitGivenOut']})" if k in rel else ""), num(size[k])]
            for k in ("faithful", "typed", "guarded")
        ]
        out.append(f"<h3>Cost</h3><p>{escape(evm['gas']['setup'])}.</p>")
        out.append(table(["Contract", "swapGivenOut gas", "exitGivenOut gas", "Runtime bytes"], rows))
    return "".join(out)


def rejected_section(cf: dict | None) -> str:
    if cf is None:
        return missing("make compile-fail")
    rows = [
        [f"<code>{escape(c['id'].split('/', 1)[1])}</code>", escape(c["mechanism"]),
         f"<code>{escape(c['observed']['error_code'])}</code>", "✓ passes" if c["observed"]["twin"]["ok"] else "✕ fails"]
        for c in cf["cases"]
    ]
    return (
        f"<p>{cf['summary']['ok']} of {cf['summary']['cases']} constructions are rejected by the compiler with the expected "
        "error, and each corrected twin compiles and passes its tests. Run any of them live with "
        "<code>make show CASE=&lt;name&gt;</code>.</p>"
        + table(["Case", "Mechanism", "Error", "Twin"], rows, numeric_from=9, nowrap_from=2)
    )


def page(reports: dict, fe) -> str:
    d, f, e, m = (reports.get(k) for k in ("differential", "fidelity", "exploration", "moonwell"))
    tiles = []
    if d:
        tiles.append(tile("Against Balancer's Solidity", f"{d['summary']['mismatches']} mismatches", f"{num(d['summary']['vectors'])} vectors, reverts included"))
    if f:
        tiles.append(tile("Against the deployed pool", f"{f['summary']['mismatches']} mismatches", f"{num(f['summary']['compared'])} quotes at block 23,717,399"))
    if e:
        exits = [e["kernels"][k]["by_operation"]["exitGivenOut"]["value_per_bpt_losses"] for k in ("faithful", "typed", "guarded")]
        tiles.append(tile("Losing exact-out exits", " → ".join(num(n) for n in exits), "Balancer, typed, guarded"))
    if m:
        at = next(p for p in m["prices"] if p["block"] == m["reference"]["mip_x43_block"])
        tiles.append(tile("cbETH at MIP-X43, in USD", f"{usd(at['moonwell_wad'])} vs {usd(at['fe_wad'])}", "Moonwell's oracle vs Dimension"))
    counts = ", ".join(
        f"{reports[s]['summary']['ok']}/{reports[s]['summary']['cases']} {label}"
        for s, label in (("unit", "unit suites"), ("compile-fail", "compile-fail cases"), ("probes", "probes")) if reports.get(s)
    )
    return TEMPLATE.format(
        fe=escape(f"Fe {fe.version} ({fe.commit[:7]})"),
        platform=escape(fe.platform),
        counts=escape(counts),
        tiles="".join(tiles),
        claims=claims_section(reports),
        moonwell=moonwell_section(m),
        balancer=balancer_section(e, reports.get("evm")),
        rejected=rejected_section(reports.get("compile-fail")),
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dimension verification</title>
<meta name="description" content="Every claim Dimension makes, with its evidence, generated from the saved reports.">
<style>
:root {{
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --band: rgba(137,135,129,0.10);
  --s1: #2a78d6; --s2: #eb6834; --good: #0ca30c; --bad: #d03b3b; --code: #f0efec;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --band: rgba(137,135,129,0.14);
    --s1: #3987e5; --s2: #d95926; --code: #262624;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --band: rgba(137,135,129,0.14);
  --s1: #3987e5; --s2: #d95926; --code: #262624;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--ink); font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 960px; margin: 0 auto; padding: 32px 16px 64px; }}
h1 {{ font-size: 28px; margin: 0 0 4px; }}
h2 {{ font-size: 20px; margin: 48px 0 8px; padding-top: 16px; border-top: 1px solid var(--grid); }}
h3 {{ font-size: 15px; margin: 24px 0 8px; }}
p {{ margin: 8px 0; color: var(--ink-2); max-width: 72ch; }}
code {{ font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--code); padding: 1px 4px; border-radius: 4px; }}
h3 code {{ font-weight: 400; color: var(--ink-2); }}
.sub {{ color: var(--ink-2); margin: 0; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 24px 0 8px; }}
.tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
.tile-label {{ font-size: 13px; color: var(--ink-2); }}
.tile-value {{ font-size: 24px; font-weight: 600; margin: 2px 0; }}
.tile-detail {{ font-size: 13px; color: var(--muted); }}
.claims {{ list-style: none; padding: 0; margin: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }}
.claims li {{ display: grid; grid-template-columns: 88px 1fr; gap: 12px; padding: 12px 16px; border-top: 1px solid var(--grid); }}
.claims li:first-child {{ border-top: 0; }}
.q {{ font-weight: 500; }}
.ev {{ color: var(--ink-2); font-size: 14px; overflow-wrap: anywhere; }}
.status {{ display: inline-flex; align-items: center; gap: 6px; font-size: 14px; }}
.dot {{ display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; color: #fff; font-size: 11px; font-weight: 700; }}
.dot.good {{ background: var(--good); }} .dot.bad {{ background: var(--bad); }}
.missing {{ color: var(--muted); }}
.scroll {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ text-align: left; padding: 8px 12px; border-top: 1px solid var(--grid); vertical-align: top; }}
thead th {{ border-top: 0; color: var(--ink-2); font-weight: 500; }}
.n {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.nw {{ white-space: nowrap; }}
figure {{ margin: 16px 0; }}
figcaption {{ font-weight: 500; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 16px; margin: 8px 0; font-size: 14px; color: var(--ink-2); }}
.key {{ display: inline-block; width: 16px; height: 2px; vertical-align: middle; margin-right: 6px; border-radius: 1px; }}
.key.s1 {{ background: var(--s1); }} .key.s2 {{ background: var(--s2); }}
.chart {{ position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 8px; }}
svg {{ display: block; width: 100%; height: auto; }}
svg:focus-visible {{ outline: 2px solid var(--s1); outline-offset: 2px; }}
.grid {{ stroke: var(--grid); stroke-width: 1; }}
.axis {{ stroke: var(--axis); stroke-width: 1; }}
.band {{ fill: var(--band); }}
.band-label, .tick {{ fill: var(--muted); font-size: 12px; }}
.label {{ fill: var(--ink-2); font-size: 13px; }}
.line {{ fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
.line.s1 {{ stroke: var(--s1); }} .line.s2 {{ stroke: var(--s2); }}
.mark {{ stroke: var(--surface); stroke-width: 2; }}
.mark.s1 {{ fill: var(--s1); }} .mark.s2 {{ fill: var(--s2); }}
.crosshair {{ stroke: var(--muted); stroke-width: 1; }}
.hit {{ fill: transparent; cursor: crosshair; }}
.tip {{ position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,0.12); min-width: 200px; }}
.tip .head {{ color: var(--muted); margin-bottom: 4px; }}
.tip .head:not(:first-child) {{ margin-top: 8px; }}
.tip .row {{ display: flex; align-items: center; gap: 8px; }}
.tip strong {{ font-variant-numeric: tabular-nums; }}
.tip .name {{ color: var(--ink-2); }}
details {{ margin-top: 8px; }}
summary {{ cursor: pointer; color: var(--ink-2); font-size: 14px; }}
footer {{ margin-top: 48px; color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<main>
<h1>Dimension verification</h1>
<p class="sub">Every claim Dimension makes, with its evidence, generated from the reports in <code>docs/results/</code>.
{fe} on {platform}. {counts}.</p>
<div class="tiles">{tiles}</div>

<h2>Claims</h2>
<p>Each claim is a question a run answers. A claim fails its run if the answer is no; nothing here is written by hand.</p>
{claims}

<h2>Moonwell MIP-X43</h2>
{moonwell}

<h2>Balancer V2</h2>
{balancer}

<h2>What the compiler rejects</h2>
{rejected}

<footer>Reproduce: <code>make ci</code>, <code>make fidelity</code>, <code>make moonwell</code>, then <code>make page</code>.
See JUDGES.md for a guided tour.</footer>
</main>
<script>
(() => {{
  const svg = document.getElementById("chart");
  const data = document.getElementById("points");
  if (!svg || !data) return;
  const points = JSON.parse(data.textContent);
  const tip = document.getElementById("tip");
  const hair = svg.querySelector(".crosshair");
  const hit = svg.querySelector(".hit");
  let focus = 0;
  const row = (cls, value, name) => {{
    const r = document.createElement("div"); r.className = "row";
    const k = document.createElement("i"); k.className = "key " + cls;
    const v = document.createElement("strong"); v.textContent = value + " USD";
    const n = document.createElement("span"); n.className = "name"; n.textContent = name;
    r.append(k, v, n); return r;
  }};
  const show = (i) => {{
    const near = points.filter((p) => Math.abs(p.x - points[i].x) < 3);
    hair.setAttribute("x1", points[i].x); hair.setAttribute("x2", points[i].x); hair.setAttribute("visibility", "visible");
    tip.replaceChildren();
    for (const p of near) {{
      const head = document.createElement("div"); head.className = "head"; head.textContent = "Block " + p.block + " · " + p.time;
      tip.append(head, row("s1", p.fe, "Dimension"), row("s2", p.moonwell, "Moonwell"));
    }}
    tip.hidden = false;
    const box = svg.getBoundingClientRect(), scale = box.width / svg.viewBox.baseVal.width;
    const left = points[i].x * scale + 16, room = box.width - tip.offsetWidth - 8;
    tip.style.left = Math.max(8, left > room ? points[i].x * scale - tip.offsetWidth - 8 : left) + "px";
    tip.style.top = "24px";
  }};
  const hide = () => {{ tip.hidden = true; hair.setAttribute("visibility", "hidden"); }};
  const nearest = (evt) => {{
    const pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY;
    const x = pt.matrixTransform(svg.getScreenCTM().inverse()).x;
    let best = 0;
    points.forEach((p, i) => {{ if (Math.abs(p.x - x) < Math.abs(points[best].x - x)) best = i; }});
    return best;
  }};
  hit.addEventListener("pointermove", (e) => {{ focus = nearest(e); show(focus); }});
  hit.addEventListener("pointerleave", hide);
  svg.addEventListener("focus", () => show(focus));
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {{
    if (e.key === "ArrowRight") focus = Math.min(points.length - 1, focus + 1);
    else if (e.key === "ArrowLeft") focus = Math.max(0, focus - 1);
    else return;
    e.preventDefault(); show(focus);
  }});
}})();
</script>
</body>
</html>
"""


def main() -> int:
    fe = resolve()
    names = ["differential", "fidelity", "exploration", "evm", "moonwell", "unit", "compile-fail", "probes"]
    reports = {k: r for k in names if (r := load(k, fe.platform)) is not None}
    OUT.write_text(page(reports, fe))
    print(f"{len(reports)} of {len(names)} reports rendered; page: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
