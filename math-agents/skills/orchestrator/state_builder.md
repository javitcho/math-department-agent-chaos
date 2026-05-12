# State Builder — Schema and Instructions for RoundState JSON

## Output schema (all fields required)

```json
{
  "established": ["bullet", "bullet"],
  "current_chunk_id": "string — id of the chunk being worked on",
  "open_flags": ["flag", "flag"],
  "round_goal": "one sentence",
  "directive_for_rep": "collegial suggestion, not a command",
  "stopping_signal": "continue | serendipity | counterexample | converged | elegant | budget | incubate | scout_pursue | scout_drop | scout_interesting",
  "stopping_reason": "one sentence — why this signal was issued",
  "priority_issues": ["top issue", "second issue", "third issue"],
  "advance_chunk": true,
  "memory_note": "one short bullet for your own memory"
}
```

## Field-by-field instructions

### `established`
Compressed bullets of everything proven or accepted so far in this session.
- Each bullet ≤ 15 words
- Only include things that are firmly established (all flags cleared, approved by agents)
- Carry forward the previous round's `established` list and add to it when chunks are approved
- Do not include the current chunk's claims unless they are already approved

### `current_chunk_id`
The id of the chunk currently under review. Do not change this unless `advance_chunk` is true.
When advancing, set to the next chunk's id.

### `open_flags`
List of unresolved issues from this and prior rounds. These are carried forward until resolved.
- Add any new flags raised by logic critic or counterex this round
- Remove flags that were resolved in this round (logic critic said "ok" on that specific item)
- Keep flags concise: ≤ 20 words each
- Do not duplicate flags

### `round_goal`
One sentence: what the next round should focus on. Be specific.
Bad: "Continue improving the proof"
Good: "Resolve the quantifier scope issue in step 3 and verify the base case of the induction"

### `directive_for_rep`
A collegial suggestion to the Rep. Phrased as a recommendation, not a command.
- Use: "You might consider...", "It could help to...", "Consider verifying..."
- Do not use: "You must...", "Rewrite...", "Fix..."
- Be specific about which step, which assumption, which claim
- If there are multiple issues, prioritize the most important one
- The Rep is allowed to push back — that is productive

### `stopping_signal`
See decision_logic.md for the full decision rules.
Default: "continue"

### `stopping_reason`
One sentence explaining why this signal was issued.
Required even when signal is "continue" — write "No stopping condition met" in that case.

### `priority_issues`
Top 3 issues from this round, ranked by severity/importance.
- Issue 1: the most critical (logical error > counterexample > elegance)
- Issue 2: next most important
- Issue 3: third
If fewer than 3 issues, fill remaining slots with "none"

### `advance_chunk`
Set to `true` only when:
- All open flags are cleared
- Logic critic returned "ok" this round
- No counterexample found
- The chunk content is substantive (not empty or placeholder)

### `memory_note`
One bullet (≤ 20 words) for your own memory about this round.
Focus on what changed, what was resolved, what remains stuck.

## How to compress `established`

When a chunk is approved:
1. Take its core claim in ≤ 15 words
2. Add it to the `established` list
3. The full chunk text is still available to agents via the session — this is just the summary

Example:
- Chunk "lemma_1" approved → add "Lemma 1: limit of f at p exists and equals L (proved)"
- Chunk "proof_main" approved → add "Main theorem proved via epsilon-delta argument"
