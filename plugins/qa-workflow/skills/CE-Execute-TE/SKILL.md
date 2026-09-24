---
name: CE-Execute-TE
description: Use when given an Xray Test Execution ticket key to run all its test cases — detects execution tool per test (Playwright for UI, Postman for API, k6 for performance), executes each, records pass/fail back in Xray. Triggers include "run the test execution", "execute PROJ-XXXX", "run tests in TE", "execute all test cases".
---

# CE-Execute-TE

Execute all test cases in an Xray Test Execution. Auto-detect tool (Playwright / Postman / k6) per test from Gherkin/steps. Record results back in Xray.

**Requires:** `XRAY_CLIENT_ID` and `XRAY_CLIENT_SECRET` env vars. See `TC-Router/references/xray-queries.md` for auth helper setup.

## Input

**TE ticket key** — e.g. `PROJ-9999`

---

## Step 0 — Authenticate with Xray

Follow `TC-Router/references/xray-queries.md` section 0. Obtain Bearer token. Set up `Invoke-Xray` helper. Token is valid ~24h — skip re-auth if already done this session.

---

## Step 1 — Fetch the Test Execution + test runs

Load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getJiraIssue`. Fetch the TE ticket. Confirm `issuetype = "Test Execution"`. If not: stop — "Key is not a Test Execution ticket."

Then run Xray GraphQL to get all test runs (includes `id` needed for status updates):

```graphql
{
  getTestExecution(issueId: "<TE_ISSUE_ID>") {
    issueId
    jira(fields: ["key", "summary"])
    testRuns(limit: 100) {
      results {
        id
        status { name }
        test {
          issueId
          jira(fields: ["key", "summary", "labels"])
          testType { name }
          gherkin
          steps { id action data result }
        }
      }
    }
  }
}
```

> `issueId` for the query = numeric Jira issue ID, not the `PROJ-XXXX` key. Get it from `getJiraIssue` response (`id` field).
>
> If `testRuns.results` empty: check TE has test cases linked. If zero, stop and inform user.

Save the full response. The `testRun.id` (UUID) is required for status updates in Step 6.

Build a table before executing:

| # | Test Run ID | Key | Summary | Type | Current Status |
|---|-------------|-----|---------|------|----------------|

---

## Step 1a — Transition the TE to In Progress + assign to self

Before executing any test:

1. Move the TE ticket's Jira status to **In Progress** so it reflects that a run is underway. Load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getTransitionsForJiraIssue`, fetch transitions for the TE key, find the one named "In Progress" (or equivalent), and call `transitionJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__transitionJiraIssue`) with its id.
2. Set the TE's **Assignee** to the configured QA assignee — the current user — via `editJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__editJiraIssue`), `fields: { assignee: { accountId: "<current user>" } }`. Resolve the accountId once with `atlassianUserInfo` (ToolSearch `select:mcp__plugin_atlassian_atlassian__atlassianUserInfo`) — never hardcode it.

No user confirmation needed for either — both are automatic at the start of every run, since starting execution *is* the signal that the current user is now the one running it.

If no "In Progress" transition is available (e.g. already in progress, or the workflow lacks that state), note it and continue. If the assignee set fails, note it and continue. Never block execution on either.

---

## Step 2 — Detect execution tool per test

For each test run, check `testType.name`, `labels`, and step content:

| Signal | Tool |
|--------|------|
| `testType = Cucumber` + steps contain `navigate`, `click`, `fill`, `button`, `page`, `see`, `checkbox`, `dropdown`, `tab` | **Playwright** |
| `testType = Cucumber` + steps contain `request`, `response`, `status code`, `endpoint`, `JSON`, `API`, `header`, `body`, `POST`, `GET`, `PUT`, `DELETE` | **Postman** |
| `testType = Cucumber` + steps contain `concurrent users`, `throughput`, `p95`, `rps`, `latency`, `load`, `vus`, `duration` | **k6** |
| `testType = Manual` | **Manual** — user confirms pass/fail |
| Label `UI` or `frontend` | Playwright |
| Label `API` or `REST` | Postman |
| Label `performance` or `load` | k6 |
| Ambiguous | Ask: `"Test {KEY} — {summary}: UI (Playwright), API (Postman), Performance (k6), or Manual?"` |

