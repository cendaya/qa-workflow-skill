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
- Assign the selected ticket to the configured QA assignee (resolve the accountId via `atlassianUserInfo`)
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

**Worked example** (PROJ-4892, a one-line Sigma query-parameter swap — abridged):

> **What changed:** one line. The service looks up a user in Sigma (the analytics tool) by email address.
> It used to ask using a parameter named `search`. Sigma turns `search` off on 2026-09-15, so it now asks
> using `email`.
>
> **Why it's high stakes:** that lookup happens every time someone opens an embedded dashboard. Break it
> and analytics dies for every product — no dashboards, no exports, no bookmarks.
>
> **What needs testing — 7 things:**
>
> 1. **Nothing looks different.** Open a dashboard as a known test user in one product, then one other
>    product. It should load as that user exactly as before. Boring = correct.
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

After delivering the briefing, continue straight into the environment preflight and Phase 0 — the briefing
is informational and does **not** block. But if the user asks anything about it, answer that first.

---

### Phase 0b — Environment preflight (HARD GATE, before any test case is written)

**This runs before Phase 1, not after Phase 2.** `CE-TC-UI` has its own environment ping at step 8a, but
that fires *after* the test cases and the Test Execution already exist — which means a dead environment is
discovered only once the artifacts are built and there is nothing left to do with them. That is exactly how
PROJ-10327 ended on 2026-09-15: 8 cases and a TE created, zero executed.

Resolve the URL from **one** source and say which one you used:

1. The tenant and account number named in the ticket itself always win — read them out of the description.
2. Otherwise `$env:USERPROFILE\.claude\qa-config.json`, `environments.<default_env>.ui.base_url`.

Credentials come from the environment variables named in that same block — `ui.username_env_var` and
`ui.password_env_var` (`QA_USERNAME` / `QA_PASSWORD` by default) — never prompt for them. Some tenants
use a different account from the default, so read the ticket before assuming. **The QA account is not
necessarily a sysadmin**: on the product under test, admin-only screens such as Setup Parameters and
Security Override redirect a non-admin user back to `/Login`, so anything needing them is `BLOCKED`, not
`FAILED`.

**An HTTP 200 does not mean the environment works.** Never gate on the status code alone — the product
under test renders its error page *with a 200*. On 2026-09-15 a status-only check reported QA healthy
after a four-hour outage; the browser then showed `Login failed for user '<db-user>'` — the app pool had
been fixed but the database credentials had not. A whole execution run would have been wasted on it.

Check the **content and the assets**, not the code. Load the page in a browser and confirm all four:

1. the page title is **not** `Error`
2. the username and password fields are present
3. no SQL, stack trace or "Oops! We couldn't load your page" text in the body
4. **`typeof window.jQuery !== 'undefined'`**, and no `/bundles/` request 404s

Item 4 is not optional and was learned the hard way. On 2026-09-15, QA passed items 1–3 — correct title,
real login form, no error text — while **every bundle 404'd**:
`/bundles/js/libraries.js`, `/bundles/js/dialog.js`, `/bundles/js/ui-behavior.js` and both CSS bundles.
jQuery never loaded, `$ is not defined` fired four times, the Sign In button did nothing and the
"unsupported browser" panel showed because the script that hides it never ran. The whole UI under test
is jQuery plus DevExpress, so nothing at all was testable — and the ticket under test happened to *be*
jQuery code, which cannot execute when `$` is undefined.

A cheap external equivalent, for a watch that has no browser — **note the tenant prefix**:

```
curl -s -o /dev/null -w "%{http_code}" https://<your-ui-host>/<tenant-id>/bundles/js/libraries.js
```

The **unprefixed** `/bundles/js/libraries.js` returns 404 even on a perfectly healthy environment, so a
check written against it fails forever and is worse than no check at all. That mistake was made on
2026-09-15 and corrected the next morning. The real fault that night was different and genuine: the
server was emitting *unprefixed* script tags, so the browser requested URLs that do not exist and jQuery
never loaded. Which is why the in-browser `typeof window.jQuery` assertion is the authority and the curl
is only a convenience — verify in the page whenever a browser is available.

Then branch:

| Result | Action |
|---|---|
| Login form renders | Say so with the resolved URL, the status code **and the page title**. Continue. |
| Anything else — non-200, an error page behind a 200, a timeout | **Stop here.** Report the URL, the exact error text, and which source the URL came from. Do not run Phase 1, do not write test cases, do not create a TE. Interactively, ask whether to wait or switch environment; unattended, log it and end the run. |

If `qa-config.json` and any stored environment note disagree on the URL, **say so and stop** rather than
picking one. That conflict is a configuration bug and guessing it produces a whole run of false BLOCKEDs.

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
- Find the code — see **Finding the code** below
- Read the diff
- Check linked Xray tests + CI status
- Validate each requirement, produce the pass/fail report

### Finding the code

**Search every repo the product spans, not just the main application repo.** Work on one product
routinely lands in more than one place — the web application repo, `<github.org>/<api-repo>` (the REST
API) and `<github.org>/<shared-lib-repo>` (shared libraries, including things like the payment iframe).
A ticket with no commits in the main application repo is *not* a ticket with no code — that mistake was
made for five tickets at once on 2026-09-16.

**Read the whole ticket first — description, comments, the Development section, and Engineering Notes.**
Not just the description. On PROJ-10613 the PR link sat in a comment (*"A pull request has been opened for
this ticket: …/pull/432"*), the real root cause sat in a second comment, and explicit QA steps plus a
database-backup path sat in `Engineering Notes - QA`. Searching git alone found none of it.

**Search alternate keys, not only the `PROJ-` key.** One ticket can carry two key systems: this project
also tracks work under legacy **`ALT-`** keys, and the branch, commits and PR may carry only that one.
PROJ-10613's fix is entirely under `ALT-40274` — four commits and PR #432, merged — while
`git log --grep "PROJ-10613"` returns only an unrelated test-spec deletion. Harvest candidate keys from
the comments, the attachment filenames (`alt-40274-fix.spec.ts` was sitting right there), and the branch
names, then search each.

In order of reliability:

```bash
git log --all --oneline --grep="<KEY>" -i          # local clone; try BOTH the PROJ- and any ALT- key
gh api -X GET search/issues -f q='<KEY> org:<github.org> type:pr'   # org-wide, more reliable than `gh search prs`
gh search commits "<KEY>" --repo <github.org>/<repo>   # when the key is not in a PR title
```

**Never conclude "no code" from a single key in a single repo.** That mistake was made for five tickets
at once on 2026-09-16; two of them had merged work.

**A merged PR is not required.** Code identifiable in a GitHub repo is enough to proceed — note the
absence of a PR entry and carry on (ruling from the configured QA assignee, 2026-09-16).

**But "exists" and "is deployed" are separate questions.** PROJ-10541 has PR #55 in
`<github.org>/<shared-lib-repo>`, **closed without merging**, on a branch *ahead 2 and behind 15* — in
GitHub, running nowhere. When code exists but is not deployed: validate it, write the cases, and mark
execution `BLOCKED` as not deployed rather than failing anything. Confirm containment with:

```bash
gh api repos/<owner>/<repo>/compare/<base>...<branch> --jq '{ahead:.ahead_by,behind:.behind_by,status:.status}'
```

**Do not trust Jira's Development panel.** It reported `pullrequest: MERGED, count=2` for PROJ-10613 while
its own JSON carried `"isStale": true`, and an org-wide search found zero PRs for that key anywhere.

**Verify fix presence by content, not by commit ancestry.** `git merge-base --is-ancestor` reported the
PROJ-8869 and PROJ-10823 fixes as absent from `origin/QA` when both were present — cherry-picks change
hashes. Grep the file on the branch instead:
`git show origin/QA:<path> | grep -c "<distinctive line from the fix>"`.

**Where the AC validation results go: the Test Execution, not the story.** The requirement table, the
verdicts, the evidence and the `For dev` block all belong on the TE, alongside the gap list that
Phase 1.6 already routes there. This keeps every QA artefact for a ticket in one place instead of
splitting the reasoning across two issues.

The story gets **one line**, and only once the TE exists:

```
QA in progress. AC validation results, the coverage matrix and the two coverage gaps found for dev
are on the Test Execution: **<TE key>**.
```

Sequencing follows from that: validation runs here in Phase 1, but its comment is **posted in Phase 2
once the TE has been created**. Hold the report until then rather than posting it to the story and
moving it later. The configured QA assignee's instruction, 2026-09-15 — the PROJ-10327 report went to the
story first and had to be relocated to PROJ-11090.

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
| **Oracle** | `ac` / `prior-behaviour` / `risk` / `none` — **where the expected result comes from**. See `../../references/qa-oracle-model.md`. This field decides everything below: only `ac` and `prior-behaviour` findings become blocking test cases, `risk` becomes a non-blocking one, `none` becomes an observation or a question and never a case |
| **Covered by** | The test case key that will exercise it (filled in during Phase 2), or `observation` / `question` when the oracle is `none` |

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

### The scope test — apply this to every finding before it goes anywhere

The governing rule is `../../references/qa-oracle-model.md`. Read it; this section is its
application at Phase 1.6.

Ask **two** questions, in order.

**First: does the ticket's own Expected Behavior cover this path?**

| Answer | What it is | Oracle | What to do |
|---|---|---|---|
| **Yes** | An **acceptance criterion failure**, not a gap | `ac` | A normal test case against the relevant `R`. Normal PASS/FAIL. It blocks Testing Approved and becomes a defect if it fails. Never use the word "gap" near it. |
| **No** | Not an AC failure — go to the second question | — | — |

**Second, for everything that answered "no": where else could the expected result come from?**

| Where | Oracle | What to do |
|---|---|---|
| The behaviour that held **before this change** — an existing passing test, a documented spec, or a demonstrated baseline you can point at | `prior-behaviour` | A normal blocking test case. This is the regression half of the suite. |
| Nowhere authoritative, but the input is one **the change actually touches** and a boundary/negative reading of it is defensible | `risk` | A test case, written **non-blocking**. State in the case's `Acceptance Criteria` section that the AC does not specify this input and name the baseline expectation being applied. A failure is flagged, not a defect, and does not hold Testing Approved on its own. |
| Nowhere. The AC is silent and the behaviour is not a departure from anything | `none` | **No test case, ever.** One paragraph under `Observations for dev`, or — better, when somebody has to decide — under `Open questions for product` in the TE description, phrased as *"the AC does not define behaviour when X; current behaviour is Y; is that intended?"* |

**Do not invent an expected result to fill a category.** A finding whose expected value you cannot
source is not a weak test case, it is undefined behaviour, and asserting against it is how a red run
stops meaning anything.

**Getting this wrong is the expensive mistake, and it is the one that actually happened.** On PROJ-10327
the finding most likely to reproduce the customer's original complaint — the double-arrow carrying
everything on a second pass after a round trip — was filed as "Gap B". The ticket's Expected Behavior
names *the double arrows* explicitly, so that was never a gap: it was R1 failing on a repeat pass.
Labelling it a gap is precisely what would have let it be waved through, because gaps are understood to
be out of scope and get ignored. The genuinely out-of-scope finding on the same ticket was the *single*
arrow, which the ticket never mentions.

### Never create a test case for an oracle-less finding

A case authored to document something that is not fixed — or to assert a value nobody specified — is a
permanently red run. It drags the TE's pass
rate down, it blocks the Testing Approved gate forever (that gate requires **every** run `PASSED`), and
worst of all it teaches everyone reading the board that a red run means nothing. The analysis is worth
doing; the artefact is what turns it into noise.

Carry the findings forward **by their oracle**:

- **`ac`** → Phase 2, a normal blocking test case against the requirement it breaks
- **`prior-behaviour`** → Phase 2, a normal blocking regression case naming the baseline it departs from
- **`risk`** → Phase 2, a case marked non-blocking. It is executed and written up like any other, but a
  deviation **auto-clears**: run `BLOCKED` with a `RISK —` reason, no queue entry, no human ruling, no
  hold on Testing Approved. The discount is paid for by reporting it in all three places — run comment,
  the TE's `Risk findings` section, and a `Risk findings` bullet under `Conclusion` on the story
  comment (`../../references/qa-oracle-model.md` §6a–6c)
- **`none`** → the TE description under `Observations for dev` or `Open questions for product`, never on
  the story, never a test case. Probe each one while testing anyway. If the probe confirms user impact,
  **raise a Defect** and create the test case against *that* ticket, where the defect's own Expected
  Behavior is finally a hard oracle and the case can pass or fail on its own terms
- **Cap by consequence.** Only record an observation you can finish this sentence for: *"a customer would
  notice this when…"*. If you cannot, drop it. "The code could be tidier" is not a finding
- Do **not** open a Defect straight from an observation unless the user asks. It is a code-review
  finding; a defect is what it becomes once execution confirms user impact

If the review turns up no gaps, say so explicitly — "gap analysis: no findings beyond the AC table" — rather than omitting the section. Report the oracle mix with it: *"D1–D4: two `ac`, one `risk`, one `none` (observation)."*

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

**First: does this ticket already have test cases?** Phase 1.5 checked the module's Test *Execution*
baseline — a different question. Before any drafting, read the ticket's links
(`getJiraIssue`, `fields: ["issuelinks"]`) and keep the **"is tested by"** links. If any exist, show
them — key, summary, current steps — and ask **update these / add only what's missing / start fresh**
(TC-Router step 4a holds the full table). Carry the answer into Phase 2 so TC-Router does not re-derive
it. Never generate over the top of linked coverage without that answer.

**Why:** nothing downstream catches it. The Test Execution is deduped by summary and the test-to-TE
link is deduped by issueId, so re-running this workflow on a ticket produces a *second set of cases*
hanging off the same ticket and the same execution, and every check still reports green.

**Run the full TC-Router workflow on this ticket.** TC-Router step 0 detects test type and routes:

- **API ticket** → CE-TC-API (happy path + edge + negative scenarios, smoke test, Postman JSON)
- **UI ticket** → CE-TC-UI (happy path + edge + negative scenarios)
- **Performance ticket** → CE-TC-Perf (baseline + load + overload, k6 script, smoke test)
- **Mixed / unclear** → TC-Router asks user which type, then proceeds

Carry forward context from Phase 1:
- The ticket's full requirements list — use it to ensure test cases cover every validated requirement
- Any requirements flagged as "manual check needed" in validation → generate explicit Manual test cases for those
- Out-of-scope changes flagged in Phase 1 → do NOT generate test cases for them (they're not in the ticket)
- **The oracle tag on every Phase 1.6 finding.** `ac` and `prior-behaviour` become blocking cases,
  `risk` becomes a non-blocking case, `none` never becomes a case at all

**Three rules protect against the opposite error — a green run that never tested anything**
(`../../references/qa-oracle-model.md` §5a). **(1) The ratchet:** the `Oracle` tag is frozen at
approval; after execution it may escalate (`risk` → `ac`) but never downgrade, and no executed case
becomes an observation, without the configured QA assignee's ruling stated in the TE comment.
**(2) Evidence the silence:** "the AC is silent" is a claim — quote the text you searched; if you
cannot, the tag defaults to `ac`. **(3) Doubt resolves toward blocking:** a wrongly-blocked ticket costs
one ruling, a wrongly-passed one ships.

**Every drafted case carries `Traces` and `Oracle` before it is presented for approval** —
`../../references/qa-oracle-model.md` §5. `Traces` is the AC/`R` id, the changed symbol, or the
consumer module from the blast-radius grep; at least one, never "general coverage". `Oracle` is `ac`,
`prior-behaviour` or `risk`. A case that cannot fill both is not in scope: it is an observation, and it
goes in the TE description instead. This is a hard gate, checked mechanically by publish-gate check 6.

**Consolidate by behaviour before writing.** Group the scenarios first: anything whose steps are identical
and differs only in the data fed in, or only in which module it points at, is **one** case with an
`Examples:` table — not one case per value. See TC-Router's iron rule "One case per distinct BEHAVIOUR".
Coverage must not shrink: every AC and every blast-radius module still has to appear as an example row, a
module row or a step. **Present the AC-to-case mapping** when the cases go for approval, so it is visible
that consolidating did not drop anything. PROJ-10500 was first written as 12 cases where 5 carried the same
coverage, and had to be rebuilt.

**Then run the publish gate** — `../../references/qa-publish-gate.md` — before Phase 2.5 executes
anything. Descriptions must be non-empty and rendering, and links must point the right way
(`inwardIssue` = TC/TE, `outwardIssue` = ticket). Both are far cheaper to fix now than after results exist.

### Regression coverage comes from the blast radius, not from the ticket

A regression case that only re-tests the changed behaviour is not a regression case. Before writing any,
**measure which modules the changed code can reach** — and measure it, never assume it from the folder
name. For each file in the diff:

| Change | How to find the consumers |
|---|---|
| A Razor partial | `grep -rn "<PartialName>" --include=*.cshtml` — every `RenderPartial`/`Partial` call site |
| A shared view / layout | same, plus anything that inherits it |
| A service or controller method | `grep -rn "<MethodName>"` across the solution; note every caller |
| A CSS class or JS hook | grep the class name — other screens may bind to it without sharing the fixed code |
| A SQL change | the other reports or screens reading the same table/columns |

Then add **one regression case per affected module** — covering that module still working *as a whole*,
not just the changed control. When a change is to a partial rendered into a screen, a fault in its
script block breaks the entire screen, so the case must cover the screen's other controls and check the
console for errors.

**Write the measurement into the TE description under `Blast radius`**, with the numbers. A reader must
be able to see what was checked and what the answer was, because "it's in `Views/Shared/` so it's risky"
and "it's in `Views/Shared/` but has one consumer" call for very different amounts of testing.

Worked example — PROJ-10327 changed `Views/Shared/CustomReportsCallStatusMultiSelect.cshtml`, which looks
wide open. Measured: **one** consumer (`CallLogReport/Index.cshtml:66`), no other definition of
`moveAllValues`, ~10 views using the `.headingWithSelect` hook but none with a dual-list move-all, and
six sibling multiselect partials none of which has an `appendTo` move-all. Affected module: the Call Log
Report screen alone → one regression case, PROJ-11095. Had any of those greps come back differently, the
execution would have needed a case per affected screen.

If the blast radius is genuinely large, say so and let the scope be a conversation — do not quietly
write forty cases, and do not quietly write none.

---

**The Test Execution is mandatory when TC-Router is invoked from this workflow.** TC-Router's own rule
("Test Execution is opt-in; ask once whether to create one") is written for a standalone run. Here,
Phase 2.5 cannot execute anything without a TE, so treat it as required and create it without asking.
Leaving it opt-in puts two user stops between validation and execution and is why a run told to go
start-to-finish dead-ends at Phase 2.

Set the TE's `description` **inside the `createTestExecution` call**, never as a follow-up edit.

---

### Phase 2.3 — Test Plan link (sprint number must match)

Find the plan from the **board**, not the ticket — the ticket normally names none, and reading it as
"no plan needed" leaves the TE orphaned:

```
project = <jira.project_key> AND issuetype = "Test Plan" AND status != Done ORDER BY created DESC
```

Then check the sprint before linking anything. The ticket's Sprint field is a custom field
(`customfield_10115` on many sites — confirm the id for your own site) and holds a **list** of every
sprint the ticket has passed through; take the entry whose `state` is `active` and ignore the `closed`
ones. Compare that number to the number in the plan's summary
(e.g. `PROJ-10856 | Sprint 377 - September 16 Release`):

- **Match** → link both the execution and its tests, then verify with `getTestPlan`.
- **Mismatch, or no open plan names the ticket's active sprint** → **leave the TE unlinked** and say so
  plainly: *"no open Test Plan for Sprint NNN; <TE> left unlinked."*

Never create a Test Plan, and never park a TE in the nearest plan just because it is the only one open —
a TE in a closed sprint's plan silently pads that sprint's numbers, which is worse than an absent one.

```
mutation { addTestExecutionsToTestPlan(issueId: "<plan id>", testExecIssueIds: ["<TE id>"]) { addedTestExecutions warning } }
mutation { addTestsToTestPlan(issueId: "<plan id>", testIssueIds: ["<case ids>"]) { addedTests warning } }
```

To undo: `removeTestExecutionsFromTestPlan` / `removeTestsFromTestPlan`, same arguments.

Both mistakes were made in one sitting on 2026-09-15 — first skipping the plan entirely, then linking
PROJ-11090 into Sprint 377's plan when PROJ-10327's active sprint was 378 and 377 was already closed.

---

### Phase 2.2 — Test-case table on the TE (MANDATORY on every Test Execution)

Once TC-Router has created the TE, its description must carry a **table of the test cases it holds**. A TE
whose description lists only acceptance criteria forces the reader to click through every linked test to find
out what is actually covered. The table makes the TE self-contained — the one artifact an executor needs.

Add (or update) this section in the TE description:

```
### Test cases in this execution

| Case | Key | Part | Title | Covers | Traces | Oracle |
| --- | --- | --- | --- | --- | --- | --- |
| <S1> | <TC key> | <group> | <test title> | <criteria numbers; gap IDs> | <AC id / symbol / module> | ac \| prior-behaviour \| risk |
```

- **Case** — the short draft id from Phase 2 (`S1`, `E3`, `G1`, …), so the TE, the report and the gap list all
  use one vocabulary.
- **Key** — the Xray test key.
- **Part** — the logical group the case belongs to (see grouping below). Use `—` when the ticket has no
  natural grouping.
- **Covers** — the AC/criterion numbers **and** any Phase 1.6 gap IDs (`D2`, `D6`) the case exercises. This is
  what makes the table auditable against Phase 1.
- **Traces** — the AC/`R` id, the changed symbol or file, or the consumer module from the blast-radius
  grep. Never empty.
- **Oracle** — `ac`, `prior-behaviour` or `risk` (`../../references/qa-oracle-model.md`). This is the
  column that says what a failure on the row is *allowed to mean*. `none` is not a legal value here — a
  finding with no oracle belongs under `Observations for dev` or `Open questions for product`, not in
  this table.

Under the table, list any `risk` cases by key with one line: *"non-blocking — the AC does not specify
`<input>`; a deviation here auto-clears as a flag for product, not a defect, and does not hold Testing
Approved."*

**A `Risk findings` section is mandatory on every TE description**, between `Test cases in this
execution` and `Observations for dev`. It holds the full write-up for each auto-cleared deviation —
input, the baseline applied *and where it came from*, why the AC cannot settle it, observed values, the
environment ladder, the counter-argument, the user-visible consequence, and the one question product
must answer. Shape in `qa-oracle-model.md` §6b. Write "none" under the heading rather than dropping
it.

Immediately after the table, state:

- The shared attributes, once, rather than repeating them per row — test type, label, Automation Status,
  Work Breakdown. E.g. "All seven are Manual, label `PROJ`, Automation Status `Not Automated`, Work Breakdown
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
- Tests **BLOCKED** → flag for manual follow-up with reason. (There is no `ABORTED` on this Xray
  instance — a write of it is rejected. `BLOCKED` is the value for anything that could not be run.)
- Tests **EXECUTING** → a suspected failure held back by the failure gate. Not a verdict; needs a human
  to rule on it before it becomes `FAILED` or is dismissed as environment noise.
- Tests **PASSED** → note coverage verified

**After all test runs are updated, transition the TE to Done — but verify first:**

Re-read `getTestRuns(testExecIssueIds: ["<TE id>"], limit: 100)` and require **zero `TO DO` and zero
`EXECUTING`** runs. Only then fetch transitions (load via ToolSearch
`select:mcp__plugin_atlassian_atlassian__getTransitionsForJiraIssue`), find "Done" (or equivalent), and
call `transitionJiraIssue`. No user confirmation needed at that point — TE closure is housekeeping.

If any run is still `TO DO` or `EXECUTING`, **do not transition**. Say which runs are outstanding and why.
"All runs are recorded" is not the same as "every run was executed and its write succeeded": a status write
can be silently rejected, and a TE with 3 of 8 executed must not be closed as Done.

If no "Done" transition is found, note it and continue — never block Phase 3.

---

### Phase 3 — Final report

**Gate before you report or transition.** Re-run all four checks in
`../../references/qa-publish-gate.md`. Check 4 matters most here: **fetch the transitions for this
issue** rather than reusing an id seen on another ticket. From *Ready for Testing* there is **no direct
"Testing Approved" transition** — the path is **Ready for Testing → Testing → Testing Approved**. A ticket
already in *Testing* moves in one hop, which is why a copied id silently fails.

Do not report work as complete with a known gate failure. If the configured QA assignee has accepted an
outstanding case as non-gating, transition — but say so in the comment, and make sure no earlier line
still claims the ticket is being held.

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

**Two comments, two audiences** — the full spec lives in `CE-Execute-TE` Step 6a/6b. Same three header
lines on both; what follows differs.

The **main ticket** gets the conclusions and nothing else:

```
**QA Verification Result:** Pass / Failed / Blocked
**Test Execution:** <TE key>
**Run:** <n> · <YYYY-MM-DD HH:mm>
**Environment:** <URL> · tenant <nnnnnnn> · build <x.y.z.nnn>

### Conclusion
- <The reported defect is fixed: what now happens, in the user's words.>
- <Existing behaviour is unaffected — the regression statement.>
- <Any related path probed and its outcome.>
- <Accessibility or secondary conclusion, if there is one.>

<n> of <m> cases passed. Full results, preconditions and per-case evidence are on **<TE key>**.
```

Every header field is mandatory — `build unknown — <why>` rather than dropping it. The **Run** number
counts the verification comments already on the TE, so retests don't stack indistinguishably. The
count line appears even on a failure: what still works narrows the search as much as what broke.

**Three or four bullets, never more.** Each is a conclusion about the *product*, not a report on the
testing — "the defect is fixed", not "8 cases executed". **One must always speak to regression**, since
that is what a reader deciding to ship actually needs. No preconditions, no per-case table, no repro
steps, no file paths on the story.

The **Test Execution** gets everything: preconditions, the full Test Results table, the AC validation
table, the coverage gaps for dev, and — when something failed — the narrative
Summary / Steps to Reproduce / Expected Result / Actual Result block, one per failing scenario.

The rule: **the story answers "can this ship?", the Test Execution answers "why do we believe that?"**

After the full report and risk checklist, show the draft comment and ask:

> "Post this summary comment to <TICKET> in Jira? (yes / no)"

**Wait for explicit confirmation before posting.** On "yes", post via `addCommentToJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__addCommentToJiraIssue`).

### Ticket transition — Testing Approved

After the completion notification is successfully posted, **offer** to transition the ticket to Testing Approved **only when Phase 1 validation was ✅ Full pass AND every run in Phase 2.5 is `PASSED`**. A single `FAILED`, `BLOCKED`, `EXECUTING` or `TO DO` run disqualifies it. If not every run passed, skip and note: "Testing Approved transition skipped — <n> run(s) not PASSED in Phase 2.5. Resolve them before marking Testing Approved."

State the gate positively like that rather than as "zero FAILED or ABORTED": `ABORTED` does not exist on this instance, so a gate phrased against it can never trip on the un-runnable cases it was meant to catch, and `BLOCKED` runs would sail straight through to Testing Approved.

Fetch transitions via `getTransitionsForJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getTransitionsForJiraIssue`). Look for a transition named "Testing Approved", "Approved", "QA Approved", or equivalent. **Ask the user first:** "Transition <TICKET> to Testing Approved? (yes / no)". Only call `transitionJiraIssue` with the matched transition id on "yes" — this is the **main ticket**, not the TE, and the skill's own iron rule ("never transition a ticket without explicit user confirmation") applies here same as anywhere else. The earlier automatic TE→Done transition (Phase 2.5) is a separate, narrower exception scoped to the test-execution housekeeping ticket only — it does not extend to the main ticket.

