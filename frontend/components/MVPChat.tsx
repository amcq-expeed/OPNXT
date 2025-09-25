import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ChatMessage,
  createChatSession,
  listChatMessages,
  postChatMessage,
  getProjectContext,
  putProjectContext,
  aiGenerateDocuments,
  generateDocuments,
  ProjectContext,
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

  async function onGenerateDocs() {
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
      const ctx = await getProjectContext(projectId).catch(() => ({ data: {} } as any));
      const data: any = (ctx && (ctx as any).data) ? { ...(ctx as any).data } : {};
      // Reset summaries and keep only current Requirements to prevent stale context
      const payload = { data: { summaries: {}, answers: { Requirements: extractedShalls } } } as any;
      await putProjectContext(projectId, payload);

      // 2) Build prompt directly from the live conversation + detected requirements
      const prompt = buildPromptFromConversation(extractedShalls, messages);
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

  return (
    <div style={{ maxWidth: 860, margin: '0 auto' }}>
      {/* Header: Chat title + Documents badge (only when documents exist) */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div className="section-title" style={{ marginBottom: 0 }}>Chat</div>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <button type="button" className="btn" onClick={onNewChat} aria-label="Start new chat">New Chat</button>
        </div>
      </div>
      {/* Chat viewport: hidden until there are messages for a clean landing view */}
      {messages.length > 0 && (
        <div className="chat-box" style={{ height: '65vh', paddingBottom: 8 }}>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {messages.map(m => (
              <li key={m.message_id} className="msg-row" style={{ justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div className={`msg ${m.role === 'user' ? 'msg-user' : 'msg-assistant'}`} aria-label={`${m.role} message`}>
                  {m.content}
                  <div className="msg-meta" style={{ textAlign: m.role === 'user' ? 'right' : 'left' }}>
                    {new Date(m.created_at).toLocaleTimeString()}
                  </div>
                </div>
              </li>
            ))}
            {assistantTyping && (
              <li className="msg-row" style={{ justifyContent: 'flex-start' }}>
                <div className="msg msg-assistant" aria-live="polite" aria-label="assistant typing">
                  <div className="typing-indicator" role="status">
                    <span className="typing-dots"><span /><span /><span /></span>
                    <span>Assistant is typing…</span>
                  </div>
                </div>
              </li>
            )}
            <div ref={bottomRef} />
          </ul>
        </div>
      )}

      {/* Composer + Actions (sticky bottom) */}
      <div className="sticky-bottom">
        <form onSubmit={onSend} style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginTop: 8 }}>
          <textarea
            className="textarea chat-input"
            aria-label="Your message"
            placeholder="Describe your idea or requirement… (Enter to send, Shift+Enter for newline)"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            style={{ flex: 1, resize: 'none' }}
          />
          <button type="submit" className="btn btn-primary" disabled={sending || !draft.trim()} aria-busy={sending}>{'Send'}</button>
        </form>

        {/* Readiness meter */}
        <div className="card" style={{ marginTop: 10, padding: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <strong>Readiness to Generate</strong>
            <span className="muted">{Math.round(readiness.score || 0)}%</span>
          </div>
          <div aria-label="Readiness progress" style={{ height: 8, background: 'var(--border)', borderRadius: 4, overflow: 'hidden', marginTop: 6 }}>
            <div style={{ width: `${Math.max(0, Math.min(100, Math.round(readiness.score || 0)))}%`, height: '100%', background: 'var(--primary)', transition: 'width 0.3s ease' }} />
          </div>
          {!readiness.ready && (
            <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
              {readiness.reason} {Array.isArray(readiness.missing) && readiness.missing.length ? `Hint: add ${readiness.missing.slice(0,3).join(', ')}.` : ''}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10, justifyContent: 'flex-start' }}>
          <button className="btn btn-primary" onClick={onGenerateDocs} disabled={!readiness.ready || generating} aria-disabled={!readiness.ready} aria-busy={generating}>
            {generating ? 'Generating…' : 'Generate Docs'}
          </button>
          {generating && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }} aria-live="polite">
              <progress aria-label="Generating documents" />
              <span className="muted">Working on generation…</span>
            </div>
          )}
          {!readiness.ready && messages.length > 0 && (
            <span className="muted" title={readiness.reason}>Keep chatting to improve readiness.</span>
          )}
          {notice && <span className="notice" aria-live="polite">{notice}</span>}
          {error && <span className="error" role="alert">{error}</span>}
        </div>
      </div>

      

      {/* Detected Requirements panel intentionally hidden for MVP-clean UI */}
    </div>
  );
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
