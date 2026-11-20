#!/usr/bin/env python3
"""The Dimension command line: start a project, check it before deploying.

Usage:
    dimension new DIR [--rev COMMIT] [--source URL]
    dimension check [DIR] [--network base] [--rpc URL] [--fe PATH] [--strict]
    dimension feeds REGISTRY.fe [...] --network base

Install it with `pipx install "git+https://github.com/Femtech-web/Dimension#subdirectory=cli"`,
or run it from a clone as `python3 cli/dimension.py`.

`new` creates a Fe project from the quickstart, as it was at the release it
pins, with Dimension as a git dependency on that release's commit. It reads
this repository's history: the clone it runs from, or else a copy fetched
from GitHub into the user's cache, file contents only as they are read.

`check` runs the checklist from docs/guide.md ("Before production") on a
project. It fails on what would let the project forge values Dimension
trusts, or misprice them, and warns on what to review:

- the Dimension dependency is pinned to a full commit, ideally a release (warn);
- no dependency is granted `allow_unsafe` (fail): on Dimension it reaches the
  test constructors, on any other its own `unsafe` code can forge values;
- no `unsafe` code in the sources (fail): a pointer cast can forge any value;
- the Fe version is one Dimension is tested on (warn), and the project compiles (fail);
- every feed is declared in the form feed-check reads (fail), and with
  `--network` is the Chainlink feed it claims to be (fail).

It also lists every label: each call of `given`, `owed`, `held` or
`supply_of`. That is where a raw number gets its meaning, a direction or a token
held or issued, which the compiler cannot verify on its own. An amount that then
moves a holding is checked against both; the list is what a reviewer must read.

What it can, it takes from the compiler. Labels and feeds are the calls the
compiler's own index (`fe scip`) resolves to Dimension's functions, whatever
name they are made under. `unsafe` is read with Fe's lexical rules (`//`
comments, double-quoted strings; Fe has no block comments), then confirmed
against the compiler: every symbol it indexes must be code here too, and the
project must still compile with its comments blanked. A cross-check that
disagrees fails. A check that cannot run, because there is no `fe` or the
project does not compile, is a warning that says so, never a pass; `--strict`
makes every warning fail too. `make consumer` requires the labels to equal
those a second compiler method finds, in the six projects it compares.

Exits 1 if any check fails. Python 3.11+, standard library only.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import feed_check  # noqa: E402

# The clone this file is in, when it runs from one rather than installed.
CLONE = Path(__file__).resolve().parents[1]
CLONED = (CLONE / ".git").exists() and (CLONE / "ingots" / "dimension").is_dir()

SOURCE = "https://github.com/Femtech-web/Dimension"
QUICKSTART = "examples/quickstart/src"
SUPPORTED_FE = ("26.6.0", "26.7.0")
# A release counts once its commit is recorded on the line after its heading.
_RELEASE = re.compile(r"^## (\d+\.\d+\.\d+)\b[^\n]*\n\nCommit `([0-9a-f]{40})`", re.MULTILINE)
_FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def history() -> Path:
    """This repository's git history: the clone, or a cached copy of GitHub's."""
    if CLONED:
        return CLONE
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "dimension" / "repo.git"
    if (cache / "HEAD").exists():
        subprocess.run(["git", "-C", str(cache), "fetch", "--quiet", "--tags", "origin", "+refs/heads/*:refs/heads/*"],
                       capture_output=True)
    else:
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", "--bare", "--filter=blob:none", SOURCE, str(cache)],
                       capture_output=True, check=True)
    return cache


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=history(), capture_output=True, text=True, check=True).stdout


def releases() -> dict[str, str]:
    """Release commit -> version, from the changelog, newest first."""
    text = (CLONE / "CHANGELOG.md").read_text() if CLONED else git("show", "HEAD:CHANGELOG.md")
    return {commit: version for version, commit in _RELEASE.findall(text)}


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
    version = tomllib.loads(git("show", f"{commit}:ingots/dimension/fe.toml"))["ingot"]["version"]
    (target / "fe.toml").write_text(
        f'[ingot]\nname = "{name}"\nversion = "0.1.0"\n\n'
        "# Fe resolves `rev` as a full commit hash. Move to a new release only after\n"
        "# reading its changelog entry.\n"
        "[dependencies.dimension]\n"
        f'source = "{source}"\nrev = "{commit}"{label}\nname = "dimension"\nversion = "{version}"\n'
    )
    print(f"created {target} from the quickstart at {commit[:7]}{label.replace('   #', ',')}")
    print(f"next:   cd {target} && fe test")
    print(f"before deploying:   {f'python3 {Path(__file__).resolve()}' if CLONED else 'dimension'} check {target}")
    return 0


class Checklist:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []
        self.labels: list[tuple[str, str]] = []

    def add(self, status: str, name: str, detail: str) -> None:
        self.rows.append((status, name, detail))

    @property
    def failed(self) -> bool:
        return any(status == "FAIL" for status, _, _ in self.rows)


def find_fe(explicit: str | None) -> str | None:
    if explicit:
        # A path is relative to where the command runs, not to the project; a bare name is looked up on PATH.
        found = str(Path(explicit).resolve()) if "/" in explicit else shutil.which(explicit)
        if not found or not Path(found).is_file():
            raise SystemExit(f"--fe {explicit}: no fe binary there")
        return found
    if found := shutil.which("fe"):
        return found
    if not CLONED:
        return None
    lock = CLONE / "scripts" / "toolchain" / "fe.lock"
    version = re.search(r"^version=(\S+)", lock.read_text(), re.MULTILINE) if lock.exists() else None
    if version and (CLONE / ".tools" / f"fe-{version[1]}" / "fe").exists():
        return str(CLONE / ".tools" / f"fe-{version[1]}" / "fe")
    installed = sorted(CLONE.glob(".tools/fe-*/fe"))
    return str(installed[0]) if installed else None


def scip(fe: str, project: Path) -> dict[str, list[tuple[int, int, int, str, int]]] | None:
    """The compiler's own index of the project (`fe scip`): for each source, every
    symbol occurrence as (line, start, end, symbol, roles), names resolved through
    imports, aliases and re-exports. None if the index cannot be built."""
    with tempfile.TemporaryDirectory(prefix="dimension-scip-") as tmp:
        out = Path(tmp) / "index.scip"
        built = subprocess.run([fe, "scip", str(project), "-o", str(out)], capture_output=True, text=True)
        if built.returncode != 0 or not out.exists():
            return None
        data = out.read_bytes()

    def varint(b: bytes, i: int) -> tuple[int, int]:
        n = shift = 0
        while True:
            x = b[i]
            i, n, shift = i + 1, n | (x & 0x7F) << shift, shift + 7
            if x < 0x80:
                return n, i

    def fields(b: bytes):
        i = 0
        while i < len(b):
            key, i = varint(b, i)
            field, wire = key >> 3, key & 7
            if wire == 0:
                value, i = varint(b, i)
            elif wire == 2:
                size, i = varint(b, i)
                value, i = b[i : i + size], i + size
            elif wire in (1, 5):
                value, i = b[i : i + (8 if wire == 1 else 4)], i + (8 if wire == 1 else 4)
            else:
                raise ValueError(f"unknown protobuf wire type {wire}")
            yield field, wire, value

    def packed(b: bytes) -> list[int]:
        out, i = [], 0
        while i < len(b):
            v, i = varint(b, i)
            out.append(v)
        return out

    index: dict[str, list[tuple[int, int, int, str, int]]] = {}
    for field, _, document in fields(data):
        if field != 2:
            continue
        path, occurrences = "", []
        for f, _, value in fields(document):
            if f == 1:
                path = value.decode()
            elif f == 2:
                where, symbol, roles = [], "", 0
                for g, wire, item in fields(value):
                    if g == 1:
                        where = packed(item) if wire == 2 else [item]
                    elif g == 2:
                        symbol = item.decode()
                    elif g == 3:
                        roles = item
                # A token spans one line; a longer range is code a macro such as
                # `#[error]` generated, which no one wrote.
                if len(where) == 3:
                    occurrences.append((where[0], where[1], where[2], symbol, roles))
        index[path] = occurrences
    return index


def offset(text: str, line: int, column: int, width: int = 0) -> int:
    """Where a (line, column) of the compiler's index falls in `text`. Columns may
    count characters, UTF-8 bytes or UTF-16 units; the reading that lands on an
    identifier of the occurrence's `width` is used."""
    lines = text.split("\n")
    start = sum(len(l) + 1 for l in lines[:line])
    here = lines[line] if line < len(lines) else ""
    candidates = [column]
    for encoding in ("utf-8", "utf-16-le"):
        unit = 1 if encoding == "utf-8" else 2
        raw = here.encode(encoding)
        candidates.append(len(raw[: column * unit].decode(encoding, "ignore")))
    for c in candidates:
        if width == 0 or re.fullmatch(r"[A-Za-z_]\w*", here[c : c + width]):
            return start + c
    return start + column


