# 🔄 Loop Engineering — The Core Protocol

> **Purpose:** This file defines the **loop engineering protocol** that both STARTUP-BUILDER.md and PROJECT-BUILDER.md use. It tells the AI agent how to operate in a continuous loop — checking what's done, doing what's not, and only stopping when everything is verified complete.

---

## The Problem This Solves

Without loop engineering, the AI agent follows a **linear pipeline**:

```
Phase 0 → Phase 1 → Phase 2 → ... → DONE (hopefully)
```

This has a fatal flaw: **the AI stops after one pass, even if the work is incomplete.** It might:
- Skip a role because the manifest file didn't mention it
- Produce shallow outputs because a skill checklist had ambiguous instructions
- Assume a phase is complete when it only completed 80% of the work

Loop engineering fixes this by wrapping the entire pipeline in a **verification loop**:

```
┌─────────────────────────────────────────────────────┐
│ while not all_phases_complete():                     │
│   state = load_state()                               │
│   next_task = determine_next_work(state)             │
│   if next_task:                                      │
│     execute_task(next_task)                          │
│     update_state(task_result)                        │
│   else:                                              │
│     all_complete = verify_all_phases()               │
│     if all_complete: break                           │
│     else: advance_to_next_incomplete_phase()         │
│ deliver_results()                                    │
└─────────────────────────────────────────────────────┘
```

The AI **cannot stop** until every completion criterion is met.

---

## 1. 📍 State File (`outputs/.loop-state.json`)

The AI maintains a JSON state file at `outputs/.loop-state.json` that tracks exactly what's been done and what remains.

### Schema:

```json
{
  "mode": "startup",
  "archetype": "ai",
  "started_at": "2026-07-22T10:00:00Z",
  "last_updated": "2026-07-22T10:00:00Z",
  "loop_count": 1,
  "current_phase": 0,
  "current_role": null,
  "phases": [
    {
      "id": "phase_0_ideation",
      "name": "Ideation",
      "status": "in_progress",
      "total_roles": 43,
      "roles_completed": 0,
      "completed_roles": [],
      "remaining_roles": ["founder-ceo", "market-researcher", "competitive-analyst", "idea-critic", "startup-namer", "..."],
      "completed_outputs": [],
      "last_output_created": null,
      "errors": []
    },
    {
      "id": "phase_1_planning",
      "name": "Planning",
      "status": "pending",
      "total_roles": 46,
      "roles_completed": 0,
      "completed_roles": [],
      "remaining_roles": [],
      "completed_outputs": [],
      "last_output_created": null,
      "errors": []
    }
  ],
  "last_action": "Loop initialized. Starting Phase 0.",
  "source_notes": [],
  "paused_for_user": false
}
```

> **Note:** The exact `total_roles` count depends on the archetype. AI archetype has ~43 roles in Phase 0. SaaS has fewer. The orchestrator handles this automatically.

### After Resuming (Mid-Execution — relevant fields only):

```json
{
  "loop_count": 7,
  "current_role": "market-researcher",
  "current_phase": 0,
  "phases": [
    {
      "id": "phase_0_ideation",
      "name": "Ideation",
      "status": "in_progress",
      "total_roles": 43,
      "roles_completed": 8,
      "completed_roles": ["founder-ceo", "market-researcher", "competitive-analyst"],
      "remaining_roles": ["customer-discovery-specialist", "deep-researcher", "idea-critic", "startup-namer"],
      "completed_outputs": [
        "research/competitive-teardown.md",
        "research/market-analysis.md",
        "business/problem-statement.md"
      ],
      "last_output_created": "research/market-analysis.md",
      "errors": []
    }
  ],
  "last_action": "Completed competitive-teardown research, found 3 key competitors",
  "source_notes": ["Source: https://g2.com/salesforce-reviews"],
  "paused_for_user": false
}
```

> **Note:** The `started_at`, `mode`, and `archetype` fields also exist in the full JSON but are omitted here for brevity — they don't change during execution.

### Rules for the State File:

1. **ALWAYS read the state file at the START of each loop iteration.** It tells you what to do next.
2. **ALWAYS update the state file at the END of each action.** Set `last_updated`, `loop_count + 1`, update `completed_outputs`, `last_action`.
3. **If the state file doesn't exist**, create it fresh (this is iteration 1).
4. **If the state file exists and has `paused_for_user: true`**, stop looping and wait for the user to respond.
5. **NEVER delete the state file** — it's the ground truth of progress.
6. **If the AI session restarts** (context reset), read the state file to resume exactly where you left off.

---

## 2. 🔄 The Loop Itself

### Step-by-Step Loop Logic:

