---
name: CE-TC-Perf
description: Use when writing performance/load test cases from a Jira ticket — generates scenarios covering baseline, load, and overload conditions, produces a k6 .js script, and runs a smoke test with 1 VU. Automatically invoked by /TC-Router for performance tickets. Triggers include "write performance tests", "perf tests for PROJ-XXXX", "load test scenarios", "k6 tests", "create performance scenarios".
---

# CE-TC-Perf

Generate Xray Cloud test cases for **performance/load** testing. Extends the TC-Router workflow with performance-specific scenario coverage, k6 script generation, and 1-VU smoke testing.

Inherits all rules and workflow from `/TC-Router` — apply those steps exactly, with the additions and overrides below.

## Scenario coverage requirement (step 5)

Every ticket must produce at minimum one case per category:

| Category | What to cover |
|----------|--------------|
| **Happy path (baseline)** | Expected normal load within SLA — verify response times, throughput, error rate = 0% |
| **Edge cases** | Ramp-up to peak load, sustained load over time, concurrent user bursts, cache cold-start vs warm |
| **Negative** | Overload beyond capacity — verify graceful degradation, error-rate threshold breach, recovery after spike |

Performance SLA defaults (override if ticket specifies):
- p95 response time < 2000ms
- Error rate < 1%
- Throughput: per-ticket baseline (document the expected RPS/VU in the scenario)

If a category has no applicable scenario, note why in the report — don't silently skip.

**The grid is subordinate to the oracle rule.** `../../references/qa-oracle-model.md` decides
whether a row gets a case at all: it must trace to an AC/derived `R`, to the changed code, or to a
measured consumer module, and it must carry an `Oracle` of `ac`, `prior-behaviour` or `risk`. A
category with nothing traceable to the blast radius gets **a stated reason in the report, not a case
invented to fill the row** — that is how PROJ-11089's a11y case ended up asserting a labelling
expectation the ticket never made, and being pulled back out of PROJ-11090 afterwards. Findings that
fall out of the grid this way go to the Test Execution under `Observations for dev` or
`Open questions for product`.

## Field mapping overrides

- **Objective** — load profile + acceptance thresholds: *"Verify that POST /invoices handles 50 concurrent VUs with p95 < 2s and error rate < 1%."*
- **Summary (title)** — format `<Module Name> | <Load Profile> - <Scenario>`: `Invoice API | Baseline Load - POST /invoices (10 VU, 60s)`, `Invoice List | Spike Test - 100 VU burst`.
- **Gherkin style** — load-profile focused. `Given the system is under <load profile>`, `When <N> virtual users send <request> concurrently for <duration>`, `Then p95 response time is below <threshold>ms and error rate is below <X>%`.
- **Data column (Manual)** — `<number of VUs>`, `<ramp duration>`, `<target RPS>`.

## Environment config

Before running any smoke test, read `$env:USERPROFILE\.claude\qa-config.json`.

1. Pick the environment block named by `default_env` (default: `"qa"`).
2. Use `api.base_url` and `api.token_env_var` from that block.
3. Use `k6.smoke_vus` / `k6.smoke_iterations` for the smoke run parameters.
4. If the user says "test against staging" or "use prod", switch to that environment block instead.

To change credentials or URLs, **edit only `qa-config.json`** — no skill files need touching.

## Additional steps

### Step 5a — Generate k6 script (immediately after step 5)

After generating all scenarios, produce a k6 `.js` file. Default options export uses `vus: 1, iterations: 1` for smoke test mode. Include a comment block showing the full load config to swap in for real runs.

