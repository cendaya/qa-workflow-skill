---
name: CE-TC-UI
description: Use when writing UI/frontend test cases from a Jira ticket — generates Gherkin/Manual scenarios covering happy path, edge cases, and negative scenarios for UI features. After writing, checks each case's Automation Status and offers to generate automation scripts (page object/step defs/feature file) via the unifieddriver generate-test-code skill for automatable cases. Automatically invoked by /TC-Router for UI tickets. Triggers include "write UI test cases", "UI tests for PROJ-XXXX", "frontend test cases", "create UI scenarios".
---

# CE-TC-UI

Generate Xray Cloud test cases for **UI/frontend** features. Extends the JD-TC-writer workflow with UI-specific scenario coverage: **happy path**, **edge cases**, and **negative scenarios**.

Inherits all rules and workflow from `/TC-Router` — apply those steps exactly, with the additions and overrides below.

## Scenario coverage requirement (step 5)

Every ticket must produce at minimum one case per category:

| Category | What to cover |
|----------|--------------|
| **Happy path** | User completes the main flow successfully with valid data and expected outcome |
| **Edge cases** | Boundary values in inputs, special characters, empty states, large data sets, session timeout mid-flow, disabled/read-only fields |
| **Negative** | Invalid/missing required fields, permission denied, form submission with server error, navigation away mid-form, duplicate submission |
| **Accessibility (a11y)** | Keyboard-only navigation through the full flow, visible focus indicators on all interactive elements, form field labels readable by screen readers, error messages programmatically announced, color not the sole indicator of state |

If a category has no applicable scenario for the ticket, note why in the report — don't silently skip.

## Field mapping overrides

- **Objective** — always persona-based: *"As a [role], I should be able to [action]. I would expect [outcome]."*
- **Gherkin style** — user-centric language only. `Given I am logged in as <role>`, `When I [interact with UI element]`, `Then I [see / cannot / am redirected]`. No CSS selectors, no internal IDs, no implementation details.
- **Data column (Manual)** — use placeholders for form inputs: `<valid first name>`, `<email address>`, `<amount within limit>`. Never literal values.
- **Summary (title)** — format `<Module Name> | <Scenario>`. Scenario describes the UI action and outcome: `Invoice Form | Submit with Missing Required Field`, `Customer Account | Navigate as Read-Only User`.

## Environment verification (before test case writing)

Read `$env:USERPROFILE\.claude\qa-config.json` to get the active environment (default: `qa`).

1. Note `ui.base_url` from the active environment block — include it in preconditions for each generated test case.
2. Ping the UI base URL to confirm the environment is reachable:
   ```powershell
   $cfg = Get-Content "$env:USERPROFILE\.claude\qa-config.json" | ConvertFrom-Json
   $UI_URL = $cfg.environments.($cfg.default_env).ui.base_url
   try {
     $resp = Invoke-WebRequest -Uri $UI_URL -Method Head -TimeoutSec 10
     Write-Host "UI env reachable: $UI_URL → $($resp.StatusCode)"
   } catch {
     Write-Host "WARNING: UI env not reachable: $UI_URL — $($_.Exception.Message)"
   }
   ```
3. If unreachable: warn the user, ask whether to proceed with test case generation or wait for the environment.
4. Note required test data in the report as manual preconditions:
   - List specific entity types needed (e.g. "an active Customer account", "an existing Invoice in Draft status")
   - Note roles/personas required (e.g. "a user with Administrator role", "a read-only Technician")
   - Flag if data must be reset between runs (e.g. "form submission creates a record — reset before re-running")
   - If a seed script or setup doc exists for the module, link it in the report

## Additional step (after step 8 — write to Xray)

### Step 8a — UI smoke test via Playwright

After test cases are written, run a basic happy-path smoke check on the QA UI.

Load via ToolSearch `select:mcp__plugin_playwright_playwright__browser_navigate`.

1. Read `qa-config.json`, get `ui.base_url` for the active environment.
2. Navigate and capture initial state:
   - `browser_navigate` → `ui.base_url`
   - `browser_take_screenshot` → capture page load
3. Log in — read `QA_USERNAME` / `QA_PASSWORD` from env vars; if unset, ask the user:
   - `browser_fill_form` → username + password
   - `browser_click` → submit
   - `browser_take_screenshot` → capture post-login state
4. Navigate to the feature under test (derived from ticket module/summary).
5. `browser_take_screenshot` → capture feature page.
6. `browser_snapshot` → accessibility tree (check: labels present, landmark roles, focus order visible).
7. Report: environment label · screenshots captured · a11y issues detected · pass/fail.

**Never hardcode credentials.** If credentials unavailable: note "UI smoke skipped — set QA_USERNAME / QA_PASSWORD env vars to enable" and skip.

### Step 8b — Generate automation scripts for automatable cases

Once cases are written and smoke-tested, check each approved case's **Automation Status**
(set in TC-Router step 6):

- `Can be Automated` or `Is Automated` → **automatable**.
- `Not Automated` or `Manual Only` → not automatable; skip, note in report.

If at least one case is automatable, ask **once**:
> "N case(s) are marked automatable. Generate automation scripts for them now via
> `generate-test-code`, or skip?"

- **Generate** — for each automatable case, invoke the `generate-test-code` skill (Skill
  tool, skill name `generate-test-code`, from the `unifieddriver` plugin) with:
  - **Target** — the UI base URL from `qa-config.json` (`ui.base_url` for the active
    environment) plus the feature page/route implied by the ticket module.
  - **Objective** — the case's **own approved Gherkin scenario, verbatim** (not
    re-derived from the raw ticket — the scenario already exists and was written to
    Xray in step 8; codegen should implement exactly that, not reinterpret the ticket).
    Also pass the ticket key so the generated feature file gets tagged
    `@JIRA-<TICKET>` and the `# Generated from <issue-URL>` header, per that skill's
    Jira-traceability convention.

  This handoff is **optional**. `generate-test-code` ships in the separate `unifieddriver`
  plugin; if that skill is not installed, skip step 8b entirely and note
  "automation codegen skipped — generate-test-code skill not installed" in the report.

  `generate-test-code` runs its own Step 0 compatibility check first — it needs a
  `.csproj` referencing `WorkWave.TA.UnifiedDriver.*` in the working directory — and
  presents every artifact (page object, step definitions, feature file) for review
  before writing. This step doesn't bypass any of that; it only decides *which* cases
  to hand off and with what scenario.
  - If Step 0 finds no `.csproj`, stop there and note in the report: "automation
    codegen skipped — no UnifiedDriver test project found in this directory."
- **Skip** — note in report; no codegen this run.

Report addition: for each automatable case, note **codegen: generated (`<file paths>`)**
/ **skipped** / **not automatable** (with the Automation Status value that excluded it).

## Common mistakes (UI-specific)

- Writing only happy path. → Must include at least one edge case and one negative per ticket.
- Using internal element IDs or CSS selectors in Gherkin. → Write in user-visible terms.
- Objective missing persona. → Always include user role and expected outcome.
- Data column contains literal values (`John Smith`, `12345`). → Use named placeholders.
- Generating automation for a `Manual Only` / `Not Automated` case. → Only `Can be
  Automated` / `Is Automated` cases qualify for step 8b.
- Letting `generate-test-code` re-derive the scenario from the raw ticket. → Pass the
  exact approved Gherkin scenario so the generated test matches what's in Xray.
- Running step 8b without a UnifiedDriver project present. → Let `generate-test-code`'s
  own Step 0 check catch this; skip and note in the report rather than forcing it.
