# Test-case markdown template

One file per ticket, named `<TICKET>.md` (e.g. `PROJ-9123.md`). This format is **symmetric**:
the skill writes it in step 7 and parses it back in step 2, so a user can hand-create or
edit it in one session and import it in another.

## Rules for the parser

- Each test case starts at a `## ` heading: `## [NEW]` or `## [UPDATE -> PROJ-1234]`.
- `**Title:**` line → the test summary.
- `**Type:**` line → `Cucumber` | `Manual` | `Both` (defaults to the folder's type if
  omitted). `Both` = two Xray tests (one of each), both linked to the ticket.
- The `Description:` and `Preconditions:` blocks map directly into the Xray description
  field (kept labeled), for either type.
- The fenced ` ```gherkin ` block → the Cucumber test's `gherkin` field. **Always include
  it** — the Manual steps derive from it.
- An optional **Manual steps** markdown table (`| # | Action | Data | Expected |`) → the
  Manual test's step rows. If omitted for a Manual/Both case, derive the rows from the
  Gherkin block per SKILL.md.
- `**Traces:**` and `**Oracle:**` are **required** on every case (see
  `../../../references/qa-oracle-model.md`). `Traces` is the AC/`R` id, the changed symbol or file, or
  the consumer module from the blast-radius grep — at least one. `Oracle` is `ac`, `prior-behaviour` or
  `risk`; `none` is not a legal value, and a case parsed with a missing or `none` oracle is rejected on
  import rather than written to Xray. Neither line is copied into the Xray description — the
  traceability is stated inside the description's `Acceptance Criteria` section, and both tags appear
  as columns in the Test Execution's coverage table.
- `**Labels:**`, `**Component:**`, `**Automation:**`, `**WorkBreakdown:**`, `**TestSet:**`
  lines are optional. They feed the Jira `labels`/`components` fields, the Automation
  Status (default new tests → `Not Automated`), the Work Breakdown initiative (default
  `Core (Default)`), and the target Test Set. Omitted → derive from the folder defaults /
  type per SKILL.md.
- `**Status:**` is optional bookkeeping for resume (`draft` / `approved`). A file with all
  `draft` cases is treated as "not yet written" and offered for import.
- For a **Both** case, track each half separately on a `**Result:**` line so a partial
  write resumes correctly, e.g. `**Result:** Cucumber: PROJ-401 created | Manual: pending`.
  On resume, only the `pending` half is (re)created; a half already showing a key is
  skipped.
- Use `[UPDATE -> KEY]` **only** when the new steps extend that test's *same scenario
  intent*, and the chosen Type matches that test's type. A distinct scenario stays `[NEW]`.
- The `Generated:` line is an ISO-8601 UTC timestamp (e.g. `2026-06-03T14:05:00Z`), or
  left as-is when hand-authored.
- Optional header lines `Test Execution:` and `Test Plan:` record step 9's per-run result
  (e.g. `Test Execution: PROJ-9123 | Measurement Assistant-Multi-polygon area calculation
  (reused)`, `Test Plan: PROJ-9100 | 06/02 Sprint Regression`). They're bookkeeping for
  resume — on import, the skill still re-confirms the Test Plan with the user and reuses
  the named execution rather than creating a duplicate. Omitted on a fresh/hand-authored
  file.

## Example

```markdown
# Test Cases — PROJ-9123 (Measurement Assistant)

Ticket: PROJ-9123
Module: Measurement Assistant
Generated: <leave for the skill to stamp>
Test Execution: <leave blank until step 9 — e.g. PROJ-9123 | Measurement Assistant-Multi-polygon area calculation (reused)>
Test Plan: <leave blank until step 9 — e.g. PROJ-9100 | 06/02 Sprint Regression>

## [NEW]
**Title:** Measurement Assistant calculates total area for a multi-polygon lawn
**Type:** Cucumber
**Traces:** AC2
**Oracle:** ac
**Labels:** PROJ, @Regression
**Component:** Measurement Assistant
**Automation:** Not Automated
**WorkBreakdown:** Core (Default)
**TestSet:** Measurement Assistant Regression
**Status:** draft

Description:
Verify the assistant sums the area of every drawn polygon into one lawn total.

Preconditions:
- User is logged into the application under test
- A customer property with map access is open

```gherkin
Scenario: Total area sums multiple polygons
  Given the Measurement Assistant is open for a property
  When I draw two separate lawn polygons
  Then the displayed total area equals the sum of both polygons
