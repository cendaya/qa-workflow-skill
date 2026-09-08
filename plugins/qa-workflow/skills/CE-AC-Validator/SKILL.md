---
name: CE-AC-Validator
description: Use when validating whether a merged PR satisfies a Jira ticket in its entirety — reads the full ticket, finds the linked GitHub PR, analyzes the diff against every requirement and AC item, checks linked Xray test results, and produces a per-requirement pass/fail report. Triggers include "validate ticket PROJ-XXXX", "check if PR satisfies the ticket", "does the merge satisfy AC", "AC validation for PROJ-XXXX", "verify implementation against ticket", "did this PR cover everything".
---

# CE-AC-Validator

Validate whether a merged GitHub PR fully satisfies a Jira ticket — its summary, description, all requirements, and acceptance criteria. Produces a per-requirement pass/fail report with evidence from the diff and linked tests.

## Inputs (ask for any that are missing)

1. **Ticket** — e.g. `PROJ-9123`. Project derived from the key.
2. **PR** — optional. Discovered automatically from ticket's remote issue links or GitHub search. Provide if auto-discovery fails.

## Iron rules

- **Never mark a requirement "pass" without code evidence in the diff.** PR title or description alone is not evidence.
- **Never mark "fail" without explaining specifically what's missing.**
- **Test results are authoritative.** A linked test that failed = that requirement fails, regardless of code analysis.
- **Out-of-scope changes are flagged, not failed.** Report them; the user decides whether they're acceptable.
- **Parse the entire ticket**, not just the AC section. Requirements hide in description body, engineering notes, QA notes, and scope sections.

## Workflow

Create a TodoWrite item per step.

### Step 1 — Read the full ticket

Load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getJiraIssue`. Extract every field:

- **Summary** — stated goal / feature
- **Description** — requirements, context, technical details, engineering notes, scope
- **Acceptance Criteria** — explicit AC bullets (may be a custom field or inside description)
- **QA / Testing notes** — testing checklist items
- **Labels, issuetype, components** — scope context
- **Remote issue links** — load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getJiraIssueRemoteIssueLinks`. Scan for GitHub PR URLs (`github.com/.../pull/N`).
- **Issue links** — scan for linked PRs or related tickets

**Cross-ticket dependency check:** From `issuelinks`, find tickets linked as `blocks`, `is blocked by`, or `clones`. For each, note its current status. If a ticket that **blocks this ticket** is not Done or Closed, flag it prominently at the top of the Step 6 report — the AC for this ticket may be incomplete without that context.

Parse the description in full — requirements appear in:
- Explicit "Acceptance Criteria" section
- "Requirements", "Scope", "Business Rules" sections
- Numbered/bulleted lists in the body
- Engineering Notes / QA Notes subsections
- "Out of scope" sections (used as negative requirements)

Build a flat numbered **requirement list** — one item per verifiable expectation, tagged with its source section and type:
- `behavioral` — observable user-facing outcome
- `technical` — implementation constraint (endpoint, model, config)
- `test` — explicitly calls for a test or QA check
- `non-code` — documentation, process, or communication (no diff evidence expected)

### Step 2 — Find the linked GitHub PR

Try in order — stop at first success:

1. **Remote issue links** (from step 1) — look for `github.com/.*/pull/\d+` URLs.
2. **GitHub PR search** — load via ToolSearch `select:mcp__plugin_github_github__search_pull_requests`. Query: `<TICKET-KEY>` in title or body, scoped to the relevant repo if known.
3. **Ticket description/comments** — scan inline text for GitHub PR URLs.
4. **Ask user** — "Could not find linked PR automatically. Provide the PR URL or number + repo (owner/repo)."

Load full PR via ToolSearch `select:mcp__plugin_github_github__pull_request_read`. Capture:
- Title, body, base branch, head branch
- Merge status (`merged` / `open` / `closed-unmerged`)
- Files changed, additions/deletions totals
- Commit list (titles + messages)
- CI check status (pass / fail / pending)

If PR is not yet merged: note prominently in the report but continue analysis.

### Step 3 — Read the diff

Load changed files from the PR. For each relevant file, read enough context to understand the change.

**Prioritize files by relevance:**
- Files whose path/name matches the ticket's module, feature keywords, or components
- New files (likely the core implementation)
- Modified service/controller/model files
- Test files (confirm test coverage)

**Skip or skim:**
- Lock files (`package-lock.json`, `yarn.lock`, `*.lock`)
- Auto-generated files
- Unrelated dependency bumps
- Pure formatting commits (confirmed by commit message)

For large PRs (>30 files): note which files were sampled vs skipped in the report.

Use ToolSearch `select:mcp__plugin_github_github__get_file_contents` to read specific files as needed.

**Exploratory testing guide:** While reading the diff, collect code areas touched but not explicitly required by any AC item:
- Shared utilities or services modified as side effects of the main change
- Config, feature flags, or environment variable changes
- Adjacent methods in changed files that weren't the primary target
- Error handling or logging paths that changed implicitly

