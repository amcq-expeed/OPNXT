import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ChatMessage,
  createChatSession,
  listChatMessages,
  postChatMessage,
  putProjectContext,
  aiGenerateDocuments,
  generateDocuments,
  saveLeanSnapshot,
} from '../lib/api';

interface MVPChatProps {
  projectId: string;
  onDocumentsGenerated?: () => void;
  onOpenDocuments?: () => void;
  docCount?: number;
}

export default function MVPChat({ projectId, onDocumentsGenerated, onOpenDocuments, docCount = 0 }: MVPChatProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState<string>('');
  const [sending, setSending] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [generating, setGenerating] = useState<boolean>(false);
  const [assistantTyping, setAssistantTyping] = useState<boolean>(false);
  const [generationStages, setGenerationStages] = useState<string[]>([]);
  const [toast, setToast] = useState<{ type: 'error' | 'info'; message: string; actionLabel?: string; action?: () => void } | null>(null);
  const [generationProgress, setGenerationProgress] = useState<number>(0);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  const pushGenerationStage = (label: string, progress?: number) => {
    setGenerationStages(prev => [...prev, label]);
    if (typeof progress === 'number') {
      setGenerationProgress(Math.max(0, Math.min(1, progress)));
    }
  };

  useEffect(() => {
    // Auto-scroll when messages change
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }));
  }, [messages.length]);

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    const created = await createChatSession(projectId, 'MVP Chat');
    setSessionId(created.session_id);
    return created.session_id;
  }

  async function refreshMessages(sid: string) {
    try {
      const msgs = await listChatMessages(sid);
      setMessages(msgs);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  async function onNewChat() {
    if (!projectId) return;
    try {
      setError(null);
      setNotice(null);
      const created = await createChatSession(projectId, 'MVP Chat');
      setSessionId(created.session_id);
      setMessages([]);
      setDraft('');
      requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }));
      setNotice('Started a new chat.');
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  async function onSend(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    try {
      setSending(true);
      setAssistantTyping(true);
      setError(null);
      const sid = await ensureSession();
      // Optimistically append user message
      const now = new Date().toISOString();
      setMessages(prev => prev.concat([{ message_id: 'local-' + Math.random().toString(36).slice(2), session_id: sid, role: 'user', content: text, created_at: now }] as any));
      await postChatMessage(sid, text);
      const msgs = await listChatMessages(sid);
      setMessages(msgs);
      setDraft('');
      setNotice('Assistant replied.');
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setSending(false);
      setAssistantTyping(false);
    }
  }

  // --- Extract canonical SHALL requirements from chat ---
  const extractedShalls = useMemo(() => {
    const texts = messages.map(m => m.content).join('\n');
    return extractShallFromText(texts);
  }, [messages]);

  // --- Readiness heuristic for enabling Generate Docs (scored, conversational-first) ---
  const readiness = useMemo(() => computeReadiness(messages, extractedShalls), [messages, extractedShalls]);

  const targetBacklogCount = useMemo(() => {
    const totalChars = messages.reduce((n, m) => n + (m.content?.length || 0), 0);
    const base = Math.max(4, reqsCount(extractedShalls) * 2);
    const depth = Math.floor(totalChars / 350); // more chat -> more backlog
    const estimate = base + depth * 3;
    return Math.max(6, Math.min(estimate, 40)); // clamp to 6..40
  }, [messages, extractedShalls]);

  function reqsCount(arr: string[]) { return Array.isArray(arr) ? arr.length : 0; }

  function buildPromptFromConversation(reqs: string[], msgs: ChatMessage[], targetStories = targetBacklogCount): string {
    // Limit transcript for prompt budget
    const recent = msgs.slice(-25);
    const transcript = recent
      .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
      .join('\n');
    const reqBlock = reqs.length ? `Detected Canonical Requirements (SHALL):\n- ${reqs.join('\n- ')}` : 'No explicit SHALL items detected; infer from transcript.';
    return [
      'You are an SDLC documentation generator. Produce COMPLETE, PRODUCTION-READY artifacts for this initiative based ONLY on the information below.',
      '',
      'Deliverables (all required):',
      '- Project Charter (problem, objectives, scope, stakeholders, constraints, success metrics)',
      '- Software Requirements Specification (SRS) with FR/NFR, use cases, assumptions, constraints, glossary',
      '- Software Design Document (SDD) with high-level architecture, components, data model, integration points',
      '- Test Plan with strategy, test types, entry/exit, environments, traceability matrix mapping to requirements',
      '',
      'Guidelines:',
      '- Be specific and self-consistent; avoid placeholders.',
      '- Ground every section in the transcript and requirements; add reasonable assumptions if gaps exist.',
      "- Treat the 'Detected Canonical Requirements (SHALL)' as the authoritative list: include them in the SRS and ensure traceability into SDD and Test Plan.",
      '',
      reqBlock,
      'Conversation Transcript (most recent first within this window):',
      transcript
    ].join('\n\n');
  }

  async function onGenerateDocs(forceSnapshot = false) {
    if (!projectId) return;
    try {
      setGenerating(true);
      setError(null);
      setNotice('Applying requirements to Stored Context…');
      setGenerationStages([]);
      setGenerationProgress(0);
      pushGenerationStage('Applying requirements to Stored Context…', 0.25);
      setToast(null);
      // 1) Persist ONLY the current session's requirements (overwrite to avoid stale context)
      const payload = { data: { summaries: {}, answers: { Requirements: extractedShalls } } } as any;
      await putProjectContext(projectId, payload);

      // 2) Build prompt directly from the live conversation + detected requirements
      const prompt = buildPromptFromConversation(extractedShalls, messages);
      const runSnapshot = forceSnapshot || !readiness.ready;
      if (runSnapshot) {
        setNotice('Summarizing discovery findings…');
        pushGenerationStage('Preparing Lean Idea Validation Snapshot…', 0.65);
        const priorMessageCount = messages.length;
        const snapshot = buildLeanSnapshot(messages, extractedShalls, readiness);
        const now = new Date().toISOString();
        // Append snapshot as assistant message for immediate feedback
        setMessages(prev => prev.concat([{
          message_id: 'snapshot-' + Math.random().toString(36).slice(2),
          session_id: sessionId || 'snapshot',
          role: 'assistant',
          content: snapshot,
          created_at: now,
        } as any]));

        try {
          pushGenerationStage('Saving snapshot to project context…', 0.85);
          await saveLeanSnapshot(projectId, {
            markdown_content: snapshot,
            metadata: {
              source: 'mvp_chat',
              generated_at: now,
              message_count_before_snapshot: priorMessageCount,
              extracted_shalls: extractedShalls.length,
              readiness: {
                ready: readiness.ready,
                score: readiness.score,
                reason: readiness.reason,
                missing: readiness.missing,
              },
            },
          });
          setNotice('Lean Idea Validation Snapshot saved. Capture more detail when you want the full SDLC bundle.');
          pushGenerationStage('Snapshot saved.', 1);
        } catch (err: any) {
          if (process.env.NODE_ENV !== 'production') {
            console.error('Failed to persist Lean Snapshot', err);
          }
          setNotice('Snapshot ready locally. Saving to project context failed.');
          pushGenerationStage('Snapshot ready (not saved).', 1);
          setToast({
            type: 'error',
            message: 'Snapshot stored in chat, but persisting to project context failed. Try again later or copy the snapshot manually.',
          });
        }
      } else {
        setNotice('Generating documents via AI…');
        pushGenerationStage('Generating documents via AI…', 0.65);
        try {
          await aiGenerateDocuments(projectId, {
            input_text: prompt,
            include_backlog: true,
            doc_types: ['ProjectCharter', 'SRS', 'SDD', 'TestPlan']
          });
        } catch (e) {
          // Fallback to deterministic generator
          setNotice('AI unavailable, falling back to deterministic generator…');
          pushGenerationStage('AI unavailable, falling back to deterministic generator…', 0.8);
          const paste = [
            'Requirements (SHALL):',
            extractedShalls.map(s => '- ' + s).join('\n'),
            '',
            'Conversation Transcript:',
            messages.map(m => `${m.role}: ${m.content}`).join('\n')
          ].join('\n');
          await generateDocuments(projectId, {
            traceability_overlay: true,
            paste_requirements: paste,
            answers: { Requirements: extractedShalls } as any,
            summaries: {}
          });
        }
        setNotice('Generation complete.');
        pushGenerationStage('Generation complete.', 1);
        try { onDocumentsGenerated && onDocumentsGenerated(); } catch {}
      }
    } catch (e: any) {
      setError(e?.message || String(e));
      const msg = e?.message || 'Generation failed. Please try again.';
      pushGenerationStage(`Generation failed: ${msg}`);
      setGenerationProgress(0);
      setToast({
        type: 'error',
        message: msg,
        actionLabel: 'Retry',
        action: () => {
          setToast(null);
          onGenerateDocs();
        },
      });
    } finally {
      setGenerating(false);
      setTimeout(() => {
        setGenerationStages([]);
        setGenerationProgress(0);
      }, 4000);
    }
  }

  const readinessScore = Math.round(readiness.score || 0);
  const readinessPercent = Math.max(0, Math.min(100, readinessScore));
  const subtitle = messages.length === 0
    ? 'Share what you’re building, who it serves, and any constraints.'
    : readiness.ready
      ? 'Charter-ready. Review your notes, then generate the full PMO package when you’re confident.'
      : 'Discovery mode. Capture problem, audience, evidence, and blockers. Save a Lean Snapshot anytime for next steps.';
  const handleToastDismiss = () => setToast(null);
  const handleToastAction = () => {
    if (!toast || !toast.action) return;
    const action = toast.action;
    setToast(null);
    action();
  };

  return (
    <div className="mvp-chat">
      <p className="mvp-chat__subtitle">{subtitle}</p>

      <div className="mvp-chat__history" role="log" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 ? (
          <div className="mvp-chat__empty">
            <p>Describe your initiative, the teams or stakeholders involved, critical features, and any constraints like timelines or compliance. Mention integrations, data needs, or non-functional requirements so the assistant can shape stronger documentation.</p>
          </div>
        ) : (
          <ul className="mvp-chat__messages">
            {messages.map(m => (
              <li
                key={m.message_id}
                className={`msg-row ${m.role === 'user' ? 'msg-row--user' : 'msg-row--assistant'}`}
              >
                <div className={`msg ${m.role === 'user' ? 'msg-user' : 'msg-assistant'}`} aria-label={`${m.role} message`}>
                  {m.content}
                  <div className="msg-meta" style={{ textAlign: m.role === 'user' ? 'right' : 'left' }}>
                    {new Date(m.created_at).toLocaleTimeString()}
                  </div>
                </div>
              </li>
            ))}
            {assistantTyping && (
              <li className="msg-row msg-row--assistant">
                <div className="msg msg-assistant" aria-live="polite" aria-label="assistant typing">
                  <div className="typing-indicator" role="status">
                    <span className="typing-dots"><span /><span /><span /></span>
                    <span>Assistant is typing…</span>
                  </div>
                </div>
              </li>
            )}
          </ul>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mvp-chat__composer">
        <form className="mvp-chat__form" onSubmit={onSend}>
          <textarea
            className="textarea chat-input mvp-chat__textarea"
            aria-label="Your message"
            placeholder="Describe your idea or requirement… (Enter to send, Shift+Enter for newline)"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); } }}
          />
          <button type="submit" className="btn btn-primary mvp-chat__send" disabled={sending || !draft.trim()} aria-busy={sending}>{sending ? 'Sending…' : 'Send'}</button>
        </form>

        <div className="mvp-chat__meta">
          <div className="mvp-chat__readiness" role="group" aria-label="Readiness to generate documents">
            <div className="mvp-chat__readiness-header">
              <strong>Readiness to Generate</strong>
              <span className="mvp-chat__readiness-score">{readinessScore}%</span>
            </div>
            <div
              className="mvp-chat__readiness-bar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={readinessPercent}
            >
              <span style={{ width: `${readinessPercent}%` }} />
            </div>
            {!readiness.ready && (
              <p className="mvp-chat__hint">
                {readiness.reason} {Array.isArray(readiness.missing) && readiness.missing.length ? `Try adding ${readiness.missing.slice(0, 3).join(', ')}.` : ''}
              </p>
            )}
          </div>

          <div className="mvp-chat__actions">
            <button className="btn btn-primary" onClick={() => onGenerateDocs()} disabled={!readiness.ready || generating} aria-disabled={!readiness.ready || generating} aria-busy={generating}>
              {generating ? 'Generating…' : 'Generate Docs'}
            </button>
            {generating && (
              <div className="mvp-chat__status" aria-live="polite">
                <progress aria-label="Generating documents" />
                <span className="muted">Working on generation…</span>
              </div>
            )}
            {!readiness.ready && messages.length > 0 && (
              <>
                <span className="mvp-chat__hint" title={readiness.reason}>Gather more validation details to unlock full docs. You can still capture a Lean Snapshot now.</span>
                <button type="button" className="btn btn-secondary" onClick={() => onGenerateDocs(true)} disabled={generating}>
                  {generating ? 'Working…' : 'Create Lean Snapshot'}
                </button>
              </>
            )}
            <button type="button" className="btn mvp-chat__ghost" onClick={onNewChat} aria-label="Start new chat">New Chat</button>
            {notice && <span className="notice" aria-live="polite">{notice}</span>}
            {error && <span className="error" role="alert">{error}</span>}
          </div>
        </div>
      </div>

      {toast && (
        <div className="toast-stack" role="status" aria-live="polite">
          <div className={`toast toast-${toast.type}`}>
            <span className="grow">{toast.message}</span>
            {toast.actionLabel && toast.action && (
              <button type="button" onClick={handleToastAction}>{toast.actionLabel}</button>
            )}
            <button type="button" className="toast-dismiss" onClick={handleToastDismiss}>Dismiss</button>
          </div>
        </div>
      )}

      {/* Detected Requirements panel intentionally hidden for MVP-clean UI */}
    </div>
  );
}

