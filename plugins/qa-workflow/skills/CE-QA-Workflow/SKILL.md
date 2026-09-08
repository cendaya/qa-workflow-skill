---
name: CE-QA-Workflow
description: Use when starting QA on a Jira ticket assigned to you — optionally uses CE-ForTesting to find and pick a ticket if none is provided, then runs CE-AC-Validator to confirm the PR satisfies the full ticket, and automatically routes to TC-Router (CE-TC-UI / CE-TC-API / CE-TC-Perf) to generate test cases. Single entry point for the full QA workflow. Triggers include "start testing PROJ-XXXX", "I'm testing PROJ-XXXX", "QA workflow for PROJ-XXXX", "ticket assigned to me PROJ-XXXX", "begin QA on PROJ-XXXX", "test this ticket PROJ-XXXX", "find me something to test", "what should I test", "pick a ticket".
---

# CE-QA-Workflow

Single entry point for the full QA lifecycle. Chains four skills in sequence:

0. **CE-ForTesting** — find and pick an unowned "Ready for Testing" ticket (only when no ticket is provided)
1. **CE-AC-Validator** — confirm the merged PR satisfies the entire ticket
2. **TC-Router** — generate Xray test cases of the correct type (UI / API / Performance)
3. **CE-Execute-TE** — execute the generated test cases and record results in Xray

Nothing moves to test case generation until validation either passes or the user explicitly approves proceeding despite failures.

Two outputs are non-negotiable on every run, regardless of ticket size:

- **Phase 0a** — a plain-English briefing, delivered *first*, before any validation or tool use.
- **Phase 2.2** — a test-case table written into the Test Execution's description.

## Inputs (ask for any that are missing)

1. **Ticket** — e.g. `PROJ-9123`. If not provided, run CE-ForTesting first to find and assign one.
2. **PR** — optional. CE-AC-Validator finds it automatically from the ticket; provide if that fails.

## Workflow

Create a TodoWrite item per step.

---

### Pre-flight — Ticket selection via CE-ForTesting

**If no ticket key was provided**, invoke the full **CE-ForTesting** workflow before anything else:

- Fetch "Ready for Testing" tickets not owned by other QA members
- Rank by ease of testing (Easy / Moderate / Harder)
- Wait for user to select a ticket key — never auto-select
- Assign the selected ticket to the current user (resolve the accountId via `atlassianUserInfo`)
- Then continue into the workflow below with that ticket key

**If a ticket key was already provided**, skip this step entirely and proceed to the plain-English briefing.

---

### Phase 0a — Plain-English briefing (MANDATORY, before any testing)

**The first thing the user sees on every ticket.** Before Phase 0, before the In QA transition, before any
validation, probing, or tool-driven work: read the ticket (`getJiraIssue`, load via ToolSearch
`select:mcp__plugin_atlassian_atlassian__getJiraIssue`) and hand back a briefing a non-engineer could act on.

This exists because the QA engineer needs to know *what they are actually testing and why it matters* before
drowning in AC tables, diffs and criterion numbers. Never skip it because the change "is only one line" — a
one-line change with a production blast radius is exactly when the briefing matters most.

Use this shape, in this order:

```
**What changed:** <one or two sentences, no jargon. Name the real-world thing, not the class.>

**Why it's high stakes:** <the blast radius in user-visible terms — what breaks, for whom, and how visibly.>

**What needs testing — <N> things:**

1. **<Short bold label.>** <What to do and what "correct" looks like.>
2. ...

**One catch to remember:** <the trap that will waste their time or mislead them if they hit it.>
```

Rules for the briefing:

- **No unexplained jargon.** Name the tool or system in parentheses on first use — "Sigma (the analytics
  tool)", "Xray (the test-management add-on)". Never leave a bare product name, class name, or acronym.
- **Reference behaviour, not code.** Say "the bookmark 'created by' name goes blank" — not
  `createdByName` is null. File and symbol names belong in the gap list, not here.
