# Chunk Splitter — Rules for Identifying Logical Chunk Boundaries

## Core principle
Each chunk contains exactly one mathematical claim or structural unit. Do not combine claims.

## What constitutes one chunk

| Type | Rule |
|------|------|
| Definition | One named concept. Standard definitions that depend on each other may be grouped only if they form an inseparable pair (e.g., open/closed). |
| Theorem | One statement. Even if short. |
| Proof | A proof is always a separate chunk from its theorem. A 3-line proof is still its own chunk. |
| Lemma | Same as Theorem — statement in one chunk, proof in another. |
| Corollary | One chunk per corollary, with its proof. |
| Remark | One chunk per remark. Never fold remarks into a theorem chunk. |
| Example | One chunk per example used to illustrate a claim. |

## Special rules

### Cross-domain remarks are always isolated
A remark that connects to another field (e.g., "this is related to the Nullstellensatz") is always its own chunk. These are serendipity surface points — the Reference Critic reads them in isolation so cross-domain connections are not buried.

### Definitions that are purely standard
Standard background definitions (e.g., "a metric space is...") may be grouped into a single "preliminaries" chunk if they are all well-known and require no development. Non-standard definitions — or definitions with subtle points — get their own chunk.

### Proof steps
For long proofs, split at natural sub-goals:
- Step A: Reduce to the case where...
- Step B: Show the reduced case holds by...
- Step C: Conclude...
Each step is a chunk if it is logically independent and contains a mini-claim.

## Chunk size target
150–400 tokens for content. If a chunk is:
- Below 50 tokens: it is likely too trivial to be its own chunk — consider merging
- Above 500 tokens: it likely contains two claims — consider splitting

## Advancement rule
A chunk advances to the next when: all open flags are resolved AND logic critic reports "ok" AND no counterexample found. The orchestrator sets `advance_chunk: true` in that case.

## Decomposer output alignment
When the decomposer produces 4-8 chunks, the orchestrator should accept that structure. Do not arbitrarily merge or split what the decomposer produced unless there is a clear boundary error.
