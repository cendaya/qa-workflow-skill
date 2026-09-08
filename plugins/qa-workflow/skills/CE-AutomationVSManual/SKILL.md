---
name: CE-AutomationVSManual
description: Use after a Reqnroll/SpecFlow regression run to reconcile automation results against an Xray Test Execution ticket — parses the Visual Studio Test Explorer results, maps green scenarios onto TE test cases, auto-marks those cases PASSED in Xray, and produces the list of cases still needing manual execution. Trigger whenever the user mentions comparing an automation run to a TE, "what do I still need to run manually", "reconcile Regression_Quick with PROJ-XXXX", "mark the passed ones in the TE", "automation vs manual coverage", or names a regression tag (@Regression_Quick / @Regression_Short / @Regression_Full / @smoke) alongside a Test Execution key. Also use it when the user just finished a regression run and wants to know their remaining manual scope.
---

# Automation vs Manual TE Reconciliation

After a regression run, the QA question is always the same: *which manual test cases in the Test Execution did automation already prove, and what's left for me?* Answering it by hand means cross-reading 200+ Xray cases against 600+ scenarios. This skill does the cross-read, writes the provable passes back to Xray, and hands back a manual worklist.

The guiding principle: **a TE case only goes green when a specific automated scenario actually proves it.** A shared Test Execution is official QA record. A false PASSED there is worse than an unfilled TO DO, because it hides untested product from everyone downstream. Everything uncertain flows to the manual list instead — that list is the deliverable, not a consolation prize.

## Inputs

Ask only for what's missing:

- **TE key** (e.g. `PROJ-9896`) — the Xray Test Execution to reconcile against.
- **Category** — defaults to `Regression_Quick`. Others: `Regression_Short`, `Regression_Full`, `smoke`.
- **Repo path** — `automation.repo_path` from `$env:USERPROFILE\.claude\qa-config.json`, or the current
  working directory. Ask if neither holds a test project with `Features/*.feature.cs`.
- **Test project name** — the folder inside the repo holding `Features/`. Required by
  `collect_results.py --project`.

Requires `XRAY_CLIENT_ID` and `XRAY_CLIENT_SECRET` in the environment. Never print either, or the bearer token derived from them.

## Workflow

### 1. Collect automation results

```bash
python <skill>/scripts/collect_results.py --repo <repo> --category Regression_Quick --out results.json
```

This finds the newest `.vs/**/TestStore/*/**.testlog` (Visual Studio's Test Explorer store), decodes it, and joins each test's last recorded outcome to the categories and scenario titles parsed from the generated `*.feature.cs` files. Output rows are `{feature, title, fqn, status}` with status in `Passed | Failed | Skipped | NotRun`.

Report the tally to the user before going further — if `NotRun` is large, the run was probably filtered or aborted, and reconciling a partial run wastes their time. Say so and let them decide.

`installs msgpack on first use` — the testlog is MessagePack framed; the script pip-installs `msgpack` if absent.

### 2. Pull the TE's current state

```bash
python <skill>/scripts/xray_te.py runs <TE-KEY> --out runs.json
```

Gives `{TE-case-key: [testRunId, currentStatus]}` for every case in the execution. Cases already PASSED by someone else are left alone — flag them in the report but don't touch them, since you don't know what evidence backed them.

### 3. Resolve coverage

Read the mapping file at `automation.te_mapping_path` in `qa-config.json` (default
`~/.claude/qa-te-mapping.md`); fall back to `references/te-mapping.md`, which ships as an empty
template describing the format. It maps TE case keys to the exact automation scenarios that prove them, and lists the areas known to have no automation at all. For each mapped case, look up every scenario in its mapping:

- Every mapped scenario `Passed` → **PASS candidate**
- Any mapped scenario `Failed` → **manual: verify failure** (a failed script is usually flaky, not a found bug — it needs human eyes before it becomes an official FAILED)
- Any mapped scenario `NotRun` or `Skipped` → **manual: not executed**
- Case absent from the mapping → **needs mapping** (see step 4)

For an area case that's mostly green with a handful of red — say Reports with 21 failed
generations out of 200 scenarios — resist the urge to round up. Report it as
*"area covered, N scenarios failed — your call"* with the failing scenario names listed, and
leave it TO DO. Whether those failures are flaky scripts or real defects is a judgment only
the tester can make, and a threshold rule would quietly write PASSED over known-red
scenarios. Making the decision cheap (names right there, one line per case) is more useful
than making it automatic.

Never mark FAILED in Xray. Failures leave the TE at TO DO and land in the manual list with their error text.

### 4. Propose mappings for unmapped cases

New TE cases appear every regression. For each unmapped case, search the automation for a scenario whose title plainly covers it, then show the user a short proposal table (`TE key | title | proposed scenario | confidence`). Ask them to confirm before any of those get written. On confirmation, append them to the user's mapping file at `automation.te_mapping_path` — never to
`references/te-mapping.md` inside the plugin, which a `/plugin update` would overwrite — so next regression is cheaper — the mapping file is the skill's memory, and it's the reason the second run costs a fraction of the first.

Cases with no plausible scenario are simply manual. Don't stretch a mapping to fill a gap; an honest gap is useful information.

### 5. Write the passes

```bash
python <skill>/scripts/xray_te.py pass --runs runs.json --keys pass_keys.txt
```

Only flips `TO DO` → `PASSED`. Add `--dry-run` first if the pass set is unusually large (say, more than half the execution) — that's a signal the mapping matched too loosely, and it's worth a look before writing.

Then re-pull with `runs` to verify the writes landed, and report the before/after counts rather than assuming success.

### 6. Report

```markdown
## Automation run — <category>
| Outcome | Count |  (Passed / Failed / Skipped / NotRun / Total, plus features fully green)

## <TE-KEY> written
- N cases marked PASSED (list keys, each with the scenario that proved it)
- M cases already PASSED before this run (untouched — list them)

## Still to run manually
### Verify automation failure (K cases)
- PROJ-XXXX <title> — `<Feature> (NN) <scenario>` failed: <error summary>
### Not executed by automation (K cases)
### No automation coverage (K cases)  — grouped by area

## Unmapped TE cases needing your call
```

Group the manual list by product area, not by reason code alone — that's how the work actually gets scheduled.

## Judgment calls worth getting right

**Area and navigation cases** (e.g. "Settings screens navigation", "Utilities", "Home Page") *are* provable. The nav features walk every menu entry and the area features cover the tabs and panels, so a fully green feature set proves the case — don't reflexively push these to manual. The mapping file's "Area and navigation cases" section lists which area cases map to which features, and its "Areas with no automation coverage" section lists the areas that genuinely stay manual.

The distinction that matters isn't umbrella-vs-specific, it's whether automation actually reaches the behaviour the case describes. A broad case over a well-automated area is provable; a narrow case over an unautomated feature isn't.

**Partial coverage** is the most tempting trap. If automation proves the batch-screen path but the case describes the customer-screen path, that case is not proven. List the covered half in the manual note so the tester can skip it, but leave the case TO DO.

**Skipped is not passed.** A scenario Reqnroll skipped proves nothing.

**One scenario can prove several cases** (e.g. a payment-reversal scenario proves both "Reversing Payment History" and "Reverse a payment") and one case can need several scenarios. The mapping file handles both directions.

## Files

- `scripts/collect_results.py` — testlog + `*.feature.cs` → results JSON
- `scripts/xray_te.py` — Xray auth, read TE runs, write PASSED
- `references/te-mapping.md` — format spec for the mapping file; the real map lives at `automation.te_mapping_path`