---

## Step 3 — Execute each test (one at a time, in order)

Never skip a test. Complete current before starting next. Record result immediately after each run.

### UI → Playwright

1. Read full Gherkin from `test.gherkin`.
2. Generate a Playwright TypeScript spec implementing the Given/When/Then steps. Output to scratchpad.
3. Run: `npx playwright test <path> --reporter=json`
4. Capture: pass/fail, error message, screenshot path on failure.

If Playwright is not installed or the app is not running, note the blocker and mark as `BLOCKED`.

### API → Postman

1. Parse Gherkin — extract: method, URL, headers, request body, response assertions.
2. Generate a Postman collection JSON. Output to scratchpad.
3. Invoke skill `postman:run-collection` with the collection path.
4. Capture: pass/fail, failed assertions, response body on failure.

### Performance → k6

1. Parse Gherkin — extract: target URL, VUs, duration, thresholds (p95, error rate, etc.).
2. Generate k6 script. Output to scratchpad.
3. Run: `k6 run <path>`
4. Capture: threshold pass/fail, p95 latency, error rate, VU count.

### Manual

Show the test steps to the user:

```
Test {KEY} — {summary}
Steps:
1. {action} | Data: {data} | Expected: {result}
2. ...

Result? (pass / fail / blocked)
If fail/blocked: notes?
```

Wait for response before continuing.

---

## Step 4 — Accumulate results

After each test, append to running table:

| # | Key | Summary | Tool | Result | Notes |
|---|-----|---------|------|--------|-------|
| 1 | PROJ-XXXX | ... | Playwright | ✅ PASS | |
| 2 | PROJ-XXXX | ... | Postman | ❌ FAIL | `status 200 expected, got 404` |

Show updated table after each test so user sees live progress.

---

## Step 5 — Update results in Xray

**Before writing a single result, run the publish gate:** `../../references/qa-publish-gate.md`.
Checks 1 and 2 (descriptions non-empty and rendering; links present and pointing the right way) must
pass *before* results go in, because both become expensive to fix afterwards — a wrong-direction link
cannot be deleted at all, only rebuilt. Run the commands; do not assume.

After all tests complete, update each test run status via Xray GraphQL.

Use `testRun.id` (UUID from Step 1 — not the Jira key):

```powershell
$updateStatus = @'
mutation UpdateStatus($id: String!, $status: String!) {
  updateTestRunStatus(id: $id, status: $status)
}
'@
Invoke-Xray $updateStatus @{ id = "<TEST_RUN_UUID>"; status = "PASSED" }
```

Valid status values **on this Xray instance**: `PASSED`, `FAILED`, `EXECUTING`, `TO DO`, `BLOCKED`.

**There is no `ABORTED`.** A write of `ABORTED` is rejected. Note also that the to-do status is `TO DO` **with a space** — `TODO` is rejected too. Both were wrong in this skill until 2026-09-15 and silently failed every un-runnable test.

Map results. **An error is not a result** — before writing anything, classify *whether a comparison
happened at all* (`../../references/qa-oracle-model.md` §8). A failure means the oracle was checked
and actual did not match expected; an error means the check never happened, and writing `FAILED` for it
sends a developer after a defect that does not exist.

| Test outcome | Xray status | Reason prefix | Gates? |
|---|---|---|---|
| ✅ PASS | `PASSED` | — | — |
| ❌ Genuine failure — code ran, missed a real oracle | `FAILED` / the failure gate below | — | Blocks |
| Environment or infrastructure — app unreachable, DB refused, healthy endpoint 500s, timeout, expired token, build not deployed | `BLOCKED` | `ENV —` | Blocks |
| Setup or precondition — fixture, seed data, missing rights, an upstream case that never created the record | `BLOCKED` | `SETUP —` | Blocks |
| Cascade — an earlier error left a state this case cannot start from | `BLOCKED` | `UPSTREAM —` | Blocks |
| Oracle-less deviation on an `oracle: risk` case | `BLOCKED` | `RISK —` | **Auto-clears** |
| Not attempted | `TO DO` (leave unchanged) | — | Blocks |

