# The oracle model — what a case is allowed to assert, and what may fail a run

> Ships with the qa-workflow plugin and is cited by the skills in `plugins/qa-workflow/skills/` — the section numbers and anchors below are load-bearing, do not renumber them.

**Read this before drafting any test case and before writing any result.** It is the single source of
truth for scope (*what gets a case at all*) and for verdict authority (*what a failing case is allowed
to mean*). `CE-QA-Workflow` Phase 1.6, `TC-Router` step 5a, `CE-Execute-TE`, an unattended run's
steps 3/5/7 and `../references/qa-publish-gate.md` check 6 all defer to this file.

## The problem it solves

A test that fails because the agent invented an expected result is not a defect — it is **undefined
behaviour reported as a failure**. The name for this is the *oracle problem*: an assertion is only as
good as the authority that says what *should* happen. Gap-hunting produces findings with no such
authority, and writing them as pass/fail cases produces permanently red runs, a blocked
*Testing Approved* gate, and a board where red means nothing.

The fix is not to stop exploring. It is to **tag every case with where its expected result came from**,
and let that tag decide whether a failure can block.

---

## 1. Blast radius — is it in scope at all?

Three inputs bound the scope. **A case must trace to at least one of them.** If it traces to none, it
is speculative and must not carry a pass/fail assertion.

| Input | Where it comes from | Strength |
|---|---|---|
| **The change** | The merge-commit diff: files, methods, endpoints, columns, views actually touched | Strongest signal |
| **The AC** | What the ticket explicitly promises — or, on an AC-less `<PROJ>` Production Defect, the `R1..Rn` derived from Expected Behavior plus the commit body, stated as derived | Strongest signal |
| **Dependent modules** | Measured consumers of the changed code — `RenderPartial` call sites, method callers, CSS/JS hooks, other readers of the same table. **Measured by grep, never inferred from a folder name** (see `CE-QA-Workflow` Phase 2) | Where regression risk actually lives |

## 2. The four categories, and what a failure means

Tag every drafted case with exactly one. **The tag decides the verdict authority — categories are not
interchangeable and must not be judged at the same severity.**

| # | Category | Oracle source | Oracle strength | A failure means | May it block *Testing Approved*? |
|---|---|---|---|---|---|
| 1 | **AC-derived functional** | `ac` — the quoted AC or derived `R` | Hard | A real defect | **Yes** |
| 2 | **Regression** | `prior-behaviour` — the behaviour that held *before* the change, ideally an existing passing test or a documented spec | Hard | A regression, a real defect | **Yes** |
| 3 | **Risk-based edge / negative / boundary** | `risk` — equivalence partitioning or boundary analysis applied to **inputs the change actually touches** | Medium | *May* be a defect | **No — flags and auto-clears** (§6a) |
| 4 | **Gap / exploratory** | `none` — the AC never specified this | **No oracle** | Nothing. There is no expected result to compare against | **Never a case at all** |

Category 4 is the whole reason for this document. It never becomes a test case.

## 3. Category 4 — the two legal outputs

When a finding has no oracle, do **one** of these. Never a third thing, and never an assertion.

**(a) An observation.** Record it without a verdict, under `Observations for dev` in the TE description:

> `<input or state X>` produces `<observed output Y>`. The AC is silent on `X`. No verdict recorded —
> there is no specified behaviour to compare against.

**(b) A spec question.** Route it back to whoever owns the requirement, under
`Open questions for product` in the TE description:

> The AC does not define behaviour when `<field is empty / negative / null / locale is fr-CA>`.
> Current behaviour is `<Y>`. Is that intended?

(b) is the higher-value form: half the time it surfaces a missing requirement rather than a non-bug.
Use (a) when the behaviour is plainly harmless, (b) when someone has to decide.

**Cap by consequence.** Only record an observation you can finish this sentence for: *"a customer would
notice this when…"*. If you cannot, drop it. "The code could be tidier" is not an observation.

If a probe later proves user impact, **raise a Defect** and write the case against *that* ticket — where
the AC is the defect's own Expected Behavior, so the case finally has a hard oracle and can legitimately
fail.

## 4. Cover vs skip

**Cover** — write a case when it is:

- traceable to an AC or a derived `R`
- inside the measured dependency graph of the change
- a high-risk path the change reaches: auth, payments, data integrity, anything with high impact × likelihood
- a boundary or negative **on an input the change actually touches**

