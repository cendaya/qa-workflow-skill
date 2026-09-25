---
name: TC-Router
description: Use when a QA engineer wants to generate or update Xray Cloud test cases from a Jira ticket. Detects test type (UI/API/Performance) and routes to /CE-TC-UI, /CE-TC-API, or /CE-TC-Perf automatically. Handles generic/mixed tickets directly. Triggers include "write test cases for PROJ-XXXX", "create Xray tests for this ticket", "generate test coverage for <module>", "make manual test steps".
---

# Test Case Writer

Turn a Jira ticket into Xray Cloud test cases — **Gherkin (Cucumber)** or **Manual**, the
user's choice per case. Nothing is written to Xray without the user approving it, one case
at a time.

## Test case description — the only accepted shape

Model every test case on **PROJ-187**. Four sections, in this order, and nothing else:

1. `What is being tested` — the persona-based objective, one paragraph
2. `Preconditions` — a bullet list
3. `Acceptance Criteria` — **this is the traceability field; it also states the oracle.** For
   `oracle: ac`, quote the requirement id(s) this case covers — the derived `R1..Rn` when the ticket has
   no ACs. For `oracle: prior-behaviour`, name the changed symbol and state the behaviour that held
   before the change. For `oracle: risk`, say plainly that the AC does not specify this input, then
   state the baseline expectation being applied and where it comes from. Never leave the section out,
   and never assert an expectation whose source you cannot name in this section
4. `Gherkin` — **inside a fenced code block**, never as loose paragraphs

Everything else — notes on the fix, commit SHAs, coverage gaps, why the case exists, the whole story of
the testing — belongs on the **Test Execution**, not on the case. A test case says what is being tested
and how to tell whether it passed. Nothing more.

### Writing it so it actually renders

**Markdown sent through Xray GraphQL's `jira.fields.description` does not render.** On 2026-09-15 all
eight PROJ-11082…PROJ-11089 descriptions were written that way and came out mangled: `###` headings
became nested numbered lists reading `1. 1. 1. What is being tested`, and the ```` ```gherkin ````
fence rendered as literal backticks in a paragraph. Xray's create mutation takes that field as plain
text.

Write the description as **HTML**, through the Atlassian MCP, which converts it correctly:

```
executeWrite name=editJiraIssue
  inputs: { issueIdOrKey, contentFormat: "html", additional_fields: { description: "<h3>…" } }
```

The HTML shape that matches PROJ-187:

```html
<h3>What is being tested</h3><p>…</p>
<h3>Preconditions</h3><ul><li><p>…</p></li></ul>
<h3>Acceptance Criteria</h3><ul><li><p>R1 — …</p></li></ul>
<h3>Gherkin</h3><pre><code class="language-gherkin">Scenario: …
  Given …
  When …
  Then …</code></pre>
