# TE case → automation scenario map

This file is a **template**. It ships empty on purpose: the real mapping is specific to your
Jira project, your Xray test cases and your automation suite, so it cannot be distributed.

## Where your real mapping lives

Create your own at the path set in `automation.te_mapping_path` in `~/.claude/qa-config.json`
(default `~/.claude/qa-te-mapping.md`). The skill reads that file when it exists and falls back
to this template when it does not. Keeping it outside the plugin means a `/plugin update` never
overwrites the mapping you have built up.

The mapping file is the skill's memory. The first reconciliation is expensive because almost
nothing is mapped; every run after that is cheap because confirmed mappings accumulate here.

## Format

Use these four sections. The skill parses headings and table rows, so keep the shapes below.

### Confirmed mappings

One row per Test Execution case that a specific automated scenario provably covers. A case
goes green **only** when a named scenario proves it — never on a feature-name hunch.

| TE case | Case title | Proving scenario(s) | Notes |
|---------|-----------|--------------------|-------|
| PROJ-1234 | Customer search returns matches | `CustomerSearch.feature: Search by account number` | |
| PROJ-1235 | Invoice totals include tax | `Billing.feature: Invoice with taxable service`; `Billing.feature: Invoice with exempt service` | both must be green |

### Area and navigation cases — automation-covered

Umbrella cases ("Settings screens navigation", "Utilities", "Home Page") that a whole green
feature set proves. List the case and the features that must all pass.

| TE case | Case title | Features that must all be green |
|---------|-----------|--------------------------------|
| PROJ-1300 | Settings screens navigation | `Nav_Settings.feature`, `Settings_*.feature` |

#### Umbrella cases that stay manual

Cases too broad for any feature set to prove. Bullet list with a one-line reason each.

- PROJ-1310 — "End-to-end new customer lifecycle": spans modules with no single owning feature.

### Areas with no automation coverage

Product areas where no automated scenario exists, so every case in them goes to the manual
list. Bullet list of area names.

- <area name> — no feature files exist for this area.

### Partial coverage — do not auto-pass

The most important section. Scenarios that *look* like they prove a case but assert something
narrower. Record what the scenario actually checks and what it misses, so the mapping is not
re-proposed on a later run.

| TE case | Tempting scenario | What it actually asserts | What it misses |
|---------|------------------|-------------------------|----------------|
| PROJ-1400 | `Payments.feature: Apply prepayment` | payment row is created | never verifies the balance fields the case is about |

### Rejected mappings — do not re-propose without new evidence

Mappings a human already reviewed and turned down. Keeps the skill from suggesting the same
wrong pairing every regression.

| TE case | Rejected scenario | Why rejected | Date |
|---------|------------------|--------------|------|

## Growing the file

Step 5 of the skill proposes mappings for unmapped cases and asks you to confirm each one.
Confirmed rows get appended to Confirmed mappings; rejected ones to Rejected mappings. Never
let the skill append without confirmation — an unreviewed mapping silently marks untested
product as PASSED in a shared Test Execution.
