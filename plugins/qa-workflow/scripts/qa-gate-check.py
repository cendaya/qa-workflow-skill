#!/usr/bin/env python
"""Mechanical publish-gate checker for the QA workflow.

Ships with the qa-workflow plugin and reads its settings from
~/.claude/qa-config.json (copy plugins/qa-workflow/qa-config.example.json there).

Runs the checks in ../references/qa-publish-gate.md (relative to this script) that
can be decided by comparing artefacts rather than by judgement, and prints one
PASS / FAIL / MANUAL line per check.

Usage:
  python qa-gate-check.py <TICKET> <TE_KEY>
  python qa-gate-check.py PROJ-1032 PROJ-1109 --story-comment story.md --te-comment te.md
  python qa-gate-check.py PROJ-1032 PROJ-1109 --json

Options:
  --story-comment <file>  Text of the comment posted on the story. Without it the
                          checks that read the story comment report MANUAL.
  --te-comment <file>     Text of the comment posted on the Test Execution.
  --approved <file>       The working <TICKET>.md written before anything reached
                          Xray. Used as the prior record for the ratchet check.
  --json                  Machine-readable output instead of the table.

Exit codes:
  0  every check PASS
  1  at least one check FAIL
  2  no FAIL, but at least one check could not be decided (MANUAL)
  3  could not talk to Xray / bad input

Credentials are read from the environment variables *named* in qa-config.json
(xray.client_id_env_var / xray.client_secret_env_var) - the same place
xray-graphql.py, its sibling in this scripts/ directory, reads them. No secret
is ever stored in the config file. Nothing is written anywhere: this script is
read-only by construction.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".claude", "qa-config.json")
SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
DEFAULT_XRAY_API_BASE = "https://xray.cloud.getxray.app/api/v2"

LEGAL_ORACLES = ("ac", "prior-behaviour", "risk")
ERROR_PREFIXES = ("ENV —", "SETUP —", "UPSTREAM —")
RISK_PREFIX = "RISK —"

# Sections every Test Execution description must carry.
REQUIRED_TE_SECTIONS = (
    "Summary",
    "Context",
    "Acceptance criteria",
    "Environment",
    "Test cases in this execution",
    "Risk findings",
    "Other information",
    "Observations for dev",
    "Open questions for product",
    "Testing checklist",
)

# Anything matching these in a description or step is a leaked credential.
SECRET_PATTERNS = (
    re.compile(r"\bapi[_-]?key\s*[=:]\s*\S+", re.I),
    re.compile(r"\bpassword\s*[=:]\s*\S+", re.I),
    re.compile(r"\b(bearer|token)\s*[=:]\s*\S{12,}", re.I),
    re.compile(r"\bconnection\s*string\s*[=:]", re.I),
)


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

class ConfigError(RuntimeError):
    """~/.claude/qa-config.json is missing, malformed or incomplete."""


_CONFIG = None


def config():
    """Load ~/.claude/qa-config.json once, lazily."""
    global _CONFIG
    if _CONFIG is None:
        if not os.path.exists(CONFIG_PATH):
            raise ConfigError(
                "no config file at {}. Copy qa-config.example.json from the "
                "qa-workflow plugin to that path and fill in your own values."
                .format(CONFIG_PATH))
        try:
            with open(CONFIG_PATH, encoding="utf-8") as fh:
                _CONFIG = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ConfigError("could not read {}: {}".format(CONFIG_PATH, exc))
    return _CONFIG


def cfg(path, default=None, required=False):
    """Dotted lookup into qa-config.json, e.g. cfg("jira.project_key")."""
    node = config()
    for part in path.split("."):
        if not isinstance(node, dict) or node.get(part) is None:
            if required:
                raise ConfigError("{} does not define '{}'".format(CONFIG_PATH, path))
            return default
        node = node[part]
    return node


def env_value(name):
    """Environment first, then the 'env' blocks of ~/.claude/settings.json."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            settings = json.load(fh)
    except (OSError, ValueError):
        return None
    value = (settings.get("env") or {}).get(name)
    if value:
        return value
    for server in (settings.get("mcpServers") or {}).values():
        value = ((server or {}).get("env") or {}).get(name)
        if value:
            return value
    return None


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

def xray_urls():
    base = cfg("xray.api_base", DEFAULT_XRAY_API_BASE).rstrip("/")
    return base + "/authenticate", base + "/graphql"