The prefix is mandatory and is what separates "the product is broken" from "the environment or the
harness is broken" for whoever reads the TE. `RISK —` is the only prefix that auto-clears: it was
exercised and the verdict was withheld. The other three were never exercised at all.

**Fail fast.** Three consecutive cases erroring for the same environmental reason means one problem,
not three: stop the run, leave the rest at `TO DO` (they were not attempted — `BLOCKED` would claim
they were), write one `ENV —` entry with the URL, the exact error and where the URL came from, and
append the TE to `<your-execution-queue>.md` under `$env:USERPROFILE\.claude\automation\`.

**Retry only the retryable** — a network blip, timeout, 502/503/504 or rate limit gets 2 attempts with
backoff, logged. Nothing else environmental is retried, and **an assertion failure is never retried**.
A case that only passes on retry is flaky, not green: `PASSED`, plus an `Observations for dev` line
saying "passed on retry N of 2 — flaky, not a clean pass".

**Capture diagnostics at the moment of the error**, before retrying or navigating away: exact error
text and stack trace quoted, the request/response, a screenshot and DOM snapshot for UI, the console
line, the exact input, the build and tenant. Recoverable now, unrecoverable in ten minutes.

**Always read the status back after writing it** — `getTestRuns` on the TE — and treat a value that did not change as a failed write, not a recorded result.

> If `updateTestRunStatus` is rejected, run introspection to verify the mutation name:
> `{ __type(name: "Mutation") { fields { name } } }`
> Adjust and retry — do not guess repeatedly.

### Before anything counts as a failure — counter-check it against the ticket

**Question zero: did a comparison actually happen?** If the case errored rather than produced a wrong
result — the app never loaded, the precondition never built, an earlier case left the state dirty — it
is `ENV —` / `SETUP —` / `UPSTREAM —` and none of what follows applies. Only a case that ran and
produced output can be counter-checked.

**Then, before the environment ladder and before touching the queue**, three questions, and a failure
has to survive all three:

1. **Is this the thing the ticket asks to fix?** Re-read Actual Behavior and Expected Behavior and say,
   in one sentence, what the defect *is*. Then ask whether what you observed is that defect, a different
   defect, or merely adjacent. A behaviour that is wrong but is not the ticket's subject is an
   observation, not a failure of this ticket.
2. **Did you verify the actual symptom, or only a proxy for it?** Name the user-visible thing the ticket
   complains about and check *that*. Counting rows, options or requests is a proxy. If the complaint is
   "the wrong data reaches the report", check the report. If it is "it displays one thing and does
   another", check both the display and the data.
3. **Was the starting state clean, or a residue of your own earlier steps?** Many screens in the product
   under test persist criteria per user, so a screen reflects whatever the last run left behind. Reload
   from a known state and re-run the ticket's own steps in the ticket's own order. If the outcome changes,
   your first result was an artefact.

The configured QA assignee's instruction, 2026-09-16: *"before failing it should be counter-checked with
the ask on the actual ticket, what is being fixed."*

The case that produced this rule: PROJ-11087 on PROJ-10327 was recorded as a failure because a move-all
carried 77 statuses when the filter read "Resolved". Both of the checks above would have caught it.
The ticket's defect was that hidden statuses were carried across **invisibly** and reached the report —
and in the observed state the destination list held 77 options with **0 hidden**, so nothing was
concealed and the report matched the screen. The starting list contents were also a residue of earlier
runs; from a clean load the ticket's own sequence passed. A real but lesser bug remained (a stale filter
label), which belongs in its own ticket.

**A withdrawn failure costs a developer nothing. A wrongly-filed one costs them an afternoon and costs
you the benefit of the doubt on the next finding.**

### Then reproduce it elsewhere

A single environment cannot tell you whether a fault is a defect, a bad tenant's data, or a broken
deploy. **Whenever a case looks like it fails, walk this ladder before recording anything.** It is cheap,
it takes minutes, and it is what turns "it failed" into a finding a developer can act on.

| Step | Where | What it tells you |
|---|---|---|
| 1 | `https://<your-ui-host>/<tenant-a>/Login` — `environments.qa.ui.base_url` in `qa-config.json` | The primary QA tenant — where the case first failed |
| 2 | `https://<your-ui-host>/<tenant-b>/Login` — a second tenant on the same QA host | A second QA tenant on the same build. **Reproduces → the code is at fault. Does not reproduce → it is tenant data or configuration, not the fix.** |
| 3 | `https://<your-staging-ui-host>/<tenant-b>/Login` — `environments.staging.ui.base_url` in `qa-config.json` | Staging, which runs older code. **Reproduces there too → pre-existing, not a regression from this ticket. Clean there → this change introduced it.** |