```
LOOP START:
  1. READ STATE  → Load outputs/.loop-state.json
  2. ANALYZE     → Determine what phase we're in and what's incomplete
  3. PLAN        → Pick ONE thing to do next:
                    a. If current phase has incomplete roles → execute the next role
                    b. If current phase has incomplete outputs → re-execute a role for missing outputs
                    c. If current phase seems complete → run verify_phase_complete()
                    d. If all phases complete → run verify_all_complete(), then EXIT LOOP
  4. EXECUTE     → Do the work (load skill, follow checklist, produce outputs)
  5. UPDATE      → Write new state to outputs/.loop-state.json
  6. REPORT      → Tell the user: "Loop #{N}: Completed [action]. [X/Y] phases done."
  7. LOOP BACK   → Go to step 1

LOOP EXIT:
  Deliver final summary to user
```

### Key Behavior Rules:

| Situation | What the AI Does |
|-----------|-----------------|
| **Phase just entered** | Load all roles for this phase, set `status: in_progress`, start executing roles one by one |
| **All roles in phase done** | Call `verify_phase_complete()` — check all outputs exist in the right paths |
| **Phase verified complete** | Set `status: completed`, advance `current_phase + 1`, set new phase to `in_progress` |
| **Role has 4 skills** | Execute all 4 skills before marking role as complete |
| **Skill has 5 checklist items** | Complete all 5 items before marking skill as done |
| **Research returned no real data** | Add `Source: No real data found — recommendation based on general expertise` and continue |
| **User needs to make a decision** | Set `paused_for_user: true`, ask the user, then WAIT. When they respond, set `paused_for_user: false` and loop continues |
| **All phases complete** | Set `status: completed` for all phases, run `verify_all_complete()`, exit loop, deliver results |

---

## 3. ✅ Completion Verification (Real Code — Not Prose)

> ✅ **The orchestrator now implements `verify_phase_complete()` and `verify_all_complete()` as real Python functions.**

To run verification:

```bash
# Check all phases against existing outputs/
python scripts/orchestrate.py --verify
```

This checks whether the required files and directories exist for each phase and produces a detailed report showing exactly what's missing.

### What It Checks Per Phase

| Phase | Files Checked |
|-------|---------------|
| **0: Ideation** | `research/competitive-teardown.md`, `research/market-analysis.md`, `business/problem-statement.md`, `business/value-proposition.md`, `business/business-model.md`, `brand/startup-name.md` |
| **1: Planning** | `product/prd.md`, `architecture/system-design.md`, `architecture/database-schema.md`, `product/roadmap.md` |
| **2: Build** | `code/`, `tests/`, `infra/` directories exist |
| **3: Ship** | `docs/`, `monitoring/`, `support/` directories exist |
| **4: Growth** | `marketing/`, `seo/`, `content/` directories exist |
| **5: Operations** | `legal/`, `hr/`, `finance/` directories exist |

### When to Run Verification

1. **After completing all roles in a phase** → Run `--verify` to confirm files exist
2. **Before exiting the loop** → Run `--verify` to confirm ALL phases complete
3. **After a session resume** → Run `--resume` to see current state, then `--verify` to check outputs

### All-Phases Completion Check

The `--verify` flag runs `verify_all_complete()` which:
1. Checks ALL phases (0-5 for startups, 0-3 for projects)
2. Checks that the `physical-guide/` folder exists
3. Returns a pass/fail report
4. Only when all pass: **exit the loop and deliver results**

### What happens if verification fails:

```
❌ Planning (1/4)
  ✅ product/prd.md
  ❌ architecture/system-design.md (missing)
  ❌ architecture/database-schema.md (missing)
  ❌ product/roadmap.md (missing)

❌ OVERALL: 2/6 phases passed
  4 phase(s) incomplete. Continue building.
```

**Keep looping until verification passes.** The AI agent should:
1. Run `python scripts/orchestrate.py --verify`
2. Check which phases/files are missing
3. Execute the next role to produce missing outputs
4. Update the state file
5. Re-run `--verify` to confirm
6. Loop back until all pass

---

## 4. 📊 Progress Reporting

The orchestrator generates a progress report automatically when initializing the loop. After EACH loop iteration, the AI agent should report progress in this format (use ASCII on Windows terminals, Unicode box-drawing elsewhere):

> **Note:** The exact role counts vary by archetype. The examples below show generic counts. For a real AI archetype startup, Phase 0 would show 43 roles, not 12.