def creds():
    id_var = cfg("xray.client_id_env_var", "XRAY_CLIENT_ID")
    secret_var = cfg("xray.client_secret_env_var", "XRAY_CLIENT_SECRET")
    cid, secret = env_value(id_var), env_value(secret_var)
    if not (cid and secret):
        raise ConfigError(
            "{} and {} must be set in the environment (or in ~/.claude/settings.json "
            "under 'env'). qa-config.json holds only the variable names."
            .format(id_var, secret_var))
    return cid, secret


def post(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode()


class Xray:
    def __init__(self):
        auth_url, self.gql_url = xray_urls()
        cid, secret = creds()
        self.token = post(auth_url, {"client_id": cid, "client_secret": secret}).strip().strip('"')

    def query(self, gql):
        body = post(self.gql_url, {"query": gql}, self.token)
        data = json.loads(body)
        if "errors" in data:
            raise RuntimeError(json.dumps(data["errors"])[:400])
        return data["data"]


# --------------------------------------------------------------------------
# result model
# --------------------------------------------------------------------------

class Results:
    def __init__(self):
        self.rows = []

    def add(self, check, verdict, detail):
        self.rows.append({"check": check, "verdict": verdict, "detail": detail})

    def passed(self, check, detail=""):
        self.add(check, "PASS", detail)

    def failed(self, check, detail):
        self.add(check, "FAIL", detail)

    def manual(self, check, detail):
        self.add(check, "MANUAL", detail)

    def exit_code(self):
        if any(r["verdict"] == "FAIL" for r in self.rows):
            return 1
        if any(r["verdict"] == "MANUAL" for r in self.rows):
            return 2
        return 0

    def render(self):
        width = max(len(r["check"]) for r in self.rows)
        icon = {"PASS": "PASS  ", "FAIL": "FAIL  ", "MANUAL": "MANUAL"}
        out = []
        for r in self.rows:
            out.append("{}  {}  {}".format(icon[r["verdict"]], r["check"].ljust(width), r["detail"]))
        counts = {v: sum(1 for r in self.rows if r["verdict"] == v) for v in ("PASS", "FAIL", "MANUAL")}
        out.append("")
        out.append("{} pass · {} fail · {} manual".format(counts["PASS"], counts["FAIL"], counts["MANUAL"]))
        if counts["FAIL"]:
            out.append("Gate FAILED — fix before recording, posting or transitioning.")
        elif counts["MANUAL"]:
            out.append("Gate INCOMPLETE — the MANUAL rows were not decided by this script.")
        else:
            out.append("Gate passed.")
        return "\n".join(out)


# --------------------------------------------------------------------------
# parsing helpers
# --------------------------------------------------------------------------

def strip_html(text):
    """Descriptions come back as HTML or wiki markup depending on how they were set."""
    text = re.sub(r"<br\s*/?>", "\n", text or "")
    text = re.sub(r"</(p|h[1-6]|li|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return (text.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&amp;", "&").replace("&nbsp;", " "))


def parse_table_rows(text):
    """Every pipe-table row in the text, as lists of trimmed cells."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if line.startswith("||"):
            # Jira wiki markup header row: ||Key||Scenario||Covers||
            cells = [c.strip() for c in line.strip("|").split("||")]
        else:
            if not line.endswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue  # separator row
        rows.append(cells)
    return rows


def section(text, heading):
    """The body of one section, up to the next heading of any level.

    Accepts markdown (`### Heading`), Jira wiki markup (`h3. Heading`) and a bold
    line (`**Heading**`), and tolerates a trailing clause on the heading itself —
    "Observations for dev - outside this ticket's scope" is the same section as
    "Observations for dev".
    """
    # The trailing clause must stay on the heading's own line: [^\S\n] is
    # horizontal whitespace only. Using \s* here lets the dash match the first
    # bullet of the body and swallow it.
    trailer = r"(?:[^\S\n]*[-—:][^\n]*)?\**[^\S\n]*$"
    pattern = re.compile(
        r"^\s*(?:#{1,6}\s*|h[1-6]\.\s*|\*\*)" + re.escape(heading) + trailer
        + r"(.*?)(?=^\s*(?:#{1,6}\s|h[1-6]\.\s)|\Z)",
        re.S | re.M | re.I,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def coverage_table(te_text):
    """Rows of the 'Test cases in this execution' table, keyed by column name."""
    body = section(te_text, "Test cases in this execution")
    if body is None:
        return None
    rows = parse_table_rows(body)
    if len(rows) < 2:
        return []
    header = [h.lower() for h in rows[0]]
    out = []
    for cells in rows[1:]:
        if len(cells) != len(header):
            continue
        out.append(dict(zip(header, cells)))
    return out


def ac_ids(te_text):
    """Requirement ids named in the TE's 'Acceptance criteria' section."""
    body = section(te_text, "Acceptance criteria") or ""
    ids = set(re.findall(r"\b(?:AC\s*#?\s*(\d+)|R(\d+))\b", body, re.I))
    return {("AC" + a) if a else ("R" + b) for a, b in ids}


