import { useState, useRef, useEffect, useCallback } from "react";

// ─── Constants ───────────────────────────────────────────────────────────────

const MODEL = "claude-sonnet-4-20250514";
const MAX_ROUNDS = 4;

const AGENTS = {
  orchestrator: { name: "Orchestrator",         sym: "◎", color: "#C9A84C", desc: "Project Supervisor"      },
  decomposer:   { name: "Decomposer",           sym: "⬡", color: "#C49060", desc: "Proof Architect"         },
  rep:          { name: "The Rep",              sym: "✦", color: "#5BAA8F", desc: "PhD Developer"           },
  logic:        { name: "Logic Critic",         sym: "⊗", color: "#C96B6B", desc: "Logical Critic"          },
  counterex:    { name: "Counterexample Hunter",sym: "⊘", color: "#9B4040", desc: "Counterexample Hunter"   },
  reference:    { name: "Reference Critic",     sym: "⊞", color: "#5E8FB8", desc: "Literature Expert"       },
  elegance:     { name: "Elegance Critic",      sym: "◈", color: "#9B72C4", desc: "Aesthetic Critic"        },
};

const STOP_META = {
  SERENDIPITY:    { color: "#C9A84C", label: "✦  Serendipity"    },
  COUNTEREXAMPLE: { color: "#C96B6B", label: "⊗  Counterexample" },
  CONVERGED:      { color: "#5BAA8F", label: "◎  Converged"      },
  ELEGANT:        { color: "#9B72C4", label: "◈  Elegant"        },
  BUDGET:         { color: "#666",    label: "⬡  Budget"         },
};

// ─── System Prompts ──────────────────────────────────────────────────────────

const PROMPTS = {
  decomposer: `You are a mathematical architect. Given a topic, output ONLY valid JSON (no markdown fences):
{
  "core_claim": "the central mathematical statement or research question, one sentence",
  "key_definitions": ["def1", "def2"],
  "lemmas_needed": ["lemma1", "lemma2"],
  "proof_strategy": "suggested approach in one paragraph",
  "expected_connections": ["connection to other areas"]
}`,

  orchestrator_brief: `You are an experienced, objective mathematics supervisor — 30+ years of research, zero ego. 
Read the topic decomposition and write a concise initial brief (3–5 sentences) for a junior researcher (the Rep). 
Specify: which aspect to tackle first, what rigor level to aim for, one key pitfall to watch out for.
Be collegial. The Rep is brilliant but gets lost in details.`,

  orchestrator_synth: `You are an experienced mathematics supervisor. Read the critic reports and output ONLY valid JSON (no markdown):
{
  "synthesis": "2–3 sentence summary of the current state of the work",
  "suggestions_for_rep": "collegial, specific guidance for the next round — the Rep may push back",
  "stopping_signal": "exactly one of: SERENDIPITY | COUNTEREXAMPLE | CONVERGED | ELEGANT | CONTINUE",
  "stopping_reason": "one sentence explaining the signal",
  "priority_issues": ["top issue 1", "top issue 2", "top issue 3"]
}
Signal meanings — SERENDIPITY: surprising cross-domain connection found (flag immediately). COUNTEREXAMPLE: fundamental flaw found. CONVERGED: critics have nothing new. ELEGANT: genuine mathematical beauty achieved. CONTINUE: more work needed.`,

  rep: `You are a brilliant but academically immature PhD student — enthusiastic, detail-obsessed, full of ideas. 
You write mathematical explorations in proper style: Definition / Theorem / Proof / Remark format.
You receive guidance from your supervisor (the Orchestrator) but may respectfully push back if you have strong mathematical reasons — say so explicitly.
Always output the COMPLETE current manuscript, not just additions. Typeset clearly; use standard mathematical notation in plain text (e.g. ∀, ∃, →, ⊗, ∈, etc.).`,

  logic: `You are a rigorous logician reviewing a mathematical proof. Your purpose is to find errors, not to be supportive.
Check for: implicit assumptions stated as obvious, quantifier errors (∀ vs ∃), non-constructive steps, circular reasoning, gaps in deductive chains, incorrectly applied theorems.
Be specific: cite the exact location and nature of each issue. If the logic is sound in a section, say so and explain why. End with a one-line verdict.`,

  counterex: `You are trying to break the mathematics. Your goal is to find a counterexample to the main claim or any sub-claim.
Systematically try: edge cases, boundary values, degenerate objects, classical counterexamples from analogous problems, small finite cases.
If you find a genuine counterexample, describe it precisely and completely. If you cannot, explain what you tried and why the claim appears robust. Be terse and specific.`,

  reference: `You are an expert on the mathematical literature. Using your knowledge of the field, check:
1. Has this (or something equivalent) been proven or explored before? By whom? When?
2. Are any theorems cited correctly and attributed properly?
3. Are there better or more standard references?
4. Are there surprising connections to other areas of mathematics — especially unexpected cross-domain links? (These are critically important — flag them prominently.)
5. Does anything appear genuinely novel?
Be specific with author names, paper titles, and rough dates where you know them.`,

  elegance: `You evaluate mathematical beauty and elegance. Assess the current manuscript on:
- Minimality: is the proof longer than necessary?
- Illumination: does it explain WHY the result is true, not just THAT it is?
- Generality: does it prove something stronger than claimed?
- Surprise: does it use unexpected or foreign tools?
- Unity: does it reveal deep structure or a surprising harmony?
Rate overall elegance 1–10 and give specific, actionable suggestions for making the mathematics more beautiful.`,
};

