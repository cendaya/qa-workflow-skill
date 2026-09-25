---
name: CE-Create-Bug
description: Use when a QA engineer wants to file a Jira Defect ticket. Searches for duplicates first, confirms before creating (issuetype=Defect, Priority=Low, Assignee=Unassigned), then asks if user wants to generate linked test cases via /TC-Router. Triggers include "create bug for <PROJ>", "log a bug in <project>", "file bug ticket", "new bug in <project>", "create defect".
---

# CE-Create-Bug

File a Jira **Defect** ticket in a target project. Searches for existing related defects first, gets approval, creates the ticket, then generates linked Xray test cases via /TC-Router.

Ticket URL pattern: `https://<jira.site>/browse/<KEY>-XXXX`

## Inputs (ask for any that are missing)

1. **Project** — defaults to `jira.project_key` from `$env:USERPROFILE\.claude\qa-config.json`. Confirm with `getVisibleJiraProjects` if the key is unclear.
2. **Bug summary** — short title describing the defect.
3. **Bug description** — enough detail to fill the description template (see below). Ask for what's missing.
4. **Priority** — default **`Low`**. User may override: `Medium`, `High`, `Critical`.
5. **Assignee** — default **`Unassigned`**. User may name a team member.
6. **Staging validation** — ask: "Did you reproduce this in staging? Is it also present in Master?" Capture yes/no for each.

## Iron rules

- **Never create the ticket without showing duplicate-search results and getting explicit approval.** Even if zero duplicates found — still confirm before creating.
- **Search is scoped to the stated project only.** Never search across all projects.
- **Issue type is always `Defect`**, not `Bug`.
- **Never auto-set Assignee to a real user** unless the user explicitly names one.
- **Ask before invoking /TC-Router** — user may choose to skip test case generation.
- **Always capture staging + Master status** in the Environment section — never leave `_Staging_` or `_Master_` blank.
- **Never echo Xray tokens or secrets** in output, files, or logs.

## Workflow

Create a TodoWrite item per step.

### Step 1 — Resolve inputs

Confirm: project key, bug summary, description details, priority (default `Low`), assignee (default `Unassigned`).

Use `getVisibleJiraProjects` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__getVisibleJiraProjects`) to resolve the project key if needed.

### Step 1b — Validate staging & Master coverage

Ask the user:

> "Has this bug been reproduced in **staging**? Is it also present in **Master**?"

Capture and record:
- **QA environment** — URL/version where bug was originally found
- **Staging** — reproduced: Yes / No + URL if yes
- **Master** — also present: Yes / No

These values populate the `## Environment` section of the description. If the user confirms Master is affected, note it explicitly there (see template).

### Step 2 — Search for existing duplicates

Search **within the stated project only** for existing Defects related to the reported issue.

Use `searchJiraIssuesUsingJql` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__searchJiraIssuesUsingJql`) with JQL:

```
project = <KEY> AND issuetype = Defect AND text ~ "<keywords>" ORDER BY created DESC
```

- Extract 3–5 keywords from the summary/description for the `text ~` clause.
- Limit to **10** results. If more exist, show the 10 most recent and note more were found.
- Zero results: state that clearly.

**Present results as a numbered list:**

```
Existing defects in <PROJECT>:
1. <KEY>-XXXX — <summary> [<status>]
   https://<jira.site>/browse/<KEY>-XXXX
2. ...
(none found)
```

Then ask:

> "Found X existing defect(s) above. Proceed with creating a new ticket, or does one of these already cover the issue?"

**Wait for explicit approval.** If user points to an existing ticket, stop and provide the link. Do not create a duplicate.

### Step 3 — Confirm ticket details

Show the full proposed ticket before creating:

```
Summary:    <bug summary>
Project:    <KEY>
Issue Type: Defect
Priority:   Low  (or user-specified)
Assignee:   Unassigned  (or user-specified)

Description:
  (formatted — see template below)
```

Ask: **"Create this ticket?"** Wait for confirmation.

### Step 4 — Create the Defect ticket

Use `createJiraIssue` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__createJiraIssue`):

