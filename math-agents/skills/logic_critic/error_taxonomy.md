# Error Taxonomy — Logic Critic Checklist

Use this as a systematic checklist when reviewing each chunk. Check for each error type.
Output one line per found error. If none found, output "ok".

---

## 1. Implicit Assumption
**What it looks like:** A hypothesis is used in the proof that was never stated in the theorem or definition.
**Examples:**
- "Since f is continuous..." — but continuity of f was never assumed
- "Because the set is bounded..." — boundedness not in hypothesis
- A lemma applied whose full set of hypotheses were not verified
**Flag as:** `[location]: missing assumption — [what is missing]`

---

## 2. Quantifier Error
**What it looks like:** ∀ and ∃ are swapped, or the scope of a quantifier is wrong.
**Examples:**
- Writing "∀ε > 0, ∃δ > 0" when the argument only works for a fixed ε
- "There exists x such that for all y..." when the argument requires "for all x there exists y..."
- Quantifier scope ambiguity: "∀x ∈ A, f(x) = g(x) + h(y)" — what is y?
**Flag as:** `[location]: quantifier error — [what should change]`

---

## 3. Non-Constructive Step
**What it looks like:** Existence is claimed without a construction, a citation, or an appeal to an axiom.
**Examples:**
- "Such an element exists by compactness" — OK if compactness was established, NOT OK if it wasn't
- "Choose x with property P" — where does this x come from?
- Existence claimed by contradiction without completing the argument
**Flag as:** `[location]: non-constructive — existence of [X] not justified`

---

## 4. Circular Reasoning
**What it looks like:** The claim being proved is used (directly or indirectly) in its own proof.
**Examples:**
- Assuming the limit exists in order to prove the limit exists
- Using a theorem that itself relies on the current lemma
- "By the result we are about to prove..."
**Flag as:** `[location]: circular — [what is assumed that shouldn't be]`

---

## 5. Gap in Deduction
**What it looks like:** Step A and Step B are both present, but the logical move from A to B is not justified.
**Examples:**
- "Therefore f is integrable" — after showing f is bounded, without invoking measurability
- A sequence of equalities where one step is not trivial but is treated as obvious
- "It follows that..." without saying what it follows from
**Flag as:** `[location]: gap — step from [A] to [B] not justified`

---

## 6. Incorrect Theorem Application
**What it looks like:** A named theorem is cited, but one or more of its hypotheses have not been verified.
**Examples:**
- Applying the Intermediate Value Theorem without verifying the function is continuous
- Using the Dominated Convergence Theorem without establishing a dominating function
- Applying a result for compact spaces to a set whose compactness is unverified
**Flag as:** `[location]: theorem misapplied — [theorem name], hypothesis [X] not verified`

---

## 7. Type Error
**What it looks like:** An operation is applied to an object of the wrong mathematical type.
**Examples:**
- Taking the norm of an element that lives in a space without a norm
- Applying a real-valued function to a complex argument without acknowledging the extension
- Treating a multilinear map as linear in all arguments simultaneously
- Composing maps whose domains and codomains don't match
**Flag as:** `[location]: type error — [operation] applied to [object of wrong type]`

---

## 8. Edge Case Omitted
**What it looks like:** The argument works for generic cases but a boundary, empty, or degenerate case is not handled.
**Examples:**
- Division proof that doesn't handle the denominator = 0 case
- Induction that doesn't verify the base case
- Set-theoretic argument that doesn't handle the empty set
- "For sufficiently large n..." without saying how large, or without handling small n separately
**Flag as:** `[location]: edge case — [case] not handled`

---

## 9. Induction Error
**What it looks like:** An inductive argument is malformed.
**Sub-types:**
- **Missing base case:** Inductive step proved, but n=0 (or n=1) never established
- **Wrong inductive hypothesis:** The IH assumed is not what is needed to complete the step
- **Strong vs weak induction confusion:** Step requires IH for all k < n, but only IH for k = n-1 is used
- **Inductive step direction:** Proof goes from n+1 to n instead of n to n+1 (or the reverse of what is stated)
**Flag as:** `[location]: induction error — [base case missing | wrong IH | direction error]`

---

## How to use this checklist

1. Read the chunk once for overall structure
2. Check each of the 9 types above, in order
3. For each one found: output one line in the format `[location] [type] [note]`
4. Use "?" for ambiguities where something feels wrong but you can't identify the exact error type
5. If none found after checking all 9: output "ok"

Output the MEMORY NOTE at the end: what you checked, what you cleared.
