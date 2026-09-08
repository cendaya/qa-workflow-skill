---
name: CE-TC-API
description: Use when writing API/REST endpoint test cases from a Jira ticket — generates Gherkin/Manual scenarios covering happy path, edge cases, and negative scenarios. After creating scenarios, smoke tests each endpoint and generates a Postman collection JSON attached to the Test Execution ticket. Automatically invoked by /TC-Router for API tickets. Triggers include "write API test cases", "REST test cases for PROJ-XXXX", "API scenarios", "endpoint tests".
---

# CE-TC-API

Generate Xray Cloud test cases for **REST API** endpoints. Extends the JD-TC-writer workflow with API-specific scenario coverage, post-creation endpoint smoke testing, and Postman collection generation.

Inherits all rules and workflow from `/TC-Router` — apply those steps exactly, with the additions and overrides below.

## Scenario coverage requirement (step 5)

Every endpoint must produce at minimum one case per category:

| Category | What to cover |
|----------|--------------|
| **Happy path** | Valid request with all required params → expected 2xx response, correct body schema |
| **Edge cases** | Optional params absent, boundary values (min/max), empty arrays, max payload size, duplicate submission, concurrent requests |
| **Negative** | Missing/invalid auth (401/403), malformed body (400), resource not found (404), method not allowed (405), server/upstream error (500/503) |
| **Security** | SQL/NoSQL injection in string fields, mass assignment (extra undeclared fields in body), IDOR (access another user's resource with valid auth), rate limiting (rapid repeated calls), oversized payload |

If a category has no applicable scenario for the ticket, note why in the report — don't silently skip.

## Field mapping overrides

- **Objective** — "Verify that…" sentence + Swagger link. Example: *"Verify that POST /invoices returns 201 with the created invoice id when given a valid payload. [Swagger](<api.swagger_url from qa-config.json>)"*
- **Summary (title)** — format `<Module Name> | <HTTP verb> - <Scenario>`: `Invoice API | POST - Create Invoice with Valid Payload`, `Invoice API | GET - Retrieve Invoice by ID - Not Found (404)`.
- **Gherkin style** — request/response focused. `Given a valid auth token`, `When I send POST /invoices with <valid payload>`, `Then the response status is 201 and body contains <invoice id>`.
- **Data column (Manual)** — `<valid auth token>`, `<valid invoice payload>`, `<existing invoice id>`. Never literal tokens or real IDs.

## Swagger contract check (before step 5 — generate cases)

Before generating scenarios, verify ticket endpoints exist in the Swagger spec and pull real schema.

```powershell
$cfg = Get-Content "$env:USERPROFILE\.claude\qa-config.json" | ConvertFrom-Json
$SWAGGER_URL = "$($cfg.environments.($cfg.default_env).api.base_url)/swagger/v1/swagger.json"
$spec = Invoke-RestMethod -Uri $SWAGGER_URL
```

For each endpoint from the ticket (method + path):
1. Check it exists in `$spec.paths` — flag ⚠️ if missing (unreleased or wrong path)
2. Pull request body schema and response schema to inform `Data` column values (real field names, correct types)
3. Note spec-defined constraints (required fields, enum values, max lengths) — use them as edge-case scenarios

If Swagger is unreachable, note "Swagger check skipped — using ticket description only" and proceed.

## Environment config

Before running any smoke test, read `$env:USERPROFILE\.claude\qa-config.json`.

1. Pick the environment block named by `default_env` (default: `"qa"`).
2. Use `api.base_url` as the base URL.
3. Use `api.token_env_var` to look up the token from the shell environment (e.g. `$env:API_TOKEN`).
4. If the user says "test against staging" or "use prod", switch to that environment block instead.

To change credentials or switch environments, **edit only `qa-config.json`** — no skill files need touching.

## Additional steps (after step 8 — write to Xray)

### Step 8a — Smoke test endpoints

After all test cases are written, smoke test each unique endpoint from the ticket:

1. Read `qa-config.json`, resolve the active environment (default: `qa`).
2. **Verify environment is reachable** before running any scenarios:
   ```powershell
   $cfg = Get-Content "$env:USERPROFILE\.claude\qa-config.json" | ConvertFrom-Json
   $PING_URL = $cfg.environments.($cfg.default_env).api.base_url
   try {
     Invoke-RestMethod -Method Get -Uri "$PING_URL/health" -TimeoutSec 10
     Write-Host "API env reachable: $PING_URL"
   } catch {
     Write-Host "WARNING: $PING_URL not reachable — $($_.Exception.Message)"
   }
   ```
   If no `/health` endpoint: try `GET /` or any known lightweight endpoint. If unreachable: warn user and ask to proceed or abort smoke test.
3. Extract endpoint list from ticket/scenarios (method + path, e.g. `POST /api/invoices`).
4. Send one request per endpoint with minimal valid data against the QA environment.
5. Verify expected status code (2xx for happy-path smoke).
6. Report: environment label · endpoint → status code → pass/fail.

```powershell
# Load qa-config.json to get active environment
$cfg     = Get-Content "$env:USERPROFILE\.claude\qa-config.json" | ConvertFrom-Json
$env_key = $cfg.default_env                        # e.g. "qa"
$env_cfg = $cfg.environments.$env_key
$BASE_URL = $env_cfg.api.base_url                  # e.g. <api.base_url from qa-config.json>
$TOKEN_VAR = $env_cfg.api.token_env_var            # e.g. "API_TOKEN"
$TOKEN = [System.Environment]::GetEnvironmentVariable($TOKEN_VAR)

Write-Host "Smoke testing against: $($env_cfg.label) ($BASE_URL)"

$headers = @{
  Authorization  = "Bearer $TOKEN"
  "Content-Type" = "application/json"
}
$resp = Invoke-RestMethod -Method Post `
  -Uri "$BASE_URL/api/<endpoint>" `
  -Headers $headers `
  -Body '{ "<field>": "<value>" }'
Write-Host "POST /api/<endpoint> → $($resp.StatusCode ?? 'ok')"
```

**Never hardcode tokens or base URLs.** If the resolved token env var is unset, ask the user before running. If the environment is unavailable, note "smoke test skipped — credentials not available" in the report.

### Step 8b — Create Postman collection via Postman MCP

Use the Postman MCP to create the collection directly in the Postman workspace — no local JSON file needed.

Load via ToolSearch `select:mcp__plugin_postman_postman__createCollection`.

1. Create the collection: name = `"<TICKET> — <Module> API Tests"`. Ask user which workspace if multiple exist.
2. For each test scenario, add a request via ToolSearch `select:mcp__plugin_postman_postman__createCollectionRequest`:
   - Name: `<HTTP verb> - <scenario title>` (matches Xray test title)
   - Method, URL (`{{base_url}}/api/<path>`), headers (`Authorization: Bearer {{api_token}}`), body with `<placeholder>` values
3. Add collection variables: `base_url` = QA base URL from `qa-config.json`, `api_token` = empty (user fills in Postman).
4. Note the Postman collection URL in the Phase 3 report.

**Fallback:** If Postman MCP unavailable, generate a local `<TICKET>-api-tests.json` (Postman Collection v2.1 format). The Test Execution (if any) is created in TC-Router **step 9**, which runs *after* this step — attach the file there once the TE exists (Jira REST API, `multipart/form-data`, header `X-Atlassian-Token: no-check`, `Authorization: Basic $env:JIRA_BASIC_AUTH`). If step 9 was skipped (no TE), just note the file path in the report.

## Common mistakes (API-specific)

- Writing only 2xx happy-path cases. → Must cover 4xx/5xx negative scenarios per endpoint.
- Hardcoding auth tokens or real values in Gherkin/Data/JSON. → Use `<placeholder>` / `{{variable}}` everywhere.
- Forgetting smoke test after write. → Step 8a runs before reporting done.
- Generating collection JSON but not attaching it. → Attach to the TE once TC-Router step 9 creates one, or note the path in the report if there's no TE.
- Skipping a coverage category without noting why. → Always explain omissions in the report.
