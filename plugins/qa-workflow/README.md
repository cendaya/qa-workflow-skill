# qa-workflow

End-to-end QA lifecycle for Jira + Xray Cloud.

## One-time setup

### 1. Config file

```powershell
Copy-Item "$env:USERPROFILE\.claude\plugins\cache\qa-workflow-skill\qa-workflow\*\qa-config.example.json" `
          "$env:USERPROFILE\.claude\qa-config.json"
```

Or just copy `qa-config.example.json` from this repo to `~/.claude/qa-config.json` by hand.

Fill in at minimum:

| Key | What |
|-----|------|
| `jira.site` | `your-site.atlassian.net` |
| `jira.project_key` | the project the skills work in |
| `environments.qa.api.base_url` | your API host |
| `environments.qa.ui.base_url` | your app's login URL |

Everything else is optional. Leave `jira.product_field`, `report_portal.*` and
`automation.*` as `null` if they don't apply — the skills detect nulls and skip
those clauses rather than emitting broken JQL.

### 2. Secrets

Config holds only variable *names*. Put the values in `~/.claude/settings.json`:

```json
{
  "env": {
    "XRAY_CLIENT_ID": "...",
    "XRAY_CLIENT_SECRET": "...",
    "QA_USERNAME": "...",
    "QA_PASSWORD": "...",
    "QA_API_TOKEN": "..."
  }
}
```

Xray Cloud credentials come from Jira → Apps → Xray → API Keys.

### 3. Required MCP servers

- **Atlassian** — `/plugin install atlassian@claude-plugins-official`. Every skill uses it.
- **Playwright** — only for `CE-TC-UI` and `CE-Execute-TE` UI runs.
- **Postman** — only for `CE-TC-API` collection generation.

Optional: the `unifieddriver` plugin, if you want `CE-TC-UI` to hand automatable cases to
its `generate-test-code` skill. Without it, that step is skipped and noted in the report.

## Usage

```
/CE-QA-Workflow PROJ-1234      # full lifecycle on one ticket
/CE-QA-Workflow                # no ticket → finds and ranks one for you first
/CE-Execute-TE PROJ-5678       # just run an existing Test Execution
/CE-Create-Bug                 # file a defect
```

Skills also trigger on plain language — "start testing PROJ-1234", "what should I test",
"write API test cases for PROJ-1234".

## The automation mapping file

`CE-AutomationVSManual` needs a map from Test Execution cases to the automated scenarios
that prove them. That map is specific to your suite, so it is not shipped. Create it at
`~/.claude/qa-te-mapping.md` (or wherever `automation.te_mapping_path` points).
`skills/CE-AutomationVSManual/references/te-mapping.md` documents the required format.

Keep it outside the plugin directory — `/plugin update` overwrites plugin files.

## Notes

- No skill writes to Jira or Xray without showing you what it will write first, except the
  two documented automatic actions in `CE-Execute-TE` (transition the TE to In Progress and
  assign it to you at the start of a run).
- `CE-AutomationVSManual` never marks a case PASSED on a feature-name guess. Anything
  uncertain goes to the manual list.
