#!/usr/bin/env python3
"""The Dimension command line: start a project, check it before deploying.

Usage:
    python3 cli/dimension.py new DIR [--rev COMMIT] [--source URL]
    python3 cli/dimension.py check [DIR] [--network base] [--rpc URL] [--fe PATH]
    python3 cli/dimension.py feeds REGISTRY.fe [...] --network base

`new` creates a Fe project from the quickstart, as it was at the release it
pins, with Dimension as a git dependency on that release's commit. Run it from
a clone of this repository.

`check` runs the checklist from docs/guide.md ("Before production") on a
project. It fails on what would let the project forge values Dimension
trusts, or misprice them, and warns on what to review:

- the Dimension dependency is pinned to a full commit, ideally a release (warn);
- `allow_unsafe` is not set on it (fail): it lets the ingot forge prices and rates;
- no `unsafe` code in the sources (fail): a pointer cast can forge any value;
- the Fe version is one Dimension is tested on (warn), and the project compiles (fail);
- every Chainlink feed it declares is the feed it claims to be (fail), with `--network`.

Exits 1 if any check fails. Python 3.11+, standard library only.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import feed_check  # noqa: E402

SOURCE = "https://github.com/Femtech-web/Dimension"
QUICKSTART = "examples/quickstart/src"
SUPPORTED_FE = ("26.6.0", "26.7.0")
_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+)\b.*?\n\nCommit `([0-9a-f]{40})`", re.MULTILINE | re.DOTALL)
_FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_UNSAFE = re.compile(r"\bunsafe\b")


def releases() -> dict[str, str]:
    """Release commit -> version, from the changelog, newest first."""
    text = (REPO / "CHANGELOG.md").read_text()
    return {commit: version for version, commit in _RELEASE.findall(text)}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def new(target: Path, rev: str | None, source: str) -> int:
    known = releases()
    rev = rev or next(iter(known))
    commit = git("rev-parse", f"{rev}^{{commit}}").strip()
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} exists and is not empty")
    name = re.sub(r"[^a-z0-9_]", "_", target.resolve().name.lower()).strip("_") or "protocol"
    files = [f for f in git("ls-tree", "--name-only", f"{commit}:{QUICKSTART}").split() if f.endswith(".fe")]
    (target / "src").mkdir(parents=True, exist_ok=True)
    for f in files:
        (target / "src" / f).write_text(git("show", f"{commit}:{QUICKSTART}/{f}"))
    label = f"   # v{known[commit]}" if commit in known else ""
    version = known.get(commit, next(iter(known.values())))
    (target / "fe.toml").write_text(
        f'[ingot]\nname = "{name}"\nversion = "0.1.0"\n\n'
        "# Fe resolves `rev` as a full commit hash. Move to a new release only after\n"
        "# reading its changelog entry.\n"
        "[dependencies.dimension]\n"
        f'source = "{source}"\nrev = "{commit}"{label}\nname = "dimension"\nversion = "{version}"\n'
    )
    print(f"created {target} from the quickstart at {commit[:7]}{label.replace('   #', ',')}")
    print(f"next:   cd {target} && fe test")
    print(f"before deploying:   python3 {Path(__file__).resolve()} check {target}")
    return 0


class Checklist:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str) -> None:
        self.rows.append((status, name, detail))

    @property
    def failed(self) -> bool:
        return any(status == "FAIL" for status, _, _ in self.rows)


def find_fe(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if found := shutil.which("fe"):
        return found
    pinned = sorted(REPO.glob(".tools/fe-*/fe"))
    return str(pinned[-1]) if pinned else None


def without_comments(text: str) -> str:
    return re.sub(r"//[^\n]*", "", text)


def checklist(project: Path, network: str | None, rpc: str | None, fe_path: str | None) -> Checklist:
    rows = Checklist()
    manifest = project / "fe.toml"
    if not manifest.exists():
        raise SystemExit(f"{project}: no fe.toml")
    dep = tomllib.loads(manifest.read_text()).get("dependencies", {}).get("dimension")
    if not isinstance(dep, dict):
        raise SystemExit(f"{manifest}: no Dimension dependency")

    known = releases()
    rev = dep.get("rev", "")
    if "path" in dep:
        rows.add("warn", "pinned", f"a path dependency ({dep['path']}): pin a release commit before deploying")
    elif not _FULL_COMMIT.match(rev):
        rows.add("warn", "pinned", f"rev {rev!r} is not a full commit hash")
    elif rev in known:
        rows.add("ok  ", "pinned", f"release v{known[rev]} ({rev[:7]})")
    else:
        rows.add("warn", "pinned", f"{rev[:7]} is not a release commit; releases are listed in the changelog")

    if dep.get("allow_unsafe"):
        rows.add("FAIL", "allow_unsafe", "set on Dimension: this ingot can forge prices and rates. Keep it to test roots")
    else:
        rows.add("ok  ", "allow_unsafe", "not set on Dimension")

    sources = sorted((project / "src").rglob("*.fe"))
    unsafe = [
        f"{path.relative_to(project)}:{i}"
        for path in sources
        for i, line in enumerate(without_comments(path.read_text()).splitlines(), 1)
        if _UNSAFE.search(line)
    ]
    if unsafe:
        rows.add("FAIL", "unsafe code", f"{', '.join(unsafe[:5])}: unsafe code can forge any value Dimension trusts")
    else:
        rows.add("ok  ", "unsafe code", f"none in {len(sources)} source files")

    fe = find_fe(fe_path)
    if fe is None:
        rows.add("warn", "fe", "no fe on PATH; pass --fe")
    else:
        reported = subprocess.run([fe, "--version"], capture_output=True, text=True).stdout.strip()
        version = (re.search(r"\d+\.\d+\.\d+", reported) or [""])[0]
        rows.add(
            "ok  " if version in SUPPORTED_FE else "warn",
            "fe version",
            f"{reported}" + ("" if version in SUPPORTED_FE else f"; Dimension is tested on {', '.join(SUPPORTED_FE)}"),
        )
        compiled = subprocess.run([fe, "check"], cwd=project, capture_output=True, text=True)
        output = (compiled.stdout + compiled.stderr).strip()
        error = re.search(r"^error\[[0-9-]+\]:.*$", output, re.MULTILINE)
        rows.add(
            "ok  " if compiled.returncode == 0 else "FAIL",
            "compiles",
            "fe check passes, with every Dimension rule" if compiled.returncode == 0 else (error[0] if error else output[-200:]),
        )

    declaring = [path for path in sources if feed_check._DECLARED.search(path.read_text())]
    if not declaring:
        rows.add("ok  ", "feeds", "no feed declarations")
    elif not network and not rpc:
        files = f"{len(declaring)} file{'' if len(declaring) == 1 else 's'}"
        rows.add("warn", "feeds", f"feeds declared in {files}, not checked: pass --network")
    else:
        result = feed_check.run(declaring, network, rpc, None, {})
        wrong = [f for f in result["feeds"] if not f["ok"]]
        rows.add(
            "FAIL" if wrong else "ok  ",
            "feeds",
            "; ".join(
                f"{f['name']}: {', '.join(c['detail'] for c in f['checks'] if not c['ok'])}"
                + (f". {f['suggestion']}" if f["suggestion"] else "")
                for f in wrong
            )
            or f"{len(result['feeds'])} feeds match Chainlink's directory and the chain at block {result['chain']['block']:,}",
        )

    return rows


def check(project: Path, network: str | None, rpc: str | None, fe_path: str | None) -> int:
    rows = checklist(project, network, rpc, fe_path)
    print(f"dimension check {project}")
    for status, name, detail in rows.rows:
        print(f"  {status}  {name:<13} {detail}")
    return 1 if rows.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dimension", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    p_new = commands.add_parser("new", help="create a project from the quickstart, pinned to a release")
    p_new.add_argument("dir", type=Path)
    p_new.add_argument("--rev", help="a commit of this repository (default: the latest release)")
    p_new.add_argument("--source", default=SOURCE, help="the git URL the dependency names")
    p_check = commands.add_parser("check", help="the checklist before deploying a project")
    p_check.add_argument("dir", type=Path, nargs="?", default=Path("."))
    p_check.add_argument("--network", choices=sorted(feed_check.NETWORKS), help="also check declared feeds")
    p_check.add_argument("--rpc", help="JSON-RPC URL for the feed check")
    p_check.add_argument("--fe", help="the fe binary (default: fe on PATH)")
    commands.add_parser("feeds", help="check feed declarations against Chainlink's directory and the chain", add_help=False)
    args, rest = parser.parse_known_args(argv)
    if args.command == "feeds":
        return feed_check.main(rest, prog="dimension feeds")
    if rest:
        parser.error(f"unrecognized arguments: {' '.join(rest)}")
    if args.command == "new":
        return new(args.dir, args.rev, args.source)
    return check(args.dir, args.network, args.rpc, args.fe)


if __name__ == "__main__":
    sys.exit(main())