### Unix/macOS (Unicode):
```
────────────────────────────────────────
  [LOOP #7] Progress Report
────────────────────────────────────────
  ⏳ Phase Ideation                  [████████░░] 8/12 roles
  ⬜ Phase Planning                  [░░░░░░░░░░] 0/6 roles
  ⬜ Phase Build                     [░░░░░░░░░░] 0/9 roles
  ⬜ Phase Ship                      [░░░░░░░░░░] 0/5 roles
  ⬜ Phase Growth                    [░░░░░░░░░░] 0/8 roles
  ⬜ Phase Operations                [░░░░░░░░░░] 0/7 roles
────────────────────────────────────────
  Last action: Completed competitive analysis
────────────────────────────────────────
```

### Windows (ASCII fallback — cmd.exe can't render Unicode box drawing):
```
--------------------------------------------------------
  [LOOP #7] Progress Report
--------------------------------------------------------
  [...] Phase Ideation                  [########..] 8/12 roles
  [  ] Phase Planning                  [..........] 0/6 roles
  [  ] Phase Build                     [..........] 0/9 roles
  [  ] Phase Ship                      [..........] 0/5 roles
  [  ] Phase Growth                    [..........] 0/8 roles
  [  ] Phase Operations                [..........] 0/7 roles
--------------------------------------------------------
  Last action: Completed competitive analysis
--------------------------------------------------------
```

> **Real-world example (AI archetype startup):**
> ```
> [...] Phase Ideation          [..........] 0/43 roles
> [  ] Phase Planning          [..........] 0/46 roles
> [  ] Phase Build             [..........] 0/61 roles
> [  ] Phase Ship              [..........] 0/28 roles
> [  ] Phase Growth            [..........] 0/94 roles
> [  ] Phase Operations        [..........] 0/104 roles
> ```

**Icons:** `[OK]` = completed, `[...]` = in progress, `[  ]` = pending (on Windows) or ✅/⏳/⬜ (on Unix)

**Note:** The orchestrator's `--loop` flag auto-generates the initial progress report. For subsequent iterations, the AI agent should produce this manually using the same format.

---

## 5. ⚠️ Loop Safety Rules

1. **NEVER modify `outputs/.loop-state.json` manually.** Only let the AI update it.
2. **Keep loop_count under 1000.** If you hit 1000 iterations, something is stuck — notify the user.
3. **If 3 consecutive loops produce no new outputs**, something is wrong. Set `paused_for_user: true` and ask the user for guidance.
4. **If a skill's `implementation_checklist` has 20+ steps**, complete them over multiple loops. Don't try to do everything in one iteration.
5. **The loop runs in a single Dev session.** If the context resets, the state file ensures you can resume.
6. **The only exit condition** is `verify_all_complete()` returning True. NOT:
   - "I've done enough for now"
   - "The user will figure out the rest"
   - "This phase is close enough"
   Only **verified complete** is complete.

---

## 6. 🔧 Starting the Loop

### Step 1: Initialize the State File (via Orchestrator)

Before entering the loop, initialize the loop state file using the orchestrator script. This populates the state with all roles for each phase:

```bash
# For a startup:
python scripts/orchestrate.py --loop --idea "Your startup idea here"

# For a project:
python scripts/orchestrate.py --loop --project "Your project idea here"
```

This creates `outputs/.loop-state.json` with:
- The matched archetype (for startups)
- All roles populated per phase
- Phase 0 set to `in_progress`, all others `pending`
- `loop_count: 1`

The orchestrator also creates the output directory structure and prints an initial progress report.

### Step 2: Enter the Loop (via Dev/Dev AI)

Then tell the AI agent:

> *"I want to build a startup. Read STARTUP-BUILDER.md and follow the instructions. My idea is: [your idea]"*

**The AI agent is responsible for the actual looping.** The orchestrator only creates the initial state file. The AI:

1. Reads `outputs/.loop-state.json`
2. Executes the next incomplete role using the skill files
3. Updates the state file after each action
4. Loops back until verified complete
5. Only stops when verification passes for all phases

### In a Resumed Session (State File Exists):

If the AI session resets (context limit), the loop can resume:

```
1. Read outputs/.loop-state.json
2. Check paused_for_user — if true, ask the user for input first
3. Resume from current_phase (index) and current_role
4. Continue the loop from where it left off
```

> **Important:** The orchestrator currently has no `--resume` flag. The AI agent must manually read the state file and determine the next action. This is a known gap (see Gap Analysis).

---

*This file is the loop engineering protocol. It transforms the linear builder files into a continuous, self-verifying pipeline. Reference this from STARTUP-BUILDER.md and PROJECT-BUILDER.md via Rule D (Loop Engineering).*

*Note: The orchestrator (`scripts/orchestrate.py`) provides the `--loop` flag to initialize the state file. The actual looping, verification, and state updates are performed by the AI agent using this protocol.*
