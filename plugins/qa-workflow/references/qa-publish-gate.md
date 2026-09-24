# QA publish gate

> Ships with the qa-workflow plugin and is cited by the skills in `plugins/qa-workflow/skills/` — the check numbers below are load-bearing, do not renumber them.

**Run this before recording any result, posting any comment, or transitioning anything.** Every check is mechanical — run the command, read the output, compare. Do not reason about whether it probably passed.

---

## Run the checker first

Most of this file is now executable. Run it before reading any of the prose:

```bash
python ../scripts/qa-gate-check.py <TICKET> <TE_KEY> \
  --story-comment story.md --te-comment te.md --approved <TICKET>.md
```

It is read-only, authenticates from `mcpServers.xray.env` like `../scripts/xray-graphql.py`, and prints
one `PASS` / `FAIL` / `MANUAL` line per check.

| Exit | Meaning | What to do |
|---|---|---|
| `0` | Every check passed | Proceed |
| `1` | At least one **FAIL** | Fix it. **Nothing is reported as finished at exit 1** |
| `2` | No fail, but a **MANUAL** row | Decide those rows by hand against the prose below, and say in the report which ones you decided and how |
| `3` | Could not reach Xray | Not a pass. Resolve and re-run |

The three optional files make the difference between `MANUAL` and a decided verdict, so supply them:
`--story-comment` / `--te-comment` are the comment bodies (fetch them back from Jira and save them —
Jira comments are not reachable from the Xray API, which may be the only credential this machine has),
and `--approved` is the working `<TICKET>.md` written at TC-Router step 7, which is the prior record
the ratchet check diffs against.

**The script decides; you do not.** Its whole purpose is that "did I test this properly?" becomes a
comparison of two sets rather than a judgement made by the same agent that produced the artefacts.
Arguing with a `FAIL` in the report, rather than fixing the artefact, defeats it entirely.

What it cannot see, and you must still check by hand: whether a case's steps actually exercise what its
title claims, whether the observable chosen is the right one (§0.5), and whether an `Inconclusive`
narrative is honest. It checks shape and consistency, never judgement.

Each of these failed in production on 2026-09-16, on work that looked finished. None of them is theoretical.

---

## 0. Reuse the ticket's existing cases — check BEFORE writing any

**Run this first, before creating a single test case:**

```
issue in linkedIssues("<TICKET>", "is tested by")
```

A ticket often already carries cases, written when it was groomed or by whoever filed it. Writing new
ones without looking creates duplicates that **cannot be fully undone**: `deleteTest` is destructive and
needs the human's approval, and the stray case's link to the ticket can never be removed because no
delete-issue-link operation exists. The duplicate stays visible on the ticket until the test itself is
deleted.

- Existing case covers the AC → **reuse it**: add it to the new Test Execution and execute it.
- Existing case is a thin shell and yours is materially better → still reuse the key where you can, and
  say in the TE comment why you added another.

Origin: on PROJ-10710 this was done correctly (PROJ-10711 was reused). On **PROJ-10714 it was not** —
PROJ-11240 was created for AC5 while PROJ-10715 and PROJ-10716 already covered exactly that, both
well-formed. The duplicate had to be pulled back out of the execution and left awaiting deletion
approval.

---

## 0.5 The oracle ruling — name it before you execute

**For every case, name the oracle before running it: the specific observable that proves the behaviour, at the layer that actually does the work.** A surface that merely acknowledges the request is not an oracle.

| Trap | Invalid oracle | Valid oracle |
|---|---|---|
| Work is queued, not done | HTTP 200 / `Success: true` from the enqueue call | The async job's **Status + Error column** (`<async-job-status-endpoint>`, **POST**; GET returns 405) |
| A parameter may never have bound | The screen completed without error | A **differential** — change only that input, prove the output changes |
| Client state vs persisted state | The row is still in the grid | **Re-fetch server-side** and check the returned markup |
| Element visibility | `offsetParent !== null` | The widget's own state — `visible` class, opacity, bounding rect |