**Skip, or downgrade to an observation** — no case when it is:

- outside the blast radius
- stable unchanged code that already has passing coverage
- third-party or framework internals
- non-deterministic or environment-dependent with no stable oracle
- speculative behaviour with no requirement behind it
- a pre-existing fault the change did not introduce (classify it, record it, judge the ticket on what it changed)

A per-category coverage requirement — CE-TC-UI's happy/edge/negative/a11y grid, CE-TC-API's and
CE-TC-Perf's equivalents — is **subordinate to this test**. A category with nothing traceable to the
blast radius produces a stated reason in the report, not a case invented to fill the row.

## 5. Required fields on every drafted case

Two fields, settled **before** the case is presented for approval. A case that cannot fill both is not
ready to be written.

| Field | Value | Notes |
|---|---|---|
| `Traces` | The AC id / derived `R` id, **or** the changed symbol or file, **or** the consumer module from the blast-radius grep | At least one. Never empty, never "general coverage" |
| `Oracle` | `ac` \| `prior-behaviour` \| `risk` | `none` is not a legal value on a case — it means the finding is an observation instead |

**Where they live:**

- The working markdown file (`<TICKET>.md`) carries them as `**Traces:**` / `**Oracle:**` lines.
- The **Xray test case description does not change shape.** It stays the four PROJ-187 sections. The
  traceability already lives inside `Acceptance Criteria`: quote the AC/`R` for `oracle: ac`; for
  `oracle: prior-behaviour` name the changed symbol and state the behaviour that held before the change;
  for `oracle: risk` say plainly that the AC does not specify this input, and state the baseline
  expectation being applied and where it comes from.
- The **Test Execution coverage table carries the tags** — an `Oracle` column and a `Traces` column.
  That table is the auditable copy.

## 5a. The three anti-false-pass rules

Every discount in this file — auto-clear, observations, `BLOCKED` prefixes — is a way for a real defect
to ship as a green run if the tagging is wrong. These three rules exist to make that expensive.

### Rule 1 — the ratchet: tags escalate, never downgrade

**The `Oracle` tag is frozen when the case is approved, before anyone knows whether it will fail.**
That timing is deliberate: a tag chosen in ignorance of the outcome cannot be motivated reasoning.

After the first execution:

| Move | Allowed? |
|---|---|
| `risk` → `ac` or `prior-behaviour` (you found the requirement or the baseline) | **Yes** — escalation, do it |
| Any tag → genuine failure via an implicit oracle (§6a) | **Yes** — always |
| `ac` or `prior-behaviour` → `risk` | **No.** The human rules on it |
| Any case → an observation, after it has been executed | **No.** The human rules on it |

A downgrade after a case has failed is the exact move that buries a defect, and it is how PROJ-10327's
double-arrow finding became "Gap B". Any tag change at all is stated in the TE comment with the reason —
never done silently.

### Rule 2 — the silence must be evidenced, not asserted

"The AC is silent on this" is a **claim**, and it carries the same evidence burden as a pass. To tag
anything `risk` or `none`, quote the text you searched — the AC block, the Expected Behavior, the
derived `R1..Rn`, the commit body — and show the silence. Name what you looked for.

**If you cannot quote the ticket text, the tag defaults to `ac`.** Not knowing whether the ticket
covers a path is not the same as the ticket not covering it.

This is auditable, not just advisory: the quotation is a **required field** — `Why the AC cannot settle
it:` in the TE's `Risk findings` block (§6b) — and publish-gate check 6 fails a block whose line reads
"the AC is silent" with nothing quoted. A claim with no quoted source is treated as an unevidenced
claim, exactly like a `PASS` with no observation behind it.

### Rule 3 — doubt resolves toward blocking

Unsure between `ac` and `risk`? `ac`. Unsure whether a deviation is a disagreement or an implicit-oracle
violation? A violation. Unsure whether an error was environmental or a genuine failure? Investigate
before writing; if it still will not resolve, the failure gate.

The asymmetry is the point: **a wrongly-blocked ticket costs one ruling from the human; a wrongly-passed
one ships.** Never resolve doubt toward the option that lets the run finish faster.

---

## 6. Verdict authority at execution time

