#!/usr/bin/env node
// Create the four release-cycle Test Executions, fill each from its Test Set,
// and link all four to one Test Plan. Run assignees are NOT set here; that is
// reconcile-run-assignees' split-by-module.mjs, run afterwards per execution.
//
//   node setup-cycle.mjs --list-plans                open Test Plans, newest first
//   node setup-cycle.mjs --plan PROJ-XXXX            dry run (nothing written)
//   node setup-cycle.mjs --plan PROJ-XXXX --apply    create, fill, link, verify
//   node setup-cycle.mjs --check-maps                saved owner maps vs Test Sets
//
// Re-running with --apply is safe: an execution whose exact summary is already
// linked to the plan is reused and topped up, never duplicated.
//
// Xray drops bulk writes while answering HTTP 200 with no warnings, so every
// write here is paced and then confirmed from a read-back, never from the
// mutation response.
//
// Env required: XRAY_CLIENT_ID, XRAY_CLIENT_SECRET
// Config required: ~/.claude/qa-config.json -> jira.project_key and the
// regression_cycle block (see qa-config.example.json).

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, isAbsolute } from "node:path";

const GQL = "https://xray.cloud.getxray.app/api/v2/graphql";
const AUTH = "https://xray.cloud.getxray.app/api/v2/authenticate";

// Everything project-specific lives in the config, never in this file.
const expand = (p) => (p.startsWith("~") ? join(homedir(), p.slice(1)) : p);
const CONFIG_PATH = expand(process.env.QA_CONFIG_PATH ?? "~/.claude/qa-config.json");
let CONFIG;
try { CONFIG = JSON.parse(readFileSync(CONFIG_PATH, "utf8")); }
catch (e) { console.error(`Cannot read ${CONFIG_PATH}: ${e.message}
Copy qa-config.example.json to ~/.claude/qa-config.json first.`); process.exit(1); }

const PROJECT = CONFIG.jira?.project_key;
const RC = CONFIG.regression_cycle ?? {};
const CYCLE = (RC.executions ?? []).filter((e) => !String(e.summary ?? "").startsWith("_"));
const MAPS_DIR = expand(RC.maps_dir ?? "~/.claude/qa-regression-maps");
const mapPath = (f) => (isAbsolute(f) ? f : join(MAPS_DIR, f));

// Optional single-select field stamped on each new execution, e.g. a work-breakdown category.
const WORK_BREAKDOWN = RC.work_breakdown?.field_id
  ? { [RC.work_breakdown.field_id]: { id: String(RC.work_breakdown.value_id) } }
  : {};

if (!PROJECT) { console.error(`jira.project_key is not set in ${CONFIG_PATH}.`); process.exit(1); }
if (!CYCLE.length) { console.error(`regression_cycle.executions is empty in ${CONFIG_PATH}. See qa-config.example.json for the shape.`); process.exit(1); }
for (const c of CYCLE) {
  if (!c.test_set) { console.error(`regression_cycle entry "${c.summary}" has no test_set.`); process.exit(1); }
  if (!c.map && !c.keys_map) console.error(`  note: "${c.summary}" has neither map nor keys_map - --check-maps will skip it and its runs stay unassigned.`);
}

const argVal = (f) => { const i = process.argv.indexOf(f); return i !== -1 ? process.argv[i + 1] : null; };
const apply = process.argv.includes("--apply");
const listPlans = process.argv.includes("--list-plans");
const checkOnly = process.argv.includes("--check-maps");
const planKey = argVal("--plan");
const DELAY = Number(argVal("--delay") ?? 150);
const CHUNK = 50;
const MAX_PASSES = 4;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

if (!process.env.XRAY_CLIENT_ID || !process.env.XRAY_CLIENT_SECRET) { console.error("Missing XRAY_CLIENT_ID / XRAY_CLIENT_SECRET."); process.exit(1); }
if (!listPlans && !checkOnly && !planKey) { console.error("Usage: node setup-cycle.mjs --list-plans | --check-maps | --plan <PLAN-KEY> [--apply]"); process.exit(1); }

// Xray rate-limits with HTTP 429 (JSON body carrying nextValidRequestDate) or,
// under load, an HTML error page. Wait and retry rather than crash mid-apply.
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
    await sleep(wait);
  }
}
let token;
async function auth() {
  const { r, text } = await xfetch(AUTH, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: process.env.XRAY_CLIENT_ID, client_secret: process.env.XRAY_CLIENT_SECRET }) });
  if (!r.ok) throw new Error(`Auth failed: ${r.status}`);
  token = text.replace(/^"|"$/g, "");
}
async function gql(query, variables = {}) {
  const { r, text, body: j } = await xfetch(GQL, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ query, variables }) });
  if (!j) throw new Error(`Xray returned HTTP ${r.status}, not JSON: ${text.slice(0, 80)}`);
  if (j.errors) throw new Error("GraphQL error: " + JSON.stringify(j.errors));
  return j.data;
}

