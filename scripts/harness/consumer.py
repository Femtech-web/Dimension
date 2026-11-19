"""A new project, depending on Dimension the way another builder would.

Usage: python3 -m harness.consumer

Builds the quickstart (examples/quickstart) as a project outside the repository
would: a fresh ingot whose fe.toml takes Dimension from this repository's git
history at HEAD (`source` and `rev`, as for any git dependency). It must
compile and pass its tests, and a misuse must be rejected with Dimension's type
error. Writes docs/results/consumer/<platform>.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.toolchain import ROOT, resolve

SCHEMA = "dimension.consumer/v1"

QUICKSTART = ROOT / "examples" / "quickstart" / "src"

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


def project(at: Path, rev: str, sources: dict[str, str]) -> Path:
    (at / "src").mkdir(parents=True)
    (at / "fe.toml").write_text(
        '[ingot]\nname = "consumer"\nversion = "0.1.0"\n\n[dependencies]\n'
        f'dimension = {{ source = "{ROOT.as_uri()}", rev = "{rev}", name = "dimension", version = "0.1.0" }}\n'
    )
    for name, text in sources.items():
        (at / "src" / name).write_text(text)
    return at


def main() -> int:
    fe = resolve()
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    sources = {f.name: f.read_text() for f in QUICKSTART.glob("*.fe")}
    with tempfile.TemporaryDirectory(prefix="dimension-consumer-") as tmp:
        quickstart = project(Path(tmp) / "quickstart", rev, sources)
        built = fe.run(["build"], quickstart)
        tested = fe.run(["test", "--backend", "sonatina"], quickstart)
        misuse = fe.run(["check"], project(Path(tmp) / "misuse", rev, {"lib.fe": MISUSE}))
    passed = re.search(r"test result: ok\. (\d+) passed; 0 failed", tested.output)
    ok_code = 0 if built.code == 0 and tested.code == 0 and passed else 1
    ok_out = built.output + tested.output
    bad_code, bad_out = misuse.code, misuse.output
    rejected = bad_code != 0 and "error[8-0000]" in bad_out
    claims = [{
        "question": "Can a new project depend on Dimension from git, and does it get Dimension's checks?",
        "holds": ok_code == 0 and rejected,
        "evidence": f"the quickstart, as a fresh project taking Dimension at {rev[:7]} by git source, "
        + (f"builds and passes its {passed.group(1)} tests" if ok_code == 0 else "does NOT build and pass")
        + ("; an incoming amount used as an outgoing one is rejected with 8-0000" if rejected else "; the misuse was NOT rejected"),
    }]
    report = {
        "schema": SCHEMA,
        "question": "Does Dimension work as a dependency of someone else's project?",
        "dependency": {"source": "this repository's git history", "rev": rev, "name": "dimension", "version": "0.1.0"},
        "fe": {"version": fe.version, "commit": fe.commit},
        "platform": fe.platform,
        "claims": claims,
    }
    out = ROOT / "docs" / "results" / "consumer"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{fe.platform}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    if ok_code != 0:
        print(ok_out[-2000:])
    print(f"{'holds' if claims[0]['holds'] else 'FAILS'}  {claims[0]['question']}\n       {claims[0]['evidence']}")
    print(f"report: {path.relative_to(ROOT)}")
    return 0 if claims[0]["holds"] else 1


if __name__ == "__main__":
    sys.exit(main())