| Oracle on the case | It fails | What to write |
|---|---|---|
| `ac` | Suspected defect | The **failure gate**: `EXECUTING` + queue entry. Never `FAILED` unattended. Blocks *Testing Approved* |
| `prior-behaviour` | Suspected regression | Same failure gate. Blocks *Testing Approved*. Walk the environment ladder first — a pre-existing fault is not this ticket's regression |
| `risk` | **Flag, and auto-clear** | Write the run `BLOCKED` with a reason starting `RISK —`. It does **not** go in the pending-failure queue, it does **not** need a human ruling, and it does **not** hold *Testing Approved*. It is reported in three places instead (§6a) |
| `none` | Cannot happen | A case with no oracle reaching the TE is a Phase 1.6 error: pull it out of the execution, move its content to `Observations for dev`, and say you did |

A `risk` deviation still gets the full write-up — the three-environment ladder, the exact error text, the
counter-argument. It is downgraded in *authority*, not in rigour.

### 6a. Auto-clear — what `risk` does instead of blocking

**Why `BLOCKED` and not `PASSED`.** A `risk` case that deviates has not failed against any authority, so
`FAILED` is a lie; but it also did not meet the baseline the case applied, so `PASSED` is a worse lie —
it hides the finding behind a green row. `EXECUTING` would re-block both gates and defeat the
auto-clear. On an instance whose only statuses are `PASSED` / `FAILED` / `TO DO` / `EXECUTING` /
`BLOCKED`, `BLOCKED` is the one honest slot: *no verdict recorded*. Make it unmistakable with the
reason string, which is mandatory and starts with the prefix:

```
RISK — no authoritative expected result; verdict withheld.
Baseline applied: <what the case expected and where that came from>.
Observed: <what actually happened>.
See "Risk findings" on <TE key>.
```

#### The implicit-oracle carve-out — a `risk` case can still be a real failure

**Auto-clear applies to disagreements about behaviour, never to the system falling over.** Some
outcomes need no specification to be wrong. If a `risk` case produces any of these, it is a **genuine
failure**: it goes to the failure gate as a suspected defect, it is queued for a human ruling, and it
**blocks** *Testing Approved* exactly like an `ac` failure. The `risk` tag does not protect it.

| Implicit oracle | Examples |
|---|---|
| **It crashed** | Unhandled exception, stack trace on screen, 500, YSOD, JS error that halts the page |
| **Data integrity** | A record lost, overwritten, orphaned, silently truncated, or written to the wrong tenant |
| **Security / privacy** | Another tenant's or user's data visible, an authorisation check bypassed, a secret rendered |
| **It hung** | Deadlock, infinite spinner, a request that never returns |

Nobody has to have written "don't crash". The distinction in practice:

| Deviation on a `risk` case | What it is |
|---|---|
| "Blank date saved as `01/01/1900` instead of staying blank" | A disagreement. The AC is silent. **Auto-clears** |
| "Blank date returns a 500" | Implicit-oracle violation. **Real failure, queued, blocks** |
| "Blank date wipes the customer's other dates" | Data integrity. **Real failure, queued, blocks** |

When in doubt between the two, treat it as a failure and queue it. A queued non-defect costs one
ruling; an auto-cleared crash ships.

**Both gates carve it out.** A `BLOCKED` run whose reason starts `RISK —` does not hold *Testing
Approved*, and does not hold the TE at `Done`. Every other `BLOCKED` still does. Nothing else about
either gate changes: a `TO DO`, an `EXECUTING`, an ordinary `BLOCKED` or any queued `ac` /
`prior-behaviour` failure still stops the transition.

**It is reported in exactly three places, and never only one:**

| Where | Depth | Shape |
|---|---|---|
| The **Xray run comment** | One paragraph | The `RISK —` block above |
| The **Test Execution description**, section `Risk findings` | **The full explanation** — this is the detailed record | Per §6b |
| The **story comment**, a `Risk findings` section **directly under `Conclusion`** | Two or three lines per finding | Per §6c |

A risk finding that reaches only the TE has effectively been buried: nobody reading the story learns the
ticket shipped with an unspecified behaviour. A risk finding that reaches only the story has no detail
anybody can act on. Both, every time.

### 6b. The TE `Risk findings` section — the detailed record

Lives in the **Test Execution description**, after `Test cases in this execution` and before
`Observations for dev`. One block per `risk` case that deviated. Write "none" under the heading when
there were none, rather than dropping it.