def use_items(code: str) -> list[tuple[int, int]]:
    """The span of every `use` item in code whose comments and strings are blanked."""
    spans = []
    for m in re.finditer(r"(?m)^[ \t]*(?:pub[ \t]*(?:\([^)\n]*\))?[ \t]+)?use\b", code):
        depth, i = 0, m.end()
        while i < len(code) and not (code[i] == "\n" and depth == 0):
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        spans.append((m.start(), i))
    return spans


_LABELLING = re.compile(r"^fe fe dimension \S+ lib/value/(given|owed|held|supply_of)\.$")
_FEED = re.compile(r"^fe fe dimension \S+ lib/value/oracle/feed\.$")


def compiled_without_comments(fe: str, project: Path, sources: list[Path]) -> bool:
    """Builds a copy of the project with every comment, as `fe_code` reads it,
    blanked. Had it mistaken where a string ends, code after a `//` inside the
    string would be blanked with it, and the copy would not compile like the
    original. Strings stay as they are: some, such as `sol(...)` selectors, are
    read by the compiler."""
    with tempfile.TemporaryDirectory(prefix="dimension-code-") as tmp:
        copy = Path(tmp).resolve() / project.resolve().name
        shutil.copytree(project, copy, ignore=shutil.ignore_patterns("out", ".git"))
        manifest = (copy / "fe.toml").read_text()
        moved = lambda m: f'path = "{os.path.relpath((project / m.group(1)).resolve(), copy)}"'
        (copy / "fe.toml").write_text(re.sub(r'path\s*=\s*"([^"]*)"', moved, manifest))
        for path in sources:
            text = path.read_text()
            code, _ = feed_check.fe_code(text)
            strings = [(m.start(), m.end()) for m in re.finditer(r'"[^"]*"', code)]
            kept = list(code)
            for start, end in strings:
                kept[start:end] = text[start:end]
            (copy / path.relative_to(project)).write_text("".join(kept))
        return subprocess.run([fe, "check"], cwd=copy, capture_output=True, text=True).returncode == 0


