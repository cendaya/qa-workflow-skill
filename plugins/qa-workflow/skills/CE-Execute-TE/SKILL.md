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
2. Set the TE's **Assignee** to the current user via `editJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__editJiraIssue`), `fields: { assignee: { accountId: "<current user>" } }`. Resolve the accountId once with `atlassianUserInfo` (ToolSearch `select:mcp__plugin_atlassian_atlassian__atlassianUserInfo`) — never hardcode it.

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

If Playwright is not installed or app is not running, note the blocker and mark as `ABORTED`.

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

Xray Cloud status values: `PASSED`, `FAILED`, `EXECUTING`, `TODO`, `ABORTED`

Map results:
| Test outcome | Xray status |
|---|---|
| ✅ PASS | `PASSED` |
| ❌ FAIL | `FAILED` |
| BLOCKED / can't run | `ABORTED` |
| Skipped | `TODO` (leave unchanged) |

> If `updateTestRunStatus` is rejected, run introspection to verify mutation name:
> `{ __type(name: "Mutation") { fields { name } } }`
> Adjust and retry — do not guess repeatedly.

---

## Step 6 — Final report + Jira comment

Show complete results table. Ask:

> "Post results summary to {TE_KEY} in Jira? (yes / no)"

On "yes", load via ToolSearch `select:mcp__plugin_atlassian_atlassian__addCommentToJiraIssue`. Post using the **QA verification format** (confirmed standard — no Ticket/Tester/Date/Defects Found/Overall Verdict lines, no Steps column). Every post starts with a **QA Verification Result** line (`Pass` if every test run is `PASSED`, `Failed` if any run is `FAILED`/`ABORTED`) above the Test Execution line:

```
**QA Verification Result:** Pass
**Test Execution:** {TE_KEY}
**Environment:** {env name/URL, build/version if known}

### Preconditions
- {precondition 1}
- {precondition 2}

### Test Results

| ID | Scenario | Expected | Actual | Status |
|---|---|---|---|---|
| PROJ-XXXX | {summary} | {expected result from AC/Gherkin} | {what was actually observed} | PASS |
```

If an AC was verified outside the linked test cases (e.g. an extra scenario the user called out), append it as its own block after the table:

```
**Additional AC — {short label}:**
Expected: {expected}
Actual: {actual}
Status: {PASS/FAIL}
```

**When one or more tests failed**, drop the Test Results table entirely for the failing scenario(s) and use a narrative Summary/Steps/Expected/Actual write-up instead — one block per failing scenario. This reads more clearly than a table row when there's a real defect to explain (root cause, repro steps, evidence). Passing tests in the same TE can still be summarized in the standard table above this block, or omitted if the failure is the only thing worth calling out.

```
**QA Verification Result:** Failed
**Test Execution:** {TE_KEY}
**Environment:** {env name/URL, build/version if known}

### Preconditions
- {precondition 1}
- {precondition 2}

### Summary
{One or two sentences: what's broken, and how it relates to what IS working/fixed, if relevant.}

### Steps to Reproduce
1. {step}
2. {step}
...

### Expected Result
{What should happen per the AC/Gherkin.}

### Actual Result
{What actually happens — the observed defect.}
```

---

## Iron rules

- **Always transition the TE to In Progress and assign it to the current user at the start of a run (Step 1a)** — both automatic, no confirmation needed.
- **Never skip a test** — if it can't run, mark `ABORTED` and explain why.
- **Never mark PASS without running the test** — no assumptions.
- **Never post to Jira without confirmation.**
- **Never update Xray status without executing first.**
- **Never process next test before recording current result.**
- If Gherkin is missing or ambiguous, ask the user to clarify steps — do not guess.
- Manual tests always require user confirmation before marking result.

## Common mistakes

- Using `testRun.id` from `getTests` instead of `getTestExecution` — the run ID and issue ID are different. Get run IDs from the TE query.
- Using wrong status strings — Xray Cloud v2 uses `PASSED`/`FAILED`, not `PASS`/`FAIL`.
- Running all scripts first, recording results last — generate, run, and record one at a time.
- Treating empty `gherkin` field as "no test" — also check `steps { action data result }` for Manual tests.
- Not checking if the target app is running before executing Playwright tests.