```
### Risk findings

**<CASE KEY> — <case title>**  ·  oracle: risk · run: BLOCKED (auto-cleared, non-gating)

- **Input under test:** <the boundary/negative input, and which changed symbol or file makes it in-scope>
- **Baseline applied:** <the expectation the case asserted, and exactly where it came from — the
  analogous field, the sibling endpoint, the framework default. Name it. "It seemed reasonable" is not
  a baseline>
- **Why the AC cannot settle it:** <quote the AC or derived R and show the silence>
- **Observed:** <what actually happened, with exact values or error text>
- **Environment ladder:** <tenant <tenant-a> / tenant <tenant-b> / staging <tenant-b> — each yes-no,
  and what that classifies it as>
- **Could be environment because:** <the strongest counter-argument, or "nothing obvious">
- **User-visible consequence:** <finish "a customer would notice this when…", or say it is invisible
  today and why it is still worth recording>
- **Decision needed from product:** <the one question, phrased so it can be answered yes/no>
```

The last line is the point of the whole section. A risk finding that does not end in a question somebody
can answer is an observation — move it to `Observations for dev` instead.

### 6c. The story comment — `Risk findings`, under `Conclusion`

The story comment stays short. Add a `Risk findings` section **immediately after `Conclusion`**, before
the closing count line — not at the end, and not folded into the conclusions themselves, where it would
read as a verdict on the fix:

```
### Risk findings
- **<CASE KEY>** — <one sentence: the input, and what was observed>. The acceptance criteria do not
  specify this, so it is recorded as a flag for product, not a defect, and does not hold approval.
  <The question product needs to answer.> Detail on <TE key>.
```

Rules for it:

- **Only when there is one.** No empty section on the story, unlike the TE.
- **Never reword it into a defect.** "does not hold approval" or "not a defect" appears verbatim in
  every entry. A reader skimming the story must not come away thinking something is broken.
- **Never reword it into a non-event either.** No "minor", no "cosmetic", no "worth noting". The
  finding is stated flatly and the question is asked.
- The count line still reports the run honestly: `7 of 8 cases passed; 1 auto-cleared risk finding.`

## 7. Enforcement

`../references/qa-publish-gate.md` **check 6** is mechanical: every case in the TE has a non-empty
`Traces` and an `Oracle` of `ac`, `prior-behaviour` or `risk`. Any case tagged `none`, or with an empty
`Traces`, fails the gate and comes out of the execution before anything is executed or reported.

Check 6 also audits the auto-clear: every `BLOCKED` run whose reason starts `RISK —` must have a
matching block in the TE's `Risk findings` section **and** a bullet under `Risk findings` in the story
comment. An auto-cleared finding reported in fewer than all three places fails the gate — auto-clearing
is what makes under-reporting it cheap, so the reporting is checked rather than trusted.

---

## Origin

PROJ-10327 is the worked example in both directions. The double-arrow finding was filed as "Gap B" when
the ticket's Expected Behavior names the double arrows explicitly — that was `oracle: ac` mislabelled as
a gap, and gaps get waved through. The *single*-arrow finding on the same ticket genuinely had no oracle.
PROJ-11089's a11y case asserted a labelling expectation the ticket never made, and had to be pulled out of
PROJ-11090 after the fact. PROJ-11236 was recorded against PROJ-10824 and then withdrawn into
`Observations for dev` for the same reason. Three removals, one cause: an assertion with no authority
behind it.


---

## 8. Errors are not results — the status taxonomy

The oracle rule says *what a comparison is allowed to mean*. This section says *whether a comparison
happened at all*. They are the same discipline, and the same failure mode: a run whose "failures" are
really broken setup tells you nothing about the code under test.

**A failure means the oracle was checked and actual did not match expected. An error means the check
never happened.** Writing `FAILED` for an error is the most expensive mistake in this file — it sends a
developer after a defect that does not exist, and it hides the environment problem that actually needs
fixing.

### 8.1 Classify the error before writing anything

The location of the error determines everything downstream. Four buckets:

**`BLOCKED` is not an escape hatch.** All three error prefixes hold *Testing Approved* and hold the TE
out of `Done`, precisely so that "I could not work out how to test this" cannot become a green ticket.
A `SETUP —` written because the harness was hard to build is honest and blocks; a `SETUP —` written to
avoid a difficult case is the false pass this whole file exists to prevent. If a case is genuinely
un-runnable by anyone, say who could run it and what they would need.