- **Frame no-op regressions explicitly.** When the correct outcome is "nothing looks different", say so —
  "Boring = correct" — so the tester doesn't hunt for a visible change that shouldn't exist.
- **Give the best tell.** For each area, name the single cheapest observable that proves breakage
  (a field that blanks, a name that disappears, a count that splits). Testers need a tripwire, not a theory.
- **Call out destructive traps in the briefing itself**, not just in the test steps — e.g. "never edit the
  real embed user; that permanently breaks it, make a new decoy instead". A trap discovered at execution
  time has already cost something.
- **The "one catch" is for lies and landmines** — behaviour that will actively mislead: an error message
  that misreports its own cause, a metric that looks healthy while broken, a pass that only holds until a
  cutoff date. If there is genuinely no such catch, write "No traps on this one." rather than inventing one.
- **Numbered list maps to the QA criteria**, but uses the user's language, not criterion numbers. Keep the
  criterion mapping for the Phase 1 table.
- Keep it to what fits on one screen. If the ticket needs more than ~8 numbered items, group them.

**Worked example** (ADA-4892, a one-line Sigma query-parameter swap — abridged):

> **What changed:** one line. The service looks up a user in Sigma (the analytics tool) by email address.
> It used to ask using a parameter named `search`. Sigma turns `search` off on 2026-09-15, so it now asks
> using `email`.
>
> **Why it's high stakes:** that lookup happens every time someone opens an embedded dashboard. Break it
> and analytics dies for every product — no dashboards, no exports, no bookmarks.
>
> **What needs testing — 7 things:**
>
> 1. **Nothing looks different.** Open a dashboard as a known test user in PestPac, then one other product.
>    It should load as that user exactly as before. Boring = correct.
> 2. **Everything downstream still works.** Dashboard, export + download, bookmarks list,
>    create/share/delete a bookmark, get/set default view. Watch the bookmark "created by" name — it goes
>    blank if the lookup breaks. Best tell you have.
> 3. **A user who isn't in Sigma gets a clean "not found"**, not a 500 crash.
> 4. **Prefix trap.** The new `email` parameter matches anything *starting with* what you type —
>    `bob@work.com` also returns `bob@work.com.au`. Code has a filter that keeps only the exact match. Test
>    it by making a **brand-new fake** Sigma user = a real test user's email + `.au`, confirm the real user
>    still resolves, then delete the fake. Never edit the real embed user — that permanently breaks it.
> 5. **Things that should NOT have changed.** Business Areas, its member list, team setup — they use the
>    same word `search` but on different Sigma endpoints and were left alone on purpose. Check they work;
>    proves nobody did a careless find-and-replace.
> 6. **Monitoring didn't split.** In Grafana, `search_members` should be one continuous line across the
>    deploy — no gap, no second line.
> 7. **Re-check 2026-09-16**, the day after Sigma pulls the plug, in dev + staging + prod.
>
> **One catch to remember:** if this ever does fail, the error message **lies** — it says "user not found"
> instead of "Sigma is down", because of a separate already-known bug. So on 2026-09-16, don't trust a
> not-found at face value.

Note what that example does: every item is an action with a visible outcome, the destructive trap is stated
inline at item 4 rather than buried in a test step, item 1 pre-empts the "I can't see any change" confusion,
and the closing catch warns about an error message that misreports its own cause.

After delivering the briefing, continue straight into the In QA transition and Phase 0 — the briefing is
informational and does **not** block. But if the user asks anything about it, answer that first.

---

### Ticket transition — In QA

At the start of the workflow, offer to move the ticket to the QA-in-progress state.

