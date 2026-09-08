---
name: CE-ForTesting
description: Use when looking for Jira tickets to pick up for QA testing. Fetches Ready for Testing tickets not owned by other QA members, ranks them by ease of testing, assigns the selected ticket to you, and launches CE-QA-Workflow. Triggers include "find me something to test", "what should I test", "pick a ticket", "what's ready for testing", "CE-ForTesting".
---

# CE-ForTesting

Fetch unowned "Ready for Testing" tickets, rank by ease of test, assign to the current user, kick off CE-QA-Workflow.

## Step 0 — Resolve config and identity

Read `$env:USERPROFILE\.claude\qa-config.json` for `jira.*`. Get the current user's accountId once
via `atlassianUserInfo` (load via ToolSearch `select:mcp__plugin_atlassian_atlassian__atlassianUserInfo`)
and reuse it — never hardcode an accountId.

## Step 1 — Fetch tickets

Load via ToolSearch `select:mcp__plugin_atlassian_atlassian__searchJiraIssuesUsingJql`. Run:

```
cloudId: <jira.site>
jql: project = <jira.project_key>
     AND status = "<jira.ready_for_testing_status>"
     [AND cf[<jira.product_field>] = "<jira.product_value>"]
     [AND reporter NOT IN (<jira.exclude_reporter_account_ids>)]
     [AND assignee NOT IN (<jira.exclude_assignee_account_ids>)]
     ORDER BY assignee ASC, priority DESC, created DESC
fields: summary, status, priority, assignee, description, issuetype, created
maxResults: 50
```

> Every value in angle brackets comes from `qa-config.json`. Clauses in square brackets are
> **conditional** — omit the whole clause when the corresponding config value is `null` or an
> empty list. A JQL `NOT IN ()` with an empty list is a syntax error, so never emit it.
>
> If `jira.product_field` is set, also prepend it to the `ORDER BY`.

## Step 2 — Rank by ease of testing

For each ticket, score it using these signals from the description:

| Signal | Tier |
|--------|------|
| "reproducible in any DB" / "any database" + short clear steps | Easy |
| Specific login + account # provided + clear steps, one DB needed | Moderate |
| Requires import file / mobile app / geographic data / custom invoice setup | Harder |

Output three sections:

```
**Easy to test** (reproducible in any DB, clear steps)
| Key | Summary | Assignee | Why easy |
|-----|---------|----------|----------|
| PROJ-XXXX | ... | Name | <one-line reason> |

**Moderate** (specific DB/account needed but credentials provided)
| Key | Summary | Assignee | Notes |
|-----|---------|----------|-------|

**Harder** (external deps, specific files, or complex setup)
| Key | Summary | Notes |
|-----|---------|-------|
```

Mark any ticket already assigned to the current user with ⭐.

End with: **"Which ticket do you want to pick up? (enter the key, e.g. PROJ-1234)"**

## Step 3 — Assign to the current user

Once user provides a key, load via ToolSearch `select:mcp__plugin_atlassian_atlassian__editJiraIssue`. Assign:

```
cloudId: <jira.site>
issueIdOrKey: <selected key>
fields: { assignee: { accountId: "<accountId from Step 0>" } }
```

Confirm: "Assigned **<KEY>** to you."

## Step 4 — Launch CE-QA-Workflow

Immediately invoke the **CE-QA-Workflow** skill with the selected ticket key as input.

## Iron rules

- Never skip the ranking — always show all three tiers.
- Never assign without the user selecting a key.
- Never auto-select on behalf of the user.
- After assigning, always chain into CE-QA-Workflow — do not stop.