Origin: PROJ-10824's Generate call returned `200 {"Success":true}` while the SQL that used to throw ran afterwards in a *separate* async processor. Had the bug still existed the response would have been identical — the whole ticket would have been signed off on a signal that could not fail.

**If the only available oracle cannot distinguish pass from fail, the case is `BLOCKED`, not passed.** Never substitute a weaker signal to get a green. Full rule: `qa-oracle-model.md` §5a Rule 3 — doubt resolves toward blocking.

---

## 1. Descriptions exist and render

`createTest` and `createTestExecution` accept **summary and steps only**. A description passed into the create call is stored as a **plain-text blob** — no headings, no code blocks, smartlinks mangled. Setting it properly is always a **second call**: `editJiraIssue` with `contentFormat: "markdown"`.

```bash
python ../scripts/xray-graphql.py \
  '{ getTests(jql: "key in (PROJ-XXXX,PROJ-YYYY,...)", limit: 30)
     { results { jira(fields: ["key","description"]) } } }'
```

- **Every** key must return a non-empty description. `desc_len=0` on any key fails the gate.
- Then read **one TC and the TE** back as HTML and confirm real elements:

```
getJiraIssue issueIdOrKey:<key> responseContentFormat:"html" responseFields:["fields.description"]
```

Must contain real `<h3>`, `<ul>` or `<ol>`, and `<pre><code class="language-gherkin">`. If you see escaped `&lt;h3&gt;`, or the whole body inside one `<p>`, it did not render.

**Required shapes**

| Artifact | Sections |
|---|---|
| Test Case | `What is being tested` · `Preconditions` · `Acceptance criteria` · `Gherkin` (fenced, `gherkin` tag) |
| Test Execution | `Summary` · `Context` · `Acceptance criteria` · `Environment` · `Test cases in this execution` · `Risk findings` · `Other information` · `Observations for dev` · `Open questions for product` · `Testing checklist` |

**Why it hides:** a suite with empty descriptions looks complete in Xray. Steps, statuses and the TE are all present, so nothing warns you. On PROJ-10500 all five TC descriptions were empty and the TE was one prose paragraph; it was only caught when the configured QA assignee looked.

---

## 2. Links exist, and point the right way

Direction: **`inwardIssue` = the TC or TE. `outwardIssue` = the ticket.** The link reads *inward → outward using the link type's **outward** description*, and for type `Test` that is "tests" — so test **tests** ticket, and the ticket page reads **"is tested by"**.

```
createIssueLink type:"Test" inwardIssue:"<TC or TE key>" outwardIssue:"<TICKET>"
```

Verify with the JQL that `CE-AC-Validator` depends on — it returns **nothing** if the direction is reversed:

```
issue in linkedIssues("<TICKET>", "is tested by")
```

- The returned count must equal **every TC plus the TE**.
- **Link the TE as well as the cases.** PROJ-10823 reached *Testing Approved* with all six artifacts unlinked.

**There is no way to fix a wrong link.** No delete-issue-link operation exists in the Atlassian MCP catalog and there may be no Jira token on the machine at all (only `XRAY_CLIENT_SECRET`). The only remedy is `deleteTest` / `deleteTestExecution` and a full rebuild — destructive, and it needs the human's approval. Get it right on the first call.

**Always link through TC-Router's linking step.** Both failures came from calling `createIssueLink` ad-hoc, which skips the reference that records the direction.

---

## 3. Both comments posted, in the settled shape

Two comments, one per ticket. Neither is optional.

**Main ticket** — header block, then three or four summarized conclusions. No per-case table.

```
QA Verification Result: Pass | Failed | Blocked   (with counts)
Test Execution: PROJ-XXXXX
Run: <n> · <YYYY-MM-DD HH:mm>
Environment: <url> · tenant <tenant-id> · build <x.y.z.nnn>

Preconditions
- ...

Conclusions
1..4
```

**Test Execution** — same header block, then the full record.

```
QA Verification Result: ...
Test Execution: PROJ-XXXXX
Run: <n> · <YYYY-MM-DD HH:mm>
Environment: ...

Preconditions
- ...

Test Results
| ID | Scenario | Expected | Actual | Status |

Observations for follow-up
Process notes
```

