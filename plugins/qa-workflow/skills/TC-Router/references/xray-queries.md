# Xray Cloud GraphQL — operations reference

All calls go to `https://xray.cloud.getxray.app/api/v2`. Credentials come from the
`XRAY_CLIENT_ID` / `XRAY_CLIENT_SECRET` environment variables. **Never print the token or
secret.**

> Schema note: field names below match Xray Cloud's documented GraphQL schema. If a call
> is rejected, run the **introspection** query at the bottom and adjust field names to the
> live schema before retrying — do not guess repeatedly against the write endpoints.

## 0. Authenticate (token valid ~24h)

PowerShell:

```powershell
$body  = @{ client_id = $env:XRAY_CLIENT_ID; client_secret = $env:XRAY_CLIENT_SECRET } | ConvertTo-Json
$token = Invoke-RestMethod -Method Post -ContentType 'application/json' `
  -Uri 'https://xray.cloud.getxray.app/api/v2/authenticate' -Body $body
$headers = @{ Authorization = "Bearer $token" }
```

Helper to run a GraphQL doc (use this for every query/mutation below). It takes optional
**variables** — always pass user/Gherkin text through `$variables`, never by string-
concatenating it into the query, so quotes/backslashes/newlines in test steps can't break
the request:

```powershell
function Invoke-Xray($query, $variables = @{}) {
  $payload = @{ query = $query; variables = $variables } | ConvertTo-Json -Depth 20
  Invoke-RestMethod -Method Post -Uri 'https://xray.cloud.getxray.app/api/v2/graphql' `
    -Headers $headers -ContentType 'application/json' -Body $payload
}
```

The numeric **projectId** is required by folder operations. Get it from the Atlassian MCP
`getJiraIssue` response (`fields.project.id`), or from any test's `jira` project field
(query `jira(fields: ["project"])` in section 1 and read its `project.id`).

---

## 1. List existing tests + their folder (candidate set for updates)

Read tests by JQL and inspect each one's `folder.path`, then filter to the target module.
This avoids relying on folder-specific list fields.

```graphql
{
  getTests(jql: "project = '<jira.project_key>' AND issuetype = Test", limit: 100, start: 0) {
    total
    results {
      issueId
      jira(fields: ["key", "summary", "project"])
      testType { name }
      gherkin
      steps { id action data result }
      folder { path name }
    }
  }
}
```

`testType.name` is `Cucumber` or `Manual`. Read `gherkin` for Cucumber candidates and
`steps { action data result }` for Manual candidates — you need the current value to build
the UPDATE diff. The folder's predominant `testType` sets the per-case default in step 6.

`limit` maxes at 100. If `total` > the number returned, **page** by re-running with
`start: 100`, `start: 200`, … until you've read `total`, or narrow the JQL (e.g. add
`AND summary ~ "<module keyword>"`) so the candidate set fits. Do not silently stop at
100 — missing existing tests causes duplicate NEW cases.

Keep results where `folder.path` equals (or is under) `/<Module>` — e.g.
`/Measurement Assistant`. Those are the UPDATE candidates. Read `project.id` here if you
still need the numeric projectId.

## 2. Confirm a module folder exists

```graphql
{
  getFolder(projectId: "<PROJECT_ID>", path: "/Measurement Assistant") {
    name
    path
    testsCount
    folders
  }
}
```

If this returns null / errors for a missing path, surface it and ask the user whether to
create the folder (do not create silently). Create only on approval:

```graphql
mutation {
  createFolder(projectId: "<PROJECT_ID>", path: "/Measurement Assistant") {
    folder { name path }
    warnings
  }
}
```

## 3. Create a new Gherkin test

Pass `gherkin` and `jira` as **variables** so quotes/backslashes/newlines in the scenario
or description are handled safely — never concatenate them into the query string. The
`description` variable carries the labeled Description/Preconditions block (see SKILL.md
field mapping); real newlines in the PowerShell string are fine.