| Bucket | What it looks like | Status to write | Does the product get judged? |
|---|---|---|---|
| **Environment / infrastructure** | App unreachable, DB connection refused, healthy endpoint 500s, timeout, expired auth token, tenant missing, build not deployed | `BLOCKED` prefixed `ENV —` | No. The system under test was never exercised |
| **Setup / precondition** | The arrange step broke: fixture would not build, seed data absent, an upstream case that should have created the record did not, no sysadmin rights to reach the screen | `BLOCKED` prefixed `SETUP —` | No. The defect, if any, is in the harness |
| **Cascade** | The case itself is fine, but an earlier error left the app or data in a state it cannot start from | `BLOCKED` prefixed `UPSTREAM —` | No. One problem, not N |
| **Genuine failure** | The code ran, produced output, and it did not match a real oracle (`ac` / `prior-behaviour`, or an implicit oracle per §6a) | The **failure gate** — `EXECUTING` + queue | Yes |
| **Oracle-less deviation** | The code ran and did something unexpected, but nothing authoritative says what should have happened | `BLOCKED` prefixed `RISK —`, auto-clears (§6a) | Not as a verdict — as a question |

`ENV —`, `SETUP —` and `UPSTREAM —` all **block** *Testing Approved* and hold the TE out of `Done`.
`RISK —` is the only prefix that auto-clears. That is the whole difference between them: a risk finding
has been investigated and settled; an error has not been investigated at all.

### 8.2 Fail fast on a dead environment

A wall of identical errors is **one problem, not two hundred**. When three consecutive cases error for
the same environmental reason — or the environment preflight fails outright — **stop the run**:

- Do not grind through the remaining cases to produce a row of `BLOCKED`s that all say the same thing.
- Leave the un-attempted cases at `TO DO`. They were not attempted; `BLOCKED` would claim they were.
- Write **one** `ENV —` entry naming the URL, the exact error, and where the URL came from.
- Append the TE to your execution queue
  (`$env:USERPROFILE\.claude\automation\<your-execution-queue>.md`) — that file exists precisely for
  executions that are built and waiting only on an environment — and move to the next ticket.

This is the existing environment-preflight hard gate applied mid-run rather than only at the start.

### 8.3 Retry only the retryable

| Error | Retry? |
|---|---|
| Network blip, timeout, 502/503/504, rate limit | **Yes** — 2 attempts, with backoff |
| Anything else environmental | No. Classify and stop |
| A genuine assertion failure | **Never.** Retrying an assertion hides real defects |

Every retry is logged. **A case that only passes on retry is flaky, not green**: write `PASSED`, then
record it under `Observations for dev` in the words *"passed on retry N of 2 — flaky, not a clean
pass"*, and carry it into the story comment's count line. A silently-retried green is how a real
intermittent defect gets shipped.

### 8.4 Isolate the blast radius of an error

Each case starts from a known state. When that cannot be guaranteed and an error has left the app or
the data dirty, **detect the cascade rather than reporting N independent findings**: mark the
downstream cases `UPSTREAM —` naming the case that broke, and say in the report that they were not
independently exercised. Ten `FAILED`s from one bad teardown is the single most misleading artefact
this workflow can produce.

### 8.5 Capture diagnostics at the moment of error

The highest-leverage thing in this section. At the point of the error, before retrying, navigating away
or cleaning up, capture:

- The exact error text and stack trace, quoted, not paraphrased
- The request and response — URL, method, status, body — for anything over the wire
- A screenshot **and** the DOM snapshot for UI, the console log, the network tab entry
- The exact input that produced it, and the state the app was in
- The build number and tenant

An error report with no evidence is noise a human has to reproduce from scratch. Everything above is
recoverable in the moment and unrecoverable ten minutes later.

### 8.6 Report completion separately from results

The final report carries **four counts, never a bare pass rate**:

```
Passed: n · Failed: n · Blocked/errored: n · Not attempted: n   (of m)
```

- `Blocked/errored` splits by prefix in the TE: `ENV —`, `SETUP —`, `UPSTREAM —`, `RISK —`.
- **When any `ENV —` or `SETUP —` exists, or blocked+errored is a third or more of the suite, the
  headline is `Inconclusive`, not a pass rate.** Say it in those words: *"the run is inconclusive — the
  environment prevented n of m cases from being exercised; fix and re-run."*
- `RISK —` runs do **not** make a run inconclusive. They were exercised; only the verdict was withheld.

Reporting "80% passed" while a third of the suite errored is lying by omission. A human reading the
report must be able to tell **"the product is broken"** from **"the environment or the harness is
broken"** at a glance — that separation is the entire point of this section.