async function openPlans() {
  const d = await gql(`query($j:String!){ getTestPlans(jql:$j, limit:25){ results { issueId jira(fields:["key","summary","status"]) } } }`,
    { j: `project = '${PROJECT}' AND issuetype = 'Test Plan' AND statusCategory != Done ORDER BY created DESC` });
  return d.getTestPlans.results;
}
async function resolvePlan(key) {
  const d = await gql(`query($j:String!){ getTestPlans(jql:$j, limit:1){ results { issueId jira(fields:["key","summary","status"])
    testExecutions(limit:100){ results { issueId jira(fields:["key","summary"]) } } } } }`, { j: `key = "${key}"` });
  const p = d.getTestPlans.results[0];
  if (!p) throw new Error(`${key} is not a Test Plan.`);
  return p;
}
async function setTests(key) {
  const d = await gql(`query($j:String!){ getTestSets(jql:$j, limit:1){ results { issueId jira(fields:["summary"]) } } }`, { j: `key = "${key}"` });
  const s = d.getTestSets.results[0];
  if (!s) throw new Error(`${key} is not a Test Set.`);
  const tests = []; let start = 0;
  for (;;) {
    const t = await gql(`query($i:String!,$s:Int!){ getTestSet(issueId:$i){ tests(limit:100,start:$s){ total results { issueId folder { path } jira(fields:["key","summary"]) } } } }`, { i: s.issueId, s: start });
    const page = t.getTestSet.tests;
    tests.push(...page.results); start += 100;
    if (start >= page.total) break;
  }
  return { summary: s.jira.summary, ids: tests.map((r) => r.issueId), tests };
}

// Compare the saved assignment maps with what the Test Sets hold RIGHT NOW.
// NEW = in the Test Set but no owner in the map (would be left unassigned).
// STALE = in the map but no longer in the Test Set (remove from the map).
// An execution whose map is a bare "default" owner cannot drift, so it is skipped.
async function checkMaps() {
  const read = (f) => JSON.parse(readFileSync(mapPath(f), "utf8"));
  let drift = 0;

  // Two executions may share a Test Set; read each set once.
  const cache = {};
  const load = async (k) => (cache[k] ??= await setTests(k));

  for (const c of CYCLE) {
    const file = c.map ?? c.keys_map;
    if (!file) continue;

    let map;
    try { map = read(file); }
    catch (e) { console.error(`\n${c.summary}: cannot read map ${mapPath(file)} - ${e.message}`); drift++; continue; }

    const set = await load(c.test_set);

    if (c.keys_map) {
      // Flat folder: tests are grouped by key, so drift is measured per test.
      const mapped = new Set(Object.values(map.groups ?? {}).flatMap((g) => g.tests));
      const inSet = new Set(set.tests.map((t) => t.jira.key));
      const isNew = set.tests.filter((t) => !mapped.has(t.jira.key));
      const stale = [...mapped].filter((k) => !inSet.has(k));
      console.log(`\n${c.test_set} (${c.summary}): ${set.tests.length} tests, ${mapped.size} in map`);
      for (const t of isNew) console.log(`  NEW test, no group: ${t.jira.key} | ${t.jira.summary}`);
      for (const k of stale) console.log(`  STALE test in map, not in set: ${k} (${Object.entries(map.groups).find(([, g]) => g.tests.includes(k))[0]})`);
      drift += isNew.length + stale.length;
      continue;
    }

    // A map that is only a default owner takes everything; nothing to drift.
    const modules = map.modules ?? {};
    if (!Object.keys(modules).length && map.default) {
      console.log(`\n${c.test_set} (${c.summary}): ${set.tests.length} tests, single owner - no drift possible`);
      continue;
    }

    const level = map.level ?? 3;
    const modOf = (path) => (path || "").split("/").filter(Boolean)[level - 1] || "(none)";
    const counts = {};
    for (const t of set.tests) counts[modOf(t.folder?.path)] = (counts[modOf(t.folder?.path)] || 0) + 1;
    const isNew = Object.keys(counts).filter((m) => !modules[m]);
    const stale = Object.keys(modules).filter((m) => !counts[m]);
    console.log(`\n${c.test_set} (${c.summary}): ${set.tests.length} tests, ${Object.keys(counts).length} modules`);
    for (const m of isNew) console.log(`  NEW module, no owner: ${m} (${counts[m]} tests)`);
    for (const m of stale) console.log(`  STALE module in map, not in set: ${m}`);
    drift += (map.default ? 0 : isNew.length) + stale.length;
  }

  console.log(drift ? `\n${drift} map entries out of date. Fix the map files before assigning runs.` : `\nMaps match the Test Sets.`);
  if (drift) process.exitCode = 2;
}
async function execTestIds(execId) {
  const ids = new Set(); let start = 0;
  for (;;) {
    const d = await gql(`query($i:[String],$s:Int!){ getTestRuns(testExecIssueIds:$i,limit:100,start:$s){ total results { test { issueId } } } }`, { i: [execId], s: start });
    for (const r of d.getTestRuns.results) ids.add(r.test.issueId);
    start += 100;
    if (start >= d.getTestRuns.total) break;
  }
  return ids;
}
async function createExec(summary) {
  const d = await gql(`mutation($j:JSON!){ createTestExecution(testIssueIds:[], jira:$j){ testExecution { issueId jira(fields:["key"]) } warnings } }`,
    { j: { fields: { summary, project: { key: PROJECT }, ...WORK_BREAKDOWN } } });
  const e = d.createTestExecution.testExecution;
  return { issueId: e.issueId, key: e.jira.key };
}

