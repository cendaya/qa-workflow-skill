#!/usr/bin/env node
// COPY of reconcile-run-assignees/scripts/split-by-module.mjs, bundled so this
// skill works as one zip. A fix here must be copied there too, and vice versa.
//
// Assign a Test Execution's run assignees BY MODULE (Test Repository folder),
// keeping every module WHOLE under one person and getting the totals as close
// to an even split as whole modules allow.
//
// Module = a segment of each test's Test Repository folder path. With --level 3
// (default) the module is the 3rd path segment, e.g.
//   /Product/System Test/Customer Screen/...   -> module "Customer Screen"
//   /Product/Regression Test/Regression Checklist -> module "Regression Checklist"
//
// Two ways to drive it:
//   AUTO (recommended) — give the people; the script partitions whole modules
//   for the closest-to-even split (largest-module-first greedy):
//     node split-by-module.mjs PROJ-XXXX --auto "<acctA>,<acctB>"
//     node split-by-module.mjs PROJ-XXXX --auto "<acctA>,<acctB>" --apply
//
//   MAP — you dictate exactly which module goes to whom:
//     node split-by-module.mjs PROJ-XXXX --map-file map.json [--apply]
//
//   KEYS — for executions whose tests have NO usable folder structure (they all
//   sit in one Test Repository folder, so there are no modules to split by).
//   You group the test keys yourself and the groups act as the modules:
//     node split-by-module.mjs PROJ-XXXX --keys-file groups.json [--apply]
//
//   No flag — just prints the module breakdown (nothing written).
//
// Optional --names-file names.json  ->  { "<accountId>": "Display Name", ... }
//   for readable output (also auto-harvested from test owners when possible).
//
// map.json format:
//   { "level": 3, "people": {"<acct>":"Name"},
//     "modules": {"Customer Screen":"<acct>"}, "default": "<acct>" }
//   A run whose module is unmapped (and no "default") is reported UNMAPPED and
//   left untouched — never assigned by guess.
//
// groups.json format (--keys-file):
//   { "people": {"<acct>":"Name"},
//     "groups": { "Admin console": { "assignee": "<acct>",
//                                    "tests": ["PROJ-1001","PROJ-1002"] } } }
//   Any test in the execution that is not listed in a group is reported
//   UNMAPPED and left untouched. A test key listed in two groups is an error.
//
// WHY WRITES ARE PACED AND VERIFIED: the Xray GraphQL API silently drops
// updateTestRun mutations when they are fired back to back at volume. It
// answers HTTP 200 with an empty `warnings` array and no rate-limit header,
// but the assignee is never persisted. Measured on a 366-test execution: 366
// mutations all "succeeded", only 108 actually landed. So --apply paces the
// calls and then re-reads the runs and retries whatever did not stick, rather
// than trusting the mutation response.
//
// Env required: XRAY_CLIENT_ID, XRAY_CLIENT_SECRET

import { readFileSync } from "node:fs";

const GQL = "https://xray.cloud.getxray.app/api/v2/graphql";
const AUTH = "https://xray.cloud.getxray.app/api/v2/authenticate";

const execKey = process.argv[2];
const apply = process.argv.includes("--apply");
const argVal = (flag) => { const i = process.argv.indexOf(flag); return i !== -1 ? process.argv[i + 1] : null; };
const mapPath = argVal("--map-file");
const keysPath = argVal("--keys-file");
const autoArg = argVal("--auto");
const namesPath = argVal("--names-file");
const levelArg = argVal("--level") ? parseInt(argVal("--level"), 10) : null;

if (!execKey || execKey.startsWith("--")) { console.error('Usage: node split-by-module.mjs <EXEC-KEY> [--auto "acctA,acctB" | --map-file map.json | --keys-file groups.json] [--level N] [--names-file names.json] [--apply]'); process.exit(1); }
if (!process.env.XRAY_CLIENT_ID || !process.env.XRAY_CLIENT_SECRET) { console.error("Missing XRAY_CLIENT_ID / XRAY_CLIENT_SECRET."); process.exit(1); }
if ([mapPath, keysPath, autoArg].filter(Boolean).length > 1) { console.error("Use only one of --auto, --map-file, --keys-file."); process.exit(1); }

const fileMap = mapPath ? JSON.parse(readFileSync(mapPath, "utf8")) : null;
const keysFile = keysPath ? JSON.parse(readFileSync(keysPath, "utf8")) : null;
const level = levelArg ?? fileMap?.level ?? 3;
const autoPeople = autoArg ? autoArg.split(",").map((s) => s.trim()).filter(Boolean) : null;
const people = { ...(fileMap?.people ?? {}), ...(keysFile?.people ?? {}), ...(namesPath ? JSON.parse(readFileSync(namesPath, "utf8")) : {}) };