Load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getTransitionsForJiraIssue`, fetch available transitions. Find one named "In QA", "Testing", "In Testing", or equivalent. Ask: "Transition <TICKET> to In QA? (yes / no)". On "yes", call `transitionJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__transitionJiraIssue`).

If no matching transition found, note it and continue — never block the workflow.

---

### Phase 0 — Historical defect pattern analysis

Search for past bugs in the same component/module to know where to test harder.

Load via ToolSearch `select:mcp__plugin_atlassian_atlassian__searchJiraIssuesUsingJql`. Run:
- Primary: `issuetype = Bug AND component = "<ticket component>" AND project = "<project key>" ORDER BY created DESC` (limit 20)
- Fallback (no component): `issuetype = Bug AND text ~ "<module keyword from ticket summary>" AND project = "<project key>" ORDER BY created DESC` (limit 10)

Extract recurring areas (same field, flow, or endpoint appearing 2+ times) and bug types (validation gaps, race conditions, permission errors). Output a **Historical risk summary** — max 5 bullets — carried forward to:
- Phase 1: flag which AC requirements overlap with past failures (scrutinize those harder)
- Phase 2: ensure test cases cover historically buggy paths

Skip and note "historical analysis skipped — no component/module context" if the ticket has no component and no clear module keyword.

---

### Phase 1 — Validate: does the PR satisfy the ticket?

**Run the full CE-AC-Validator workflow on this ticket.** Follow every step of that skill exactly:

- Read the full ticket (summary, description, AC, engineering notes, QA notes)
- Find the linked GitHub PR via remote issue links → GitHub search → ask user
- Read the diff
- Check linked Xray tests + CI status
- Validate each requirement, produce the pass/fail report

### Phase 1.5 — Regression check + flaky test detection

After the CE-AC-Validator report, before the gate decision, verify the module's existing test baseline.

**Regression check:** JQL via `searchJiraIssuesUsingJql`: `issuetype = "Test Execution" AND component = "<ticket component>" ORDER BY created DESC` — fetch last 5 TEs. If no component, try TEs linked to the ticket's epic or label.

| TE Status | Action |
|-----------|--------|
| All green across last 5 TEs | Note "Module regression baseline: clean ✅" |
| Has failures | Warn: "Existing module tests show failures — review before QA. May not be caused by this ticket." |
| No TE found | Note "No recent Test Execution found for this module" |

**Flaky test detection:** For tests linked to this module, compare results across the last 5 TEs. A test is **flaky** if it alternates pass/fail without a code change between runs. List flaky test keys and names with the note: "Unreliable — results on this ticket may be noise."

Informational only — does not block the gate.

---

### Phase 1.6 — Gap analysis (D1..Dn)

The AC verdict table in Phase 1 says *whether* each requirement is met. The gap list says *what is wrong* — including problems that sit outside the AC wording entirely and would otherwise go unrecorded. Produce it for every ticket, after the validation report and before the gate decision.

Write one entry per finding, numbered `D1..Dn`:

| Field | Content |
|-------|---------|
| **ID** | `D1`, `D2`, … stable within this ticket, referenced by the test cases and the TE |
| **Severity** | High / Medium / Low / Info. `Info` is for observations that need a decision, not a fix |
| **Finding** | What is wrong, in one or two sentences. Name the file, constant or function where the cause sits |
| **Repro** | The concrete input, payload or state that triggers it — enough for a dev to reproduce without asking |
| **Covered by** | The test case key that will exercise it (filled in during Phase 2) |

What belongs in the gap list beyond outright AC failures:

- **Conditional passes** — an AC met only for the inputs the code happens to handle (a closed set of enum values, a type vocabulary, a locale)
- **Spec conflicts** — an AC that contradicts a sibling ticket, cites a criterion that does not exist, or depends on an unbuilt story
- **Unratified decisions** — an open question on the ticket that the code has already answered. Flag it to be closed, not built
- **Wrong-fallback behaviour** — the code degrades safely but not the way the ticket says it should
- **CI and test-infrastructure risk** — flaky, slow or timeout-marginal tests. Mark these clearly as *not a product defect* so they are not mistaken for AC failures
- **Unit-coverage gaps** — the assertion that would have caught the finding, written as a note for dev

Confirming a suspected finding:

1. Write the smallest probe test that proves it, run it, and capture the actual numbers or output
2. **Delete the probe and leave the working tree clean.** QA's output is findings, not a patch — a probe left behind lands in someone else's PR scope, and a failing one breaks CI
3. Record the evidence in the finding: the measured values, not "appears to overlap"

Carry the gap list forward:

- Phase 2 — every gap must be covered by a test case. A gap expected to fail is still a case; title it so the expected failure is obvious and say so in the case's Notes
- Phase 3 — the full gap list goes in the **TE description and as a comment on the TE**, not on the story
- Do **not** open a Defect ticket straight from a gap unless the user asks. A gap is a code-review finding; a defect is what it becomes once manual execution confirms user impact

If the review turns up no gaps, say so explicitly — "gap analysis: no findings beyond the AC table" — rather than omitting the section.

---

After the report is produced, determine the **validation outcome**:

| Outcome | Condition |
|---------|-----------|
| ✅ **Full pass** | All requirements pass or N/A — proceed automatically to Phase 2 |
| ⚠️ **Partial** | Some requirements partial or need manual check — ask: "Some requirements are partial or unverifiable. Proceed to test case generation?" |
| ❌ **Fail** | One or more requirements fail — show the failures, then ask: "Validation found failures. Options: (1) Proceed to test case generation anyway, (2) Stop and raise failures with the dev team, (3) Re-run validation after fixes, (4) Auto-file bugs for each ❌ failure via CE-Create-Bug." |

If user picks **option 4**: show a preview of each bug that would be created:

```
The following bugs will be created in Jira:
1. [<TICKET>] <requirement text> — not implemented
2. [<TICKET>] <requirement text> — not implemented
...