def checklist(project: Path, network: str | None, rpc: str | None, fe_path: str | None) -> Checklist:
    rows = Checklist()
    manifest = project / "fe.toml"
    if not manifest.exists():
        raise SystemExit(f"{project}: no fe.toml")
    deps = tomllib.loads(manifest.read_text()).get("dependencies", {})
    dep = deps.get("dimension")
    if not isinstance(dep, dict):
        raise SystemExit(f"{manifest}: no Dimension dependency")

    try:
        known = releases()
    except (OSError, subprocess.CalledProcessError):
        known = None
    rev = dep.get("rev", "")
    if "path" in dep:
        rows.add("warn", "pinned", f"a path dependency ({dep['path']}): pin a release commit before deploying")
    elif not _FULL_COMMIT.match(rev):
        rows.add("warn", "pinned", f"rev {rev!r} is not a full commit hash")
    elif known is None:
        rows.add("warn", "pinned", f"{rev[:7]}: the release list could not be read from {SOURCE}")
    elif rev in known:
        rows.add("ok  ", "pinned", f"release v{known[rev]} ({rev[:7]})")
    else:
        rows.add("warn", "pinned", f"{rev[:7]} is not a release commit; releases are listed in the changelog")

    granted = sorted(name for name, d in deps.items() if isinstance(d, dict) and d.get("allow_unsafe"))
    if granted:
        rows.add(
            "FAIL",
            "allow_unsafe",
            f"granted to {', '.join(granted)}: "
            + ("Dimension's test constructors forge prices and rates" if "dimension" in granted else "")
            + ("; " if "dimension" in granted and len(granted) > 1 else "")
            + ("a dependency's own unsafe code can forge any value" if set(granted) - {"dimension"} else "")
            + ". Keep it to test roots",
        )
    else:
        rows.add("ok  ", "allow_unsafe", "granted to none of the dependencies")

    sources = sorted((project / "src").rglob("*.fe"))
    texts = {path: path.read_text() for path in sources}
    codes = {path: feed_check.fe_code(text) for path, text in texts.items()}
    fe = find_fe(fe_path)
    compiled = None
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
    index = scip(fe, project) if compiled is not None and compiled.returncode == 0 else None

    # Unsafe code: read with Fe's own lexical rules, then held to the compiler twice.
    # A disagreement with the compiler fails; a check the compiler cannot run is a warning, never a pass.
    unreadable = [f"{path.relative_to(project)}: {problem}" for path, (_, problems) in codes.items() for problem in problems]
    if index is not None:
        for path, text in texts.items():
            code = codes[path][0]
            for line, start, end, symbol, _ in index.get(str(path.relative_to(project)), []):
                at = offset(text, line, start, end - start)
                if not re.fullmatch(r"[A-Za-z_]\w*", text[at : at + end - start]):
                    continue
                if code[at : at + end - start] != text[at : at + end - start]:
                    unreadable.append(f"{path.relative_to(project)}:{line + 1}: the compiler sees code that dimension check read as a string or comment")
                    break
        if not unreadable and not compiled_without_comments(fe, project, sources):
            unreadable.append("with its comments blanked as dimension check reads them, the project no longer compiles")
    unsafe = [
        f"{path.relative_to(project)}:{code.count(chr(10), 0, m.start()) + 1}"
        for path, (code, _) in codes.items()
        for m in re.finditer(r"\bunsafe\b", code)
    ]
    if unsafe:
        rows.add("FAIL", "unsafe code", f"{', '.join(unsafe[:5])}: unsafe code can forge any value Dimension trusts")
    elif unreadable:
        rows.add("FAIL", "unsafe code", f"cannot be confirmed: {'; '.join(unreadable[:3])}")
    elif index is None:
        rows.add("warn", "unsafe code", f"none found in {len(sources)} source files, but not confirmed by the compiler: it must compile")
    else:
        rows.add("ok  ", "unsafe code", f"none in {len(sources)} source files, confirmed against the compiler")

    # Labels and feeds: every call the compiler resolves to Dimension's, whatever name it is made under.
    feed_sites: list[tuple[Path, int]] = []
    if index is None:
        rows.add("warn", "labels", "not listed: the project must compile for the compiler to resolve them")
    else:
        for path, text in texts.items():
            code = codes[path][0]
            spans = use_items(code)
            for line, start, end, symbol, roles in index.get(str(path.relative_to(project)), []):
                at = offset(text, line, start, end - start)
                if roles & 1 or any(a <= at < b for a, b in spans):
                    continue
                if _FEED.match(symbol):
                    feed_sites.append((path, line + 1))
                    continue
                target = _LABELLING.match(symbol)
                if not target:
                    continue
                name, i = text[at : at + end - start], at + end - start
                while i < len(code) and code[i].isspace():
                    i += 1
                generics = ""
                if code.startswith("<", i):
                    depth, j = 0, i
                    while j < len(code):
                        depth += {"<": 1, ">": -1}.get(code[j], 0)
                        if depth == 0:
                            break
                        j += 1
                    generics = re.sub(r"\s+", " ", text[i : j + 1]).replace("< ", "<").replace(" >", ">").replace(",>", ">")
                label = target.group(1) + (generics or " (type inferred)") + ("" if name == target.group(1) else f" as {name}")
                rows.labels.append((f"{path.relative_to(project)}:{line + 1}", label))
        rows.labels.sort(key=lambda site: (site[0].rsplit(":", 1)[0], int(site[0].rsplit(":", 1)[1])))
        rows.add(
            "note",
            "labels",
            f"{len(rows.labels)} place{'' if len(rows.labels) == 1 else 's'} a raw number gets its meaning, as the compiler resolves them, listed below: review each"
            if rows.labels
            else "no raw number gets its meaning here",
        )

    declared = {}
    for path in {path for path, _ in feed_sites}:
        try:
            declared[path] = feed_check.declarations(path)
        except SystemExit as unread:
            declared[path] = []
    unreadable_feeds = [
        f"{path.relative_to(project)}:{line}"
        for path, line in feed_sites
        if not any(int(d.source.rsplit(":", 1)[1]) == line for d in declared[path])
    ]
    if index is None:
        rows.add("warn", "feeds", "not checked: the project must compile for the compiler to find every feed")
    elif unreadable_feeds:
        rows.add("FAIL", "feeds", f"{', '.join(unreadable_feeds)}: declare each feed as `pub const N: Feed<B, Q> = feed(...)`, the form feed-check reads")
    elif not feed_sites:
        rows.add("ok  ", "feeds", "no feed declarations")
    elif not network and not rpc:
        rows.add("warn", "feeds", f"{len(feed_sites)} feeds declared, not checked: pass --network")
    else:
        result = feed_check.run(sorted(declared), network, rpc, None, {})
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