```powershell
$query = @'
mutation CreateGherkinTest($gherkin: String!, $jira: JSON!) {
  createTest(testType: { name: "Cucumber" }, gherkin: $gherkin, jira: $jira) {
    test { issueId jira(fields: ["key"]) }
    warnings
  }
}
'@
$vars = @{
  gherkin = "Scenario: <name>`n  Given ...`n  When ...`n  Then ..."
  jira = @{
    fields = @{
      summary     = "<test title>"            # action-first, no "Verify" prefix
      project     = @{ key = "<jira.project_key>" }
      description = "Description:`n<what/why>`n`nPreconditions:`n- <p1>`n- <p2>"
      labels      = @("<jira.project_key>")                    # product key + any suite/feature tags
      components  = @(@{ name = "<Component>" }) # must already exist in the project
    }
  }
}
$resp = Invoke-Xray $query $vars
```

`labels` / `components` are standard Jira fields forwarded through `jira.fields` (Component
names must pre-exist). Capture `test.issueId` and the new key for the next steps —
including the Test Set add (section 7) and Automation Status (section 8).

> **Description formatting warning.** The `description` string passed via `jira.fields`
> in `createTest` renders with broken `1. a. i.` outline formatting in Jira — markdown
> headings (`### Objective`) are not honoured. After creating all tests, update every
> description via the Atlassian MCP `editJiraIssue` with `contentFormat: "markdown"`,
> passing the description as plain markdown (`**Objective**`, `- bullet`). Batch all
> updates after all `createTest` calls complete.

## 3b. Create a new Manual test

Same `jira` (summary + labeled description), but `testType` is **Manual** and the body is
`steps` — an array of `{ action, data, result }` rows. Pass `steps` and `jira` as
variables.

```powershell
$query = @'
mutation CreateManualTest($steps: [CreateStepInput], $jira: JSON!) {
  createTest(testType: { name: "Manual" }, steps: $steps, jira: $jira) {
    test { issueId jira(fields: ["key"]) }
    warnings
  }
}
'@
$vars = @{
  steps = @(
    @{ action = "<do this>";        data = "<input value>"; result = "<expected outcome>" }
    @{ action = "<then do this>";   data = "";              result = "<expected outcome>" }
  )
  jira = @{
    fields = @{
      summary     = "<test title>"
      project     = @{ key = "<jira.project_key>" }
      description = "Description:`n<what/why>`n`nPreconditions:`n- <p1>`n- <p2>"
      labels      = @("<jira.project_key>")
      components  = @(@{ name = "<Component>" })
    }
  }
}
$resp = Invoke-Xray $query $vars
```

For **Both**, run section 3 and 3b for the same case (two separate tests), then fold both
issueIds into the section 4 batch and link both in section 6.

## 4. Place the new test in the module folder

```graphql
mutation {
  addTestsToFolder(
    projectId: "<PROJECT_ID>"
    path: "/Measurement Assistant"
    testIssueIds: ["<NEW_ISSUE_ID>"]
  ) {
    folder { path testsCount }
    warnings
  }
}
```

> **Index lag (transient).** Right after `createTest`, the new issue may not be indexed,
> so this call can fail with `Error adding tests to folder: tests with ids … don't exist
> on Jira.` Don't treat it as a real failure — wait a few seconds and retry. Best pattern:
> create all NEW tests first, collect their issueIds, then call `addTestsToFolder` once
> with the whole batch (retry that single call until it succeeds, a couple of attempts).

## 5. Update an existing test

**Append/modify/replace only when the chosen type matches the candidate's `testType`.**
Mixing types needs `updateTestType`, which **wipes the existing definition** — don't;
create NEW of the chosen type instead (see SKILL.md cross-type guard).

### 5a. Cucumber test

- **Append:** read its current `gherkin` (section 1), append the new `Scenario:` blocks in
  your code (keep existing scenarios; skip a block that already exists verbatim). Send the
  combined text.
- **Modify:** read the current `gherkin`, edit only the lines inside the affected
  scenario(s) in your code, leave the other scenarios byte-for-byte unchanged, send the
  merged text.
- **Replace:** send only the new gherkin.

```powershell
$query = @'
mutation UpdateGherkin($issueId: String!, $gherkin: String!) {
  updateGherkinTestDefinition(issueId: $issueId, gherkin: $gherkin) { issueId gherkin }
}
'@
Invoke-Xray $query @{ issueId = "<ISSUE_ID>"; gherkin = $fullGherkinText }
```

### 5b. Manual test

- **Append:** `addTestStep` once per new row. New rows land **at the end**, after existing
  steps. Read current `steps` (section 1) first and **skip any proposed row whose
  `action` + `data` + `result` already exist verbatim** (the Manual dedup key, mirroring
  the Gherkin "verbatim Scenario" rule). The `#` shown in the markdown table is
  display-only — it is not the Xray step index.