```

## [NEW]
**Title:** Measurement Assistant rejects a self-intersecting polygon
**Type:** Both
**Traces:** PolygonValidator.Validate()
**Oracle:** risk
**Status:** draft
**Result:** Cucumber: pending | Manual: pending

Description:
Verify the invalid-shape error path. (Distinct scenario → NEW, not appended to PROJ-8801.)

Preconditions:
- The Measurement Assistant is open

```gherkin
Scenario: Self-intersecting polygon is rejected
  Given the Measurement Assistant is open
  When I draw a polygon whose edges cross
  Then an invalid-shape error is shown
  And no area is recorded
```

Manual steps:

| # | Action | Data | Expected |
|---|--------|------|----------|
| 1 | Open the Measurement Assistant for a property | | Assistant is ready to draw |
| 2 | Draw a polygon whose edges cross | self-intersecting shape | An invalid-shape error is shown and no area is recorded |

## [UPDATE -> PROJ-8801]
**Title:** Measurement Assistant single polygon area
**Type:** Cucumber
**Traces:** AreaCalculator.Recalculate() — behaviour before the change
**Oracle:** prior-behaviour
**Status:** draft

Description:
Extend the existing single-polygon area test with a recalculation case — same scenario
intent, so it appends onto PROJ-8801.

Preconditions:
- A single lawn polygon is drawn

```gherkin
Scenario: Area recalculates when a single polygon is resized
  Given a single lawn polygon with a known area
  When I drag one vertex to enlarge it
  Then the displayed area updates to the new value
```
```

## Canonical example (gold standard)

Deliberately **domain-neutral** (a cake recipe) so it teaches *shape*, not a product's
house style. **Use it as the model only when the target folder has no existing tests to
model on** (SKILL.md step 5 "nothing comparable" branch) — otherwise mirror the folder.

```markdown
## [NEW]
**Title:** Bake a Simple White Cake
**Type:** Manual
**Traces:** AC1
**Oracle:** ac
**Labels:** @Example, Example.feature
**Component:** General/Shared
**Automation:** Not Automated
**WorkBreakdown:** Core (Default)
**TestSet:** Example Recipes
**Status:** draft

Description:
As a baker, I want to bake a simple white cake from seven ingredients. The recipe should
yield one 9-inch square cake that serves 12.

Preconditions:
- The seven cake ingredients are on hand
- A 9-inch square cake pan is available

```gherkin
Scenario: Bake a simple white cake
  Given the seven cake ingredients and a greased 9-inch square pan
  When I cream the sugar and butter, beat in the eggs and vanilla, mix in the dry
    ingredients and milk, and bake the batter at 350°F until the top springs back
  Then the recipe yields one 9-inch square cake that serves 12
```

Manual steps:

| # | Action | Data | Expected |
|---|--------|------|----------|
| 1 | Gather ingredients; preheat oven to 350°F; grease and flour a 9-inch square pan | (reference image) | Assembled ingredients match the reference |
| 2 | Cream sugar and butter; add eggs one at a time; mix in vanilla | (reference image) | Mixture matches the reference |
| 3 | Combine flour and baking powder; add to the wet ingredients; stir in milk until smooth | (reference image) | Texture matches the reference |
| 4 | Pour the batter into the prepared pan | (reference image) | Poured batter matches the reference |
| 5 | Bake until the top springs back when lightly touched (30–40 min) | (reference image) | Cake is baked through |
| 6 | Cool completely; frost | (reference image) | Yields one 9-inch square cake that serves 12 |
```

**Why it's the gold standard** (each point maps to a SKILL.md rule):

- **Persona-led Description** — opens with "As a baker, I want to…" and states the expected
  outcome up front.
- **Action-first Summary** — "Bake a Simple White Cake"; no "Verify" prefix.
- **Concrete, measurable Expected Results** — the last step asserts *one 9-inch cake, serves
  12*, not "it works".
- **Data column carries support material** — here a reference image per step; Data may
  equally hold values or navigation.
- **Domain constants stay literal** — `350°F`, `9-inch`, `seven ingredients` are part of the
  behavior under test, not parameterizable test data (see SKILL.md "Generic data" exception).