If no matching transition is found, inform the user: "No 'Testing Approved' transition available from the current status. Available transitions: <list>. Transition manually if needed."

## Unattended mode

The iron rules below assume a human is watching. When this workflow is driven on a schedule — see your
unattended routine file (`$env:USERPROFILE\.claude\automation\<your-routine>.md`) — nobody will answer a
question, so every "ask the user" gate has to resolve one way or the other in advance. **Never invent a
third option: act per the table or stop and log it.**

| Gate | Interactive | Unattended |
|---|---|---|
| Ticket selection (CE-ForTesting) | user picks from the ranked list | take the highest-priority eligible ticket per the routine's ordering rule; the "never auto-select" rule is suspended here and only here |
| Phase 0a briefing | first output, user-facing | write it to the run log instead of the chat |
| Phase 0b environment preflight | ask whether to wait or switch | **hard stop**, log the URL and error, end the run |
| In QA transition | ask | do it |
| Phase 1 ⚠️ Partial or ❌ Fail | ask which of the 4 options | proceed to Phase 2 for Partial; **stop the ticket** on Fail, log it, leave it unprocessed so it retries |
| Auto-filing bugs from ❌ failures | ask, then CE-Create-Bug | **never**. Queue the finding for a human. |
| Test Execution creation | opt-in | required (Phase 2) |
| Test Plan link | user picks the plan | sprint-match rule in Phase 2.3; unlinked on mismatch |
| Manual test steps ("Result? pass/fail/blocked") | user answers | drive it yourself; if it genuinely cannot be driven, `BLOCKED` with the reason |
| Failing test | write `FAILED` | **failure gate** — `EXECUTING` + queue entry + notify. Never `FAILED`. |
| Test **errored** rather than failed | — | Not a result. `BLOCKED` prefixed `ENV —` / `SETUP —` / `UPSTREAM —` per `qa-oracle-model.md` §8; never `FAILED`. Three in a row on the same environmental cause → stop the run, rest stays `TO DO`, TE goes to your execution queue (`$env:USERPROFILE\.claude\automation\<your-execution-queue>.md`) |
| Posting the Jira comment | ask | post it |
| TE → Done | automatic after the zero-`TO DO`/zero-`EXECUTING` check | same |
| Main ticket → Testing Approved | ask | only when every run is `PASSED` **or is a `BLOCKED` run whose reason starts `RISK —`** (those auto-clear, `qa-oracle-model.md` §6a); otherwise leave in Testing and queue. An auto-cleared risk finding must already be reported in all three places before the transition is offered |