- `project`: resolved key (`jira.project_key`, e.g. `<PROJ>`)
- `issuetype`: `Defect`
- `summary`: bug summary
- `priority`: `{ "name": "<priority>" }` — default `Low`
- `assignee`: omit for unassigned, or set by account id if user specified someone

After creation, update the description via `editJiraIssue` with `contentFormat: "markdown"` — Jira renders plain-string descriptions with broken formatting.

Report the new ticket:

```
Defect created: <KEY>-XXXX
https://<jira.site>/browse/<KEY>-XXXX
```

### Step 5 — Offer test case generation

After reporting the new ticket, ask:

> "Would you like to generate linked test cases for this defect? (yes / no)"

**If yes** — invoke the **TC-Router** skill, passing:
- The new defect ticket key (e.g. `PROJ-XXXX`)
- The project name

TC-Router detects the test type and routes to **CE-TC-UI** (UI/frontend), **CE-TC-API** (REST endpoints) or **CE-TC-Perf** (load/performance); mixed or generic defects it handles itself. That skill handles Xray test case creation and linking. Each test case is linked to the defect ticket using issue link type **Test**:
- inwardIssue = TC key, outwardIssue = defect ticket key
- Defect ticket shows: **"is tested by [TC key]"**
- TC shows: **"tests [DEFECT key]"**

**If no** — end the workflow. Ticket is already created and no further action is needed.

## Description template

Match the format used in PROJ-9554 exactly — H2 headers (`##`), this section order:

```markdown
## Summary
<1–2 sentence description of the defect. Describe what's broken and, if known, isolate it from a working counterpart.>

## Expected Behavior
<What should happen according to spec or existing working behavior.>

## Actual Behavior
<What actually happens. Reference the working counterpart if one exists.>

## Environment
* _Product/Module:_ <module or feature area>
* _QA Environment:_ <URL where bug was found>
* _Staging:_ <URL — Bug reproduced in staging: Yes / No>
* _Master:_ <Bug also present in Master: Yes / No>
* _Scope:_ <how broad is this — single site, all sites, specific config?>

## Preconditions / Setup
1. <prerequisite condition>
2. <prerequisite condition>

## Steps to Reproduce
1. <step>
2. <step>
3. <step>

## Acceptance Criteria
* <verifiable criterion 1>
* <verifiable criterion 2>
* <verifiable criterion 3>

## Additional Context / Investigation Notes
<Any extra detail that helps developers locate or understand the defect: logs, screenshots, stack traces, related tickets, workarounds, frequency/intermittency, or links to relevant code/config. Use "N/A" if none.>

## BDD Scenario
```gherkin
Feature: <feature name>
  Scenario: <scenario title>
    Given <precondition>
    When <action>
    Then <expected outcome>
```
```

**Notes on filling the template:**
- If the user provides partial info, fill what's known; mark unknowns as `<not provided>`.
- **BDD Scenario** is optional — include it if the bug maps cleanly to a Gherkin scenario. Skip if reproduction steps are too exploratory.
- Keep Acceptance Criteria distinct and testable — each bullet should be independently verifiable.
- In the Environment section, include login credentials only if the user provides them and the site is non-production/staging.

## Common mistakes

- Creating the ticket before showing duplicate search results. → Always search and show results first.
- Using issuetype `Bug` instead of `Defect`. → this project uses `Defect`.
- Searching outside the stated project. → JQL must always include `project = <KEY>`.
- Using `###` H3 headers in the description. → Use `##` H2 headers matching PROJ-9554.
- Auto-triggering /TC-Router without asking. → Always ask user first; they may want to skip test case generation.
- Setting a real Assignee by default. → Default is always Unassigned unless user specifies.
- Not showing proposed ticket details before creating. → Always confirm in Step 3.
- Assuming zero duplicates means skip the approval gate. → Still confirm once even if none found.
- Passing description as plain string in `createJiraIssue`. → Always set description after creation via `editJiraIssue` with `contentFormat: "markdown"`.