def ids_in(cell):
    found = set()
    for a, b in re.findall(r"\b(?:AC\s*#?\s*(\d+)|R(\d+))\b", cell or "", re.I):
        found.add(("AC" + a) if a else ("R" + b))
    return found


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------

def check_descriptions(res, tests, te_desc, te_key):
    empty = [t["key"] for t in tests if not (t["description"] or "").strip()]
    if empty:
        res.failed("1 descriptions non-empty", "empty on " + ", ".join(sorted(empty)))
    else:
        res.passed("1 descriptions non-empty", "{} cases, all non-empty".format(len(tests)))

    if not (te_desc or "").strip():
        res.failed("1 TE description", te_key + " description is empty")
        return

    missing = [s for s in REQUIRED_TE_SECTIONS if section(te_desc, s) is None]
    if missing:
        res.failed("1 TE description sections", "missing: " + ", ".join(missing))
    else:
        res.passed("1 TE description sections", "all {} present".format(len(REQUIRED_TE_SECTIONS)))

    unrendered = [t["key"] for t in tests if "&lt;h3&gt;" in (t["description"] or "")]
    if unrendered:
        res.failed("1 descriptions rendered", "escaped HTML in " + ", ".join(sorted(unrendered)))
    else:
        res.passed("1 descriptions rendered", "no escaped markup found")


def check_links(res, linked_keys, tests, te_key):
    expected = {t["key"] for t in tests} | {te_key}
    missing = sorted(expected - linked_keys)
    if missing:
        res.failed("2 links present + directed",
                   "not returned by linkedIssues(..,'is tested by'): " + ", ".join(missing))
    else:
        res.passed("2 links present + directed",
                   "{} artefacts linked (cases + TE)".format(len(expected)))


def check_comments(res, story_comment, te_comment):
    required = ("QA Verification Result:", "Test Execution:", "Run:", "Environment:", "Preconditions")
    for label, text in (("story", story_comment), ("TE", te_comment)):
        if text is None:
            res.manual("3 {} comment shape".format(label), "not supplied — pass --{}-comment <file>"
                       .format("story" if label == "story" else "te"))
            continue
        missing = [f for f in required if f not in text]
        if missing:
            res.failed("3 {} comment shape".format(label), "missing: " + ", ".join(missing))
            continue
        result_line = re.search(r"QA Verification Result:\*{0,2}\s*(\w+)", text)
        value = result_line.group(1) if result_line else ""
        if value not in ("Pass", "Failed", "Blocked", "Inconclusive"):
            res.failed("3 {} comment shape".format(label),
                       "result value {!r} not one of Pass/Failed/Blocked/Inconclusive".format(value))
        elif not re.search(r"Passed:\s*\d+.*Failed:\s*\d+.*Blocked", text, re.S):
            res.failed("3 {} comment counts".format(label),
                       "four counts missing (Passed · Failed · Blocked/errored · Not attempted)")
        else:
            res.passed("3 {} comment shape".format(label), "header, counts and result value present")


def check_secrets(res, tests, te_desc, runs):
    hits = []
    for t in tests:
        blob = (t["description"] or "") + " " + json.dumps(t.get("steps") or [])
        for pat in SECRET_PATTERNS:
            if pat.search(blob):
                hits.append(t["key"])
                break
    for pat in SECRET_PATTERNS:
        if pat.search(te_desc or ""):
            hits.append("TE description")
            break
    for r in runs:
        for pat in SECRET_PATTERNS:
            if pat.search(r.get("comment") or ""):
                hits.append("run comment on " + (r.get("key") or "?"))
                break
    if hits:
        res.failed("5 no credentials in artefacts", "possible secret in " + ", ".join(sorted(set(hits))))
    else:
        res.passed("5 no credentials in artefacts", "no apiKey/password/token pattern found")