- **Modify:** `updateTestStep` on each existing row being tweaked, keyed by its **stepId**
  (from section 1). Pass all three of `action` / `data` / `result` — set the unchanged ones
  to their current values so nothing is blanked — and leave untouched rows alone. Combine
  with `addTestStep` when the same case also adds rows. `updateTestStep` takes only
  `stepId` + `step` (**no `issueId`**) and returns an `UpdateTestStepResult` wrapper — select
  `{ warnings }`, **not** step fields (the step's own fields aren't on that type).
- **Replace:** deterministic reset — `removeTestStep` every existing row, then
  `addTestStep` the new set in order. Do **not** update in place; a count mismatch between
  old and new rows would otherwise orphan or drop rows. `removeTestStep` takes **only
  `stepId`** — no `issueId` argument.

> **Signature note:** `removeTestStep(stepId: String!)` and
> `updateTestStep(stepId: String!, step: UpdateStepInput!)` are keyed by **stepId alone** —
> passing `issueId` to either is a schema mismatch that will get rejected. Confirm against
> the introspection query at the bottom of this file if a call errors.

```powershell
$addStep = @'
mutation AddStep($issueId: String!, $step: CreateStepInput!) {
  addTestStep(issueId: $issueId, step: $step) { id action data result }
}
'@
foreach ($s in $newRows) {        # append: $newRows already deduped against current steps
  Invoke-Xray $addStep @{ issueId = "<ISSUE_ID>"; step = @{ action = $s.action; data = $s.data; result = $s.result } }
}

# modify: update specific existing rows in place, keyed by stepId (no issueId arg).
# Pass all three fields; keep unchanged ones at their current value.
$updStep = @'
mutation UpdStep($stepId: String!, $step: UpdateStepInput!) {
  updateTestStep(stepId: $stepId, step: $step) { warnings }
}
'@
Invoke-Xray $updStep @{ stepId = "<STEP_ID>"; step = @{ action = "<current or new>"; data = "<current or new>"; result = "<current or new>" } }

# replace: remove every existing row (ids from section 1), then add the new set in order.
# removeTestStep takes ONLY stepId — no issueId.
$rmStep = @'
mutation RmStep($stepId: String!) { removeTestStep(stepId: $stepId) }
'@
foreach ($id in $existingStepIds) { Invoke-Xray $rmStep @{ stepId = $id } }
foreach ($s in $newRows)         { Invoke-Xray $addStep @{ issueId = "<ISSUE_ID>"; step = @{ action = $s.action; data = $s.data; result = $s.result } } }
```

## 6. Link a test to the ticket (as "tests")

Xray requirement coverage uses the Jira issue link type **Test**. The TC/TE must be
the **inward** issue and the ticket must be the **outward** issue — this makes the ticket
page show "is tested by [TC]". Create it via the Atlassian MCP (load with ToolSearch
`select:mcp__plugin_atlassian_atlassian__createIssueLink`):

- `type` name: `Test`
- **inwardIssue**: the **new test/TE key** — TC/TE page shows "tests [ticket]"
- **outwardIssue**: the **ticket** (e.g. `PROJ-9123`) — ticket page shows "is tested by [TC]"

> **Empirically verified (PROJ-9165):** `inwardIssue = TC key, outwardIssue = defect key`
> produces "is tested by [TC]" on the defect. The reverse (inward = defect) produces
> "tests [TC]" — wrong direction. Follow the inward = TC/TE rule exactly.

If the `Test` link type name differs in this Jira, list types first with
`select:mcp__plugin_atlassian_atlassian__getIssueLinkTypes` and use the matching name.

## 7. Add the test to a Test Set (best practice: ≥1 per test)

Find an existing Test Set for the module/feature, then add the new test(s). **Never create
a set silently** — ask first (mirrors the folder rule).

```graphql
{ getTestSets(jql: "project = '<jira.project_key>' AND summary ~ '<Module>'", limit: 20, start: 0) {
    results { issueId jira(fields: ["key","summary"]) } } }
```

```powershell
$query = @'
mutation AddToSet($setId: String!, $testIds: [String]!) {
  addTestsToTestSet(issueId: $setId, testIssueIds: $testIds) { addedTests warning }
}
'@
Invoke-Xray $query @{ setId = "<TESTSET_ISSUE_ID>"; testIds = @("<NEW_ISSUE_ID>") }
```