Confirm? (yes / no / edit first)
```

**Wait for explicit confirmation before creating any Jira issue.** On "yes": for each ❌ Fail requirement, follow the CE-Create-Bug skill to file a bug pre-filled with:
- Summary: `[<TICKET>] <requirement text> — not implemented`
- Description: the requirement text, what was missing in the diff, PR URL
- Link to the original ticket (`createIssueLink` type Test)

After filing bugs, ask: "Bugs filed. Proceed to Phase 2 (test case generation) or stop here?"

**Wait for user decision on Partial or Fail before continuing.** Never auto-proceed past a failure.

---

### Phase 2 — Generate: create Xray test cases via TC-Router

Once validation passes (or user approves proceeding):

**Run the full TC-Router workflow on this ticket.** TC-Router step 0 detects test type and routes:

- **API ticket** → CE-TC-API (happy path + edge + negative scenarios, smoke test, Postman JSON)
- **UI ticket** → CE-TC-UI (happy path + edge + negative scenarios)
- **Performance ticket** → CE-TC-Perf (baseline + load + overload, k6 script, smoke test)
- **Mixed / unclear** → TC-Router asks user which type, then proceeds

Carry forward context from Phase 1:
- The ticket's full requirements list — use it to ensure test cases cover every validated requirement
- Any requirements flagged as "manual check needed" in validation → generate explicit Manual test cases for those
- Out-of-scope changes flagged in Phase 1 → do NOT generate test cases for them (they're not in the ticket)

---

### Phase 2.2 — Test-case table on the TE (MANDATORY on every Test Execution)

Once TC-Router has created the TE, its description must carry a **table of the test cases it holds**. A TE
whose description lists only acceptance criteria forces the reader to click through every linked test to find
out what is actually covered. The table makes the TE self-contained — the one artifact an executor needs.

Add (or update) this section in the TE description:

```
### Test cases in this execution

