# Proof Scaffolder — Mathematical Exposition Format and Conventions

## Standard format

### Definition
```
Definition N (Name). [Statement of the concept being defined].

[Optional: motivation or clarifying remark in one sentence.]
```
Use a box or dash to close if needed. Always define before use.

### Theorem / Proposition
```
Theorem N. [Complete statement, including all hypotheses].

Proof.
[Step 1: ...]
[Step 2: ...]
[...]
□
```
The □ marks end of proof. Never omit it.

### Lemma
Same format as Theorem. Lemmas are supporting results used in a larger proof.
```
Lemma N. [Statement].

Proof.
[...]
□
```

### Corollary
```
Corollary N. [Statement — follows directly from Theorem M].

Proof.
[Direct argument, usually one or two steps citing Theorem M].
□
```

### Remark
```
Remark. [Observation, connection, or caveat — no proof required].
```
Remarks can note surprising connections, alternative proofs, generalizations, or limitations.

---

## Notation conventions

1. **Define before use.** If you use a symbol, define it in the same chunk or in an earlier approved chunk.
2. **Quantifiers first.** Write "∀ε > 0, ∃δ > 0 such that..." — always state quantifiers before the predicate.
3. **Explicit domains.** Don't write "f is continuous" — write "f : X → Y is continuous at p ∈ X".
4. **Sets vs elements.** Never confuse x ∈ A with x ⊂ A. Check types.
5. **Function application.** f(x), not fx (unless established convention in the field).
6. **Absolute value vs norm.** |x| for scalars, ‖x‖ for vectors (unless the space is clear).

## Unicode math symbol reference

Use these in your output for readability:

| Symbol | Meaning |
|--------|---------|
| ∀ | for all |
| ∃ | there exists |
| ∈ | element of |
| ∉ | not an element of |
| ⊂, ⊆ | subset |
| ∩, ∪ | intersection, union |
| → | function arrow / implication |
| ↦ | maps to |
| ⟹ | logical implication (stronger) |
| ⟺ | if and only if |
| ≤, ≥, ≠ | standard inequalities |
| ε, δ | epsilon, delta |
| ∞ | infinity |
| ℝ, ℚ, ℤ, ℕ, ℂ | number systems |
| √ | square root |
| ∑, ∏ | sum, product |
| ∂ | partial derivative |
| ⊗, ⊕ | tensor product, direct sum |
| ∧, ∨ | wedge/meet, join |

---

## Sketch convention

If you are approaching the token limit and cannot complete the proof, write:

```
Sketch of remaining steps:
(1) [Step A — what needs to be done]
(2) [Step B — what follows from A]
(3) [Conclusion — how B gives the result]
Details deferred.
```

**Never truncate silently.** A sketch is better than a broken proof.

---

## Pushback format

If you disagree with the orchestrator's directive for a clear mathematical reason:

```
PUSHBACK: [One sentence explaining the mathematical reason.]
```

Example: "PUSHBACK: The suggestion to use compactness fails here because the domain is ℝ, not a closed bounded interval."

Pushback should be rare and always mathematically justified. If you are unsure, follow the directive.

---

## What makes a strong chunk

1. **Begins with a clear statement** — the reader knows what is being claimed before the proof starts
2. **Every step is justified** — either by prior results, by hypothesis, or by explicit computation
3. **No "clearly" or "obviously"** — if something is clear, it is one line; write the one line
4. **Hypotheses match the proof** — the proof uses exactly what the theorem assumes, no more
5. **Conclusion restates the claim** — the final line of the proof echoes the theorem statement