Only on user approval, create one — but **lazily**: the user confirms the *name* during
per-case approval (step 6), and you call `createTestSet` only on the **first successful
test write** in step 8, reusing the returned id for the rest of the run. This avoids an
empty set when every case is skipped.

Name a new set **`<Product> - <Module>`** and set its **Product** single-select field to
the name's product prefix. The field id is `jira.product_field` and the option ids are in
`jira.product_options`, both in `qa-config.json`. Pass Product right in the `createTestSet`
`jira.fields` (below), or set it after create via the Atlassian MCP `editJiraIssue`. Skip
the Product field entirely when `jira.product_field` is `null`. See SKILL.md Field
mapping → Test Set.

```powershell
$query = @'
mutation NewSet($jira: JSON!) {
  createTestSet(jira: $jira) { testSet { issueId jira(fields: ["key"]) } warnings }
}
'@
$set = Invoke-Xray $query @{ jira = @{ fields = @{
  summary = "<Product> - <Module>"; project = @{ key = "<jira.project_key>" }
  <jira.product_field> = @{ id = "<option id from jira.product_options>" }   # omit when product_field is null
} } }
# capture $set...testSet.issueId, then addTestsToTestSet as above
```

## 8. Set Automation Status + Work Breakdown (Jira custom fields — via Atlassian MCP, not Xray)

Neither field is in the Xray `Test` GraphQL type — both are Jira custom fields, set after
create via the Atlassian MCP. Resolve their field ids from the Test issue type, then set the
**values approved in step 6**:

- **Automation Status** — default new tests to `Not Automated` (user may have bumped it to
  `Can be Automated`, or `Manual Only` for a test that can't be automated).
- **Work Breakdown** — default `Core (Default)` (user may have overridden it to a swarm
  initiative).

1. `getJiraIssueTypeMetaWithFields` (project `<jira.project_key>`, issuetype `Test`) → find each field and
   its `customfield_NNNNN` id and the option value/id.
2. `editJiraIssue` setting each field to the matching option.

If a field or option can't be resolved, **don't fail** — record the intended value in the
report for the user to set manually.

---

## 9. Test Execution context — open Test Plans, existing execution, ticket's tests

Run these in step 4 (so the context is known before writes) and again in step 9 as needed.

### 9a. List the board's open Test Plans (user picks one in step 9)

```graphql
{ getTestPlans(jql: "project = '<jira.project_key>' AND issuetype = 'Test Plan' AND status != Done ORDER BY created DESC",
    limit: 50, start: 0) {
    total
    results { issueId jira(fields: ["key", "summary", "status"]) }
  } }
```

The `ORDER BY created DESC` keeps the **newest plans first** — present them to the user in
that order. Present the list and let the user choose (always, even if only one comes back).
If `total` is 0, ask whether to create a plan (section 10c) or skip the link.

### 9b. Find an existing Test Execution for this ticket (dedupe)

Match on the summary the skill assigns: `<TICKET> | <Module>-<short description>`. Reuse
it instead of creating a duplicate; read its current `tests` so you only add what's
missing.

```graphql
{ getTestExecutions(jql: "project = '<jira.project_key>' AND issuetype = 'Test Execution' AND summary ~ 'PROJ-9123'",
    limit: 10, start: 0) {
    results {
      issueId
      jira(fields: ["key", "summary"])
      tests(limit: 100) { results { issueId } }
    }
  } }
```

`summary ~ 'PROJ-9123'` is a contains-match; confirm the result's summary actually starts
with `PROJ-9123 | ` before treating it as the reuse target (a `~` match can be loose).

### 9c. Collect every test that "is tested by"-links the ticket

Step 9 adds **all** the ticket's coverage, not just this run's. Union this run's new/updated
issueIds with the tests already linked to the ticket. Read the ticket's links via the
Atlassian MCP `getJiraIssue` (`fields: ["issuelinks"]`): keep links of type **Test** where
the ticket reads **"is tested by"** the other issue, then resolve those keys to issueIds:

```graphql
{ getTests(jql: "project = '<jira.project_key>' AND key in (PROJ-401, PROJ-402)", limit: 100) {
    results { issueId jira(fields: ["key"]) }
  } }
```

De-dupe the union by issueId before adding to the execution.

## 10. Create / reuse a Test Execution and link it to a Test Plan

### 10a. Create a new execution (when 9b found none)

`testIssueIds` seeds it with the collected tests; `jira.fields` carries the summary,
**description (mandatory — see SKILL.md step 9 template, never left blank)**, and
component. **Do not set `assignee`** — leave whatever Jira applies. Summary format is
`<TICKET> | <Module>-<short description of what is being tested>`.

> **Do not skip `description` here.** It has been omitted in past runs because this example
> only showed `summary`/`project`/`components` — copying it verbatim silently drops the
> Summary/Context/Acceptance criteria/Other information template from SKILL.md step 9. Build
> that template string *before* calling `createTestExecution` and always include it as
> `jira.fields.description` in the same call — don't plan to add it later via a follow-up
> `editJiraIssue`, which is easy to forget once the tests are already created.

```powershell
$query = @'
mutation NewExec($testIds: [String], $jira: JSON!) {
  createTestExecution(testIssueIds: $testIds, jira: $jira) {
    testExecution { issueId jira(fields: ["key"]) }
    warnings
  }
}
'@
$vars = @{
  testIds = @("<ISSUE_ID_1>", "<ISSUE_ID_2>")
  jira = @{ fields = @{
    summary     = "PROJ-9123 | Measurement Assistant-Multi-polygon area calculation"
    project     = @{ key = "<jira.project_key>" }
    description = "### Summary`nTest Execution for PROJ-9123: <ticket summary>.`n`n### Context`n<technical description>`n`n### Acceptance criteria`n* <AC bullet>`n`n### Other information`n* Testing checklist:`n    * <QA checklist item>"
    components  = @(@{ name = "<Component>" })          # ticket's, else folder's predominant
  } }
}
$exec = Invoke-Xray $query $vars
# capture $exec...testExecution.issueId and key
```

### 10b. Reuse an existing execution (when 9b found one)

Add only the tests it doesn't already hold (compare against `tests` from 9b). The call is
idempotent enough — already-present tests are ignored — but filtering keeps the warning noise
down.

```powershell
$query = @'
mutation AddToExec($execId: String!, $testIds: [String]!) {
  addTestsToTestExecution(issueId: $execId, testIssueIds: $testIds) { addedTests warning }
}
'@
Invoke-Xray $query @{ execId = "<EXEC_ISSUE_ID>"; testIds = @("<ISSUE_ID>", "...") }
```

### 10c. Link the execution to the chosen Test Plan

```powershell
$query = @'
mutation LinkExecToPlan($planId: String!, $execIds: [String]!) {
  addTestExecutionsToTestPlan(issueId: $planId, testExecIssueIds: $execIds) {
    addedTestExecutions warning
  }
}
'@
Invoke-Xray $query @{ planId = "<TESTPLAN_ISSUE_ID>"; execIds = @("<EXEC_ISSUE_ID>") }
```

Then **copy the execution's tests into the plan** — the same collected, de-duped test set
that seeds the execution (section 9c). The execution link above associates the *execution*
with the plan but does **not** add those tests to the plan's own test list, so add them
explicitly. Idempotent — tests already in the plan are ignored.

```powershell
$query = @'
mutation AddTestsToPlan($planId: String!, $testIds: [String]!) {
  addTestsToTestPlan(issueId: $planId, testIssueIds: $testIds) { addedTests warning }
}
'@
Invoke-Xray $query @{ planId = "<TESTPLAN_ISSUE_ID>"; testIds = @("<ISSUE_ID_1>", "<ISSUE_ID_2>") }
```

Create a Test Plan only on explicit approval (no open plan + user said yes) — confirm its
summary first (e.g. `<sprint dates> Sprint | Release Regression`):

```powershell
$query = @'
mutation NewPlan($jira: JSON!) {
  createTestPlan(jira: $jira) { testPlan { issueId jira(fields: ["key"]) } warnings }
}
'@
$plan = Invoke-Xray $query @{ jira = @{ fields = @{
  summary = "<confirmed plan name>"; project     = @{ key = "<jira.project_key>" } } } }
# then addTestExecutionsToTestPlan AND addTestsToTestPlan with $plan...testPlan.issueId
```

---

## Introspection (only if a call is rejected)

```graphql
{ __type(name: "Test") { fields { name } } }
{ __type(name: "Mutation") { fields { name } } }
{ __type(name: "Folder") { fields { name } } }
{ __type(name: "Step") { fields { name } } }
{ __type(name: "CreateStepInput") { inputFields { name } } }
{ __type(name: "UpdateStepInput") { inputFields { name } } }
{ __type(name: "TestExecution") { fields { name } } }
{ __type(name: "TestPlan") { fields { name } } }
```