def check_oracle_tags(res, rows):
    if rows is None:
        res.failed("6 traceability + oracle", "no 'Test cases in this execution' table in the TE")
        return None
    if not rows:
        res.failed("6 traceability + oracle", "coverage table is empty")
        return []
    if "oracle" not in rows[0] or "traces" not in rows[0]:
        res.failed("6 traceability + oracle",
                   "coverage table has no Oracle/Traces column (found: {})".format(", ".join(rows[0])))
        return rows
    bad = []
    for r in rows:
        key = r.get("key", "?")
        if not r.get("traces"):
            bad.append("{}: empty Traces".format(key))
        oracle = (r.get("oracle") or "").strip().lower()
        if oracle not in LEGAL_ORACLES:
            bad.append("{}: oracle {!r}".format(key, r.get("oracle")))
    if bad:
        res.failed("6 traceability + oracle", "; ".join(bad))
    else:
        res.passed("6 traceability + oracle", "{} cases, all traced and tagged".format(len(rows)))
    return rows


def check_ac_floor(res, rows, te_desc):
    acs = ac_ids(te_desc or "")
    if not acs:
        res.manual("6a AC floor", "no AC/R ids found in the TE 'Acceptance criteria' section")
        return
    if not rows:
        res.failed("6a AC floor", "no coverage table to check {} criteria against".format(len(acs)))
        return
    # A hard oracle satisfies the floor: an AC verified by a regression case is
    # still verified. Only oracle:risk cannot carry a criterion, because a risk
    # case auto-clears and so can never report that criterion broken.
    covered = set()
    for r in rows:
        if (r.get("oracle") or "").strip().lower() in ("ac", "prior-behaviour"):
            covered |= ids_in(r.get("covers", "")) | ids_in(r.get("traces", ""))
    uncovered = sorted(acs - covered)
    if uncovered:
        body = section(te_desc, "Test cases in this execution") or ""
        excused = [a for a in uncovered if re.search(re.escape(a) + r"\b[^\n]{0,200}(no test case|by design|not observable|not a black-box)", body, re.I)]
        still = [a for a in uncovered if a not in excused]
        if still:
            res.failed("6a AC floor",
                       "no oracle:ac / prior-behaviour case for " + ", ".join(still) + " — run cannot be reported Pass")
        else:
            res.passed("6a AC floor", "{} criteria covered; {} excused in writing".format(len(acs), len(excused)))
    else:
        res.passed("6a AC floor", "all {} criteria have a hard-oracle case".format(len(acs)))


def parse_approved_tags(path):
    """Oracle tags recorded in the working <TICKET>.md, per case title."""
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    project_key = cfg("jira.project_key", required=True)
    result_key_re = re.compile(r"\*\*Result:\*\*.*?\b(" + re.escape(project_key) + r"-\d+)")
    tags = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"\*\*Title:\*\*\s*(.+)", line.strip())
        if m:
            current = m.group(1).strip()
        m = re.match(r"\*\*Oracle:\*\*\s*(\S+)", line.strip())
        if m and current:
            tags[current] = m.group(1).strip().lower()
        m = result_key_re.match(line.strip())
        if m and current and current in tags:
            tags[m.group(1)] = tags[current]
    return tags


def check_ratchet(res, rows, approved):
    if approved is None:
        res.manual("6b ratchet", "no --approved <TICKET>.md supplied; cannot diff against the approved tags")
        return
    if not rows:
        res.failed("6b ratchet", "no coverage table to compare")
        return
    rank = {"ac": 2, "prior-behaviour": 2, "risk": 1}
    downgrades = []
    for r in rows:
        title = (r.get("title") or "").strip()
        key = (r.get("key") or "").strip()
        was = approved.get(title) or approved.get(key)
        if not was:
            continue
        now = (r.get("oracle") or "").strip().lower()
        if rank.get(was, 0) > rank.get(now, 0):
            downgrades.append("{}: {} -> {}".format(key or title, was, now))
    if downgrades:
        res.failed("6b ratchet",
                   "downgraded after approval (needs the configured QA assignee's ruling "
                   "in the TE comment): " + "; ".join(downgrades))
    else:
        res.passed("6b ratchet", "no tag downgraded since approval")


