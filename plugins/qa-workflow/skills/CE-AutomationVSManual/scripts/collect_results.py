"""Collect Reqnroll/SpecFlow automation results from the Visual Studio Test Explorer store.

Visual Studio records Test Explorer runs in .vs/<solution>/v17/TestStore/<n>/*.testlog,
a MessagePack-framed binary log. Each frame is [1, seq, kind, guid, payload]:

  kind 2 = test case discovered   payload[2]=testId, payload[5]=FQN, payload[6]=display name
  kind 3 = test result            payload[2]=testId, payload[9]=outcome (1 pass, 2 fail, 3 skip)

Long strings are interned after first use: payload[5] holds either the literal FQN or an
int id, and payload[18]/payload[22] carry the id for payload[5]/payload[6]. So the literal
occurrences build an id -> string table that resolves the interned ones.

Categories (Regression_Quick etc.) are not readable from the log for interned records, so
they come from the generated *.feature.cs files, which carry both the NUnit CategoryAttribute
list and the scenario title in DescriptionAttribute.

Usage:
    python collect_results.py --repo <repo-root> [--category Regression_Quick] [--out results.json]
"""

import argparse
import glob
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

OUTCOME = {1: "Passed", 2: "Failed", 3: "Skipped"}
FRAME = b"\x95\x01\xd2"


def ensure_msgpack():
    try:
        import msgpack  # noqa: F401
    except ImportError:
        print("installing msgpack...", file=sys.stderr)
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "msgpack"], check=True)
    import msgpack
    return msgpack


def newest_testlog(repo):
    logs = glob.glob(os.path.join(repo, ".vs", "**", "TestStore", "**", "*.testlog"), recursive=True)
    if not logs:
        raise SystemExit(
            "No .testlog found under {}/.vs/**/TestStore/. Run the suite from Visual Studio "
            "Test Explorer first, or check the repo path.".format(repo)
        )
    return max(logs, key=os.path.getmtime)


def decode_frames(path, msgpack):
    """Unpack each frame independently; the log is framed, not one continuous stream."""
    data = open(path, "rb").read()
    offsets = []
    i = data.find(FRAME)
    while i != -1:
        offsets.append(i)
        i = data.find(FRAME, i + 1)
    recs = []
    for pos in offsets:
        try:
            obj = msgpack.Unpacker(
                io.BytesIO(data[pos:pos + 400000]), raw=False, strict_map_key=False
            ).unpack()
        except Exception:
            continue  # a truncated tail frame is normal; skip it
        if isinstance(obj, list) and len(obj) == 5:
            recs.append(obj)
    return recs


def last_outcome_by_fqn(recs):
    k2 = [r[4] for r in recs if r[2] == 2 and isinstance(r[4], list) and len(r[4]) > 22]
    k3 = [r[4] for r in recs if r[2] == 3 and isinstance(r[4], list) and len(r[4]) > 9]

    interned = {}
    for p in k2:
        if isinstance(p[5], str) and isinstance(p[18], int):
            interned[p[18]] = p[5]
        if isinstance(p[6], str) and isinstance(p[22], int):
            interned[p[22]] = p[6]

    id2fqn = {}
    for p in k2:
        fqn = p[5] if isinstance(p[5], str) else interned.get(p[5])
        if fqn:
            id2fqn[p[2]] = fqn

    # Frames are chronological, so the last result for a test is its current state -
    # the same thing Test Explorer shows after reruns.
    last = {}
    errors = {}
    for q in k3:
        fqn = id2fqn.get(q[2])
        if not fqn:
            continue
        last[fqn] = OUTCOME.get(q[9], str(q[9]))
        msg = q[10] if len(q) > 10 and isinstance(q[10], str) else ""
        if msg:
            errors[fqn] = msg.strip().splitlines()[0][:300]
    return last, errors


def parse_generated_tests(repo, project):
    """Map FQN -> {title, cats, feature} from the Reqnroll-generated *.feature.cs files."""
    tests = {}
    pattern = os.path.join(repo, project, "Features", "*.feature.cs")
    for path in glob.glob(pattern):
        txt = open(path, encoding="utf-8-sig", errors="replace").read()
        ns = re.search(r"namespace\s+([\w.]+)", txt)
        cls = re.search(r"public partial class (\w+)", txt)
        if not (ns and cls):
            continue
        for m in re.finditer(r"TestAttribute\(\)\](.*?)public\s+[^\n]*?\s(\w+)\s*\(", txt, re.S):
            attrs, meth = m.group(1), m.group(2)
            if "TestAttribute()" in attrs:
                continue  # overlapping match into the next test block
            desc = re.search(r'DescriptionAttribute\("([^"]*)"\)', attrs)
            tests["{}.{}.{}".format(ns.group(1), cls.group(1), meth)] = {
                "title": desc.group(1) if desc else meth,
                "cats": re.findall(r'CategoryAttribute\("([^"]*)"\)', attrs),
                "feature": os.path.basename(path)[: -len(".feature.cs")],
            }
    if not tests:
        raise SystemExit(
            "No generated tests parsed from {}. Build the project so Reqnroll "
            "regenerates *.feature.cs.".format(pattern)
        )
    return tests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--project", required=True,
                    help="Name of the test project folder holding Features/*.feature.cs")
    ap.add_argument("--category", default="Regression_Quick")
    ap.add_argument("--out", default="results.json")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    msgpack = ensure_msgpack()

    log = newest_testlog(repo)
    recs = decode_frames(log, msgpack)
    last, errors = last_outcome_by_fqn(recs)
    tests = parse_generated_tests(repo, args.project)

    rows = []
    for fqn, meta in tests.items():
        if args.category not in meta["cats"]:
            continue
        rows.append({
            "fqn": fqn,
            "feature": meta["feature"],
            "title": meta["title"],
            "status": last.get(fqn, "NotRun"),
            "error": errors.get(fqn, ""),
        })
    rows.sort(key=lambda r: (r["feature"], r["title"]))

    by_feature = defaultdict(Counter)
    for r in rows:
        by_feature[r["feature"]][r["status"]] += 1

    payload = {
        "testlog": log,
        "category": args.category,
        "counts": dict(Counter(r["status"] for r in rows)),
        "total": len(rows),
        "features": len(by_feature),
        "features_all_passed": sum(1 for c in by_feature.values() if set(c) == {"Passed"}),
        "features_with_failures": sum(1 for c in by_feature.values() if c["Failed"]),
        "results": rows,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)

    print("testlog: {}".format(log))
    print("category {}: {} tests across {} features".format(args.category, len(rows), len(by_feature)))
    print("counts: {}".format(payload["counts"]))
    print("features fully green: {}/{}".format(payload["features_all_passed"], len(by_feature)))
    print("wrote {}".format(args.out))


if __name__ == "__main__":
    main()
