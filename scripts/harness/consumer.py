"""A new project, depending on Dimension the way another builder would.

Usage: python3 -m harness.consumer

Creates a project the way another builder would, with `dimension new`
(cli/dimension.py): the quickstart, taking Dimension from this repository's git
history at HEAD (`source` and `rev`, as for any git dependency). It must compile
and pass its tests, and a misuse must be rejected with Dimension's type error.
Then `dimension check` must pass the project, and fail it once it is set up to
forge trusted values. Last, its list of labels must equal the compiler's: each
ingot is checked against a copy of Dimension in which `given`, `owed`, `held`
and `supply_of` demand a trait nothing implements, so the compiler reports every
call at its own site.
Writes docs/results/consumer/<platform>.json.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from harness.toolchain import ROOT, resolve

sys.path.insert(0, str(ROOT / "cli"))
import dimension  # noqa: E402

SCHEMA = "dimension.consumer/v1"

MISUSE = """use dimension::{Admitted, Asset, In, Out, Quantity, admit, given, scaling_factor}

pub struct USDC {}

impl Asset for USDC {
    const DECIMALS: u256 = 6
}

/// An amount arriving, used where an amount leaving is required.
pub fn wrong(_ raw: u256) -> Quantity<USDC, Out, Admitted> {
    admit(given<USDC, In>(raw), scaling_factor<USDC>())
}
"""

# A price no oracle read produced, forged by the root's own unsafe code (tests/unsafe_root).
FORGE = """use dimension::Price

pub struct ETH {}
pub struct USD {}

pub fn forged(_ wad: u256) -> Price<ETH, USD> {
    let buf = MemArray<u256>::new_zeroed(1)
    let p: *u256 = buf.ptr()
    unsafe { *p = wad }
    let q: *Price<ETH, USD> = p as *Price<ETH, USD>
    unsafe { *q }
}
"""


# The same forgery between two strings that look like a block comment, which Fe
# does not have: a reader that took them for one would miss the unsafe code.
HIDDEN = (
    'pub fn opening() -> String<2> {\n    "/*"\n}\n\n'
    + FORGE.replace("use dimension::Price\n", "")
    + '\npub fn closing() -> String<2> {\n    "*/"\n}\n'
)
HIDDEN = "use dimension::Price\n\n" + HIDDEN

# A feed built inside a function, where feed-check cannot read it.
UNREAD_FEED = """use dimension::value::oracle::{Feed, feed}

pub struct ETH {}
pub struct USD {}