def check_risk_reporting(res, runs, te_desc, story_comment):
    risk_runs = [r for r in runs if (r.get("comment") or "").lstrip().startswith(RISK_PREFIX)]
    if not risk_runs:
        res.passed("6c risk three-place reporting", "no auto-cleared risk findings on this run")
        return
    findings = section(te_desc or "", "Risk findings") or ""
    problems = []
    for r in risk_runs:
        key = r.get("key") or "?"
        comment = r.get("comment") or ""
        if "Baseline applied:" not in comment or "Observed:" not in comment:
            problems.append("{}: run comment missing Baseline applied/Observed".format(key))
        if key not in findings:
            problems.append("{}: no block in the TE 'Risk findings' section".format(key))
        else:
            block = findings[findings.index(key):]
            block = block[:block.find("\n**", 1)] if "\n**" in block[1:] else block
            m = re.search(r"Why the AC cannot settle it:\s*(.+)", block)
            if not m:
                problems.append("{}: 'Why the AC cannot settle it' line absent".format(key))
            elif not re.search(r"[\"'“‘`]", m.group(1)):
                problems.append("{}: silence asserted with no quotation from the ticket".format(key))
            if "Decision needed from product" not in block:
                problems.append("{}: no 'Decision needed from product' question".format(key))
        if story_comment is None:
            res.manual("6c risk three-place reporting",
                       "story comment not supplied; {} auto-clear(s) cannot be fully checked".format(len(risk_runs)))
            story_ok = None
        else:
            story_section = section(story_comment, "Risk findings") or ""
            if key not in story_section:
                problems.append("{}: not in the story comment's 'Risk findings' section".format(key))
            elif not ("not a defect" in story_section.lower()
                      and "does not hold approval" in story_section.lower()):
                problems.append("{}: story entry missing the verbatim 'not a defect' / "
                                "'does not hold approval' wording".format(key))
    if problems:
        res.failed("6c risk three-place reporting", "; ".join(problems))
    elif story_comment is not None:
        res.passed("6c risk three-place reporting",
                   "{} auto-clear(s), all reported in three places".format(len(risk_runs)))


def check_run_states(res, runs, story_comment):
    counts = {}
    for r in runs:
        counts[r.get("status") or "?"] = counts.get(r.get("status") or "?", 0) + 1
    detail = " · ".join("{} {}".format(v, k) for k, v in sorted(counts.items()))

    errored = [r for r in runs
               if (r.get("status") == "BLOCKED"
                   and any((r.get("comment") or "").lstrip().startswith(p) for p in ERROR_PREFIXES))]
    unlabelled = [r.get("key") for r in runs
                  if r.get("status") == "BLOCKED"
                  and not (r.get("comment") or "").lstrip().startswith(ERROR_PREFIXES + (RISK_PREFIX,))]
    if unlabelled:
        res.failed("8 blocked runs carry a prefix",
                   "BLOCKED with no ENV/SETUP/UPSTREAM/RISK prefix: " + ", ".join(sorted(k or "?" for k in unlabelled)))
    else:
        res.passed("8 blocked runs carry a prefix", detail or "no runs")

    # An auto-cleared RISK run was exercised - only the verdict was withheld - so
    # it never counts toward the inconclusive threshold.
    blocked_or_errored = sum(
        1 for r in runs
        if r.get("status") in ("BLOCKED", "EXECUTING")
        and not (r.get("comment") or "").lstrip().startswith(RISK_PREFIX))
    total = len(runs) or 1
    inconclusive = bool(errored) or (blocked_or_errored / total) >= (1 / 3)
    if not inconclusive:
        res.passed("8.6 inconclusive headline", "not required ({}/{} blocked or executing)".format(blocked_or_errored, total))
    elif story_comment is None:
        res.manual("8.6 inconclusive headline",
                   "required ({} env/setup errors, {}/{} blocked) — story comment not supplied"
                   .format(len(errored), blocked_or_errored, total))
    elif "Inconclusive" in story_comment:
        res.passed("8.6 inconclusive headline", "required and present")
    else:
        res.failed("8.6 inconclusive headline",
                   "required ({} env/setup errors, {}/{} blocked or executing) but the story comment "
                   "does not say Inconclusive".format(len(errored), blocked_or_errored, total))