def check(project: Path, network: str | None, rpc: str | None, fe_path: str | None, strict: bool = False) -> int:
    rows = checklist(project, network, rpc, fe_path)
    print(f"dimension check {project}")
    for status, name, detail in rows.rows:
        print(f"  {status}  {name:<13} {detail}")
    if rows.labels:
        width = max(len(where) for where, _ in rows.labels)
        print("\n  labels to review (an amount that moves a holding is also checked against it):")
        for where, label in rows.labels:
            print(f"    {where:<{width}}  {label}")
    warned = any(status == "warn" for status, _, _ in rows.rows)
    return 1 if rows.failed or (strict and warned) else 0


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
    p_check.add_argument("--strict", action="store_true", help="exit 1 on any warning too, such as a check that could not run")
    commands.add_parser("feeds", help="check feed declarations against Chainlink's directory and the chain", add_help=False)
    args, rest = parser.parse_known_args(argv)
    if args.command == "feeds":
        return feed_check.main(rest, prog="dimension feeds")
    if rest:
        parser.error(f"unrecognized arguments: {' '.join(rest)}")
    if args.command == "new":
        return new(args.dir, args.rev, args.source)
    return check(args.dir, args.network, args.rpc, args.fe, args.strict)


if __name__ == "__main__":
    sys.exit(main())