Label these as "exploratory risk zones" — output in Step 6 as a separate report section. These are not failures; they are suggestions for where to probe beyond the AC.

### Step 4 — Check linked tests and results

1. **Xray tests linked to the ticket** — JQL: `issue in linkedIssues("<TICKET>", "is tested by")`. Fetch via Xray GraphQL (`getTests`, see xray-queries reference). For each linked test: get latest execution result (pass / fail / not run / blocked).

2. **Test Execution tickets** — scan ticket's issue links for Test Execution types. If found, check status and results summary.

3. **CI checks** — from PR `pull_request_read` response: note which CI checks passed/failed. A failed CI check is evidence for failing requirements covered by those checks.

4. **Postman results** — if a `.json` collection was attached to a TE ticket (from CE-TC-API), note its existence. If Postman MCP is available, offer to run it.

### Step 5 — Validate requirement by requirement

For each item in the requirement list from step 1, determine verdict:

| Verdict | Criteria |
|---------|----------|
| ✅ **Pass** | Clear implementation found in diff AND (test passes OR requirement is non-testable with explanation) |
| ❌ **Fail** | No code evidence found, OR linked test explicitly failed, OR requirement not addressed in PR |
| ⚠️ **Partial** | Some evidence but implementation appears incomplete, OR test exists but not yet run |
| ➖ **N/A** | Non-code requirement (docs, process) — note what was or wasn't done |
| 🔍 **Manual check needed** | Cannot determine from diff alone (runtime behavior, migration result, third-party integration) |

**Evidence sources** (cite specifically — file path + function/class name when possible):
- Code diff: file changed, method added/modified, config updated
- Commit message: explicitly references the requirement
- PR description: author's own confirmation with technical detail
- Test file: new or updated test covering this behavior
- Xray test result: linked test passing
- CI: relevant check passed

**Also check:**
- **Out-of-scope changes** — diff files/changes with no matching requirement → list separately
- **PR description accuracy** — does it claim to implement things not in the diff?
- **Requirements with zero evidence** — no code, no test, no mention in PR

### Step 6 — Produce report

```
## Validation Report — <TICKET>: <ticket summary>

**PR:** <URL> | **Status:** merged ✅ / open ⚠️ / closed without merge ❌
**Branch:** `<head>` → `<base>` | **Files changed:** N | **Commits:** N
**CI:** ✅ all checks pass / ❌ N checks failed / ⚠️ pending

---

### Requirement Coverage

| # | Requirement | Source | Code Evidence | Test | Verdict |
|---|-------------|--------|---------------|------|---------|
| 1 | <requirement text> | AC | `src/invoices.js` — `addInvoice()` added | PROJ-400 ✅ | ✅ Pass |
| 2 | <requirement text> | AC | not found in diff | none | ❌ Fail |
| 3 | <requirement text> | Eng Notes | partial — `utils.js` updated but edge case missing | PROJ-401 ⚠️ not run | ⚠️ Partial |
| 4 | <requirement text> | Description | `routes/invoice.js` — POST /invoices added | CI: api-tests ✅ | ✅ Pass |
| 5 | <requirement text> | QA Notes | runtime behavior — cannot verify from diff | — | 🔍 Manual |

---

### Summary
- ✅ Pass: N / M requirements
- ⚠️ Partial: N / M
- ❌ Fail: N / M
- 🔍 Needs manual check: N / M
- ➖ N/A: N / M

**Overall verdict:** ✅ Satisfies ticket / ⚠️ Partially satisfies / ❌ Does not satisfy

---

### Out-of-scope changes (review needed)
- `src/unrelated-module.js` — refactored logging (no matching requirement)
- `config/feature-flags.js` — new flag added (not mentioned in ticket)

---

### Action items
- [ ] Requirement #2 — <what's missing and where to look>
- [ ] Requirement #3 — <what the partial gap is>
- [ ] Manual verification needed for requirement #5 — <what to check and how>
- [ ] Review out-of-scope change in `src/unrelated-module.js` — intentional?

### Exploratory testing suggestions
- `<file or module>` — <why it's a risk zone; what to probe>
- `<shared utility modified as side effect>` — regression risk; test adjacent behaviors

### Dependency flags
| Ticket | Link type | Status | Risk |
|--------|-----------|--------|------|
| PROJ-XXXX | blocks this ticket | In Progress | ⛔ AC may be incomplete without this |
```

## Common mistakes

- Marking "pass" because the PR title or branch name mentions the ticket key. → Require diff evidence.
- Only reading the AC section and missing requirements in the description body. → Parse the entire ticket.
- Ignoring failed CI checks. → CI failures are evidence of requirement failures.
- Treating out-of-scope changes as failures. → Flag them; the user decides.
- Marking "fail" without a specific explanation. → Always state what's missing and where it should be.
- Skipping `getJiraIssueRemoteIssueLinks`. → Always check this first — it's the most reliable PR source.
- Accepting "PR description says it's done" as pass evidence. → Authors self-report; verify in the diff.
