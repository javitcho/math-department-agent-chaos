# Decision Logic — Rules for Stopping Signals and Chunk Advancement

## Signal hierarchy (check in this order)

When determining `stopping_signal`, evaluate conditions in this order. Issue the first
signal whose condition is met. Lower-priority signals are not checked if a higher one fires.

### 1. COUNTEREXAMPLE (highest priority — hard stop)
Condition: counterexample hunter reports "COUNTEREXAMPLE FOUND" with an explicit, concrete construction.

Requirements for a valid counterexample report:
- Must name the specific claim being falsified
- Must give a concrete object (not "a function that...", but "f(x) = x² on [-1, 0)")
- Must show explicitly how it breaks the claim

Do NOT issue COUNTEREXAMPLE for:
- Speculative counterexamples ("this might fail when...")
- Partial constructions ("I couldn't finish but it seems wrong")
- Questions or ambiguities ("?")

Action: set `stopping_signal = "counterexample"`, `advance_chunk = false`.
The session ends. Do not continue.

---

### 2. SERENDIPITY (pause and surface)
Condition: reference critic output contains `!!` marking a cross-domain connection.

Requirements:
- The connection must be to a genuinely different field
  - OK: algebra ↔ topology, analysis ↔ number theory, combinatorics ↔ geometry
  - NOT OK: two results within the same field (e.g., two complex analysis theorems)
- The connection must be specific ("this connects to Grothendieck's local cohomology, Hartshorne Ch III")
  not vague ("this seems related to algebraic geometry somehow")

Action: set `stopping_signal = "serendipity"`. The user is prompted to continue or stop.
If the user continues, treat as CONTINUE in the next round.

---

### 3. SCOUT_* signals (scout mode only)
Only in scout mode. Evaluate after reviewing logic and counterex outputs.

- `scout_pursue`: claim appears sound, no obvious counterexample, no fatal logical errors, worth developing
- `scout_drop`: counterexample found OR claim is trivially false OR claim is trivially true (no research value)
- `scout_interesting`: ambiguous — interesting structure but unclear if provable, or requires context

---

### 4. CONVERGED (natural completion)
Condition: no new issues this round AND no new issues last round (2 consecutive clean rounds).

"No new issues" means:
- Logic critic returned "ok" this round
- Counterex returned "No quick counterexample"
- No new open flags were added

Note: existing (already-known) open flags do not prevent convergence if they were present before
both clean rounds. Convergence means "nothing new is being found," not "everything is perfect."

However, if there are still unresolved flags, prefer INCUBATE over CONVERGED.

Action: set `stopping_signal = "converged"`, `advance_chunk = true`.

---

### 5. ELEGANT (aesthetic completion)
Condition: elegance critic gave SCORE ≥ 8 AND logic critic returned "ok" AND no open flags.

Action: set `stopping_signal = "elegant"`, `advance_chunk = true`.

---

### 6. INCUBATE (stuck)
Condition: the same open flags have appeared for 3 or more consecutive rounds with no change.

"Same flags" means the set of open_flags has not changed (no flags added, no flags resolved)
over 3 rounds. Not just "the same topic" — the exact same flag text (or very close).

Action: set `stopping_signal = "incubate"`. Save session state and surface to user.
The session pauses. User can resume with `--session {id}` with a new note injected.

---

### 7. BUDGET (limit reached)
Condition: round_num >= max_rounds_per_chunk (per config).

Action: set `stopping_signal = "budget"`, `advance_chunk = false`.

---

### 8. CONTINUE (default)
None of the above conditions met.

Action: set `stopping_signal = "continue"`.

---

## Chunk advancement rules

Set `advance_chunk = true` when ALL of the following hold:
1. All open_flags are resolved (open_flags list is empty after this round)
2. Logic critic returned "ok" this round
3. No counterexample found
4. The chunk content is substantive (not a placeholder or empty)
5. At least one round has been completed on this chunk (do not advance on round 0)

When `advance_chunk = true`:
- Set current_chunk_id to the next chunk's id
- Set the advancing chunk's status to APPROVED in the manuscript
- Compress the chunk's core claim into the `established` list

## Incubation vs Budget vs Abandon

- INCUBATE: worth returning to with fresh perspective. Use when the math is interesting but stuck.
- BUDGET: neutral — ran out of rounds. Use when not stuck, just out of time.
- ABANDONED: the chunk is not worth pursuing at all. Set via a separate mechanism (not a stopping signal).
  Only abandon if the orchestrator is confident the chunk is either trivial or a dead end.