function buildLeanSnapshot(
  messages: ChatMessage[],
  shalls: string[],
  readiness: { ready: boolean; reason: string; score: number; missing: string[] }
): string {
  const userMessages = messages.filter(m => m.role === 'user');
  const latestUser = userMessages.length ? userMessages[userMessages.length - 1].content.trim() : '';
  const firstUser = userMessages.length ? userMessages[0].content.trim() : '';
  const conceptSource = latestUser || firstUser;
  const conceptSummary = conceptSource
    ? conceptSource.split(/\n+/).map(s => s.trim()).filter(Boolean).slice(0, 2).join(' ')
    : 'Idea still forming — capture the problem, audience, and envisioned solution.';

  const userText = userMessages.map(m => (m.content || '').toLowerCase()).join(' ');
  const signals: string[] = [];
  if (/(interview|customer discovery|user research|survey)/.test(userText)) {
    signals.push('Customer discovery activities referenced.');
  }
  if (/(waitlist|signup|beta|pilot|demo|prototype|poc)/.test(userText)) {
    signals.push('Early adoption signal (waitlist/beta/prototype) mentioned.');
  }
  if (/(revenue|pricing|paid|contract|invoice|subscription)/.test(userText)) {
    signals.push('Monetisation evidence or pricing exploration noted.');
  }
  if (/(partner|integration|loi|memorandum|channel)/.test(userText)) {
    signals.push('Partnership or integration interest highlighted.');
  }
  if (!signals.length) {
    signals.push('No validation signals captured yet. Focus on interviews, signups, or prototype feedback.');
  }

  const missingKeys = Array.isArray(readiness.missing) ? readiness.missing : [];
  const unknownMap: Record<string, string> = {
    'stakeholders/users': 'Stakeholders, personas, or buyers not clearly identified.',
    'scope/objectives': 'Value proposition, success metrics, or boundaries remain unclear.',
    'NFRs (performance/security)': 'Non-functional expectations (e.g., performance, security, compliance) still unknown.',
    'constraints/risks': 'Constraints, risks, or assumptions not documented.',
    'UI/API/integrations': 'Interfaces, integrations, or touchpoints not described yet.',
    'testing/acceptance': 'Acceptance criteria or validation tests not articulated.',
    'data model/retention': 'Data flows, retention, or schema considerations missing.',
    'clear requirements (SHALL)': 'Concrete requirements not yet articulated as SHALL statements.'
  };
  const criticalUnknowns = missingKeys.map(m => unknownMap[m] || `${m} still needs clarification.`);
  if (!criticalUnknowns.length) {
    criticalUnknowns.push('Key uncertainties resolved — ready to formalize when you choose.');
  }

  const experimentTemplates: Record<string, { experiment: string; goal: string; owner: string; timeframe: string }> = {
    'stakeholders/users': {
      experiment: 'Stakeholder interviews (5 conversations)',
      goal: 'Validate primary personas and pains',
      owner: 'Founder / Product Lead',
      timeframe: '1-2 weeks'
    },
    'scope/objectives': {
      experiment: 'Success metrics workshop',
      goal: 'Quantify KPIs and MVP boundaries',
      owner: 'Product + Sponsor',
      timeframe: '1 week'
    },
    'NFRs (performance/security)': {
      experiment: 'NFR & compliance spike',
      goal: 'Document performance/security baselines',
      owner: 'Tech Lead / Security',
      timeframe: '1 week'
    },
    'constraints/risks': {
      experiment: 'Risk and constraint mapping',
      goal: 'Surface budget, timeline, and regulatory concerns',
      owner: 'Project Sponsor',
      timeframe: '1 week'
    },
    'UI/API/integrations': {
      experiment: 'Integration touchpoint sketching',
      goal: 'Outline key interfaces and data exchanges',
      owner: 'Product + Engineering',
      timeframe: '1 week'
    },
    'testing/acceptance': {
      experiment: 'Acceptance criteria drafting session',
      goal: 'Define how success will be validated',
      owner: 'QA / Product',
      timeframe: '3-5 days'
    },
    'data model/retention': {
      experiment: 'Data model whiteboarding',
      goal: 'Clarify entities, retention, and compliance needs',
      owner: 'Engineering',
      timeframe: '1 week'
    },
    'clear requirements (SHALL)': {
      experiment: 'Requirement refinement workshop',
      goal: 'Draft 5-7 canonical SHALL statements',
      owner: 'Product + Engineering',
      timeframe: '3-5 days'
    }
  };

  const experiments = missingKeys
    .map(key => experimentTemplates[key])
    .filter(Boolean) as { experiment: string; goal: string; owner: string; timeframe: string }[];
  if (!experiments.length) {
    experiments.push(
      {
        experiment: 'Customer validation interviews',
        goal: 'Validate problem urgency and willingness to pay',
        owner: 'Founder / Product Lead',
        timeframe: '1-2 weeks'
      },
      {
        experiment: 'MVP scope checkpoint',
        goal: 'Agree on top 3 capabilities and success metrics',
        owner: 'Product + Sponsor',
        timeframe: '1 week'
      }
    );
  }

  const checklistItems = [
    { label: 'Executive sponsor identified', key: 'stakeholders/users' },
    { label: 'Top 3 capabilities prioritised', key: 'scope/objectives' },
    { label: 'Success metrics (KPIs) defined', key: 'scope/objectives' },
    { label: 'Constraints / risks documented', key: 'constraints/risks' },
    { label: 'Non-functional requirements captured', key: 'NFRs (performance/security)' },
    { label: 'Compliance / privacy considerations assessed', key: 'NFRs (performance/security)' },
    { label: 'Acceptance / test strategy outlined', key: 'testing/acceptance' }
  ];
  const missingSet = new Set(missingKeys);
  const readinessChecklist = checklistItems.map(item => `${missingSet.has(item.key) ? '- [ ]' : '- [x]'} ${item.label}`);

  const requirementsBlock = shalls.length
    ? ['## Detected Requirements (SHALL)', ...shalls.map(s => `- ${s}`)].join('\n')
    : '';

  const nowIso = new Date().toISOString();

  return [
    '# Lean Idea Validation Snapshot',
    `Generated: ${nowIso}`,
    '',
    '## Concept Summary',
    conceptSummary,
    '',
    '## Validation Signals',
    signals.map(s => `- ${s}`).join('\n'),
    '',
    '## Critical Unknowns',
    criticalUnknowns.map(u => `- ${u}`).join('\n'),
    '',
    '## Recommended Next Experiments',
    '| Experiment | Goal | Owner | Timeframe |',
    '| --- | --- | --- | --- |',
    experiments.map(e => `| ${e.experiment} | ${e.goal} | ${e.owner} | ${e.timeframe} |`).join('\n'),
    '',
    '## Readiness Checklist',
    readinessChecklist.join('\n'),
    '',
    requirementsBlock
  ].filter(Boolean).join('\n');
}

