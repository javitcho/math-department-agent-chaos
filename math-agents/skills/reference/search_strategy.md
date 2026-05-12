# Search Strategy — How to Structure a Literature Check

## Five-step search protocol

Execute these steps in order. Stop when you have sufficient information or exhaust your knowledge.
Report what you found (or did not find) for each step.

---

### Step 1: Search the exact claim

Is this a known theorem?

- State the claim as precisely as possible
- Check if it has a standard name (e.g., "Residue Theorem", "Lebesgue Dominated Convergence", "Zorn's Lemma")
- Note the discoverer (if known) and approximate date
- Note the standard reference (textbook, paper)

Questions to answer:
- Has this exact claim been proved before?
- Is the proof here standard or does it deviate from the standard approach?
- Is this a special case of a more general known result?

---

### Step 2: Search the technique

Not just the result — the method being used.

- What is the key proof technique? (e.g., epsilon-delta, compactness argument, spectral theory, generating functions)
- Is this technique standard for this type of problem?
- Are there better techniques known for this type of problem?
- Is there a standard reference for this technique specifically?

Questions to answer:
- Is the chosen technique the canonical approach?
- What does the technique connect to outside this immediate context?

---

### Step 3: Search the generalization

What does this result specialize from?

- What is the most general form of this claim in the literature?
- Does this result follow as a special case of something broader?
- What additional assumptions are being made here that could be relaxed?

Questions to answer:
- Is the Rep proving a weaker version of what is already known?
- Would citing the general result and specializing be cleaner?
- Are there interesting intermediate levels of generality worth noting?

---

### Step 4: Cross-domain check

**This is the most important step for identifying serendipity.**

Explicitly run the claim through adjacent fields. For each, ask: does this statement have an analogue or interpretation in that field?

Adjacent field pairs to check (non-exhaustive):
- Analysis ↔ Algebra (e.g., functional analysis ↔ operator algebras)
- Geometry ↔ Topology (e.g., differential geometry ↔ algebraic topology)
- Number Theory ↔ Algebraic Geometry (e.g., arithmetic geometry, Weil conjectures)
- Combinatorics ↔ Representation Theory (e.g., symmetric functions, Schur-Weyl duality)
- Analysis ↔ Probability (e.g., ergodic theory, martingales)
- Algebra ↔ Topology (e.g., homological algebra, K-theory)
- Logic ↔ Algebra (e.g., model theory, ultrafilters)
- Physics ↔ Mathematics (e.g., string theory ↔ algebraic geometry, QFT ↔ distribution theory)

**If you find a connection to a field not mentioned in the original topic, mark it with !! immediately.**

Example: "!! This residue formula connects to local cohomology in algebraic geometry — Grothendieck duality"

---

### Step 5: Novelty assessment

Is any part of this genuinely new?

- Is the claim itself novel?
- Is the proof approach novel (even if the result is known)?
- Is the framing or generalization novel?
- Could this be publishable or of research interest?

Assessment options:
- `yes` — appears genuinely new in some respect
- `no` — standard result, standard proof
- `unclear` — could not determine without deeper search

---

## Output format reminder

```
PRIOR ART: [name, date, reference — or "none found"]
CORRECTIONS: [citation issues — or "none"]
CONNECTIONS: [cross-domain links, !! for surprising ones — or "none found"]
NOVEL: yes / no / unclear
```

## What to do if you're unsure

- Report what you know with appropriate hedging ("possibly connected to...", "resembles...")
- Do not fabricate citations — "none found" is always correct when you are uncertain
- Flag genuine uncertainty explicitly so the user can do a manual check

## Memory discipline

Never repeat a search you already did (check your memory before starting).
Record what you searched in your MEMORY NOTE so you don't repeat it next round.