- Statuses are `Pass` / `Failed` / `Blocked` / `Inconclusive`. Not `PASS`. **`Inconclusive` whenever any
  `ENV —` or `SETUP —` run exists, or blocked+errored reaches a third of the suite** — the environment
  or the harness stopped the product being exercised, so a pass rate would be lying by omission
  (`qa-oracle-model.md` §8.6).
- **Four counts on both comments, never a bare pass rate:**
  `Passed: n · Failed: n · Blocked/errored: n · Not attempted: n (of m)`. The TE splits
  blocked/errored by prefix — `ENV —` / `SETUP —` / `UPSTREAM —` / `RISK —` — so a reader can tell
  "the product is broken" from "the environment is broken" at a glance.
- **`Run:` is mandatory**, on both comments. Retests stack: re-run a TE after a fix and you get two
  comments with identical headers and no way to tell them apart. Count the comments already on the TE
  to get `n`. This is **not** the prohibited "Date line" — that was a standalone date field; this is a
  run counter, and it was added to the standard later and deliberately.
- **`Environment` must carry the build number.** If it genuinely cannot be read, write
  `build unknown — <why>` rather than dropping the field. Three weeks later the build is the difference
  between "this was verified" and "verified against what?".
- **No** Ticket line and no Tester line.
- `Preconditions` is mandatory on both.
- Comments take **markdown**. `contentFormat: "html"` on a comment is escaped to literal tags — it does not error, it just renders wrong.
- Read the comment back and confirm the table and headings rendered.

---

## 4. Transitions — fetch, never reuse an id

```
getTransitionsForJiraIssue issueIdOrKey:<TICKET>
```

From **Ready for Testing there is no direct "Testing Approved" transition.** The path is **Ready for Testing → Testing (271) → Testing Approved (1061)**. A ticket already sitting in *Testing* moves in one hop, which is why an id copied from such a ticket silently does not apply.

A `BLOCKED` run whose comment starts `RISK —` is **not** outstanding — it auto-cleared (`qa-oracle-model.md` §6a) and does not hold the transition, provided check 6's three-place audit passes. Every other `BLOCKED`, `TO DO` and `EXECUTING` still does.

Transition only when nothing is outstanding, or when the human has explicitly accepted an outstanding case as non-gating — and if so, say that in the comment rather than leaving text that claims the opposite.

---

## Gate summary

| # | Check | Command | Pass condition |
|---|---|---|---|
| 0 | Reuse existing cases | `linkedIssues(t,"is tested by")` **before writing** | no duplicate of an existing case |
| 0.5 | Oracle named | state it in each case's Acceptance criteria | oracle is at the layer that does the work |
| 1 | Descriptions | `getTests` + `getJiraIssue` html | all non-empty; real `<h3>` and fenced gherkin |
| 2 | Links | `linkedIssues(t,"is tested by")` | count == all TCs + TE |
| 3 | Comments | read both back | header block + correct table shape on each |
| 4 | Transition | `getTransitionsForJiraIssue` | id taken from this issue's own list |
| 5 | No credentials | JQL sweep + Xray steps/run comments | no apiKey, password or token in any artefact |
| 6 | Traceability + oracle | read the TE's coverage table; `getTestRuns` for `RISK —` comments | every case has a non-empty `Traces` and an `Oracle` of `ac`/`prior-behaviour`/`risk`; every auto-cleared risk finding is in all three places |
| 6a | AC floor | coverage table vs the AC list | every AC / derived `R` has ≥1 `oracle: ac` case, or a stated reason it cannot |
| 6b | Ratchet | approved tag vs current tag | no tag downgraded after execution without the human's ruling, stated in the TE comment |

If any check fails, fix it before moving on. Do not report the work as complete with a known gate failure.

---

## Check 5 — no credential values in any artefact (added 2026-09-18)

No apiKey, password, token or connection string may appear in a test case description, test step,
Test Execution description, test run comment or ticket comment. Reference credentials by name and
location only.