pub fn eth_usd() -> Feed<ETH, USD> {
    feed(
        Address::new(0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70),
        decimals: 8,
        max_age: 1_800,
        min_wad: 1,
        max_wad: 2,
    )
}
"""


def variant(base: Path, at: Path, manifest: tuple[str, str] | None = None, source: tuple[str, str] | None = None) -> Path:
    """A copy of `base` with one line of its fe.toml replaced, or one source file replaced."""
    shutil.copytree(base, at, ignore=shutil.ignore_patterns("out"))
    if manifest:
        text = (at / "fe.toml").read_text()
        (at / "fe.toml").write_text(text.replace(*manifest))
    if source:
        (at / "src" / source[0]).write_text(source[1])
    return at


# The projects whose label calls are compared with the compiler's, by path from the root.
LABELLED = ["tests/labels", "examples/quickstart", "ingots/vault", "ingots/balancer_v2", "ingots/balancer_explorer", "ingots/moonwell"]
_SITE = re.compile(r"error\[6-0003\][^\n]*\n\s*┌─ (\S+?\.fe):(\d+):\d+")


def compiler_labels(fe, ingot: str) -> list[str]:
    """Every call of `given`, `owed`, `held` or `supply_of` in an ingot, as the compiler finds them."""
    skip = shutil.ignore_patterns("out")
    with tempfile.TemporaryDirectory(prefix="dimension-labels-") as tmp:
        root = Path(tmp)
        shutil.copytree(ROOT / "ingots", root / "ingots", ignore=skip)
        if not (root / ingot).exists():
            shutil.copytree(ROOT / ingot, root / ingot, ignore=skip)
        value = root / "ingots" / "dimension" / "src" / "value.fe"
        text = value.read_text()
        for name in ("given", "owed"):
            text = text.replace(f"pub fn {name}<T, F: Flow>(", f"pub fn {name}<T, F: Flow + LabelSite>(", 1)
        for name in ("held", "supply_of"):
            text = text.replace(f"pub fn {name}<T>(", f"pub fn {name}<T: LabelSite>(", 1)
        value.write_text(text + "\npub trait LabelSite {}\n")
        checked = fe.run(["check"], root / ingot)
    return sorted(f"{path}:{line}" for path, line in _SITE.findall(checked.output))


def failures(rows: dimension.Checklist) -> set[str]:
    return {name for status, name, _ in rows.rows if status == "FAIL"}


def main() -> int:
    fe = resolve()
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    manifest = subprocess.run(["git", "show", f"{rev}:ingots/dimension/fe.toml"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    version = tomllib.loads(manifest)["ingot"]["version"]
    with tempfile.TemporaryDirectory(prefix="dimension-consumer-") as tmp:
        quickstart = Path(tmp) / "quickstart"
        with contextlib.redirect_stdout(io.StringIO()):
            dimension.new(quickstart, rev, ROOT.as_uri())
        built = fe.run(["build"], quickstart)
        tested = fe.run(["test", "--backend", "sonatina"], quickstart)
        misuse = fe.run(["check"], variant(quickstart, Path(tmp) / "misuse", source=("lib.fe", MISUSE)))
        checked = dimension.checklist(quickstart, None, None, str(fe.binary))
        unsafe_dep = dimension.checklist(
            variant(quickstart, Path(tmp) / "unsafe-dep", manifest=('name = "dimension"', 'name = "dimension"\nallow_unsafe = true')),
            None,
            None,
            str(fe.binary),
        )
        unsafe_code = dimension.checklist(
            variant(quickstart, Path(tmp) / "unsafe-code", source=("forge.fe", FORGE)), None, None, str(fe.binary)
        )
        hidden = dimension.checklist(
            variant(quickstart, Path(tmp) / "hidden-unsafe", source=("forge.fe", HIDDEN)), None, None, str(fe.binary)
        )
        unread_feed = dimension.checklist(
            variant(quickstart, Path(tmp) / "unread-feed", source=("feeds.fe", UNREAD_FEED)), None, None, str(fe.binary)
        )
    compared = {}
    for ingot in LABELLED:
        if fe.run(["check"], ROOT / ingot).code != 0:
            raise SystemExit(f"{ingot} does not compile")
        listed_by_cli = sorted(where for where, _ in dimension.checklist(ROOT / ingot, None, None, str(fe.binary)).labels)
        compared[ingot] = (listed_by_cli, compiler_labels(fe, ingot))
    agree = all(cli == compiler for cli, compiler in compared.values())
    passed = re.search(r"test result: ok\. (\d+) passed; 0 failed", tested.output)
    ok_code = 0 if built.code == 0 and tested.code == 0 and passed else 1
    ok_out = built.output + tested.output
    rejected = misuse.code != 0 and "error[8-0000]" in misuse.output
    clean = not checked.failed
    # The quickstart's labels, in order: a deposit arriving, a payout and a charge.
    listed = [label for _, label in checked.labels]
    labelled = listed == ["given<USDC, In>", "owed<USDC, Out>", "owed<USDC, In>"]
    judged = [row for row in checked.rows if row[0] != "note"]
    warned = [name for status, name, _ in judged if status == "warn"]
    caught = (
        failures(unsafe_dep) == {"allow_unsafe"}
        and failures(unsafe_code) == {"unsafe code"}
        and failures(hidden) == {"unsafe code"}
        and failures(unread_feed) == {"feeds"}
    )
    claims = [
        {
            "question": "Can a new project depend on Dimension from git, and does it get Dimension's checks?",
            "holds": ok_code == 0 and rejected,
            "evidence": f"`dimension new` creates the quickstart taking Dimension at {rev[:7]} by git source; it "
            + (f"builds and passes its {passed.group(1)} tests" if ok_code == 0 else "does NOT build and pass")
            + ("; an incoming amount used as an outgoing one is rejected with 8-0000" if rejected else "; the misuse was NOT rejected"),
        },
        {
            "question": "Does `dimension check` pass that project, list its labels for review, and fail it once it can forge values Dimension trusts?",
            "holds": clean and caught and labelled,
            "evidence": f"the new project: {sum(s.strip() == 'ok' for s, _, _ in judged)} of {len(judged)} checks ok"
            + (f", warnings on {', '.join(warned)}" if warned else ", no warnings")
            + f"; its {len(listed)} labels listed for review ({', '.join(listed)}); "
            f"with allow_unsafe set on Dimension it fails {', '.join(sorted(failures(unsafe_dep))) or 'nothing'}; "
            f"with a price forged by a pointer cast, which compiles, it fails {', '.join(sorted(failures(unsafe_code))) or 'nothing'}; "
            f"with the forgery between the strings \"/*\" and \"*/\", it fails {', '.join(sorted(failures(hidden))) or 'nothing'}; "
            f"with a feed built where feed-check cannot read it, it fails {', '.join(sorted(failures(unread_feed))) or 'nothing'}",
        },
        {
            "question": "In each project compared, does `dimension check` list exactly the label calls a second compiler method finds?",
            "holds": agree,
            "evidence": "identical to the compiler's list in each of the projects compared: "
            + ", ".join(f"{ingot} {len(cli)}" + ("" if cli == compiler else f" (compiler {len(compiler)})") for ingot, (cli, compiler) in compared.items())
            + ". tests/labels writes them in every form found so far: type inferred, aliased, re-exported and renamed in another file, through an aliased module and a module path, generic in the direction, a holding and a supply, and decoys: a comment, a string, a local function sharing a label's name, and an unrelated function sharing a re-exported one",
        },
    ]
    report = {
        "schema": SCHEMA,
        "question": "Does Dimension work as a dependency of someone else's project?",
        "dependency": {"source": "this repository's git history", "rev": rev, "name": "dimension", "version": version},
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "labels": {ingot: {"cli": cli, "compiler": compiler} for ingot, (cli, compiler) in compared.items()},
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "consumer"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    if ok_code != 0:
        print(ok_out[-2000:])
    for claim in claims:
        print(f"{'holds' if claim['holds'] else 'FAILS'}  {claim['question']}\n       {claim['evidence']}")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if all(c["holds"] for c in claims) else 1


if __name__ == "__main__":
    sys.exit(main())