Record all three outcomes, not just the one that confirms your hypothesis, and put them straight into
the queue entry's **"could be environment because"** line — this ladder is how that line gets written
honestly instead of guessed at.

Two things to keep straight:

- Step 3 is **classification only**. Reproducing on staging tells you the fault predates the fix; it
  never makes staging the place to run the test suite. Never fail a ticket, or pass one, on the basis of
  a staging run.
- If step 2 does not reproduce, say so plainly and drop the confidence rating. A fault that appears on
  one tenant and not another on the same build is a data or configuration story until proven otherwise,
  and filing it as a code defect wastes a developer's afternoon.

When a fault is pre-existing (step 3 reproduces), it is **not** a failure of this ticket. Note it, raise
it separately if it matters, and judge the ticket on what it actually changed.

### The failure gate (mode: `notify-before-failing`)

**First, read the case's oracle.** `../../references/qa-oracle-model.md` §6 decides what a failure
on this case is allowed to mean, before any question of how to write it:

| Oracle on the case | A failure is | Authority |
|---|---|---|
| `ac` | A suspected defect | Blocks *Testing Approved* |
| `prior-behaviour` | A suspected regression | Blocks *Testing Approved*. Walk the environment ladder first — a pre-existing fault is not this ticket's regression |
| `risk` | A **flag**, not a defect | **Auto-clears.** Write the run `BLOCKED` with a reason starting `RISK —`. No queue entry, no human ruling, does not hold *Testing Approved* or TE `Done`. Report it in all three places — run comment, TE `Risk findings`, story `Risk findings` under `Conclusion` (`qa-oracle-model.md` §6a–6c) |
| `none` | Impossible — and a signal something went wrong upstream | A case with no oracle should never have reached the TE. Pull it out of the execution, move its content to `Observations for dev`, and say you did |

The oracle changes the **authority** of the failure, never the rigour of the write-up: a `risk`
deviation still gets the full ladder, the exact error text and the counter-argument. It skips the queue
because no human ruling is needed, **not** because it needs less evidence.

The `RISK —` run comment is mandatory and has a fixed shape:

```
RISK — no authoritative expected result; verdict withheld.
Baseline applied: <what the case expected and where that came from>.
Observed: <what actually happened>.
See "Risk findings" on <TE key>.
```

Default is direct write: a failing test gets `FAILED` immediately. When the caller asks for
`notify-before-failing` — an unattended run always does, and an interactive user may — do **not**
write `FAILED`. Instead:

1. Write `EXECUTING` on that run, so the TE shows work in progress rather than a verdict.
2. Append an entry to the caller's queue file (an unattended run uses
   `$env:USERPROFILE\.claude\automation\<your-pending-failures>.md`) carrying: run id, TE key,
   **the case's oracle tag** (`ac` or `prior-behaviour` — a `risk` case never reaches this queue),
   **the three-environment ladder result** (QA tenant A / QA tenant B / staging tenant B, each
   yes-no), the step that broke, expected vs observed with exact error text, evidence, a confidence
   rating, and a mandatory **"could be environment because"** counter-argument.