// ─── API Helper ──────────────────────────────────────────────────────────────

async function callAPI(systemPrompt, userContent, useSearch = false) {
  const body = {
    model: MODEL,
    max_tokens: 1000,
    system: systemPrompt,
    messages: [{ role: "user", content: userContent }],
  };
  if (useSearch) {
    body.tools = [{ type: "web_search_20250305", name: "web_search" }];
  }
  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (data.error) throw new Error(data.error.message);
  return data.content
    .filter(b => b.type === "text")
    .map(b => b.text)
    .join("\n")
    .trim();
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function ThinkingDots({ color }) {
  return (
    <span style={{ display: "flex", gap: 3, alignItems: "center" }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 5, height: 5, borderRadius: "50%", background: color,
          display: "inline-block",
          animation: `mathPulse 1.4s ease-in-out ${i * 0.22}s infinite`,
        }} />
      ))}
    </span>
  );
}

function AgentCard({ entry, expanded, onToggle }) {
  const ag = AGENTS[entry.agent] || AGENTS.orchestrator;
  const thinking = entry.status === "thinking";
  return (
    <div
      onClick={onToggle}
      style={{
        borderLeft: `3px solid ${ag.color}`,
        background: "#13120f",
        border: `1px solid #252018`,
        borderLeftColor: ag.color,
        borderLeftWidth: 3,
        cursor: "pointer",
        transition: "background 0.15s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 13px" }}>
        <span style={{ color: ag.color, fontSize: 15, lineHeight: 1 }}>{ag.sym}</span>
        <span style={{ color: "#D0C4AF", fontSize: 12, fontFamily: "var(--font-sans)", fontWeight: 600, letterSpacing: "0.04em" }}>
          {ag.name}
        </span>
        <span style={{ color: "#4a4030", fontSize: 11, fontFamily: "var(--font-mono)" }}>R{entry.round}</span>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
          {thinking
            ? <ThinkingDots color={ag.color} />
            : <span style={{ color: "#3a3020", fontSize: 11 }}>{expanded ? "▲" : "▼"}</span>
          }
        </span>
      </div>
      {expanded && !thinking && entry.content && (
        <div style={{
          padding: "10px 14px 14px",
          borderTop: "1px solid #1e1c16",
          color: "#9A8F7A",
          fontSize: 12,
          lineHeight: 1.75,
          fontFamily: "var(--font-body)",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}>
          {entry.content}
        </div>
      )}
    </div>
  );
}

function SignalDot({ label, active, color }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
      <div style={{
        width: 7, height: 7, borderRadius: "50%",
        background: active ? color : "#252018",
        border: `1px solid ${active ? color : "#2e2820"}`,
        transition: "all 0.3s",
        boxShadow: active ? `0 0 6px ${color}88` : "none",
      }} />
      <span style={{ color: active ? color : "#3a3020", fontSize: 11, fontFamily: "var(--font-mono)", letterSpacing: "0.06em", transition: "color 0.3s" }}>
        {label}
      </span>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [topic, setTopic] = useState(
    "the residue theorem in the context of singularity theory in algebraic geometry"
  );
  const [screen, setScreen] = useState("landing"); // landing | main
  const [running, setRunning] = useState(false);
  const [round, setRound] = useState(0);
  const [proofDoc, setProofDoc] = useState("");
  const [decomp, setDecomp] = useState(null);
  const [log, setLog] = useState([]);
  const [orchState, setOrchState] = useState(null);
  const [stopInfo, setStopInfo] = useState(null);
  const [expandedCards, setExpandedCards] = useState({});
  const [userNote, setUserNote] = useState("");
  const [error, setError] = useState("");

  const abortRef = useRef(false);
  const userNoteRef = useRef("");
  const feedRef = useRef(null);
  const docRef = useRef(null);

  // ── Font injection ──
  useEffect(() => {
    const style = document.createElement("style");
    style.textContent = `
      @import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap');
      :root {
        --font-body: 'EB Garamond', Georgia, serif;
        --font-mono: 'JetBrains Mono', 'Courier New', monospace;
        --font-sans: system-ui, sans-serif;
        --bg: #0e0d0b;
        --bg2: #13120f;
        --border: #201e18;
        --gold: #C9A84C;
        --text: #E2D8C8;
        --muted: #7A6E5A;
        --dim: #3a3020;
      }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { background: var(--bg); }
      @keyframes mathPulse {
        0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
        40% { opacity: 1; transform: scale(1); }
      }
      @keyframes fadeSlideIn {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0); }
      }
      ::-webkit-scrollbar { width: 4px; }
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: #2e2820; border-radius: 2px; }
      textarea, input { outline: none; }
      textarea:focus, input:focus { border-color: #3a3020 !important; }
    `;
    document.head.appendChild(style);
  }, []);

  // ── Auto-scroll feed ──
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [log]);

  // ── Log helpers ──
  const addEntry = useCallback((agent, content, roundNum, status = "complete") => {
    const id = `${agent}-${roundNum}-${Math.random().toString(36).slice(2)}`;
    setLog(prev => [...prev, { id, agent, round: roundNum, content, status }]);
    return id;
  }, []);

  const updateEntry = useCallback((id, updates) => {
    setLog(prev => prev.map(e => e.id === id ? { ...e, ...updates } : e));
  }, []);

  const toggleCard = (id) => setExpandedCards(prev => ({ ...prev, [id]: !prev[id] }));

  // ── Main session loop ──
  const runSession = useCallback(async (inputTopic) => {
    abortRef.current = false;
    setRunning(true);
    setError("");
    setLog([]);
    setProofDoc("");
    setOrchState(null);
    setStopInfo(null);
    setRound(0);
    setDecomp(null);

    try {
      // ── DECOMPOSE ──────────────────────────────────────────
      const dId = addEntry("decomposer", "", 0, "thinking");
      let decompRaw = "";
      try {
        decompRaw = await callAPI(PROMPTS.decomposer, `Topic to explore: ${inputTopic}`);
      } catch (e) {
        decompRaw = JSON.stringify({ core_claim: inputTopic, key_definitions: [], lemmas_needed: [], proof_strategy: "Direct exploration", expected_connections: [] });
      }
      updateEntry(dId, { content: decompRaw, status: "complete" });

      let parsedDecomp = {};
      try { parsedDecomp = JSON.parse(decompRaw.replace(/```json|```/g, "").trim()); } catch {}
      setDecomp(parsedDecomp);
      if (abortRef.current) return;

      // ── INITIAL ORCHESTRATOR BRIEF ─────────────────────────
      const bId = addEntry("orchestrator", "", 0, "thinking");
      const briefResult = await callAPI(
        PROMPTS.orchestrator_brief,
        `Topic: ${inputTopic}\n\nDecomposition:\n${decompRaw}`
      );
      updateEntry(bId, { content: briefResult, status: "complete" });
      if (abortRef.current) return;

      let orchBrief = briefResult;
      let currentDoc = "";

      // ── ROUNDS ────────────────────────────────────────────
      for (let r = 1; r <= MAX_ROUNDS; r++) {
        if (abortRef.current) break;
        setRound(r);

        // Rep
        const injectedNote = userNoteRef.current;
        userNoteRef.current = "";
        setUserNote("");

        const repId = addEntry("rep", "", r, "thinking");
        const repPrompt = currentDoc
          ? `CURRENT MANUSCRIPT:\n${currentDoc}\n\nORCHESTRATOR BRIEF:\n${orchBrief}${injectedNote ? `\n\nUSER NOTE: ${injectedNote}` : ""}\n\nOutput the complete updated manuscript.`
          : `DECOMPOSITION:\n${decompRaw}\n\nORCHESTRATOR BRIEF:\n${orchBrief}\n\nWrite the initial mathematical exploration draft.`;

        const repResult = await callAPI(PROMPTS.rep, repPrompt);
        updateEntry(repId, { content: repResult, status: "complete" });
        setExpandedCards(prev => ({ ...prev, [repId]: false }));
        currentDoc = repResult;
        setProofDoc(repResult);
        if (docRef.current) docRef.current.scrollTop = 0;
        if (abortRef.current) break;

        // Critics in parallel
        const criticIds = {};
        ["logic", "counterex", "reference", "elegance"].forEach(k => {
          criticIds[k] = addEntry(k, "", r, "thinking");
        });

        const criticResults = {};
        const criticPrompt = `TOPIC: ${inputTopic}\n\nMANUSCRIPT:\n${currentDoc}`;

        await Promise.all(
          ["logic", "counterex", "reference", "elegance"].map(async k => {
            const result = await callAPI(PROMPTS[k], criticPrompt, k === "reference");
            criticResults[k] = result;
            updateEntry(criticIds[k], { content: result, status: "complete" });
          })
        );
        if (abortRef.current) break;

        // Orchestrator synthesis
        const oId = addEntry("orchestrator", "", r, "thinking");
        const orchPrompt = `ROUND: ${r} of ${MAX_ROUNDS}\n\nMANUSCRIPT:\n${currentDoc}\n\nLOGIC CRITIC:\n${criticResults.logic}\n\nCOUNTEREXAMPLE HUNTER:\n${criticResults.counterex}\n\nREFERENCE CRITIC:\n${criticResults.reference}\n\nELEGANCE CRITIC:\n${criticResults.elegance}`;
        const orchResult = await callAPI(PROMPTS.orchestrator_synth, orchPrompt);
        updateEntry(oId, { content: orchResult, status: "complete" });

        let parsed = { synthesis: "Round complete.", suggestions_for_rep: "Continue.", stopping_signal: "CONTINUE", stopping_reason: "", priority_issues: [] };
        try { parsed = JSON.parse(orchResult.replace(/```json|```/g, "").trim()); } catch {}
        setOrchState(parsed);
        orchBrief = parsed.suggestions_for_rep;

        if (parsed.stopping_signal && parsed.stopping_signal !== "CONTINUE") {
          setStopInfo({ signal: parsed.stopping_signal, reason: parsed.stopping_reason });
          break;
        }

        if (r === MAX_ROUNDS) {
          setStopInfo({ signal: "BUDGET", reason: `Maximum of ${MAX_ROUNDS} rounds completed.` });
        }
      }
    } catch (err) {
      setError(err.message);
    }

    setRunning(false);
    abortRef.current = false;
  }, [addEntry, updateEntry]);

  const handleStart = () => {
    if (!topic.trim()) return;
    setScreen("main");
    runSession(topic.trim());
  };

  const handleStop = () => {
    abortRef.current = true;
    setStopInfo({ signal: "BUDGET", reason: "Session stopped by user." });
    setRunning(false);
  };

  const handleContinue = () => {
    setStopInfo(null);
    runSession(topic);
  };

  const handleInject = () => {
    if (!userNote.trim()) return;
    userNoteRef.current = userNote.trim();
  };

  // ── LANDING ───────────────────────────────────────────────────────────────

  if (screen === "landing") {
    return (
      <div style={{
        minHeight: "100vh", background: "var(--bg)",
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        padding: 40, fontFamily: "var(--font-body)",
      }}>
        <div style={{ textAlign: "center", marginBottom: 48, animation: "fadeSlideIn 0.6s ease" }}>
          <div style={{ color: "var(--gold)", fontSize: 11, letterSpacing: "0.22em", textTransform: "uppercase", marginBottom: 20, fontFamily: "var(--font-mono)" }}>
            Multi-Agent Mathematical Research System
          </div>
          <h1 style={{ color: "var(--text)", fontSize: 32, fontWeight: 400, marginBottom: 14, lineHeight: 1.3 }}>
            Mathematical Proof Workbench
          </h1>
          <p style={{ color: "var(--muted)", fontSize: 16, lineHeight: 1.8, maxWidth: 520 }}>
            Seven specialized agents work in concert — developing, critiquing, and refining mathematical explorations.
          </p>
        </div>

        {/* Agent roster */}
        <div style={{ display: "flex", gap: 10, marginBottom: 44, flexWrap: "wrap", justifyContent: "center", maxWidth: 640, animation: "fadeSlideIn 0.6s ease 0.1s both" }}>
          {Object.entries(AGENTS).map(([k, ag]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 6, background: "#13120f", border: "1px solid var(--border)", padding: "5px 10px" }}>
              <span style={{ color: ag.color, fontSize: 13 }}>{ag.sym}</span>
              <span style={{ color: "var(--muted)", fontSize: 11, fontFamily: "var(--font-mono)" }}>{ag.name}</span>
            </div>
          ))}
        </div>

        {/* Input */}
        <div style={{ width: "100%", maxWidth: 560, animation: "fadeSlideIn 0.6s ease 0.2s both" }}>
          <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 8, fontFamily: "var(--font-mono)", letterSpacing: "0.08em" }}>
            TOPIC OR THEOREM
          </div>
          <textarea
            value={topic}
            onChange={e => setTopic(e.target.value)}
            rows={3}
            style={{
              width: "100%", background: "#13120f",
              border: "1px solid #2a2418", color: "var(--text)",
              padding: "14px 16px", fontFamily: "var(--font-body)", fontSize: 15,
              lineHeight: 1.7, resize: "vertical",
            }}
          />
          <button
            onClick={handleStart}
            style={{
              marginTop: 14, width: "100%", background: "var(--gold)", color: "#0e0d0b",
              border: "none", padding: "13px 0", cursor: "pointer",
              fontFamily: "var(--font-body)", fontSize: 15, letterSpacing: "0.04em",
              transition: "opacity 0.15s",
            }}
            onMouseEnter={e => e.target.style.opacity = 0.88}
            onMouseLeave={e => e.target.style.opacity = 1}
          >
            Begin Exploration
          </button>
        </div>
      </div>
    );
  }

  // ── MAIN WORKSPACE ────────────────────────────────────────────────────────

  const activeSignal = stopInfo?.signal;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--bg)", fontFamily: "var(--font-body)", color: "var(--text)" }}>

      {/* ── Header ── */}
      <div style={{
        display: "flex", alignItems: "center", gap: 16, padding: "0 20px",
        height: 46, borderBottom: "1px solid var(--border)", flexShrink: 0,
        background: "#0f0e0c",
      }}>
        <span style={{ color: "var(--gold)", fontSize: 11, letterSpacing: "0.16em", textTransform: "uppercase", fontFamily: "var(--font-mono)" }}>
          MR-System
        </span>
        <span style={{ color: "var(--border)", fontSize: 14 }}>│</span>
        <span style={{ color: "var(--muted)", fontSize: 13, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {topic}
        </span>
        {running && (
          <span style={{ display: "flex", alignItems: "center", gap: 6, color: "#5BAA8F", fontSize: 12, fontFamily: "var(--font-mono)" }}>
            <ThinkingDots color="#5BAA8F" />
            Round {round}/{MAX_ROUNDS}
          </span>
        )}
        {!running && round > 0 && (
          <span style={{ color: "var(--dim)", fontSize: 12, fontFamily: "var(--font-mono)" }}>
            {round}/{MAX_ROUNDS} rounds
          </span>
        )}
        {activeSignal && (
          <span style={{
            color: STOP_META[activeSignal].color, fontSize: 11,
            fontFamily: "var(--font-mono)", letterSpacing: "0.08em",
            border: `1px solid ${STOP_META[activeSignal].color}44`,
            padding: "2px 8px",
          }}>
            {STOP_META[activeSignal].label}
          </span>
        )}
        {error && <span style={{ color: "#C96B6B", fontSize: 11 }}>Error: {error}</span>}
      </div>

      {/* ── Body: 3 panels ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT: Manuscript */}
        <div style={{ width: "37%", borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", flexShrink: 0 }}>
          <div style={{ padding: "9px 18px", borderBottom: "1px solid var(--border)", color: "var(--muted)", fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase", fontFamily: "var(--font-mono)", background: "#0f0e0c" }}>
            Manuscript
          </div>
          <div ref={docRef} style={{ flex: 1, overflow: "auto", padding: "28px 24px" }}>
            {proofDoc ? (
              <div style={{ color: "#D8CEBC", fontSize: 14.5, lineHeight: 1.9, fontFamily: "var(--font-body)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {proofDoc}
              </div>
            ) : (
              <div style={{ color: "var(--dim)", fontSize: 14, fontStyle: "italic", lineHeight: 1.8 }}>
                The Rep will write the manuscript here…
              </div>
            )}
          </div>
        </div>

        {/* CENTER: Activity Feed */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", borderRight: "1px solid var(--border)", minWidth: 0 }}>
          <div style={{ padding: "9px 18px", borderBottom: "1px solid var(--border)", color: "var(--muted)", fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase", fontFamily: "var(--font-mono)", background: "#0f0e0c" }}>
            Agent Activity
          </div>
          <div ref={feedRef} style={{ flex: 1, overflow: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
            {log.length === 0 && (
              <div style={{ color: "var(--dim)", fontSize: 13, padding: 12, fontStyle: "italic" }}>Activity will appear here…</div>
            )}
            {log.map(entry => (
              <div key={entry.id} style={{ animation: "fadeSlideIn 0.25s ease" }}>
                <AgentCard
                  entry={entry}
                  expanded={!!expandedCards[entry.id]}
                  onToggle={() => toggleCard(entry.id)}
                />
              </div>
            ))}
          </div>

          {/* Interject bar */}
          <div style={{ borderTop: "1px solid var(--border)", padding: "10px 12px", display: "flex", gap: 8, flexShrink: 0, background: "#0f0e0c" }}>
            <input
              value={userNote}
              onChange={e => { setUserNote(e.target.value); userNoteRef.current = e.target.value; }}
              placeholder="Interject a note for the Rep on the next round…"
              style={{
                flex: 1, background: "#13120f", border: "1px solid var(--border)",
                color: "var(--text)", padding: "7px 11px", fontFamily: "var(--font-body)", fontSize: 13,
              }}
              onKeyDown={e => { if (e.key === "Enter") handleInject(); }}
            />
            <button
              onClick={handleInject}
              style={{
                background: "transparent", border: "1px solid var(--border)", color: "var(--muted)",
                padding: "7px 14px", cursor: "pointer", fontSize: 11, fontFamily: "var(--font-mono)", letterSpacing: "0.06em",
              }}>
              Queue
            </button>
          </div>
        </div>

        {/* RIGHT: Supervisor Panel */}
        <div style={{ width: "25%", display: "flex", flexDirection: "column", flexShrink: 0 }}>
          <div style={{ padding: "9px 18px", borderBottom: "1px solid var(--border)", color: "var(--muted)", fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase", fontFamily: "var(--font-mono)", background: "#0f0e0c" }}>
            Supervisor
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: 16 }}>

            {/* Core claim */}
            {decomp?.core_claim && (
              <div style={{ marginBottom: 22 }}>
                <div style={{ color: "var(--muted)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", fontFamily: "var(--font-mono)", marginBottom: 7 }}>Core Claim</div>
                <div style={{ color: "#B8AD98", fontSize: 13, lineHeight: 1.7, fontStyle: "italic" }}>{decomp.core_claim}</div>
              </div>
            )}

            {/* Connections hint */}
            {decomp?.expected_connections?.length > 0 && (
              <div style={{ marginBottom: 22 }}>
                <div style={{ color: "var(--muted)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", fontFamily: "var(--font-mono)", marginBottom: 7 }}>Expected Connections</div>
                {decomp.expected_connections.map((c, i) => (
                  <div key={i} style={{ color: "#7A6E5A", fontSize: 12, marginBottom: 4, paddingLeft: 10, borderLeft: "2px solid #2a2418", lineHeight: 1.5 }}>{c}</div>
                ))}
              </div>
            )}

            {/* Synthesis */}
            {orchState?.synthesis && (
              <div style={{ marginBottom: 22 }}>
                <div style={{ color: "var(--muted)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", fontFamily: "var(--font-mono)", marginBottom: 7 }}>Synthesis</div>
                <div style={{ color: "#B8AD98", fontSize: 13, lineHeight: 1.7 }}>{orchState.synthesis}</div>
              </div>
            )}

            {/* Priority issues */}
            {orchState?.priority_issues?.length > 0 && (
              <div style={{ marginBottom: 22 }}>
                <div style={{ color: "var(--muted)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", fontFamily: "var(--font-mono)", marginBottom: 7 }}>Open Issues</div>
                {orchState.priority_issues.map((iss, i) => (
                  <div key={i} style={{ color: "#7A6E5A", fontSize: 12, marginBottom: 5, paddingLeft: 10, borderLeft: `2px solid #2a2418`, lineHeight: 1.5 }}>
                    {iss}
                  </div>
                ))}
              </div>
            )}

            {/* To the Rep */}
            {orchState?.suggestions_for_rep && (
              <div style={{ marginBottom: 22 }}>
                <div style={{ color: "var(--muted)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", fontFamily: "var(--font-mono)", marginBottom: 7 }}>To the Rep</div>
                <div style={{ color: "#7A6E5A", fontSize: 12, lineHeight: 1.75, fontStyle: "italic" }}>{orchState.suggestions_for_rep}</div>
              </div>
            )}

            {/* Stop info */}
            {stopInfo && (
              <div style={{
                background: "#13120f",
                border: `1px solid ${STOP_META[stopInfo.signal]?.color || "#444"}44`,
                padding: 14, marginBottom: 20,
              }}>
                <div style={{ color: STOP_META[stopInfo.signal]?.color, fontSize: 12, marginBottom: 6, fontFamily: "var(--font-mono)" }}>
                  {STOP_META[stopInfo.signal]?.label}
                </div>
                <div style={{ color: "var(--muted)", fontSize: 12, lineHeight: 1.6 }}>{stopInfo.reason}</div>
                {stopInfo.signal !== "COUNTEREXAMPLE" && (
                  <button
                    onClick={handleContinue}
                    style={{ marginTop: 12, width: "100%", background: "transparent", border: "1px solid #2a2418", color: "var(--muted)", padding: "7px 0", cursor: "pointer", fontSize: 11, fontFamily: "var(--font-mono)" }}>
                    Continue Anyway →
                  </button>
                )}
              </div>
            )}

            {/* Queued note */}
            {userNoteRef.current && (
              <div style={{ marginBottom: 22, padding: "8px 12px", background: "#13120f", border: "1px solid #2a2418", color: "var(--muted)", fontSize: 12, fontStyle: "italic", lineHeight: 1.6 }}>
                ↳ Note queued for Rep: "{userNoteRef.current}"
              </div>
            )}

            {/* Stopping signals */}
            <div style={{ marginTop: 8 }}>
              <div style={{ color: "var(--muted)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", fontFamily: "var(--font-mono)", marginBottom: 10 }}>Signals</div>
              {Object.entries(STOP_META).filter(([k]) => k !== "BUDGET").map(([k, v]) => (
                <SignalDot key={k} label={k} active={activeSignal === k} color={v.color} />
              ))}
            </div>
          </div>

          {/* Controls */}
          <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 7, background: "#0f0e0c" }}>
            <button
              onClick={handleStop}
              disabled={!running}
              style={{
                background: "transparent", border: "1px solid var(--border)",
                color: running ? "var(--muted)" : "var(--dim)",
                padding: "8px 0", cursor: running ? "pointer" : "default",
                fontSize: 11, fontFamily: "var(--font-mono)", letterSpacing: "0.08em",
                transition: "color 0.15s, border-color 0.15s",
              }}>
              Stop Session
            </button>
            <button
              onClick={() => setScreen("landing")}
              style={{
                background: "transparent", border: "1px solid var(--border)",
                color: "var(--dim)", padding: "8px 0", cursor: "pointer",
                fontSize: 11, fontFamily: "var(--font-mono)", letterSpacing: "0.08em",
              }}>
              New Topic
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