// --keys-file: flatten groups into testKey -> {group, assignee}, rejecting dupes.
let keyMap = null;
if (keysFile) {
  keyMap = new Map();
  for (const [group, def] of Object.entries(keysFile.groups ?? {})) {
    if (!def?.assignee) { console.error(`Group "${group}" has no "assignee".`); process.exit(1); }
    for (const k of def.tests ?? []) {
      if (keyMap.has(k)) { console.error(`Test ${k} is listed in two groups: "${keyMap.get(k).group}" and "${group}".`); process.exit(1); }
      keyMap.set(k, { group, to: def.assignee });
    }
  }
  if (!keyMap.size) { console.error("--keys-file has no tests in any group."); process.exit(1); }
}
const nameFor = (acct) => people[acct] || acct || "(unassigned)";

// Xray rate-limits with HTTP 429 (JSON body carrying nextValidRequestDate) or,
// under load, an HTML error page. Both are transient: wait and retry rather
// than crash mid-apply. Proven 2026-09-24 running four executions back to back.
const MAX_TRIES = 6;
async function xfetch(url, init) {
  for (let attempt = 1; ; attempt++) {
    const r = await fetch(url, init);
    const text = await r.text();
    let body = null;
    try { body = JSON.parse(text); } catch {}
    const limited = r.status === 429 || r.status >= 500 || body === null;
    if (!limited || attempt >= MAX_TRIES) return { r, text, body };
    const until = Date.parse(body?.error?.nextValidRequestDate ?? "");
    const wait = Math.min(Math.max((until || 0) - Date.now(), 0) + 1000, 90000) || 5000 * attempt;
    console.error(`  Xray busy (HTTP ${r.status}), waiting ${Math.round(wait / 1000)}s then retrying (${attempt}/${MAX_TRIES - 1})`);
    await new Promise((res) => setTimeout(res, wait));
  }
}
async function auth() {
  const { r, text } = await xfetch(AUTH, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: process.env.XRAY_CLIENT_ID, client_secret: process.env.XRAY_CLIENT_SECRET }) });
  if (!r.ok) throw new Error(`Auth failed: ${r.status} ${text}`);
  return text.replace(/^"|"$/g, "");
}
async function gql(token, query, variables = {}) {
  const { r, text, body: j } = await xfetch(GQL, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ query, variables }) });
  if (!j) throw new Error(`Xray returned HTTP ${r.status}, not JSON: ${text.slice(0, 80)}`);
  if (j.errors) throw new Error("GraphQL error: " + JSON.stringify(j.errors, null, 2));
  return j.data;
}
async function resolveExec(token, key) {
  const d = await gql(token, `query($j:String!){ getTestExecutions(jql:$j, limit:1){ results { issueId jira(fields:["summary"]) } } }`, { j: `key = "${key}"` });
  const res = d.getTestExecutions?.results ?? [];
  if (!res.length) throw new Error(`No Test Execution found for key ${key}`);
  return { issueId: res[0].issueId, summary: res[0].jira?.summary ?? "" };
}
async function fetchRuns(token, id) {
  const runs = []; let start = 0; const limit = 100;
  for (;;) {
    const d = await gql(token, `query($i:[String],$l:Int!,$s:Int!){ getTestRuns(testExecIssueIds:$i,limit:$l,start:$s){ total results { id assigneeId test { folder{path} jira(fields:["key","assignee"]) } } } }`, { i: [id], l: limit, s: start });
    runs.push(...(d.getTestRuns.results ?? [])); start += limit;
    if (start >= (d.getTestRuns.total ?? 0)) break;
  }
  return runs;
}
async function updateAssignee(token, runId, accountId) {
  return gql(token, `mutation($id:String!, $a:String){ updateTestRun(id:$id, assigneeId:$a){ warnings } }`, { id: runId, a: accountId });
}
const moduleOf = (path) => (path || "").split("/").filter(Boolean)[level - 1] || "(none)";

// Write pacing / retry. Xray drops un-paced bulk writes without saying so.
const WRITE_DELAY_MS = Number(argVal("--delay") ?? 150);
const MAX_PASSES = 4;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Largest-module-first greedy: each whole module goes to the person with the
// smallest running total. Closest-to-even split while keeping modules intact.
function autoAssign(byModule, accts) {
  const totals = Object.fromEntries(accts.map((a) => [a, 0]));
  const modules = {};
  for (const [m, count] of Object.entries(byModule).sort((a, b) => b[1] - a[1])) {
    const pick = accts.reduce((best, a) => (totals[a] < totals[best] ? a : best), accts[0]);
    modules[m] = pick; totals[pick] += count;
  }
  return { modules };
}

