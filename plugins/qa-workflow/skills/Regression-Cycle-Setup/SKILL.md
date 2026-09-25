---
name: Regression-Cycle-Setup
description: Use when a QA engineer wants to set up a release cycle's regression and smoke Test Executions in Xray Cloud. Creates one Test Execution per entry in the regression_cycle config block, fills each from its Test Set, links all of them to one Test Plan the user picks, then assigns the runs from saved owner maps so each person stays in one area of the app. Trigger on "set up regression", "create the regression executions", "set up the release cycle", "create regression and smoke executions", "new regression cycle for <plan>".
---

# Regression Cycle Setup

Builds one release cycle's Test Executions and assigns their runs. It changes live Jira and
Xray data, so it always does a dry run and gets an OK first.

The cycle is **not** hardcoded. It is whatever `regression_cycle.executions` lists in
`~/.claude/qa-config.json` — one entry per execution, each naming its Test Set and its
assignment map. A typical cycle is two regression executions split across the team plus a
prerelease and a post-release smoke execution owned by one person each.

Execution names are used exactly as written, with no date or release suffix. The Test Plan
tells the cycles apart.

## Scope

This skill creates the executions (stamping `regression_cycle.work_breakdown` if configured),
adds the Test Sets' tests, links the executions to the chosen Test Plan, and sets run
assignees. It does **not** touch run statuses, the Test issues themselves (including their
Jira Assignee), the Test Sets, or the plan's other fields. It never creates a Test Plan.

## What's in this folder

- `scripts/setup-cycle.mjs`: creates, fills, links, and verifies the executions, and checks the
  maps against the Test Sets.
- `scripts/split-by-module.mjs`: sets the run assignees. It is a **copy** of the one in the
  `reconcile-run-assignees` skill. If you have both skills installed and fix one copy, copy the
  fix to the other.
- `references/assignment-map.example.json` — folder-based map format (`--map-file`), for a Test
  Set whose tests are filed under module folders.
- `references/group-map.example.json` — key-based map format (`--keys-file`), for a Test Set
  whose tests all sit in one flat folder and have to be grouped by test key instead.

## Setup

Fill the `regression_cycle` block in `~/.claude/qa-config.json` (see
`qa-config.example.json`). Each execution entry takes `summary`, `test_set`, and either `map`
or `keys_map` naming a file in `maps_dir`.

**The maps are yours, not the plugin's.** They hold real Jira account ids, so `maps_dir`
defaults to `~/.claude/qa-regression-maps` — outside the plugin directory, because
`/plugin update` overwrites plugin files. Copy the two `.example.json` files there, rename
them to match your config, and fill in your own people and modules. Find an accountId with
the Atlassian MCP `lookupJiraAccountId`.

People are stored by account id, so the owners are the same no matter who runs the skill.
Edit the maps when the team or the areas change.

## Requirements

- Node 18 or newer.
- `XRAY_CLIENT_ID` / `XRAY_CLIENT_SECRET` set in the environment (an Xray Cloud API key). Never
  echo them or the token.
- `jira.project_key` and `regression_cycle.executions` set in the config. The script exits with
  a message if either is missing.

## Workflow

`<S>` = this skill's folder.

1. **Ask which Test Plan.** Run `node <S>/scripts/setup-cycle.mjs --list-plans` and ask the user
   to pick one (usually the next release). All the executions go on that one plan. If no plans
   are open, stop and say so.

2. **Dry run and confirm.** Run `node <S>/scripts/setup-cycle.mjs --plan <PLAN>`. It shows each
   execution, its Test Set, and the test count, plus whether it will be created or reused. Reuse
   happens when an execution with that exact name is already on the plan, so a re-run never makes
   duplicates. Show this to the user and wait for an OK.

3. **Create and verify.** Re-run with `--apply`. It creates the executions, adds tests in paced
   batches, links them to the plan, and prints a read-back of `n/n tests, on <PLAN>` for each
   execution. Anything short of `n/n` or not on the plan is a failure. Report it and re-run
   `--apply`, which only fills the gaps. Note the new execution keys.

4. **Sync the maps with the Test Sets.** The Test Sets are the only source of truth for who gets
   what; the map files are just saved decisions and drift as tests are added or removed. Run
   `node <S>/scripts/setup-cycle.mjs --check-maps`.
   - **STALE** (in a map, no longer in the Test Set): remove it from the map file. No need to ask.
   - **NEW** (in the Test Set, no owner): every test must end up assigned, so never skip one. If
     the owner is obvious from subject (a promotions test goes to the promotions group), add it to
     that person's module or group and say so in the report. If it is not obvious, ask, proposing
     the person whose areas are closest.

   An execution whose map is a single `default` owner cannot drift and is reported as such.
   Re-run `--check-maps` until it prints `Maps match the Test Sets.` before assigning anything.

5. **Assign runs, dry run first.** For each execution, run the split with no `--apply`, pointing
   at that execution's map from the config:

   ```bash
   node <S>/scripts/split-by-module.mjs <EXEC-KEY> --map-file  <MAPS_DIR>/<map>
   node <S>/scripts/split-by-module.mjs <EXEC-KEY> --keys-file <MAPS_DIR>/<keys_map>
   ```

   Show the split per person for the regression executions. After step 4 there should be no
   UNMAPPED items; if one appears, go back to step 4 rather than assigning it by count. Keeping
   each person in one area matters more than equal totals.

6. **Apply and verify, one execution at a time.** Re-run each command with `--apply --delay 300`,
   waiting about 20 seconds between executions. Firing them all back to back gets Xray to reject
   requests for a minute ("too many requests"). The split script waits and retries when that
   happens, but pacing avoids it. Then dry-run each once more. Done only when every execution
   shows `to reassign: 0` and no UNMAPPED items.

7. **Report**, briefly: the plan, the execution keys with test counts, the regression split per
   person, and any map changes made in step 4.

## Common mistakes

- Trusting the mutation responses. Xray answers HTTP 200 for writes it then drops. Both scripts
  confirm from a read-back; quote those lines, not the send counts.
- Creating a second set of executions after a partial failure. Re-run `--apply` with the same plan:
  it reuses same-named executions already on that plan.
- Assigning an UNMAPPED module by guess, or dropping it. Assign it by subject or ask, then add it
  to the map file so the next cycle has it.
- Leaving stale entries in a map. They are harmless to the split but make the map misleading.
  Remove them in step 4.
- Changing Test issue assignees to "fix" ownership. Those are global across every execution. Only
  run assignees change here.
- Keeping the filled-in maps inside the skill folder. `/plugin update` overwrites it. They belong
  in `maps_dir`.