Anything not in this table keeps its interactive behaviour, which means it blocks — so if a run stalls
unattended, the missing row is the bug.

## Iron rules

- **Never skip CE-ForTesting when no ticket is provided.** Always surface and rank available tickets — never guess or auto-select one. *(Suspended in unattended mode — see the table above.)*
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
- Writing a case whose expected result you invented. → If neither the AC nor the prior behaviour says what should happen, there is no oracle: it is an observation or a question for product, not a case. `../../references/qa-oracle-model.md`.
- Judging a `risk` case at the same severity as an `ac` one. → A boundary you chose yourself failing is a flag, not a defect. It auto-clears; say so in the report instead of letting it read as a failure.
- Auto-clearing a `risk` deviation and then mentioning it in only one place. → All three, every time: run comment, TE `Risk findings`, story `Risk findings` under `Conclusion`. Publish-gate check 6 fails the run otherwise. A finding that ships unnoticed is the cost of getting the auto-clear wrong.
- Filing a Defect straight off a gap. → A gap is a code-review finding. It becomes a defect once manual execution confirms user impact, and only if the user asks for a ticket.
- Reporting a gap as "looks like it overlaps / may be slow". → Prove it with a probe, quote the measured numbers, then delete the probe.
- Jumping to TC-Router without finishing the full CE-AC-Validator report. → Complete Phase 1 entirely first.
- Drafting test cases without checking the ticket's "is tested by" links first. → A re-run then hangs a second set of cases off the same ticket and the same TE, and nothing downstream flags it. Ask update / add-only / start fresh before Phase 2.
- Generating test cases for out-of-scope changes flagged in validation. → Only test what's in the ticket.
- Auto-proceeding after a Partial verdict. → Ask the user.
- Losing the requirement list between phases. → Use Phase 1's requirement table to guide Phase 2 case coverage.
- Skipping Phase 2.5 because TC-Router didn't create a TE. → Ask the user for the TE key; never proceed to Phase 3 without executing.
- Auto-transitioning the main ticket to Testing Approved because the gate conditions (full pass + zero failures) are met. → The gate conditions decide whether to *offer* the transition, not whether to skip asking. Always confirm with the user first — the TE→Done auto-transition in Phase 2.5 is a narrow exception for that housekeeping ticket only and doesn't extend to the main ticket.