def check_transition_ready(res, runs):
    outstanding = []
    for r in runs:
        status = r.get("status")
        comment = (r.get("comment") or "").lstrip()
        if status == "PASSED":
            continue
        if status == "BLOCKED" and comment.startswith(RISK_PREFIX):
            continue  # auto-cleared
        outstanding.append("{} {}".format(r.get("key") or "?", status))
    if outstanding:
        res.passed("4 transition readiness",
                   "NOT ready — outstanding: " + ", ".join(sorted(outstanding))
                   + " (informational, not a gate failure)")
    else:
        res.passed("4 transition readiness", "every run PASSED or auto-cleared — safe to transition")


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------

def load(xr, ticket, te_key):
    q = '''
    {
      getTestExecutions(jql: "key = %s", limit: 1) {
        results {
          issueId
          jira(fields: ["key", "description"])
          tests(limit: 100) {
            results {
              issueId
              jira(fields: ["key", "summary", "description"])
              steps { action data result }
            }
          }
          testRuns(limit: 100) {
            results { status { name } comment test { jira(fields: ["key"]) } }
          }
        }
      }
    }''' % te_key
    data = xr.query(q)["getTestExecutions"]["results"]
    if not data:
        raise RuntimeError("Test Execution {} not found".format(te_key))
    te = data[0]

    tests = []
    for t in te["tests"]["results"]:
        j = t["jira"]
        tests.append({"key": j.get("key"), "summary": j.get("summary"),
                      "description": strip_html(j.get("description") or ""),
                      "steps": t.get("steps")})

    runs = []
    for r in te["testRuns"]["results"]:
        runs.append({"key": (r.get("test") or {}).get("jira", {}).get("key"),
                     "status": (r.get("status") or {}).get("name"),
                     "comment": r.get("comment")})

    # A Test Execution is not a Test, so getTests can never return it however the
    # link is directed - the TE reports as missing on every correctly-linked suite.
    jql = 'issue in linkedIssues(\\"%s\\", \\"is tested by\\")' % ticket
    linked = xr.query('{ getTests(jql: "%s", limit: 100) { results { jira(fields: ["key"]) } } }' % jql)
    linked_keys = {t["jira"].get("key") for t in linked["getTests"]["results"]}
    linked_te = xr.query('{ getTestExecutions(jql: "%s", limit: 50) { results { jira(fields: ["key"]) } } }' % jql)
    linked_keys |= {t["jira"].get("key") for t in linked_te["getTestExecutions"]["results"]}

    return {
        "te_desc": strip_html(te["jira"].get("description") or ""),
        "tests": tests,
        "runs": runs,
        "linked_keys": linked_keys,
    }


def read_optional(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main():
    ap = argparse.ArgumentParser(description="Mechanical QA publish-gate checker")
    ap.add_argument("ticket")
    ap.add_argument("te_key")
    ap.add_argument("--story-comment")
    ap.add_argument("--te-comment")
    ap.add_argument("--approved")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        xr = Xray()
        data = load(xr, args.ticket, args.te_key)
    except ConfigError as exc:
        print("configuration problem: {}".format(exc), file=sys.stderr)
        return 3
    except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as exc:
        print("could not read {} from Xray: {}".format(args.te_key, exc), file=sys.stderr)
        return 3

    story = read_optional(args.story_comment)
    te_comment = read_optional(args.te_comment)
    try:
        approved = parse_approved_tags(args.approved)
    except ConfigError as exc:
        print("configuration problem: {}".format(exc), file=sys.stderr)
        return 3

    res = Results()
    check_descriptions(res, data["tests"], data["te_desc"], args.te_key)
    check_links(res, data["linked_keys"], data["tests"], args.te_key)
    check_comments(res, story, te_comment)
    check_transition_ready(res, data["runs"])
    check_secrets(res, data["tests"], data["te_desc"], data["runs"])
    rows = check_oracle_tags(res, coverage_table(data["te_desc"]))
    check_ac_floor(res, rows, data["te_desc"])
    check_ratchet(res, rows, approved)
    check_risk_reporting(res, data["runs"], data["te_desc"], story)
    check_run_states(res, data["runs"], story)

    if args.json:
        print(json.dumps({"ticket": args.ticket, "te": args.te_key, "checks": res.rows}, indent=2))
    else:
        print("QA publish gate — {} / {}".format(args.ticket, args.te_key))
        print()
        print(res.render())
    return res.exit_code()


if __name__ == "__main__":
    sys.exit(main())