3. Continue with the remaining tests. One suspected failure never ends the run.

A `BLOCKED` is still written directly — it is not a failure and does not go in the queue.

Rationale: environment noise has produced false failures repeatedly on this project. A human rules
on the queue and marks `FAILED` afterwards.

### If the Xray MCP is not connected

Do not assume it is. On 2026-09-15 `createTest` / `createTestExecution` were unavailable in a live
session. The fallback — and the more reliable path for unattended runs — is the allowlisted helper,
which authenticates itself from `mcpServers.xray.env` in `~/.claude/settings.json`:

```
python ../../scripts/xray-graphql.py "<query or mutation>"
```

It exits 1 and prints the body when the response carries `errors`. Ad-hoc `curl` and inline
`python -c` against `xray.cloud.getxray.app` are **not** allowlisted and will stall an unattended run.

---

## Step 6 — Final report + Jira comment

**Two comments, two audiences.** The main ticket answers *"can this ship?"*; the Test Execution answers
*"why do we believe that?"*. Both open with the same header block; what follows differs.

**Do not improvise a shape because the content feels like it needs one.** On 2026-09-16 both PROJ-9870 and
PROJ-10500 were posted as free prose under a `### QA Verification` heading — numbered conclusions, no header
block, no table — and had to be rewritten. The template exists so the configured QA assignee does not
re-read a different shape each time: *"why is the PROJ-9870 qa confirmation message does not follow our
formatting"* / *"I need it all to be consistent."* Write the block below verbatim, then **read the comment
back** and confirm the headings and table rendered (check 3 of the publish gate).

### The header block — identical on both, every field mandatory

```
**QA Verification Result:** Pass / Failed / Blocked
**Test Execution:** {TE_KEY}
**Run:** {n} · {YYYY-MM-DD HH:mm}
**Environment:** {URL} · tenant {nnnnnnn} · build {x.y.z.nnn}
```

**No field is optional, and "if known" is not an escape hatch.** The build number is the single most
useful thing in the comment three weeks later — it is the difference between "this was verified" and
"this was verified, but on what?". If you genuinely cannot read the build, write
`build unknown — <why>` rather than dropping the field.

The **Run** line exists because retests stack. Re-run a TE after a fix and you get two comments with
identical headers and no way to tell which is which. `Run: 1` on the first pass, `Run: 2` on the retest,
and so on — count the comments already on the TE to get `n`.

Result values — **exactly three**, and they use the same vocabulary as the Xray run statuses so nobody
has to translate between the comment and the execution:

| Value | When |
|---|---|
| `Pass` | Every run is `PASSED` |
| `Failed` | Any run is `FAILED` |
| `Blocked` | Any run is `BLOCKED`, or still `EXECUTING` because the failure gate held it back |

`Failed` wins over `Blocked` when both are present — a confirmed defect is the more important fact.

### 6a — The main ticket: conclusions only

**Three or four bullets. Never more.** Each is a conclusion about the *product*, not a report on the
testing — "the defect is fixed", not "8 cases executed". **One bullet must always speak to regression**
(what still works), because that is what someone deciding to ship actually needs. No preconditions, no
per-case rows, no repro steps, no file paths.

```
**QA Verification Result:** Pass
**Test Execution:** {TE_KEY}
**Run:** {n} · {YYYY-MM-DD HH:mm}
**Environment:** {URL} · tenant {nnnnnnn} · build {x.y.z.nnn}

### Conclusion
- {The reported defect is fixed: <what now happens, in the user's words>.}
- {Existing behaviour is unaffected — <the regression statement>.}
- {<Any related path probed and its outcome>.}
- {<Accessibility / secondary conclusion, if there is one>.}

### Risk findings
- **{CASE KEY}** — {the input, and what was observed}. The acceptance criteria do not specify this, so
  it is recorded as a flag for product, not a defect, and does not hold approval. {The question product
  needs to answer.} Detail on **{TE_KEY}**.

{n} of {m} cases passed{; k auto-cleared risk finding(s)}. Full results, preconditions and per-case evidence are on **{TE_KEY}**.
```