function extractShallFromText(text: string): string[] {
  const out: string[] = [];
  const lines = text.split(/\r?\n/);
  for (const ln of lines) {
    const cleanedLine = ln.trim().replace(/^[-*•\d.\)\s]+/, '').trim();
    if (!cleanedLine) continue;
    const sentences = cleanedLine
      .split(/(?<=[.!?])\s+|\s*;\s+|(?<!\w)\s*-\s+(?=\w)/)
      .map(s => s.trim())
      .filter(Boolean);
    for (let s of sentences) {
      let t = s.trim();
      if (t.length < 6) continue;
      if (/^(note|summary|context)[:\s]/i.test(t)) continue;

      // Handle "As a ..., I want to ..." style
      const asMatch = t.match(/^As\s+a[n]?\s+[^,]+,\s*I\s+want\s+to\s+(.+?)(?:\s+so\s+that.*)?$/i);
      if (asMatch) {
        t = asMatch[1].trim();
      }

      // Strip subjects + modals (the system|system|we|it) + (shall|should|must|will|needs to|need to)
      const modal = t.match(/^(?:the\s+system|system|we|it)\s+(?:shall|should|must|will|needs?\s+to|need\s+to)\s+(.*)$/i);
      if (modal) {
        t = modal[1].trim();
      }

      // Remove leading infinitive markers
      t = t.replace(/^(?:to\s+|be\s+able\s+to\s+)/i, '');

      // If sentence already uses SHALL, normalize and keep
      if (/\bshall\b/i.test(s)) {
        let keep = s.replace(/^the\s+system\s+shall/i, 'The system SHALL');
        if (!/[.!?]$/.test(keep)) keep += '.';
        out.push(keep);
        continue;
      }

      // Otherwise, construct canonical SHALL
      if (!/[.!?]$/.test(t)) t += '.';
      const clause = t.charAt(0).toUpperCase() + t.slice(1);
      let composed = `The system SHALL ${clause}`;
      composed = composed.replace(/^The system SHALL\s+(?:The\s+system\s+shall\s+)/i, 'The system SHALL ');
      out.push(composed);
    }
  }
  const seen = new Set<string>();
  const uniq: string[] = [];
  for (const r of out) { const rr = r.trim(); if (rr && !seen.has(rr)) { seen.add(rr); uniq.push(rr); } }
  return uniq;
}