| Case | Key | Part | Title | Covers |
| --- | --- | --- | --- | --- |
| <S1> | <TC key> | <group> | <test title> | <criteria numbers; gap IDs> |
```

- **Case** — the short draft id from Phase 2 (`S1`, `E3`, `G1`, …), so the TE, the report and the gap list all
  use one vocabulary.
- **Key** — the Xray test key.
- **Part** — the logical group the case belongs to (see grouping below). Use `—` when the ticket has no
  natural grouping.
- **Covers** — the AC/criterion numbers **and** any Phase 1.6 gap IDs (`D2`, `D6`) the case exercises. This is
  what makes the table auditable against Phase 1.

Immediately after the table, state:

- The shared attributes, once, rather than repeating them per row — test type, label, Automation Status,
  Work Breakdown. E.g. "All seven are Manual, label `ADA`, Automation Status `Not Automated`, Work Breakdown
  `Core (Default)`."
- **Execution grouping and its prerequisites** — for each group, the credential or access needed to run it.
  Groups usually have *different* blockers, and an executor must be able to see that one group is runnable
  today while another waits on a token. Prefer grouping by **what it takes to run** (a service token, an
  upstream admin console, an observability stack) over grouping by endpoint.
- **Any criterion with no test case, and why** — e.g. "Criteria 6 and 7 have no test case by design: they are
  a build result and a repo-wide string search, not black-box observables." Silence reads as an oversight;
  an explicit line reads as a decision.

**Writing it:** the description field is a Jira field, not an Xray GraphQL field. Set it via
`editJiraIssue` (load via ToolSearch `select:mcp__claude_ai_Atlassian__editJiraIssue`) with
`contentFormat: "markdown"`.

**Do not append markdown onto a description that is already wiki markup** (`h3.`, `{{mono}}`) — the two
render differently and the result is a mess. Rewrite the whole description in markdown in one call so the
format is consistent. Keep every existing section (Summary, Context, Acceptance criteria, Other information,
checklists) and add the table; never drop content to make the edit easier.

If the description write fails, record the intended table in the Phase 3 report and continue — never block
execution on it.

---

### Phase 2.5 — Execute: run test cases via CE-Execute-TE

Once TC-Router completes and a Test Execution (TE) ticket exists, **invoke CE-Execute-TE** with the TE key.

The TE key comes from TC-Router's output. If TC-Router did not create a TE, ask: "Enter the Test Execution key to run (e.g. PROJ-XXXX), or type 'skip' to go to Phase 3."

**Run the full CE-Execute-TE workflow.** That skill will:
- Fetch all test runs in the TE via Xray GraphQL
- Detect tool per test (Playwright / Postman / k6 / Manual) from Gherkin content and labels
- Execute each test case one at a time
- Update pass/fail status in Xray for each test run
- Show live results as tests complete

Carry execution results into Phase 3:
- Tests **FAILED** → add to "Open items" with test key + failure detail
- Tests **ABORTED** → flag for manual follow-up with reason
- Tests **PASSED** → note coverage verified

**After all test runs are updated, transition the TE to Done automatically:**

Load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getTransitionsForJiraIssue`, fetch transitions for the TE key. Find the transition named "Done" (or equivalent). Call `transitionJiraIssue` with the matched transition id. No confirmation needed — TE closure is automatic once all runs are recorded.

If no "Done" transition is found, note it and continue — never block Phase 3.

---

### Phase 3 — Final report

After both phases complete, produce a summary:

