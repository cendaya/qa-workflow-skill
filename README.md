# qa-workflow-skill

A Claude Code plugin marketplace containing **qa-workflow** — an end-to-end QA lifecycle
toolkit for teams working in Jira + Xray Cloud.

## Install

```
/plugin marketplace add cendaya/qa-workflow-skill
/plugin install qa-workflow@qa-workflow-skill
```

Then follow the one-time setup in [plugins/qa-workflow/README.md](plugins/qa-workflow/README.md).

## What's in it

| Skill | Does |
|-------|------|
| `CE-QA-Workflow` | Single entry point — chains ticket pickup → AC validation → test-case generation → execution |
| `CE-ForTesting` | Finds unowned "Ready for Testing" tickets, ranks them by ease of test, assigns one to you |
| `CE-AC-Validator` | Reads the ticket, finds the merged PR, checks the diff against every acceptance criterion |
| `TC-Router` | Detects UI / API / performance and routes to the right generator |
| `CE-TC-UI` | Gherkin/Manual UI cases, optional Playwright codegen handoff |
| `CE-TC-API` | API cases, endpoint smoke test, Postman collection |
| `CE-TC-Perf` | Baseline/load/overload scenarios, k6 script, 1-VU smoke |
| `CE-Execute-TE` | Runs a Test Execution's cases and writes results back to Xray |
| `CE-Create-Bug` | Files a Jira defect after a duplicate search |
| `CE-AutomationVSManual` | Reconciles a Reqnroll/SpecFlow regression run against a Test Execution |
| `Regression-Cycle-Setup` | Creates a release cycle's regression/smoke Test Executions from your config, links them to a Test Plan, splits the runs across the team by module. Needs `regression_cycle` configured plus your own assignment maps |

Shared by several skills:

| Reference | Does |
|-----------|------|
| `references/qa-oracle-model.md` | What a case is allowed to assert — every case carries `Traces` and an `Oracle`, or it is an observation rather than a case |
| `references/qa-publish-gate.md` | The checks that must pass before work is reported done |
| `scripts/qa-gate-check.py` | Runs that gate mechanically. Exit 0 proceed, 1 fix, 2 decide by hand, 3 Xray unreachable |
| `scripts/xray-graphql.py` | Xray GraphQL helper for when the Xray MCP is not loaded |

## Configuration

Every environment-specific value — Jira site, project key, hostnames, custom field ids,
account ids — lives in `~/.claude/qa-config.json`, which is **not** part of this repo.
Copy `plugins/qa-workflow/qa-config.example.json` and fill it in. See the plugin README.

No credentials are stored in config either: it holds only the *names* of environment
variables. Set the actual secrets in `~/.claude/settings.json` under `env`.

## License

MIT