**`Risk findings` goes directly under `Conclusion`, on both the pass and the fail variant, and only
when there is one** — no empty section on the story. Every entry keeps the words *"not a defect"* and
*"does not hold approval"* verbatim: a reader skimming the story must not come away thinking something
is broken. Equally, no softening — no "minor", no "cosmetic". State the finding flatly and ask the
question. The full write-up lives in the TE's `Risk findings` section, never only on the story.
`qa-oracle-model.md` §6c.

Failing variant — same shape, the conclusions become what is broken and what it blocks:

```
**QA Verification Result:** Failed
**Test Execution:** {TE_KEY}
**Run:** {n} · {YYYY-MM-DD HH:mm}
**Environment:** {URL} · tenant {nnnnnnn} · build {x.y.z.nnn}

### Conclusion
- {The reported defect is **not** fixed on <which path>: <what happens instead>.}
- {<What does work — be specific, it narrows the dev's search>.}
- {<What is unaffected>.}
- {Recommend <Requires Rework / further investigation> — <one clause why>.}

{n} of {m} cases passed. Repro steps, evidence and per-case results are on **{TE_KEY}**.
```

**Always state the count, even on a failure.** "6 of 8 passed" is half of what a developer needs to
locate the fault — what still works narrows the search as much as what broke.

`Blocked` is the third result value: use it when any run is `BLOCKED`, or held at `EXECUTING` by the
failure gate, and spend one bullet saying what was not covered and why. **A `BLOCKED` run whose reason
starts `RISK —` does not make the result `Blocked`** — it auto-cleared, it is reported under
`Risk findings`, and a run with nothing else outstanding is still `Pass`.

`Inconclusive` is the fourth. **Use it whenever any `ENV —` or `SETUP —` run exists, or when
blocked+errored reaches a third of the suite** — the environment or the harness stopped the product
being exercised, so no pass rate is meaningful. Say it in those words: *"the run is inconclusive — the
environment prevented n of m cases from being exercised; fix and re-run."* Reporting a pass rate over a
suite a third of which never ran is lying by omission.

**Every comment carries four counts, never a bare pass rate:**

```
Passed: n · Failed: n · Blocked/errored: n · Not attempted: n   (of m)
```

In the TE, split `Blocked/errored` by prefix so the reader can tell the buckets apart at a glance. If something also genuinely
failed, the result is `Failed` — a confirmed defect outranks an un-run case.

### 6b — The Test Execution: everything

Show the complete results table, then ask:

> "Post results summary to {TE_KEY} in Jira? (yes / no)"

On "yes", load via ToolSearch `select:mcp__plugin_atlassian_atlassian__addCommentToJiraIssue`. Post using the **QA verification format** (confirmed standard — no Ticket/Tester/Date/Defects Found/Overall Verdict lines, no Steps column), opening with the header block above:

```
**QA Verification Result:** Pass
**Test Execution:** {TE_KEY}
**Run:** {n} · {YYYY-MM-DD HH:mm}
**Environment:** {URL} · tenant {nnnnnnn} · build {x.y.z.nnn}

### Preconditions
- {precondition 1}
- {precondition 2}

### Test Results

| ID | Scenario | Expected | Actual | Status |
|---|---|---|---|---|
| PROJ-XXXX | {summary} | {expected result from AC/Gherkin} | {what was actually observed} | PASS |

Acceptance criteria and the coverage matrix: see the description of this Test Execution.
```

### Description is the plan; the comment is the record