```
## QA Workflow Summary — <TICKET>: <summary>

### Phase 1: Validation
- PR: <URL>
- Result: ✅ Full pass / ⚠️ Partial (N manual checks needed) / ❌ N failures (user approved proceeding)
- Failures carried forward: <list any unresolved failures for manual follow-up>

### Phase 2: Test Cases Generated
| Test Key | Title | Type | Verdict |
|----------|-------|------|---------|
| PROJ-XXXX | ... | Cucumber | created |
| PROJ-XXXX | ... | Manual | created |

- Test Set: <name / none>
- Test Execution: <key / none>
- Files generated: <Postman JSON path / k6 .js path / none>

### Phase 2.5: Execution Results
| Test Key | Summary | Tool | Result | Notes |
|----------|---------|------|--------|-------|
| PROJ-XXXX | ... | Playwright | ✅ PASS | |
| PROJ-XXXX | ... | Postman | ❌ FAIL | assertion failed: status 200 expected, got 404 |

N passed / M failed / K blocked

### Test coverage delta
- Requirements with zero Xray coverage before this workflow: N / M total
- New coverage added by this run: N requirements now have at least one linked test
- Still uncovered after this run: <list any requirement text with no test case created>

### Open items for manual follow-up
- [ ] <validation failure not yet resolved>
- [ ] <requirement flagged as "manual check needed">
- [ ] <out-of-scope change that needs review>
```

### Risk-based execution order

After the combined report, output a priority-ranked execution checklist:

1. **Critical** — test cases covering requirements that were ❌ Fail or ⚠️ Partial in Phase 1 (prove the fix first)
2. **High** — happy path / core flow cases; areas matching historical risk summary from Phase 0
3. **Medium** — edge cases in areas with no prior defect history
4. **Low** — negative/error-path cases and boundary checks in stable areas

Output as a numbered checklist with test key, title, and priority tier.

### QA completion notification

Post the completion comment to the **main ticket** using the same **QA verification format** as CE-Execute-TE's Step 6 (see `[[feedback_qa_verification_format]]` memory / CE-Execute-TE SKILL.md) — not a separate "QA Workflow Complete" template. One consistent format across the TE comment and the main-ticket comment:

```
**QA Verification Result:** Pass / Failed
**Test Execution:** <TE key>
**Environment:** <qa-config.json default_env label>

### Preconditions
- <precondition 1>
- <precondition 2>

### Test Results

| ID | Scenario | Expected | Status |
|---|---|---|---|
| PROJ-XXXX | <summary> | <expected result from AC/Gherkin> | PASS |
```

(No `Actual` column here by default for the main-ticket post — mirrors the CE-Execute-TE table minus the `Actual` column, since the main ticket is a summary rollup, not a detailed run log. Include `Actual` only if the user asks for it on a specific ticket.)

When one or more tests failed, follow CE-Execute-TE's narrative Summary/Steps/Expected/Actual variant instead of the table, same as the TE comment.

After the full report and risk checklist, show the draft comment and ask:

> "Post this summary comment to <TICKET> in Jira? (yes / no)"

**Wait for explicit confirmation before posting.** On "yes", post via `addCommentToJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__addCommentToJiraIssue`).

### Ticket transition — Testing Approved

After the completion notification is successfully posted, **offer** to transition the ticket to Testing Approved **only when Phase 1 validation was ✅ Full pass AND Phase 2.5 had zero FAILED or ABORTED tests**. If either phase had failures, skip and note: "Testing Approved transition skipped — unresolved failures in Phase 1 or Phase 2.5. Resolve them before marking Testing Approved."

Fetch transitions via `getTransitionsForJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getTransitionsForJiraIssue`). Look for a transition named "Testing Approved", "Approved", "QA Approved", or equivalent. **Ask the user first:** "Transition <TICKET> to Testing Approved? (yes / no)". Only call `transitionJiraIssue` with the matched transition id on "yes" — this is the **main ticket**, not the TE, and the skill's own iron rule ("never transition a ticket without explicit user confirmation") applies here same as anywhere else. The earlier automatic TE→Done transition (Phase 2.5) is a separate, narrower exception scoped to the test-execution housekeeping ticket only — it does not extend to the main ticket.

If no matching transition is found, inform the user: "No 'Testing Approved' transition available from the current status. Available transitions: <list>. Transition manually if needed."

## Iron rules