(async () => {
  const token = await auth();
  const exec = await resolveExec(token, execKey);
  const runs = await fetchRuns(token, exec.issueId);

  for (const r of runs) { const a = r.test?.jira?.assignee; if (a?.accountId && a?.displayName && !people[a.accountId]) people[a.accountId] = a.displayName; }

  // Bucket = the thing kept whole under one person: a folder module normally,
  // or a hand-drawn group of test keys when --keys-file is used (for executions
  // whose tests share one folder and so have no modules to split by).
  const bucketOf = (run) => keyMap
    ? (keyMap.get(run.test?.jira?.key)?.group ?? "(ungrouped)")
    : moduleOf(run.test?.folder?.path);

  const byModule = {};
  for (const r of runs) { const m = bucketOf(r); byModule[m] = (byModule[m] || 0) + 1; }
  console.log(`\n${execKey} | ${exec.summary} — ${runs.length} runs`);
  console.log(keyMap ? `Groups (from --keys-file):` : `Modules (folder segment ${level}):`);
  for (const [m, v] of Object.entries(byModule).sort((a, b) => b[1] - a[1])) console.log(`   ${String(v).padStart(3)}  ${m}`);

  const assignment = autoPeople ? autoAssign(byModule, autoPeople) : (keysFile ? { modules: {} } : fileMap);
  if (!assignment) { console.log(`\nNo --auto, --map-file or --keys-file given. (Nothing written.)`); return; }

  const actions = [];
  const split = {}, unmapped = {};
  let already = 0;
  for (const run of runs) {
    const module = bucketOf(run);
    const to = keyMap
      ? (keyMap.get(run.test?.jira?.key)?.to ?? null)
      : (assignment.modules?.[module] ?? assignment.default ?? null);
    const testKey = run.test?.jira?.key ?? "?";
    if (!to) { unmapped[module] = (unmapped[module] || 0) + 1; continue; }
    split[nameFor(to)] = (split[nameFor(to)] || 0) + 1;
    if (run.assigneeId === to) { already++; continue; }
    actions.push({ runId: run.id, testKey, module, to, name: nameFor(to) });
  }

  if (autoPeople) {
    console.log(`\nAuto split (whole modules, closest to even) — module -> person:`);
    for (const [m, a] of Object.entries(assignment.modules)) console.log(`   ${String(byModule[m]).padStart(3)}  ${m}  ->  ${nameFor(a)}`);
  }
  console.log(`\n  already correct : ${already}`);
  console.log(`  to reassign     : ${actions.length}`);
  if (Object.keys(unmapped).length) { console.log(`  UNMAPPED (skipped — add to map):`); for (const [k, v] of Object.entries(unmapped)) console.log(`      ${v}  ${k}`); }
  console.log(`  resulting split :`);
  for (const [k, v] of Object.entries(split).sort((a, b) => b[1] - a[1])) console.log(`      ${v}  ${k}`);
  console.log("");
  for (const a of actions) console.log(`  ${apply ? "SET " : "WOULD SET "}${a.testKey} [${a.module}] -> ${a.name}`);

  if (!apply) { console.log(`\nDRY RUN. Re-run with --apply to make these changes.`); return; }

  // Xray answers HTTP 200 with no warnings for writes it then silently drops
  // (see header note). So: pace the mutations, re-read the runs, and retry
  // whatever did not stick. Never report success from the mutation response.
  let pending = actions;
  for (let pass = 1; pass <= MAX_PASSES && pending.length; pass++) {
    let sent = 0, errored = 0;
    for (const a of pending) {
      try { await updateAssignee(token, a.runId, a.to); sent++; }
      catch (e) { errored++; console.error(`  ERROR ${a.testKey}: ${e.message}`); }
      await sleep(WRITE_DELAY_MS);
    }
    const after = await fetchRuns(token, exec.issueId);
    const nowById = new Map(after.map((r) => [r.id, r.assigneeId]));
    const stuck = pending.filter((a) => nowById.get(a.runId) !== a.to);
    console.log(`  pass ${pass}: sent ${sent}${errored ? `, ${errored} errored` : ""}, verified ${pending.length - stuck.length}, ${stuck.length} did not persist`);
    pending = stuck;
  }

  const done = actions.length - pending.length;
  console.log(`\nApplied and VERIFIED: ${done}/${actions.length}.`);
  if (pending.length) {
    console.log(`STILL NOT APPLIED after ${MAX_PASSES} passes (${pending.length}):`);
    for (const a of pending) console.log(`   ${a.testKey} [${a.module}] -> ${a.name}`);
    process.exitCode = 1;
  }
})().catch((e) => { console.error(e.message); process.exitCode = 1; });