```

Escape `<` and `>` inside Gherkin placeholders as `&lt;` / `&gt;`.

Note `description` goes in **`additional_fields`** — a top-level `description` on `editJiraIssue` is
dropped silently.

**Always read the description back and check it rendered** — `getJiraIssue` with
`responseContentFormat: "html"` — before calling the case done. Confirm real `<h3>` elements and a
`<pre><code class="language-gherkin">` block. Creating eight cases and discovering the formatting is
broken afterwards costs more than the one verification call.

The same applies to the Test Execution description: same HTML path, same read-back check.

---

> **Do not assume the Xray MCP is connected.** On 2026-09-15 `createTest` and
> `createTestExecution` were unavailable in a live session — the MCP simply was not loaded.
> When that happens, do not stop: fall back to the allowlisted helper, which authenticates
> itself from `mcpServers.xray.env` in `~/.claude/settings.json` and speaks the same GraphQL:
>
> ```
> python ../../scripts/xray-graphql.py "<query or mutation>"
> ```
>
> It exits 1 and prints the body when the response carries `errors`. All of PROJ-11082…PROJ-11090
> was created this way. For unattended runs the helper is the *primary* path, not the fallback.
> Ad-hoc `curl` and inline `python -c` against `xray.cloud.getxray.app` are not allowlisted and
> will stall an unattended run.

## Inputs (ask for any that are missing)

1. **Project** — defaults to `jira.project_key` from `$env:USERPROFILE\.claude\qa-config.json`. If
   the prefix isn't obvious, confirm it with the user (or list projects via the Atlassian
   MCP `getVisibleJiraProjects`).
2. **Ticket** — e.g. `PROJ-9123`.
3. **Module(s)** — e.g. `Measurement Assistant`, `Invoice Printing`. Map to Xray Test
   Repository folder names.

## Iron rules

- **The publish gate is mandatory and mechanical, and it is a script.** After creating any test
  or Test Execution, and before reporting the work as done, run
  `python ../../scripts/qa-gate-check.py <TICKET> <TE_KEY> --approved <TICKET>.md` and act
  on the exit code — 0 proceed, 1 fix the artefact, 2 decide the MANUAL rows by hand, 3 Xray
  unreachable (not a pass). Then the remaining checks in
  `../../references/qa-publish-gate.md`: descriptions non-empty **and** rendering,
  links present **and** pointing the right way, comments in the settled shape, transition
  ids fetched rather than reused. Run the commands and read the output — do not judge
  whether it probably passed. All four checks failed on real work on 2026-09-16, on a suite
  that looked finished in Xray.

  In particular: `createTest` takes **summary and steps only**. The description is always a
  **separate** `editJiraIssue` call with `contentFormat: "markdown"`. A description passed
  into the create call is stored as plain text.
- **Every case carries `Traces` and `Oracle`, and a case with no oracle is never written.** This is the
  oracle rule, governed by `../../references/qa-oracle-model.md` — read it before drafting.
  `Traces` = the AC id / derived `R` id, the changed symbol or file, or the consumer module from the
  blast-radius grep; at least one, never empty, never "general coverage". `Oracle` = where the expected
  result comes from:

  | Oracle | Source of the expected result | Authority of a failure |
  |---|---|---|
  | `ac` | The quoted AC or derived `R` | Real defect. Blocks *Testing Approved* |
  | `prior-behaviour` | The behaviour before the change — an existing passing test, a spec, a demonstrated baseline | Real regression. Blocks *Testing Approved* |
  | `risk` | Boundary/equivalence analysis on an input **the change actually touches** | Flag, not a defect. Does **not** block |
  | `none` | Nothing — the AC is silent | **Not a case.** An observation or a spec question on the TE |

  A case you cannot tag is not a weak case, it is undefined behaviour with an invented expected value.
  Send it to the TE description under `Observations for dev` or `Open questions for product` and move
  on. PROJ-11089 and PROJ-11236 were both written as assertions with no oracle and both had to be
  pulled back out of finished-looking executions.
- **Never write to Xray without explicit per-case approval.** On any uncertainty: skip.
- **Keep cases generic — never bake in specific data.** Test cases are reused across many
  runs; the QA engineer plugs real values in at test time. Write data as named placeholders
  (`<customer name>`, `<valid policy number>`, `<past-due balance>`), categories ("a valid
  account", "an inactive customer"), or roles — not literal values like `John Smith`,
  `12345`, `$4.99`. The scenario describes *what kind* of data is needed; the tester
  supplies the *actual* value. See "Generic data" below.
- **Reuse before you write.** Existing tests in the module are the starting material, not
  just update candidates — model new cases on the ones with a similar use case (style,
  step structure, naming, label/component convention). See step 5.
- **Never echo the Xray token or secret** into output, files, or logs.
- **Soft cap of 10 cases.** Generate at most 10. If full coverage genuinely needs more,
  STOP and ask whether to create extra cases (and how many). Never silently exceed or
  silently truncate.
- **One case per distinct BEHAVIOUR, never one per data value.** This is the difference
  between a suite someone will read and a suite that looks like padding. Before writing,
  group the scenarios: if two would have the *same* steps and differ only in the value
  fed in or the module it is pointed at, they are **one** case with a `Scenario Outline`
  and an `Examples:` table (or a table in the description and one step per row).

  Merge when the steps are identical and only the data changes. Keep separate when the
  *behaviour* differs — a value being preserved, a value being rejected, and a field being
  disabled are three behaviours, however similar they look.

  ```
  WRONG - 4 cases, one per year          RIGHT - 1 case, 4 examples
    hold date 9999 saves as entered        hold To date preserves the entered year
    hold date 9998 saves as entered          | entered    | wrong      |
    hold date 2099 saves as entered          | 12/31/9999 | 12/31/1991 |
    hold date 9997 saves as entered          | 12/31/2099 | 12/31/1999 |
  ```

  The same applies to regression coverage across a blast radius: **one** case with a module
  table beats one case per module. Coverage is unchanged — the modules are still named, still
  stepped, still assertable — but the suite reads as five behaviours instead of twelve
  near-duplicates.

  **Consolidating must not drop coverage.** Every acceptance criterion, and every module in
  the blast radius, must still appear somewhere — as an example row, a module row, or a step.
  Merging is about presentation, not scope. State the mapping (which AC each case covers)
  when you present the cases for approval.

  **Why:** PROJ-10500 was first written as 12 cases — four differing only by year value, six
  differing only by module — and had to be deleted and rebuilt as 5. The configured QA
  assignee: *"similar scenarios should be put together in one TCS so that not too many TCs
  that seems redundant is added"*, while *"maintaining coverage for all testing of the
  entirety of the ticket."*
- **Never auto-create a Test Repository folder** — except for API tickets (see step 4):
  if the resolved API folder doesn't exist, create it automatically.
- **Never auto-create a Test Set.** Each test should join ≥1 Test Set; the set (existing,
  new, or **none**) is chosen during per-case approval (step 6), before any test is created.
- **Work Breakdown is a required field on every written test.** Show the default
  `Core (Default)` in step 6 and let the user override it for swarm-initiative work; set it
  via the Atlassian MCP in step 8 — never block the run if the field id can't be resolved.
- **Test Execution is opt-in; the Test Plan link is not.** After per-case approvals, ask
  once whether to create a Test Execution. If yes, step 9 bundles **every** test that *is
  tested by*-links the ticket (not just this run's), then **always** has the user pick a
  Test Plan from the board's open plans — even if there's only one — and links both the
  execution and its tests into that plan. Never auto-create a Test Execution or a Test Plan
  without asking.

  Two exceptions, both learned the hard way on 2026-09-15:

  - **Invoked from CE-QA-Workflow, the Test Execution is required, not opt-in** — that
    workflow's Phase 2.5 cannot execute anything without one, so asking just dead-ends a
    run that was told to go start-to-finish.
  - **A plan is only eligible if its sprint matches the ticket's active sprint.** Read
    `customfield_10115` — a *list* of every sprint the ticket passed through — and take the
    entry whose `state` is `active`. If no open plan names that sprint, **leave the execution
    unlinked** and say so. Do not offer the user the only open plan when its sprint is
    closed: a TE parked there silently pads a finished sprint's numbers. PROJ-11090 was linked
    into `Sprint 377` when its ticket was in 378, and had to be removed.

## Workflow

Create a TodoWrite item per step.

0. **Detect test type and route.** Before proceeding, determine the test type from the
   user's request and/or the ticket:

   | Signal | Type | Route to |
   |--------|------|----------|
   | User says "API / REST / endpoint tests"; ticket label `API`; summary/description mentions REST, HTTP, endpoint, swagger, GET/POST/PUT/DELETE | **API** | **CE-TC-API** |
   | User says "performance / load / perf / k6 tests"; ticket label `Performance`/`Perf`/`Load`; keywords: load test, stress, throughput, latency, VU | **Performance** | **CE-TC-Perf** |
   | User says "UI / frontend / browser tests"; ticket label `UI`/`Frontend`; keywords: screen, page, button, form, browser, navigate, click | **UI** | **CE-TC-UI** |
   | Mixed or unclear | Ask user: "Is this a UI, API, or Performance test?" | — |

   If type is clear, **immediately invoke the appropriate skill** and stop here — do not
   continue with steps 1–10 below. If genuinely generic (no type signal), continue.

1. **Resolve inputs.** Confirm project key, ticket, module(s).

2. **Resume check.** `saveLocation` in `.test-case-writer.json` (next to this SKILL.md) is
   a **directory**. Read it; if non-empty, look for `<saveLocation>/<TICKET>.md`. Also
   accept an explicit file path the user names. **If empty and no path is named, skip
   resume and generate fresh.** If a matching file is found, offer: **resume** (parse it
   per `references/md-template.md`) or **generate fresh**. A half-finished file
   round-trips — it uses the same template this skill writes.

3. **Read the ticket.** Use the Atlassian MCP `getJiraIssue` (load via ToolSearch
   `select:mcp__plugin_atlassian_atlassian__getJiraIssue`) for summary, description,
   acceptance criteria, and the numeric **project id** (`fields.project.id` — required by
   the Xray folder calls in steps 4 & 8). If that field is absent, derive the project id
   from any existing test's `jira` project in step 4, or ask the user. Fallback if MCP is
   unavailable: ask the user to paste the requirements and project id.

4. **Authenticate to Xray** and **locate the module folder(s)** + **list existing tests**.
   See `references/xray-queries.md` (auth, folder lookup, listing folder tests). Pull the
   **full set** of tests in the matched folder(s) — these are your starting material, not
   just a fallback for updates. **Read several of them in full** (gherkin / step rows), not
   only their titles, so you absorb the module's house style: how scenarios are phrased,
   how steps are grouped, naming patterns, what gets parameterized. Note the folder's
   **predominant test type** (Cucumber vs Manual) — the per-case default in step 6 — and
   its **predominant component(s) and label convention**, reused as defaults (see Field
   mapping). **Also resolve candidate Test Sets** for the module now (`getTestSets`, see
   reference §7) so a target set is known *before* any test is created — picked/confirmed
   during per-case approval (step 6).

   **And resolve the Test Execution context** for step 9 while you're authenticated: list
   the board's **open Test Plans** (status ≠ Done — see reference §9) so the user has
   something to pick from later, and look for an **existing Test Execution** whose summary
   matches `<TICKET> | <Module>-…` (see Field mapping → Test Execution) so step 9 can reuse
   it instead of creating a duplicate.

   When the folder is large, narrow the listing toward the ticket's feature with a
   `summary ~ "<keyword>"` JQL filter (see reference §1) so the most relevant existing
   tests surface — but still skim the broader folder for ones whose *use case* overlaps
   even if the wording doesn't match.

   **API tickets:** If the ticket has label `API`, issuetype contains "API", or the summary/
   description is clearly about REST/HTTP endpoints, use `/API Testing/<FeatureName>` as the
   target folder, where `<FeatureName>` is derived from the ticket's subject/module (e.g.
   ticket about "Call Ahead" → `/API Testing/Call Ahead`). Search for that path first; if
   `/API Testing` exists but the subfolder does not, create the subfolder automatically. If
   `/API Testing` itself is missing, create both levels. No user confirmation needed for
   this auto-create — it is the expected folder structure for API tickets.

4a. **Does this ticket already have test cases? (mandatory, before drafting anything.)**
   Folder listing answers *"what exists in this module"*. It does not answer *"did someone
   already write cases for this exact ticket"* — and re-running the workflow on a ticket is
   common. Read the ticket's links via Atlassian MCP `getJiraIssue`
   (`fields: ["issuelinks"]`) and keep the **"is tested by"** links (same read as reference
   §9c, which step 9 needs anyway — do it once here and carry the result forward).

   If any exist, **stop and show them** — key, summary, and current `gherkin` / `steps` —
   then ask which applies:

   | Option | Meaning |
   |---|---|
   | **Update these** | The ticket's scope changed; the existing cases should absorb it. Tag them UPDATE in step 5. |
   | **Add to them** | Existing cases stand; this run only writes what they do not already cover. Present the gap list first. |
   | **Start fresh** | The old cases are wrong or belong to a superseded scope. Say what happens to them — they are not silently orphaned. |

   Never draft over the top of linked coverage without that answer. **Why:** the TE is
   deduped by summary (§9b) and the test-to-TE link is deduped by issueId (step 9), so a
   re-run silently produces a *second set of cases* linked to the same ticket and the same
   execution, and nothing in the pipeline flags it.

5. **Generate cases** (≤10), **anchored to the existing tests from step 4**. Before
   drafting anything new, match each requirement against what's already in the folder:
   - Is there a test covering the **same scenario intent**? → tag **UPDATE → `<KEY>`** (the
     new steps belong in that test).
   - Is there a test with a **similar use case** but a different angle (adjacent flow, same
     feature different path)? → still write a **NEW** case, but **mirror that test** — reuse
     its phrasing patterns, step granularity, Given/When/Then rhythm, title style, and
     label/component defaults. Reuse over reinvention: a reader should not be able to tell
     the new case from a hand-written one in that folder. Cite the model test you followed
     in the report.
   - Nothing comparable? → write fresh, in the folder's house style.

   When in doubt between UPDATE and NEW, choose NEW (a merely related-but-distinct scenario
   is its own test). The match doesn't need to be exact on data or wording — overlap of
   *purpose* is enough to make an existing test worth reusing as a model.

   **Every NEW case must name its nearest existing test and say why it is not an UPDATE.**
   One line per case in the approval report: `NEW — nearest: PROJ-2201 "Edit Property Items";
   different because the case asserts the Property *Details* panel, not Items`. If the
   nearest test cannot be named, step 4's candidate set was too narrow — widen the JQL or
   page further and look again before drafting. "Nothing comparable" is a legitimate answer
   in a thinly covered module, but it is an answer you state, not one you reach by not
   looking.

   **Why:** the default above is deliberately biased toward NEW, and an unexamined bias
   produces a folder of near-duplicates. Forcing the comparison into writing turns the
   tie-break into a visible decision the reviewer can overrule — and makes it obvious when
   the real problem is that step 4 only read the first 100 tests.

   Build each case as a title, a labeled description block, and a **Gherkin scenario**
   (always — the Manual form derives from it, see Field mapping). Keep all data **generic**
   (placeholders / categories, never literal values — see Iron rules and "Generic data").

5a. **AC/regression completeness check (mandatory, before step 6).** Before presenting the
   case list for approval, cross-check it against every validated requirement:
   - **No gaps against AC/ticket.** If a CE-AC-Validator report (or equivalent requirement
     list) exists for this ticket, walk its requirement table row by row and confirm each
     one maps to at least one drafted case. A requirement with zero mapped cases is a gap —
     draft a case for it before moving on, don't silently drop it.
   - **Regression coverage has two halves, and both are required.**

     **(a) The behaviour the fix touches.** If the ticket is a defect/bug-fix (issuetype
     Defect/Production Defect, or the diff/PR is clearly a targeted fix), draft at least one
     case that exercises the **pre-existing correct behavior the fix touches** — not just the
     bug scenario itself.

     **(b) The affected modules.** Measure which modules the changed code can reach and add one
     case per module, covering that module still working *as a whole*. Grep for the consumers of
     every changed file — `RenderPartial` call sites for a partial, callers for a method, the
     class name for a CSS/JS hook, the same tables for a SQL change — and record the counts in
     the TE under a `Blast radius` heading. Never infer reach from the folder name: PROJ-10327's
     fix was in `Views/Shared/` yet had exactly one consumer, while a change with one innocuous-
     looking caller can touch every report on the board. Full rule in `CE-QA-Workflow`
     Phase 2. A fix that decodes/transforms/short-circuits data on every call can
     break the unaffected (already-working) input path; a reviewer's logical happy-path
     simulation is not a substitute for an actual regression case. Model it as
     "`<Feature> With <Baseline/Standard Input> (Regression)`".
   - **Oracle audit — every drafted case, before approval.** Walk the list and put a `Traces` and an
     `Oracle` on each one. Any case that ends up `none`, or whose `Traces` you cannot name, comes out
     of the list now and goes to the TE description as an observation or a spec question. Report the
     mix: *"7 cases — 4 `ac`, 2 `prior-behaviour`, 1 `risk`; 2 findings downgraded to observations."*
     Per-category coverage grids (CE-TC-UI's happy/edge/negative/a11y, and the API and Perf
     equivalents) are **subordinate to this**: a category with nothing traceable to the blast radius
     gets a stated reason in the report, not a case invented to fill the row.
   - State in the report which requirement each case maps to, and call out explicitly if a
     requirement has no case (with reason) rather than leaving it implicit.

6. **Approve one at a time.** Show each case's `Traces` and `Oracle` alongside it — they are settled
   in step 5a, not decided here, but the user must be able to see that a `risk` case is non-blocking
   before approving it. Walk cases individually. For each, the user picks a **type**
   (**Gherkin** / **Manual** / **Both**, pre-selected to the folder's predominant type
   from step 4) and an action. **Three values are approved here, not just defaulted** (hard
   approval-of-value gates):
   - **Automation Status** — show the proposed value (**`Not Automated`** by default for
     new tests, until a human confirms automatability); user confirms or overrides (e.g.
     bumps to `Can be Automated`, or `Manual Only` for a test that genuinely can't be
     automated). This approves the *value*; the actual Jira write happens in step 8 and
     still degrades to a report note if the field id can't be resolved (never orphans the
     test).
   - **Work Breakdown** — the Initiative identifier (required field). Show the default
     **`Core (Default)`**; the user should be conscious of it and override when the work
     belongs to a swarm initiative. Like Automation Status, this approves the *value*; the
     write happens in step 8 and degrades to a report note if the field id can't be
     resolved.
   - **Test Set** — show the candidate set(s) from step 4; user picks one, or approves
     **creating** a new set (**name confirmed here, but not created yet** — use the
     `<Product> - <Module>` convention, see Field mapping), or explicitly chooses **none**.
     The *decision* is settled before any test is created; the `createTestSet` call is
     **deferred to step 8** and runs lazily on the first successful write, so skipping
     every case never leaves an empty set behind.

   After all per-case approvals, if at least one case was approved, ask **once**:
   > "After writing, create a **Test Execution** for these tests, or **skip**?"

   - **Test Execution** — decision only, settled here; the actual assembly (bundling every
     test linked to the ticket, creating/reusing the execution, and picking a Test Plan)
     happens in **step 9**, once the approved tests exist.
   - **Skip** — note in report; step 9 is skipped entirely.

   Then the per-action flow:
   - **NEW** → present title + description + the Gherkin scenario (and, for Manual/Both,
     the derived Action/Data/Expected step rows); user picks **add** / **skip** and the
     type. **Both** = create two tests for this case — one Cucumber, one Manual — both
     foldered and both linked to the ticket (an Xray test can only be one type).
   - **UPDATE** → show a **current-vs-proposed diff** in the candidate's own form (Gherkin
     diff for a Cucumber test, step-row diff for a Manual test); user picks **append** /
     **modify** / **replace** / **skip**.
     - **append** — add new steps/scenarios, leaving every existing step untouched.
     - **modify** — **edit specific existing steps in place** when their logic can be
       tweaked to fit the scenario: reword an Action, adjust a Data placeholder/constraint,
       refine an Expected Result, or edit a line inside an existing Gherkin scenario. Change
       **only** the steps that need it and leave the rest intact — the middle ground between
       append (adds nothing to what's there) and replace (discards it). The diff must show
       exactly which existing steps change. A case can both **modify** some steps and
       **append** others.
     - **replace** — swap the whole definition; last resort, when most steps must change.

   **Cross-type guard.** Append/modify/replace only when the chosen type **matches** the
   existing test's type. Appending Gherkin onto a Manual test (or vice-versa) would require
   `updateTestType`, which **destroys the existing definition** — never silently convert.
   On a type mismatch, offer **NEW of the chosen type** instead (recommended), and note
   the related existing test in the report for manual follow-up.

   If the user approves **zero** cases, skip steps 7–9 and report an empty result.

7. **Offer markdown save.** First run with no `saveLocation`: ask **once** for a save
   **directory**, persist it to `.test-case-writer.json` (persist it even if the user then
   declines the actual save — it's the remembered location for next time). Offer to write
   the approved set as `<saveLocation>/<TICKET>.md` (per `references/md-template.md`)
   **before** pushing to Xray.

8. **Write approved cases to Xray** (see `references/xray-queries.md`):
   - NEW Gherkin → `createTest` type **Cucumber** with the `gherkin` scenario. Pass
     `jira.fields` summary + labeled description **and** `labels` / `components` per Field
     mapping.
   - NEW Manual → `createTest` type **Manual** with the derived `steps` (Action/Data/
     Expected rows) and the same `jira.fields` (summary, description, labels, components).
   - NEW Both → two `createTest` calls (one Cucumber, one Manual) for the same case.
   - Every written test → **set the approved Automation Status** (from step 6) via the
     Atlassian MCP `editJiraIssue`. If the field id can't be resolved, record the intended
     value in the report (Field mapping). Don't abort on it — never orphan a created test.
   - Every written test → **set the approved Work Breakdown** (from step 6, default
     `Core (Default)`) via `editJiraIssue`. Field id is project-specific (discover with
     `getJiraIssueTypeMetaWithFields`); if it can't be resolved, note the intended value in
     the report. Never abort on it.
   - Every written test → **add to the approved Test Set** (`addTestsToTestSet`). If the
     user chose a **new** set in step 6, create it **lazily here** (one `createTestSet`,
     triggered by the *first* successful test write; reuse that id for the rest of the run).
     If they picked an **existing** set, use its id. If **none**, note it in the report. No
     asking at write time — the decision is done; only the creation was deferred.
   - All NEW tests → `addTestsToFolder` (module folder). **Index lag:** a just-created
     test may not be indexed yet, so `addTestsToFolder` can fail with "tests with ids …
     don't exist on Jira." Transient — collect all new ids, wait a few seconds, retry the
     folder add as one batch. See the reference note in section 4.
   - UPDATE-append (Cucumber) → fetch current gherkin, append new `Scenario:` blocks, then
     `updateGherkinTestDefinition`. Leave existing scenarios untouched.
   - UPDATE-append (Manual) → `addTestStep` for each new row. Leave existing steps intact.
   - UPDATE-modify (Cucumber) → fetch current gherkin, edit **only** the lines/steps inside
     the affected scenario(s), leave every other scenario byte-for-byte unchanged, then
     `updateGherkinTestDefinition` with the merged gherkin.
   - UPDATE-modify (Manual) → `updateTestStep` on each existing row being tweaked (by its
     step id), leaving the untouched rows alone. If the same case also adds rows, combine
     with UPDATE-append (`addTestStep`) in the same write.
   - UPDATE-replace → Cucumber: `updateGherkinTestDefinition` with the new gherkin.
     Manual: replace the step rows (`updateTestStep` / remove + re-add).
   - **Every written test** → link to the ticket so the ticket shows "is tested by [TC]"
     and each TC shows "tests [ticket]": `createIssueLink` type `Test`,
     inwardIssue = TC key, outwardIssue = ticket. For **Both**, link both new tests. Never
     skip, even when a Test Execution is also created later. See reference §6.

   **Continue on error.** Track each *test* independently — for **Both** type (Cucumber +
   Manual), if one createTest/link fails, still record the one that succeeded; never roll
   back a created test. Move to the next unit, don't abort the run.

9. **Assemble the Test Execution and link it to a Test Plan** (only if the user chose to
   create one in step 6; skip entirely — and skip to step 10 — otherwise). See
   `references/xray-queries.md` §9–10.

   - **Collect every test linked to the ticket**, not just this run's. Start from the tests
     created/updated in step 8, then re-read the ticket's issue links and add any other
     test that already **is tested by**-links it. Union and de-dupe by issueId — a re-run
     shouldn't drop pre-existing coverage.
   - **Create-or-reuse the execution.** Summary is
     `<TICKET> | <Module>-<short description of what is being tested>` (e.g.
     `PROJ-9123 | Measurement Assistant-Multi-polygon area calculation`). If step 4 already
     found an execution with that summary, **reuse it** — just `addTestsToTestExecution`
     the collected tests (the call ignores ones already in it). Otherwise
     `createTestExecution` with those tests, description drawn from the ticket's AC using
     this template:
     ```
     ### Summary
     Test Execution for <TICKET>: <ticket summary>.

     ### Context
     <technical description from ticket — what the implementation adds/changes>

     ### Acceptance criteria
     * <AC bullet points from ticket>

     ### Other information
     * <additional tech details: existing operations, endpoint routes, models, response codes>

     ### Risk findings
     * <per auto-cleared `oracle: risk` deviation — the full write-up, ending in the one question
       product must answer. Shape in `qa-oracle-model.md` §6b>
     * <or "none">

     ### Observations for dev
     * <oracle-less findings, recorded without a verdict: "X produces Y; the AC is silent on X">
     * <or "none">

     ### Open questions for product
     * <"The AC does not define behaviour when X. Current behaviour is Y. Is that intended?">
     * <or "none">

     ### Testing checklist
     * <QA checklist items from ticket Engineering Notes / QA section>
     ```

     `Observations for dev` and `Open questions for product` are where every `oracle: none` finding
     goes (`../../references/qa-oracle-model.md` §3). Write "none" under each rather than dropping
     the heading — silence reads as an oversight.
     Set the execution's **Component(s)** from the ticket's (else the folder's predominant
     component). **Never set or change the assignee** — leave whatever Jira applies.
     Link the execution to the ticket: `createIssueLink` type `Test`, inwardIssue = TE key,
     outwardIssue = ticket. Ticket shows "is tested by [TE]", TE shows "tests [ticket]".
   - **Pick the Test Plan with the user.** Show the open Test Plans from step 4 **newest
     first** and have them choose — always, even if there's exactly one. If they pick one,
     do **both** writes against that plan:
     - Link the execution via `addTestExecutionsToTestPlan`.
     - **Copy the execution's tests into the plan** via `addTestsToTestPlan` — the same
       collected, de-duped test set that seeds the execution. Linking the execution alone
       does **not** register those tests in the plan's own test list. The call is
       idempotent — safe to re-run.
     If **none are open**, ask whether to create a Test Plan (confirm its summary, e.g.
     `<sprint dates> Sprint | Release Regression`) or skip the link this run — never
     auto-create one.

   **Continue on error.** If the execution write or the plan link fails, keep the tests you
   already created — record the execution/plan status in the report; don't roll anything back.

10. **Report.** One row **per test** (a Both-type case yields two rows — one Cucumber, one
   Manual): test key (`—` for skipped/uncreated), type, action (created / appended /
   modified / replaced / skipped / failed), link status, **automation status** (set /
   intended-value for manual follow-up), **work breakdown** (set / intended-value),
   **Test Set** (added / none). For a NEW case modeled on an existing test, note
   **modeled on `<KEY>`**. Note any cross-type-guard skips here.

   Then a closing **Test Execution** line (if step 9 ran): its key and summary (created /
   reused), how many tests it now holds, and the **Test Plan** it was linked to (key +
   summary, or "skipped — no plan" / the intended value if the link failed) — including how
   many of those tests were copied into the plan. If step 6 chose skip, say the execution
   step was skipped.

## Field mapping

- **Description field** (both types) — use this 3-section format, sourced from the ticket
  description and QA notes:

  ```
  ### Objective
  <see guardrails below>

  ### Preconditions
  - <precondition 1>
  - <precondition 2>

  ### Acceptance Criteria
  * <AC bullet points from the ticket relevant to this specific scenario>

  ### BDD Scenario
  ```gherkin
  Scenario: <scenario name>
    Given ...
    When ...
    Then ...
  ```
  ```

  **Objective guardrails by test type:**

  - **UI test:** Clear description of the scenario being tested, including the user persona
    and action. May include prerequisites and expected results. Example: *"As an
    Administrator, I should be able to create a new opportunity from the Opportunity List.
    I would expect to see the new Opportunity listed both at the Account level and in the
    Opportunity List after a refresh."*

  - **API test:** Short, direct "Verify that…" sentence describing the scenario. Include a
    Swagger link when available (default: `<api.swagger_url from qa-config.json>`).
    Example: *"Verify that after charging a saved card the correct amount value is returned.
    [Swagger](<api.swagger_url from qa-config.json>)"*

  Preconditions stay inside the description field (labeled) — do **not** create separate
  Xray Precondition entities.
- **Gherkin (Cucumber):** scenario goes in the `gherkin` field.
- **Manual:** steps go in Xray step rows — each row has `action`, `data`, `result`.
- **Link:** issue link type **Test** — TC/TE is the **inward** issue, ticket is the
  **outward** issue. `inwardIssue = TC key, outwardIssue = ticket`. The ticket page shows
  "is tested by [TC key]"; the TC page shows "tests [ticket]". For **Both**, link both
  new tests to the ticket this way. **Do not swap these** — inward = ticket produces the
  opposite label ("tests [TC]") on the ticket, which is wrong.
- **Summary (title):** format is `<Module Name> | <Scenario>` — e.g.
  `Invoice Printing | Create New Opportunity from Opportunity List`.
  Module Name = the Xray Test Repository folder name (from step 4). Scenario = concise,
  action-first description of what is performed. **Avoid a "Verify" prefix** — fold
  validation into the Expected Result, not the title. Keep wording consistent across a
  folder's tests.
- **Automation Status** (best-practice field, set on the Jira issue — *not* an Xray GraphQL
  field). Four states: **`Not Automated`** (not yet fleshed out enough to know whether it
  can be automated), **`Manual Only`** (cannot be automated), **`Can be Automated`** (has
  all the content needed to be automatable), **`Is Automated`** (set after the automation
  PR merges). **Default new tests to `Not Automated`** — the user **confirms or overrides
  this value in step 6** (e.g. bumps it to `Can be Automated`) before any write.
  Set it after create via the Atlassian MCP (`editJiraIssue`) on the Automation Status
  custom field. The field id is project-specific — discover it with
  `getJiraIssueTypeMetaWithFields` (issuetype Test); if it can't be resolved, **note the
  intended value in the report** for the user to set manually. Never block the run on it.
- **Work Breakdown** (required custom field, set on the Jira issue via `editJiraIssue`) —
  identifies the **Initiative** a test belongs to. **Default `Core (Default)`**; surface it
  in step 6 so the user is conscious of it and overrides when the work is a swarm
  initiative. Field id is project-specific — discover with `getJiraIssueTypeMetaWithFields`;
  if unresolved, note the intended value in the report.
- **Labels** (`jira.fields.labels`, optional) — apply the project/product key label (e.g.
  `PROJ`) plus any automation tags the ticket/folder convention implies (feature file or
  suite, e.g. `@Regression`). Reuse the folder's existing label convention; don't invent
  new schemes.
- **Component** (`jira.fields.components`, `[{ name }]`) — populate so the test reports and
  groups correctly. Default to the **ticket's component(s)**, else the **predominant
  component of the folder's existing tests** (from step 4). Component names must already
  exist in the project — if none can be resolved, ask rather than guess.
- **Test Set** (step 6/8) — a feature/module bucket of tests, **not** ticket-scoped (unlike
  the Test Execution). When **creating** a new set, name it **`<Product> - <Module>`**: the
  product prefix, then the module — e.g. `<Product> - Document Storage`,
  `<Product> - Billing`. **Product** is one of the keys in `jira.product_options` in
  `qa-config.json`; **Module** is the feature, matching the module folder
  name from step 4. If `jira.product_options` is empty, drop the product prefix and name
  the set `<Module>`. Confirm the name with the user in step 6 before the lazy
  `createTestSet` in step 8, and **reuse** an existing set rather than creating a
  near-duplicate under a differently-worded name.
  Also set the **Product** single-select field on the new set to the **same product as the
  name prefix**, using `jira.product_field` (the field id) and the matching option id from
  `jira.product_options` in `qa-config.json`. Pass it in the `createTestSet` `jira.fields`,
  or set it via `editJiraIssue` after create. Skip this entirely when `jira.product_field`
  is `null`. Field ids are project-specific; if it can't be resolved, note the intended
  value in the report rather than failing the run.
- **Test Execution** (step 9, one per ticket) — `summary` is
  `<TICKET> | <Module>-<short description of what is being tested>` (e.g.
  `PROJ-9123 | Measurement Assistant-Multi-polygon area calculation`); carry the ticket's (or
  folder's) **Component(s)** so the run reports correctly. Holds **every** test that *is
  tested by*-links the ticket. **Reuse** an existing execution with the same summary
  instead of duplicating. **Leave the assignee alone** — the skill never sets or reassigns
  it; ownership is the QA's call in Jira.
- **Test Plan** (step 9, the link target) — the skill never assumes which plan is "current":
  it lists the board's **open** plans (status ≠ Done), **newest first**, and the user
  picks — always, even if there's only one. Against the chosen plan, do **two** writes: link
  the execution (`addTestExecutionsToTestPlan`) **and** copy the execution's collected tests
  into the plan (`addTestsToTestPlan`) so the plan's own test list reflects the ticket's
  coverage — the execution link alone doesn't populate it. Both are idempotent. Only create
  a plan on explicit approval, with a concise summary like
  `<sprint dates> Sprint | Release Regression`.

### Generic data (no specific values)

Cases are templates reused across many test runs — the engineer supplies real values at
execution time. Author every case so it stays valid no matter what concrete data is used:

- **Reference data by name or category, not value.** Use `<customer name>`, `<valid email>`,
  `<inactive account>`, `<amount over credit limit>`, `<a date in the past>` — not
  `Jane Doe`, `acct 88213`, `$250.00`, `2025-01-03`.
- **State the *constraint* the value must satisfy** where it matters ("a customer with an
  open balance", "an invoice already marked paid") — that's the part the tester needs;
  the literal value is theirs to pick.
- **Manual `Data` column** = the placeholder/parameter and any constraint, e.g.
  `<policy number> (active, auto-renew on)`. Leave it blank when the step needs no input.
- **Gherkin** = use Scenario with named placeholders. Only reach for a `Scenario Outline` +
  `Examples` table when the *intent* is to cover several data variants; even then, fill the
  table with representative **categories** (`valid`, `expired`, `empty`), not real records.
- **Exception:** fixed domain constants that are part of the behavior under test, not test
  data (a specific error message string, a required status name, an enum value), stay
  literal — paraphrasing them would change what's being verified.

### Deriving Manual steps from the Gherkin scenario

Always author the Gherkin first, then map it so the two forms stay parallel:

- `Given …` → fold into **Preconditions** (description). If a Given describes a setup
  action, also emit it as a first step row (Action = the setup, Expected = "ready").
- `When …` (+ following `And`) → a step's **Action**.
- A concrete input value on the **When/And (action) side** → that step's **Data**. Values
  stated on the `Then` side stay in **Expected Result**, not Data.
- `Then …` (+ following `And`) → that step's **Expected Result**.

Group each `When … Then …` pair into one step row; consecutive `And`s extend the current
row's Action or Expected.

## Config

`.test-case-writer.json` (beside this file) holds `{ "saveLocation": "<path>" }`. Empty
on a fresh install. Set it once (step 7), reuse silently after, and use it as the
auto-scan target for resume (step 2).

## Common mistakes

- Writing to Xray before the user approved that specific case. → Approve per-case first.
- Creating a folder that wasn't found. → Ask instead.
- Putting preconditions in separate entities. → Keep them in the description, labeled.
- Exceeding 10 cases without asking. → Stop at 10, ask to extend.
- Trying to make one test both Cucumber and Manual. → A test is one type; **Both** = two
  separate tests, both linked to the ticket.
- Converting a Manual test to Cucumber (or vice-versa) to append. → Destroys the existing
  definition. Append only when types match; otherwise create NEW of the chosen type.
- Replacing a whole test, or appending a near-duplicate step, when only one existing step
  needed a small tweak. → Use **modify**: edit just the steps whose logic must change and
  leave the rest intact.
- Using **modify** to bend a test onto a different persona/workflow. → That's a NEW case;
  modify only tweaks steps within the test's existing scenario intent.
- Starting a Summary with "Verify". → Use an action-first title; validation belongs in the
  Expected Result.
- Auto-creating a Test Set, or leaving a test in no Test Set silently. → Use an existing
  set or ask; record "none" in the report if declined.
- Naming a new Test Set freeform (e.g. just the module, or `<ticket> | …` like an
  execution). → Use **`<Product> - <Module>`** (e.g. `<Product> - Document Storage`); see
  Field mapping.
- Creating a Test Set without its **Product** field, or with a Product that disagrees with
  the name prefix. → Set Product (`jira.product_field`) to match the prefix: one of the
  values in `jira.product_options`.
- Auto-creating a Test Execution without asking. → Always ask after per-case approvals;
  note in report if skipped.
- Creating a second Test Execution for a ticket that already has one. → Reuse the
  execution whose summary is `<TICKET> | <Module>-…`; just add the tests to it.
- Putting only this run's tests into the execution. → Include every test that *is tested
  by*-links the ticket, re-queried at the end (step 9).
- Picking the Test Plan yourself, or auto-creating one. → Always have the user choose from
  the open plans; create a plan only on explicit approval, or skip the link.
- Linking the execution to the plan but leaving the plan's test list empty. → Also copy the
  execution's tests into the plan with `addTestsToTestPlan`; the execution link alone
  doesn't register them.
- Setting/reassigning the execution's assignee. → Never touch it; leave whatever Jira sets.
- Forgetting Work Breakdown. → Required field; default `Core (Default)`, override for swarm
  initiatives, set via the Atlassian MCP and note in the report if its id can't be resolved.
- Defaulting Automation Status to `Can be Automated` for an un-reviewed test. → Default
  `Not Automated`; the user bumps it in step 6 once automatability is confirmed.
- Treating Automation Status as an Xray GraphQL field. → It's a Jira custom field; set it
  via the Atlassian MCP, and never block the run if its id can't be resolved.
- Passing description as a plain string in `createTest` `jira.fields.description`. → Jira
  renders it with broken `1. a. i.` outline formatting instead of bold headings and bullets.
  **Always update descriptions after creation** via `editJiraIssue` with
  `contentFormat: "markdown"` — pass the description as markdown (`**Bold**`, `- bullet`).
  Batch all 10 updates after all tests are created.
- Baking literal data into a case (`John Smith`, `$4.99`, real account numbers). → Use
  named placeholders + the constraint the value must meet; the tester supplies the value.
- Drafting new cases from scratch while ignoring near-identical existing tests in the
  folder. → Read the folder first; model new cases on the closest existing one and match
  its style, even when it's not an UPDATE.
- Writing cases only for the bug scenario on a defect ticket and skipping regression
  coverage for the unaffected/baseline path the fix touches. → Run the step 5a check; add a
  `(Regression)` case confirming pre-existing correct behavior still works post-fix.
- Treating a validated requirement (from CE-AC-Validator) as covered just because a related
  case exists. → Step 5a requires an explicit per-requirement mapping; a requirement with no
  mapped case is a gap, not an assumption.
