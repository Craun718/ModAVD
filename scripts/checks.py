"""Public repository checks: patch replay, release metadata, byte preservation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def git(repo, *args):
    result = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.longpaths=true", "-C", str(repo), *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"git {' '.join(map(str, args[:4]))}: {result.stderr[-6000:]}")
    return result.stdout.strip()


def check_notes(notes, sums, sizes=None, source_sums=None):
    text = Path(notes).read_text(encoding="utf-8-sig")
    known = re.search(r"(?ms)^## 已知问题\s*\n(.*?)(?=^## |\Z)", text)
    if known:
        for line in known[1].splitlines():
            if line.startswith("- ") and not re.search(r"https://github\.com/ModAVD/ModAVD/issues/[1-9][0-9]*", line):
                raise ValueError("Each known issue must link to a repository issue")
    hashes = {}
    checksum_lines = Path(sums).read_text(encoding="utf-8-sig").splitlines()
    if source_sums:
        checksum_lines += Path(source_sums).read_text(encoding="utf-8-sig").splitlines()
    for line in checksum_lines:
        m = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if not m or m[2] in hashes:
            raise ValueError(f"Invalid/duplicate checksum line: {line}")
        hashes[m[2]] = m[1]
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\| `([^`]+)` \| (.+?) \| `([0-9a-f]{64})` \|", line)
        if not m:
            continue
        if m[1] in rows:
            raise ValueError(f"Duplicate notes asset: {m[1]}")
        size = re.search(r"([0-9][0-9,]*) 字节", m[2])
        if not size or int(size[1].replace(",", "")) <= 0:
            raise ValueError(f"Missing positive byte size: {m[1]}")
        n = int(size[1].replace(",", ""))
        human = re.match(r"([0-9]+\.[0-9]) (KiB|MiB)", m[2])
        if human:
            unit = 1024 if human[2] == "KiB" else 1024**2
            if f"{n/unit:.1f}" != human[1]:
                raise ValueError(f"Human-readable size disagrees with bytes: {m[1]}")
        if sizes is not None and sizes.get(m[1]) != n:
            raise ValueError(f"Actual size differs: {m[1]}")
        rows[m[1]] = m[3]
    if not hashes or rows != hashes:
        raise ValueError("Release notes asset table differs from SHA256SUMS.txt")
    print(f"Release metadata OK: {Path(notes).name}, {len(rows)} assets")


def metadata(root):
    attrs = (root / ".gitattributes").read_text(encoding="utf-8-sig")
    if not re.search(r"(?m)^\*\.patch\s+-text\s*$", attrs):
        raise ValueError(".gitattributes must include *.patch -text")
    notes = sorted((root / "release").glob("*.md"))
    if not notes:
        raise ValueError("No release notes")
    for path in notes:
        # Historical releases each keep their own original published checksums.
        assets = json.loads(path.with_suffix(".assets.json").read_text(encoding="utf-8"))
        check_notes(path, path.with_suffix(".SHA256SUMS.txt"), {name: a["bytes"] for name, a in assets.items()}, path.with_suffix(".sources.SHA256SUMS.txt"))
        # The size manifest and both checksum files must also agree, independently of notes.
        lines = path.with_suffix(".SHA256SUMS.txt").read_text().splitlines() + path.with_suffix(".sources.SHA256SUMS.txt").read_text().splitlines()
        hashes = dict((line.split("  ")[1], line.split("  ")[0]) for line in lines)
        if hashes != {name: a["sha256"] for name, a in assets.items()}:
            raise ValueError("Size manifest hashes differ from checksum files")


def replay(root, work):
    if work.exists():
        raise ValueError("Replay workspace already exists; choose a fresh directory")
    work.mkdir(parents=True)
    series = json.loads((root / "patches/series.json").read_text(encoding="utf-8"))
    base_text = (root / "patches/BASE.md").read_text(encoding="utf-8")
    summary = []
    for s in series:
        if not re.fullmatch(r"platform/[a-zA-Z0-9_/-]+", s["upstream"]) or any(not re.fullmatch(r"[0-9a-f]{40}", s[k]) for k in ["base", "head", "tree"]):
            raise ValueError("Invalid AOSP project/base")
        base_rows = [line for line in base_text.splitlines() if f"`{s['dir']}`" in line and line.startswith("|")]
        if len(base_rows) != 1 or any(value not in base_rows[0] for value in [s["base"], s["head"], s["upstream"]]):
            raise ValueError("series.json and BASE.md differ")
        if int(base_rows[0].split("|")[4].strip()) != s["count"]:
            raise ValueError("series.json and BASE.md patch counts differ")
        directory = s["dir"]
        if not re.fullmatch(r"[a-z0-9_-]+/[a-z0-9_-]+", directory):
            raise ValueError("Unsafe series directory")
        repo = work / directory.replace("/", "-")
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.name", "qiyinxi")
        git(repo, "config", "user.email", "qiyinxi@foxmail.com")
        git(repo, "config", "gc.auto", "0")
        git(repo, "fetch", "--no-tags", "--depth=1", "https://android.googlesource.com/" + s["upstream"], s["base"])
        git(repo, "checkout", "-q", "--detach", "FETCH_HEAD")
        patches = sorted((root / "patches" / directory).glob("*.patch"))
        if len(patches) != s["count"] or not patches:
            raise ValueError("Patch count differs")
        git(repo, "am", "--keep-cr", "-q", *patches)
        count = int(git(repo, "rev-list", "--count", s["base"] + "..HEAD"))
        tree = git(repo, "rev-parse", "HEAD^{tree}")
        if count != s["count"] or tree != s["tree"]:
            raise ValueError(f"Replayed count/tree differs: {directory}")
        authors = set(git(repo, "log", "--format=%an <%ae>", s["base"] + "..HEAD").splitlines())
        messages = git(repo, "log", "--format=%B", s["base"] + "..HEAD")
        if authors != {"qiyinxi <qiyinxi@foxmail.com>"} or re.search(r"(?i)co-authored-by:", messages):
            raise ValueError("Patch authors/trailers differ")
        summary.append({"series": directory, "commits": count, "tree": tree, "depth": 1})
        print(f"Clean AOSP shallow replay: {directory}: {count} patches; tree {tree}", flush=True)
    (work / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["metadata", "patches"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    args.root = args.root.resolve()
    try:
        if args.command == "metadata":
            metadata(args.root)
        else:
            if args.work is None:
                parser.error("patches requires --work (a fresh directory)")
            replay(args.root, args.work)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