function computeReadiness(messages: ChatMessage[], shalls: string[]): { ready: boolean; reason: string; score: number; missing: string[] } {
  const userCount = messages.filter(m => m.role === 'user').length;
  const totalChars = messages.reduce((n, m) => n + (m.content?.length || 0), 0);
  const allText = messages.map(m => m.content).join('\n');
  const hasStakeholders = /(stakeholder|user(?:s)?|persona|customer|admin|operator)/i.test(allText);
  const hasScope = /(scope|objective|goal|outcome|success|kpi|metric)/i.test(allText);
  const hasNFR = /(nfr|non[- ]?functional|performance|latency|throughput|availability|reliability|security|compliance|gdpr|hipaa)/i.test(allText);
  const hasConstraints = /(constraint|assumption|risk|limitation|budget|timeline|deadline)/i.test(allText);
  const hasInterface = /(\bui\b|ux|screen|page|api|endpoint|integration|webhook)/i.test(allText);
  const hasTesting = /(test|qa|acceptance\s*criteria|traceability)/i.test(allText);
  const hasData = /(data\s*model|schema|database|storage|retention|index)/i.test(allText);
  // Q&A loop detection
  let qaLoop = false;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'assistant' && /\?/.test(m.content || '')) {
      qaLoop = messages.slice(i + 1).some(x => x.role === 'user' && (x.content || '').trim().length >= 20);
      break;
    }
  }
  let score = 0; const missing: string[] = [];
  if (shalls.length >= 5) score += 25; else if (shalls.length >= 3) score += 20; else if (shalls.length >= 1) score += 10; else missing.push('clear requirements (SHALL)');
  if (hasStakeholders) score += 15; else missing.push('stakeholders/users');
  if (hasScope) score += 15; else missing.push('scope/objectives');
  if (hasNFR) score += 10; else missing.push('NFRs (performance/security)');
  if (hasConstraints) score += 10; else missing.push('constraints/risks');
  if (hasInterface) score += 10; else missing.push('UI/API/integrations');
  if (hasTesting) score += 5; else missing.push('testing/acceptance');
  if (hasData) score += 5; else missing.push('data model/retention');
  if (userCount >= 2) score += 10;
  if (userCount >= 3) score += 10;
  if (totalChars >= 400) score += 10;
  if (qaLoop) score += 10;
  if (score > 100) score = 100;
  const ready = score >= 60;
  const reason = ready ? `Ready (score ${score}).` : `Readiness ${score}%. Keep chatting to cover gaps.`;
  return { ready, reason, score, missing };
}