Two sweeps are required, because **Xray step text and run comments are not in Jira's `text ~` index** —
a clean JQL result does not mean the artefacts are clean:

```
# 1. Jira descriptions + comments
project = <PROJ> AND text ~ "<first-8-chars-of-secret>*"

# 2. Xray steps and run comments
getTests(jql: "key in (<case keys>)") { results { steps { action data result } } }
getTestRuns(testExecIssueIds: ["<te issueId>"]) { results { comment } }
```

Origin: on PROJ-10920 the QA apiKey for the API under test reached six case descriptions, six step
actions, the TE description, a run comment and both verification comments before the configured QA
assignee caught it.


---

## Check 6 — every case traces to something, and names its oracle (added 2026-09-22)

Governed by `../references/qa-oracle-model.md`. Read the TE's `Test cases in this execution`
table and check every row:

- **`Traces` is non-empty** — an AC id, a derived `R` id, a changed symbol or file, or a consumer
  module from the blast-radius grep. "General coverage" is not a value.
- **`Oracle` is `ac`, `prior-behaviour` or `risk`.** `none` is not legal on a case.

A row failing either check **comes out of the execution before anything is executed or reported**: its
content moves to `Observations for dev` or `Open questions for product` in the TE description, and the
move is stated rather than done quietly.

Then check the authority is recorded, not just the tag: every `risk` case is listed under the table as
non-blocking, in words — *"a failure here is a flag for product, not a defect, and does not hold
Testing Approved."* A `risk` case that reads like an `ac` case in the report is the same false-failure
problem wearing a tag.

**Then audit every auto-clear — three places, all three required.** A `risk` deviation is written
`BLOCKED` with a reason starting `RISK —` and does not hold the transition. That discount is paid for
by the reporting, so the reporting is checked, not trusted:

```
getTestRuns(testExecIssueIds: ["<te issueId>"]) { results { status { name } comment } }
```

For every run whose comment starts `RISK —`, confirm all three exist:

| # | Where | Pass condition |
|---|---|---|
| 1 | The Xray run comment | Starts `RISK —`, and carries `Baseline applied:`, `Observed:` and a pointer to the TE |
| 2 | The TE description, `Risk findings` | A block for that case key, whose **`Why the AC cannot settle it:` line contains an actual quotation from the ticket** — not the words "the AC is silent" on their own — and which ends in a `Decision needed from product:` question |
| 3 | The story comment, `Risk findings` under `Conclusion` | A bullet for that case key containing the words "not a defect" and "does not hold approval" |

Any one missing fails the gate. A finding that auto-clears and is then under-reported is worse than one
that blocked: the ticket ships and nobody knows the question was ever asked.

**Then the two anti-false-pass audits.** Both are mechanical, and both exist because every discount in
`qa-oracle-model.md` is a route for a real defect to ship green.

**6a — the AC floor.** Every acceptance criterion, and every derived `R1..Rn`, has **at least one case
tagged `oracle: ac`**. Read the TE's coverage table against the AC list in the same description and
compare the two sets. An AC with no `ac`-tagged case means the run cannot be reported `Pass`, whatever
the other cases did — a suite can be 8-for-8 green and still never have tested the thing the ticket
promised. If an AC genuinely has no black-box observable, say so under the table as a stated decision
(*"criterion 6 is a build result, not observable"*) — that is a decision; silence is an oversight.

**6b — the ratchet.** Compare each case's `Oracle` in the TE table against the tag it was approved with.
Escalations (`risk` → `ac`/`prior-behaviour`) are fine and need no approval. **A downgrade — `ac` or
`prior-behaviour` → `risk`, or any executed case moved to an observation — fails the gate** unless
the human ruled on it and the TE comment says so with the reason. Downgrading a tag after a case has
failed is the single cheapest way to bury a defect.

**Why it hides:** a case with an invented expected result looks exactly like a real one in Xray — it
has a title, steps, a link and a folder. It only shows itself when it fails and nobody can say what it
was measuring against. PROJ-11089 (an a11y labelling expectation the ticket never made) and PROJ-11236
(against PROJ-10824) both had to be pulled back out of executions that already looked finished.