```javascript
import http from 'k6/http';
import { check, group, sleep } from 'k6';

// Smoke test (1 VU, 1 iteration) — swap options below for full load run
export const options = {
  vus: 1,
  iterations: 1,
  // Full load config (uncomment and tune):
  // stages: [
  //   { duration: '30s', target: <ramp_vus> },
  //   { duration: '1m',  target: <peak_vus>  },
  //   { duration: '30s', target: 0           },
  // ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed:   ['rate<0.01'],
  },
};

// Base URL and token injected from qa-config.json via the k6 run command below
const BASE_URL = __ENV.API_BASE_URL || '<api.base_url from qa-config.json>';
const TOKEN    = __ENV.API_TOKEN    || '';

const HEADERS = {
  Authorization:  `Bearer ${TOKEN}`,
  'Content-Type': 'application/json',
};

export default function () {
  // --- Happy path: baseline load ---
  group('Baseline - <endpoint> valid request', () => {
    const res = http.post(
      `${BASE_URL}/api/<endpoint>`,
      JSON.stringify({ /* <field>: '<placeholder>' */ }),
      { headers: HEADERS }
    );
    check(res, {
      'status 200/201':  (r) => r.status === 200 || r.status === 201,
      'p95 < 2000ms':    (r) => r.timings.duration < 2000,
    });
  });

  // --- Edge case: ramp / concurrent ---
  group('Edge - <concurrent scenario>', () => {
    const res = http.get(`${BASE_URL}/api/<endpoint>`, { headers: HEADERS });
    check(res, { 'status 200': (r) => r.status === 200 });
  });

  // --- Negative: overload / error path ---
  group('Negative - <overload scenario>', () => {
    const res = http.post(
      `${BASE_URL}/api/<endpoint>`,
      JSON.stringify({ /* malformed or overload payload */ }),
      { headers: HEADERS }
    );
    check(res, { 'expected error status': (r) => r.status >= 400 });
  });

  sleep(1);
}
```

- One `group()` per Xray scenario
- All credentials via `__ENV` — never hardcoded
- Save as `<TICKET>-perf-test.js` in the saveLocation directory

### Step 8a — Run smoke test with 1 VU (after step 8)

After writing to Xray, run the generated k6 script in smoke-test mode.

First, read `$env:USERPROFILE\.claude\qa-config.json` to resolve the active environment (default: `qa`). Use `api.base_url` and `api.token_env_var` from that block.

```powershell
# Load qa-config.json
$cfg      = Get-Content "$env:USERPROFILE\.claude\qa-config.json" | ConvertFrom-Json
$env_key  = $cfg.default_env
$env_cfg  = $cfg.environments.$env_key
$BASE_URL = $env_cfg.api.base_url
$TOKEN    = [System.Environment]::GetEnvironmentVariable($env_cfg.api.token_env_var)
$SMOKE_VUS = $env_cfg.k6.smoke_vus          # from config, default 1
$SMOKE_ITER = $env_cfg.k6.smoke_iterations  # from config, default 1

Write-Host "Running k6 smoke test against: $($env_cfg.label) ($BASE_URL)"

$env:API_BASE_URL = $BASE_URL
$env:API_TOKEN    = $TOKEN

k6 run --vus $SMOKE_VUS --iterations $SMOKE_ITER "<saveLocation>\<TICKET>-perf-test.js"
```

- If k6 not installed: prompt user (`winget install k6` / `choco install k6`) or note the file path for manual execution
- Report result: environment label · all checks green = pass; list any failing checks

**To change environment:** edit `default_env` in `qa-config.json` — no skill edits needed.

### Step 9a — Attach k6 script to Test Execution ticket (after TC-Router step 9)

The Test Execution (if any) is created in TC-Router **step 9**, which runs after the Xray
writes and this smoke test. Once step 9 completes, if it created a TE, attach the `.js`
file via the Jira REST API (same pattern as CE-TC-API step 8b's fallback, substituting the
`.js` file path and `Content-Type: text/javascript`).

If step 9 was skipped (no TE), note the file path in the report instead.

## Common mistakes (performance-specific)

- Writing only baseline happy-path cases. → Must cover ramp-up edge cases and overload negative per ticket.
- Hardcoding credentials or base URLs in k6 script. → Use `__ENV` variables always.
- Exporting options with high VU count and no comment. → Smoke test default must be `vus: 1`; include commented full-load config.
- Not running the smoke test. → Step 8a runs before reporting done; note skip reason if k6 unavailable.
- Skipping a coverage category without noting why. → Always explain omissions in the report.