// Add tests in paced chunks, re-read, retry the ones that did not land.
async function fill(exec, wanted) {
  let missing = wanted.filter((id) => !exec.have.has(id));
  for (let pass = 1; pass <= MAX_PASSES && missing.length; pass++) {
    for (let i = 0; i < missing.length; i += CHUNK) {
      try { await gql(`mutation($i:String!,$t:[String]){ addTestsToTestExecution(issueId:$i, testIssueIds:$t){ warning } }`, { i: exec.issueId, t: missing.slice(i, i + CHUNK) }); }
      catch (e) { console.error(`  ERROR adding tests to ${exec.key}: ${e.message}`); }
      await sleep(DELAY);
    }
    const now = await execTestIds(exec.issueId);
    const before = missing.length;
    missing = wanted.filter((id) => !now.has(id));
    console.log(`  ${exec.key} pass ${pass}: ${before - missing.length} added, ${missing.length} still missing`);
  }
  return missing.length;
}

(async () => {
  await auth();

  if (checkOnly) return checkMaps();

  if (listPlans) {
    const plans = await openPlans();
    if (!plans.length) console.log("No open Test Plans in " + PROJECT + ".");
    for (const p of plans) console.log(`  ${p.jira.key} | ${p.jira.summary} [${p.jira.status?.name ?? "?"}]`);
    return;
  }

  const plan = await resolvePlan(planKey);
  console.log(`\nTest Plan ${plan.jira.key} | ${plan.jira.summary} [${plan.jira.status?.name ?? "?"}]`);
  const onPlan = new Map(plan.testExecutions.results.map((e) => [e.jira.summary, { issueId: e.issueId, key: e.jira.key }]));

  const sets = {};
  for (const c of CYCLE) sets[c.test_set] ??= await setTests(c.test_set);

  const plans = [];
  for (const c of CYCLE) {
    const existing = onPlan.get(c.summary) ?? null;
    const have = existing ? await execTestIds(existing.issueId) : new Set();
    const wanted = sets[c.test_set].ids;
    const toAdd = wanted.filter((id) => !have.has(id)).length;
    plans.push({ ...c, existing, have, wanted });
    console.log(`  ${c.summary.padEnd(28)} <- ${c.test_set} (${sets[c.test_set].summary}, ${wanted.length} tests)  ` +
      (existing ? `REUSE ${existing.key}, ${toAdd} to add` : `CREATE, ${toAdd} to add`));
  }
  if (!apply) { console.log(`\nDRY RUN. Re-run with --apply to make these changes.`); return; }

  let problems = 0;
  const made = [];
  for (const p of plans) {
    const exec = p.existing ?? await createExec(p.summary);
    if (!p.existing) console.log(`\n  created ${exec.key} | ${p.summary}`);
    exec.have = p.have;
    const left = await fill(exec, p.wanted);
    if (left) { problems++; console.log(`  ${exec.key}: ${left} tests STILL MISSING after ${MAX_PASSES} passes`); }
    made.push({ ...exec, summary: p.summary, wanted: p.wanted.length });
  }

  const toLink = made.filter((e) => !onPlan.has(e.summary)).map((e) => e.issueId);
  for (let pass = 1; pass <= MAX_PASSES && toLink.length; pass++) {
    await gql(`mutation($p:String!,$e:[String]!){ addTestExecutionsToTestPlan(issueId:$p, testExecIssueIds:$e){ warning } }`, { p: plan.issueId, e: toLink });
    await sleep(DELAY);
    const linked = new Set((await resolvePlan(planKey)).testExecutions.results.map((e) => e.issueId));
    toLink.splice(0, toLink.length, ...toLink.filter((id) => !linked.has(id)));
  }
  if (toLink.length) { problems++; console.log(`  ${toLink.length} executions NOT linked to ${planKey}`); }

  console.log(`\nVERIFIED from read-back:`);
  for (const e of made) {
    const n = (await execTestIds(e.issueId)).size;
    console.log(`  ${e.key} | ${e.summary}: ${n}/${e.wanted} tests${toLink.includes(e.issueId) ? ", NOT on plan" : `, on ${planKey}`}`);
  }
  if (problems) process.exitCode = 1;
})().catch((e) => { console.error(e.message); process.exitCode = 1; });