- **Never skip CE-ForTesting when no ticket is provided.** Always surface and rank available tickets — never guess or auto-select one.
- **Never skip the Phase 0a plain-English briefing.** It is the first output on every ticket, before any validation, probing or tool use. "The change is only one line" is not an exemption — that is precisely when the blast radius needs stating.
- **Never ship a TE without the Phase 2.2 test-case table.** Every Test Execution's description carries the case table, the shared attributes, the execution grouping with its prerequisites, and an explicit line for any criterion left uncovered.
- **Never skip Phase 1.** Test case generation without validation risks testing the wrong implementation.
- **Never skip Phase 1.6.** Every ticket gets a gap list, even a passing one — "no findings beyond the AC table" is a valid gap list, silence is not.
- **Never leave a probe test in the repo.** Write it, run it, capture the numbers, delete it. QA delivers findings, not a patch.
- **Never skip Phase 2.5.** Test execution is what actually verifies the implementation works — generating cases without running them is incomplete QA.
- **Never auto-proceed past a ❌ Fail verdict.** User must explicitly approve.
- **Carry validation context into test generation.** Test cases must map to validated requirements — no gaps, no extras from out-of-scope changes.
- **A Partial verdict is not a pass.** Treat it as a soft block — inform the user, get approval.
- **Never create a Jira issue without explicit user confirmation.** Always preview the bug list and wait for "yes" before calling CE-Create-Bug.
- **Never post a Jira comment without explicit user confirmation.** Always show the draft comment and wait for "yes" before calling `addCommentToJiraIssue`.
- **Never transition a ticket without explicit user confirmation.** Always fetch available transitions first; never auto-transition.

## Common mistakes

- Skipping CE-ForTesting when no ticket key was provided. → Always run it first; never assume a ticket.
- Opening with the AC table, the diff, or a criterion-numbered verdict. → Phase 0a briefing comes first, in the user's language. Criterion numbers are for Phase 1.
- Writing the briefing in engineer-speak — class names, null checks, field identifiers. → Describe observable behaviour. `createdByName` is null becomes "the bookmark 'created by' name goes blank".
- Inventing a "one catch" because the template has the slot. → Write "No traps on this one." when there genuinely isn't one.
- Leaving the TE description as AC-only, so the executor must open every linked test to learn what is covered. → Phase 2.2 table, always.
- Appending the Phase 2.2 markdown table onto a TE description that is already wiki markup. → Rewrite the whole description in markdown in one `editJiraIssue` call, preserving every existing section.
- Dropping existing TE description sections to make the table edit simpler. → Keep Summary, Context, AC, Other information and the checklists; add the table alongside them.
- Grouping the TE table by endpoint when the groups actually differ by credential. → Group by what it takes to run, and name each group's prerequisite, so a runnable group isn't blocked behind a waiting one.
- Treating the AC verdict table as the whole finding set. → An AC can pass while the code is still wrong for inputs the AC never named. That is what Phase 1.6 is for.
- Filing a Defect straight off a gap. → A gap is a code-review finding. It becomes a defect once manual execution confirms user impact, and only if the user asks for a ticket.
- Reporting a gap as "looks like it overlaps / may be slow". → Prove it with a probe, quote the measured numbers, then delete the probe.
- Jumping to TC-Router without finishing the full CE-AC-Validator report. → Complete Phase 1 entirely first.
- Generating test cases for out-of-scope changes flagged in validation. → Only test what's in the ticket.
- Auto-proceeding after a Partial verdict. → Ask the user.
- Losing the requirement list between phases. → Use Phase 1's requirement table to guide Phase 2 case coverage.
- Skipping Phase 2.5 because TC-Router didn't create a TE. → Ask the user for the TE key; never proceed to Phase 3 without executing.
- Auto-transitioning the main ticket to Testing Approved because the gate conditions (full pass + zero failures) are met. → The gate conditions decide whether to *offer* the transition, not whether to skip asking. Always confirm with the user first — the TE→Done auto-transition in Phase 2.5 is a narrow exception for that housekeeping ticket only and doesn't extend to the main ticket.
