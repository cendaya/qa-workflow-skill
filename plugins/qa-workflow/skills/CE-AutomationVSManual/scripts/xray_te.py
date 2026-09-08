"""Xray Cloud helper: read a Test Execution's runs, and mark runs PASSED.

Auth comes from XRAY_CLIENT_ID / XRAY_CLIENT_SECRET. The bearer token is held in memory
only and never printed - it grants write access to test results.

By design this script can only write PASSED. Marking a case FAILED from an automation
failure would put script flakiness into the official QA record, so failures are reported
for a human instead.

Usage:
    python xray_te.py runs PROJ-9896 --out runs.json
    python xray_te.py pass --runs runs.json --keys pass_keys.txt [--dry-run]

pass_keys.txt is one TE case key per line; blank lines and #comments are ignored.
"""

import argparse
import json
import os
import sys
import urllib.request

BASE = "https://xray.cloud.getxray.app/api/v2"
PAGE = 100


def post(url, payload, token=None):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def authenticate():
    cid = os.environ.get("XRAY_CLIENT_ID")
    secret = os.environ.get("XRAY_CLIENT_SECRET")
    if not (cid and secret):
        raise SystemExit(
            "XRAY_CLIENT_ID and XRAY_CLIENT_SECRET must be set in the environment "
            "(see ~/.claude/settings.json 'env')."
        )
    token = post(BASE + "/authenticate", {"client_id": cid, "client_secret": secret})
    if not isinstance(token, str):
        raise SystemExit("Xray authentication failed.")
    return token


def graphql(token, query):
    out = post(BASE + "/graphql", {"query": query}, token)
    if "errors" in out:
        raise SystemExit("Xray GraphQL error: {}".format(out["errors"]))
    return out["data"]


def resolve_exec_id(token, key):
    q = '{ getTestExecutions(jql: "key = %s", limit: 1) { results { issueId } } }' % key
    results = graphql(token, q)["getTestExecutions"]["results"]
    if not results:
        raise SystemExit("Test Execution {} not found (or not visible to this Xray client).".format(key))
    return results[0]["issueId"]


def fetch_runs(token, exec_id):
    runs, start, total = {}, 0, None
    while total is None or start < total:
        q = (
            '{ getTestRuns(testExecIssueIds: ["%s"], limit: %d, start: %d) '
            '{ total results { id status { name } test { jira(fields: ["key"]) } } } }'
            % (exec_id, PAGE, start)
        )
        tr = graphql(token, q)["getTestRuns"]
        total = tr["total"]
        for r in tr["results"]:
            runs[r["test"]["jira"]["key"]] = [r["id"], r["status"]["name"]]
        if not tr["results"]:
            break
        start += PAGE
    return runs, total


def cmd_runs(args):
    token = authenticate()
    exec_id = resolve_exec_id(token, args.key)
    runs, total = fetch_runs(token, exec_id)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(runs, fh, indent=1)
    tally = {}
    for _, status in runs.values():
        tally[status] = tally.get(status, 0) + 1
    print("{} (issueId {}): {} test runs".format(args.key, exec_id, total))
    print("current statuses: {}".format(tally))
    print("wrote {}".format(args.out))


def cmd_pass(args):
    runs = json.load(open(args.runs, encoding="utf-8"))
    keys = [
        ln.strip()
        for ln in open(args.keys, encoding="utf-8")
        if ln.strip() and not ln.strip().startswith("#")
    ]

    missing = [k for k in keys if k not in runs]
    already = [k for k in keys if k in runs and runs[k][1] == "PASSED"]
    other = [k for k in keys if k in runs and runs[k][1] not in ("TO DO", "PASSED")]
    todo = [k for k in keys if k in runs and runs[k][1] == "TO DO"]

    if missing:
        print("not in this Test Execution ({}): {}".format(len(missing), ", ".join(missing)))
    if already:
        print("already PASSED, untouched ({})".format(len(already)))
    if other:
        print("skipped, unexpected status ({}): {}".format(
            len(other), ", ".join("{}={}".format(k, runs[k][1]) for k in other)))
    print("to flip TO DO -> PASSED: {}".format(len(todo)))

    if args.dry_run:
        print("\n--dry-run, nothing written:")
        for k in todo:
            print("  " + k)
        return

    token = authenticate()
    ok, failed = [], []
    for k in todo:
        run_id = runs[k][0]
        q = 'mutation { updateTestRunStatus(id: "%s", status: "PASSED") }' % run_id
        try:
            graphql(token, q)
            ok.append(k)
            print("PASSED {}".format(k))
        except SystemExit as exc:
            failed.append((k, str(exc)))
            print("ERROR  {}: {}".format(k, exc), file=sys.stderr)
    print("\nwrote {} PASSED, {} errors".format(len(ok), len(failed)))
    if failed:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_runs = sub.add_parser("runs", help="fetch all test runs for a Test Execution")
    p_runs.add_argument("key", help="Test Execution key, e.g. PROJ-9896")
    p_runs.add_argument("--out", default="runs.json")
    p_runs.set_defaults(func=cmd_runs)

    p_pass = sub.add_parser("pass", help="mark listed cases PASSED (TO DO only)")
    p_pass.add_argument("--runs", required=True)
    p_pass.add_argument("--keys", required=True)
    p_pass.add_argument("--dry-run", action="store_true")
    p_pass.set_defaults(func=cmd_pass)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