**Do not repeat the AC validation table in the comment.** It already lives in the TE description, which
is the canonical copy. Duplicating it guarantees the two drift and nobody can tell which is current.

| Lives in the TE **description** | Lives in the TE **comment** |
|---|---|
| Acceptance criteria / derived requirements table | The run's results table |
| Coverage matrix — which case covers which requirement | What actually happened on this run |
| Blast radius measurement | Environment, build, run number |
| `Risk findings` — the full write-up per auto-cleared `oracle: risk` deviation | A two-or-three-line `Risk findings` entry per deviation, under `Conclusion` |
| `Observations for dev` (oracle-less findings) | Repro detail for anything that failed *on this run* |

If a run reveals the description is wrong — a requirement was misread, a case covers something else —
**fix the description** and say in the comment that you did. Don't correct it in a comment and leave the
description stale.

If an AC was verified outside the linked test cases (e.g. an extra scenario the user called out), append it as its own block after the table:

```
**Additional AC — {short label}:**
Expected: {expected}
Actual: {actual}
Status: {PASS/FAIL}
```

**When one or more tests failed**, drop the Test Results table for the failing scenario(s) and use a narrative Summary/Steps/Expected/Actual write-up instead — one block per failing scenario. This reads more clearly than a table row when there's a real defect to explain.

Two rules on that block:

- **Always summarise the passes too.** One line above the failure blocks — `6 of 8 cases passed` plus
  the standard table for them. Never omit it on the grounds that the failure is the only interesting
  thing: what still works narrows a developer's search as much as what broke.
- **Steps to Reproduce covers the failure and nothing else.** Start at the last known-good state and
  give only the steps that lead to the fault, with the failing step marked. Do not restate the whole
  test case, do not include setup that is already in Preconditions, and do not fold in steps from the
  cases that passed. A developer should be able to follow it top to bottom and hit the defect — every
  line that isn't on that path is noise that makes the repro look harder than it is.

```
**QA Verification Result:** Failed
**Test Execution:** {TE_KEY}
**Run:** {n} · {YYYY-MM-DD HH:mm}
**Environment:** {URL} · tenant {nnnnnnn} · build {x.y.z.nnn}

{n} of {m} cases passed — see the table above. The block below is the failure.

### Preconditions
- {precondition 1}
- {precondition 2}

### Summary
{One or two sentences: what's broken, and how it relates to what IS working/fixed, if relevant.}

### Steps to Reproduce
1. {step}
2. {step}
3. **{the step where it fails}** — {what happens instead}
...

### Expected Result
{What should happen per the AC/Gherkin.}

### Actual Result
{What actually happens — the observed defect.}
```

---

## Iron rules

- **Always transition the TE to In Progress and assign it to the current user at the start of a run (Step 1a)** — both automatic, no confirmation needed.
- **Never skip a test** — if it can't run, mark `BLOCKED` and explain why. There is no `ABORTED` on this instance.
- **Never mark PASS without running the test** — no assumptions.
- **Never invent the expected result.** If the case does not say what should happen and neither the AC
  nor the prior behaviour does, the case has no oracle: it cannot fail. Record what was observed under
  `Observations for dev` on the TE and leave the run un-failed.
- **Never post to Jira without confirmation.**
- **Never update Xray status without executing first.**
- **Never process next test before recording current result.**
- If Gherkin is missing or ambiguous, ask the user to clarify steps — do not guess.
- Manual tests always require user confirmation before marking result.

## Common mistakes

- Using `testRun.id` from `getTests` instead of `getTestExecution` — the run ID and issue ID are different. Get run IDs from the TE query.
- Using wrong status strings — this instance uses `PASSED`/`FAILED`/`BLOCKED`/`EXECUTING`/`TO DO`. Not `PASS`/`FAIL`, not `ABORTED`, not `TODO` without the space.
- Running all scripts first, recording results last — generate, run, and record one at a time.
- Treating empty `gherkin` field as "no test" — also check `steps { action data result }` for Manual tests.
- Not checking if the target app is running before executing Playwright tests.
