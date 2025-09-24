import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Project, DocGenResponse, getProject, generateDocuments, artifactUrl, zipUrl, enrichProject, EnrichResponse, getProjectContext, putProjectContext, computeImpacts, ImpactResponse, ProjectContext, listDocumentVersions, getDocumentVersion, DocumentVersionsResponse, aiGenerateDocuments, diagLLM, DiagLLM, analyzeUploads, applyUploadRequirements, UploadAnalyzeResponse } from "../../lib/api";
import Tabs from "../../components/Tabs";
import ChatPanel from "../../components/ChatPanel";
import NextAction from "../../components/ui/NextAction";
import Stat from "../../components/ui/Stat";
import Stepper from "../../components/ui/Stepper";

export default function ProjectDetailsPage() {
  const router = useRouter();
  const id = typeof router.query.id === "string" ? router.query.id : "";

  const [project, setProject] = useState<Project | null>(null);
  const [docs, setDocs] = useState<DocGenResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Auto-clear notices after a short delay and when tab changes
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    // Clear banner when switching tabs via query
    setNotice(null);
  }, [router.query.tab]);

  // Chat/Paste requirements UX state
  const [promptText, setPromptText] = useState<string>("");
  const requirementsRef = useRef<HTMLTextAreaElement | null>(null);
  const [enriching, setEnriching] = useState<boolean>(false);
  const [overlayOn, setOverlayOn] = useState<boolean>(false);
  const [enriched, setEnriched] = useState<EnrichResponse | null>(null);

  // Design Q&A (Open Questions in SDD)
  const [designQuestions, setDesignQuestions] = useState<string[]>([]);
  const [designAnswers, setDesignAnswers] = useState<Record<number, string>>({});
  const [qaNotice, setQaNotice] = useState<string | null>(null);
  const [designGenerating, setDesignGenerating] = useState<boolean>(false);

  // Stored Context state
  const [ctx, setCtx] = useState<ProjectContext | null>(null);
  const [ctxPlanning, setCtxPlanning] = useState<string>("");
  const [ctxRequirements, setCtxRequirements] = useState<string>("");
  const [savingCtx, setSavingCtx] = useState<boolean>(false);
  // Approvals (persisted in ctx.data.approvals)
  const [approvals, setApprovals] = useState<Record<string, { approved: boolean; approved_at?: string }>>({});

  // Impact analysis state
  const [frInput, setFrInput] = useState<string>("");
  const [impacts, setImpacts] = useState<ImpactResponse | null>(null);
  const [analyzing, setAnalyzing] = useState<boolean>(false);

  // Versioning state
  const [versions, setVersions] = useState<DocumentVersionsResponse | null>(null);
  const [previewVersion, setPreviewVersion] = useState<{ filename: string; version: number } | null>(null);

  // AI generation options
  const [docTypes, setDocTypes] = useState<string[]>(["Project Charter", "SRS", "SDD", "Test Plan"]);
  const [includeBacklog, setIncludeBacklog] = useState<boolean>(false);
  const [llmDiag, setLlmDiag] = useState<DiagLLM | null>(null);
  // Scenario chips → prefill chat input
  const [chipPrefill, setChipPrefill] = useState<string | undefined>(undefined);
  const scenarioChips = useMemo(() => [
    'Healthcare Appointment System',
    'Bank Payment Platform',
    'E-commerce Store',
    'Custom Application',
  ], []);

  // Upload analysis state
  const [uploadResult, setUploadResult] = useState<UploadAnalyzeResponse | null>(null);
  const [uploadReqs, setUploadReqs] = useState<string[]>([]);
  const [uploadSel, setUploadSel] = useState<Record<string, boolean>>({});
  const [uploadBusy, setUploadBusy] = useState<boolean>(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  // Read ?prefill= from URL once to seed ChatPanel
  useEffect(() => {
    const p = typeof router.query.prefill === 'string' ? router.query.prefill : undefined;
    if (p && !chipPrefill) {
      try { setChipPrefill(decodeURIComponent(p)); }
      catch { setChipPrefill(p); }
    }
  }, [router.query.prefill]);

  // Derived overview metrics
  const answers = useMemo(() => (ctx as any)?.data?.answers || {}, [ctx]);
  const reqCount = useMemo(() => Array.isArray(answers?.Requirements) ? answers.Requirements.length : 0, [answers]);
  const charterApproved = !!approvals?.["ProjectCharter.md"]?.approved;
  const srsApproved = !!approvals?.["SRS.md"]?.approved;
  const sddApproved = !!approvals?.["SDD.md"]?.approved;
  const testApproved = !!approvals?.["TestPlan.md"]?.approved;
  const approvedCount = useMemo(() => Object.values(approvals || {}).filter(a => a?.approved).length, [approvals]);
  const docCount = useMemo(() => {
    if (docs?.artifacts) return docs.artifacts.length;
    return Object.keys(versions?.versions || {}).length;
  }, [docs, versions]);
  const currentIndex = useMemo(() => {
    let idx = 0; // Charter
    if (charterApproved) idx = 1; // Requirements
    if (reqCount > 0) idx = 2; // Specifications
    if (srsApproved) idx = 3; // Design
    if (sddApproved) idx = 4; // Implementation
    if (testApproved) idx = 6; // Deployment
    return idx;
  }, [charterApproved, reqCount, srsApproved, sddApproved, testApproved]);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        setNotice(null);
        // If unauthenticated, bounce to login with returnTo
        if (typeof window !== 'undefined') {
          // naive check: API call will fail if unauthorized, but check token first for faster UX
          const token = (typeof window !== 'undefined') ? window.localStorage.getItem('opnxt_token') : null;
          if (!token) {
            const rt = encodeURIComponent(window.location.pathname + window.location.search);
            window.location.href = `/login?returnTo=${rt}`;
            return;
          }
        }
        const p = await getProject(id);
        setProject(p);
        // Do not auto-load existing document contents on landing; show empty state until user acts
        // Load version metadata
        try {
          const v = await listDocumentVersions(id);
          setVersions(v);
        } catch {}
        // Fetch stored context
        try {
          const c = await getProjectContext(id);
          setCtx(c);
          const data = (c && c.data) || {} as any;
          const planning = (data.summaries && data.summaries.Planning) || "";
          const reqs = (data.answers && data.answers.Requirements) || [];
          setCtxPlanning(String(planning || ""));
          setCtxRequirements(Array.isArray(reqs) ? reqs.join("\n") : "");
          const aps = (data.approvals && typeof data.approvals === 'object') ? data.approvals : {};
          setApprovals(aps);
        } catch {}
      } catch (e: any) {
        setError(e?.message || String(e));
        if (typeof window !== 'undefined') {
          const rt = encodeURIComponent(window.location.pathname + window.location.search);
          window.location.href = `/login?returnTo=${rt}`;
        }
      } finally {
        setLoading(false);
      }

    })();
  }, [id]);

  async function loadLatestDocs() {
    if (!id) return;
    try {
      const v = await listDocumentVersions(id);
      setVersions(v);
      const files = Object.keys(v.versions || {});
      if (files.length === 0) { setDocs(null); setSelected(null); return; }
      const artifacts: { filename: string; content: string }[] = [];
      for (const fname of files) {
        const list = v.versions[fname] || [];
        const latest = list.length ? list[list.length - 1].version : undefined;
        if (latest === undefined) continue;
        const dv = await getDocumentVersion(id, fname, latest);
        artifacts.push({ filename: dv.filename, content: dv.content });
      }
      const resp = { project_id: id, artifacts } as DocGenResponse;
      setDocs(resp);
      if (artifacts.length > 0) setSelected(artifacts[0].filename);
    } catch (e: any) {
      // Non-fatal: show empty state; generation can be triggered manually
      setDocs(null);
      setSelected(null);
    }
  }

  const selectedArtifact = useMemo(
    () => {
      if (!docs) return null;
      const direct = docs.artifacts.find(a => a.filename === selected) || null;
      return direct;
    },
    [docs, selected]
  );

  const sddArtifact = useMemo(
    () => {
      if (!docs) return null;
      return docs.artifacts.find(a => /sdd/i.test(a.filename)) || null;
    },
    [docs]
  );

  const testPlanArtifact = useMemo(
    () => {
      if (!docs) return null;
      return docs.artifacts.find(a => /test\s*plan/i.test(a.filename)) || null;
    },
    [docs]
  );

  // Parse Open Questions from SDD content
  useEffect(() => {
    const content = sddArtifact?.content || '';
    if (!content) { setDesignQuestions([]); return; }
    function extractOpenQuestionsFromMarkdown(md: string): string[] {
      const lines = md.split(/\r?\n/);
      let idx = -1;
      for (let i = 0; i < lines.length; i++) {
        if (/\bOpen\s*Questions\b/i.test(lines[i])) { idx = i; break; }
      }
      if (idx < 0) return [];
      const qs: string[] = [];
      // Capture inline question(s) on the same line, e.g., "... Open Questions: What ...?"
      const sameLine = lines[idx];
      const inline = sameLine.replace(/^.*\bOpen\s*Questions\b\s*[:\-–—]?\s*/i, '').trim();
      if (inline) {
        // Split by typical delimiters if multiple questions present
        const parts = inline.split(/(?<=\?)\s+|;\s+/).map(s => s.trim()).filter(Boolean);
        for (const p of parts) {
          const q = p.endsWith('?') ? p : (p ? p + '?' : '');
          if (q) qs.push(q);
        }
      }
      // Capture following bullet/lines until next heading
      for (let i = idx + 1; i < lines.length; i++) {
        const ln = lines[i];
        if (/^\s*#{1,6}\s+/.test(ln)) break; // next markdown heading
        const m = ln.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
        const txt = (m ? m[1] : ln).trim();
        if (!txt) continue;
        // Accept explicit Q: prefix or question mark
        let q = txt.replace(/^Q[:\s-]+/i, '').trim();
        if (!q) continue;
        if (!/[?]$/.test(q)) q += '?';
        qs.push(q);
      }
      // Deduplicate, keep order
      const seen = new Set<string>();
      const uniq: string[] = [];
      for (const q of qs) { if (!seen.has(q)) { seen.add(q); uniq.push(q); } }
      return uniq;
    }
    setDesignQuestions(extractOpenQuestionsFromMarkdown(content));
  }, [sddArtifact?.content]);

  function onAnswerChange(idx: number, value: string) {
    setDesignAnswers(prev => ({ ...prev, [idx]: value }));
  }

  async function applyDesignAnswersToContext() {
    if (!id) return;
    const answered = designQuestions
      .map((q, i) => ({ q, a: (designAnswers[i] || '').trim() }))
      .filter(x => x.a.length > 0);
    if (answered.length === 0) { setQaNotice('Add at least one answer to apply.'); return; }
    try {
      setQaNotice(null);
      const current = await getProjectContext(id);
      const data: any = (current && current.data) ? { ...current.data } : {};
      const answers: Record<string, any> = Array.isArray(data.answers) ? {} : (data.answers || {});
      const existing: string[] = Array.isArray(answers['Design Answers']) ? answers['Design Answers'] : [];
      const merged = existing.slice();
      for (const item of answered) {
        const entry = `Q: ${item.q}\nA: ${item.a}`;
        if (!merged.includes(entry)) merged.push(entry);
      }
      const payload = { data: { ...data, answers: { ...answers, 'Design Answers': merged } } } as any;
      await putProjectContext(id, payload);
      setQaNotice(`Applied ${answered.length} answer(s) to Stored Context.`);
    } catch (e: any) {
      setQaNotice(e?.message || String(e));
    }
  }

  async function applyAndGenerateFromDesign() {
    try {
      setDesignGenerating(true);
      await applyDesignAnswersToContext();
      await onAIGenerateSmart();
    } finally {
      setDesignGenerating(false);
    }
  }

  function discussInChat(question: string) {
    try {
      setChipPrefill(`Open Question from SDD: ${question}\nMy answer/thoughts: `);
    } catch {}
    try { router.push(`/projects/${id}?tab=Requirements`); } catch {}
  }

  async function onUploadFilesChanged(list: FileList | null) {
    if (!id || !list || list.length === 0) return;
    const files = Array.from(list);
    try {
      setUploadBusy(true);
      setUploadMsg(null);
      const resp = await analyzeUploads(id, files);
      setUploadResult(resp);
      const all = Array.from(new Set((resp.items || []).flatMap(it => it.requirements || [])));
      setUploadReqs(all);
      const map: Record<string, boolean> = {};
      all.forEach(r => map[r] = true);
      setUploadSel(map);
      setUploadMsg(`Analyzed ${files.length} file(s); found ${all.length} requirement(s).`);
    } catch (e: any) {
      setUploadMsg(e?.message || String(e));
    } finally {
      setUploadBusy(false);
    }
  }

  async function onApplyFromUploads(generate: boolean) {
    if (!id) return;
    const selected = uploadReqs.filter(r => uploadSel[r]);
    if (selected.length === 0) { setUploadMsg('Select at least one requirement to apply.'); return; }
    try {
      setUploadBusy(true);
      setUploadMsg(null);
      await applyUploadRequirements(id, { requirements: selected, category: 'Requirements', append_only: true });
      setUploadMsg(`Applied ${selected.length} requirement(s) to Stored Context.`);
      if (generate) {
        await onAIGenerateSmart();
      }
    } catch (e: any) {
      setUploadMsg(e?.message || String(e));
    } finally {
      setUploadBusy(false);
    }
  }

  async function onRegenerate() {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const resp = await generateDocuments(id, { traceability_overlay: overlayOn });
      setDocs(resp);
      if (resp.artifacts.length > 0) {
        const keep = selected && resp.artifacts.find(a => a.filename === selected);
        setSelected(keep ? keep.filename : resp.artifacts[0].filename);
      }
      setNotice(`Generated ${resp.artifacts.length} documents.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // Convenience: generate backlog with AI option enabled
  async function onGenerateBacklogSmart() {
    try {
      setIncludeBacklog(true);
      await onAIGenerateSmart();
    } finally {
      // keep includeBacklog on for subsequent runs
    }
  }

  // Regenerate only the SDD using AI and keep other artifacts intact
  async function onAIGenerateSDD() {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const latest = await getProjectContext(id);
      setCtx(latest);
      const prompt = buildSmartPrompt(latest);
      const req: any = { input_text: prompt, include_backlog: includeBacklog, doc_types: ['SDD'] };
      const resp = await aiGenerateDocuments(id, req);
      setDocs(prev => {
        const others = (prev?.artifacts || []).filter(a => !/sdd/i.test(a.filename));
        return { project_id: id, artifacts: [...others, ...resp.artifacts] } as DocGenResponse;
      });
      const sdd = resp.artifacts.find(a => /sdd/i.test(a.filename));
      if (sdd) setSelected(sdd.filename);
      setNotice('AI-generated SDD.');
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  function isApproved(filename: string): boolean {
    return !!approvals?.[filename]?.approved;
  }

  async function setApproval(filename: string, approved: boolean) {
    if (!id) return;
    try {
      const current = await getProjectContext(id);
      const data: any = (current && current.data) ? { ...current.data } : {};
      const aps: Record<string, { approved: boolean; approved_at?: string }> = (data.approvals && typeof data.approvals === 'object') ? { ...data.approvals } : {};
      aps[filename] = { approved, approved_at: new Date().toISOString() };
      const payload = { data: { ...data, approvals: aps } } as any;
      await putProjectContext(id, payload);
      setApprovals(aps);
      setNotice(approved ? `Approved ${filename}` : `Unapproved ${filename}`);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  async function onPreviewVersion(fname: string, version: number) {
    if (!id) return;
    try {
      setError(null);
      const v = await getDocumentVersion(id, fname, version);
      // Create a transient artifact for preview
      const artifact = { filename: v.filename, content: v.content };
      // Replace or add to docs preview state without altering saved files
      setDocs(prev => {
        const base = prev || { project_id: id, artifacts: [] } as any;
        const others = (base.artifacts || []).filter((a: any) => a.filename !== v.filename);
        return { ...base, artifacts: [...others, artifact] };
      });
      setSelected(v.filename);
      setPreviewVersion({ filename: v.filename, version: v.version });
      setNotice(`Previewing ${v.filename} v${v.version}`);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  async function onEnrich() {
    if (!id || !promptText.trim()) return;
    try {
      setEnriching(true);
      setError(null);
      const resp = await enrichProject(id, promptText.trim());
      setEnriched(resp);
      setNotice("Content enriched.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setEnriching(false);
    }
  }

  async function onGenerateWithInputs() {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const opts: any = { traceability_overlay: overlayOn };
      if (enriched && (Object.keys(enriched.answers || {}).length > 0 || Object.keys(enriched.summaries || {}).length > 0)) {
        opts.answers = enriched.answers;
        opts.summaries = enriched.summaries;
      } else if (promptText.trim()) {
        opts.paste_requirements = promptText.trim();
      }
      const resp = await generateDocuments(id, opts);
      setDocs(resp);
      if (resp.artifacts.length > 0) setSelected(resp.artifacts[0].filename);
      setNotice(`Generated ${resp.artifacts.length} documents.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onAIGenerate() {
    if (!id || !promptText.trim()) return;
    try {
      setLoading(true);
      setError(null);
      const req: any = { input_text: promptText.trim(), include_backlog: includeBacklog };
      if (docTypes && docTypes.length > 0 && docTypes.length < 4) req.doc_types = docTypes.slice();
      const resp = await aiGenerateDocuments(id, req);
      setDocs(resp);
      if (resp.artifacts.length > 0) {
        const keep = selected && resp.artifacts.find(a => a.filename === selected);
        setSelected(keep ? keep.filename : resp.artifacts[0].filename);
      }
      setNotice(`AI-generated ${resp.artifacts.length} documents.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  function buildSmartPrompt(overrideCtx?: ProjectContext | null): string {
    // 1) Prefer explicit text from builder
    const fromBuilder = promptText.trim();
    if (fromBuilder) return fromBuilder;

    // 2) If enriched content exists, synthesize a prompt
    if (enriched && (Object.keys(enriched.answers || {}).length > 0 || Object.keys(enriched.summaries || {}).length > 0)) {
      const planning = enriched.summaries?.Planning || '';
      const reqs = (enriched.answers?.Requirements || []).filter(Boolean);
      const lines = [
        planning ? `Planning Summary:\n${planning}` : '',
        reqs.length ? `Requirements:\n- ${reqs.join('\n- ')}` : '',
      ].filter(Boolean);
      if (lines.length) return lines.join('\n\n');
    }

    // 3) Fallback to Stored Context
    const sourceCtx = overrideCtx ?? ctx;
    const data: any = sourceCtx?.data || {};
    const planning = data?.summaries?.Planning || '';
    const reqs: string[] = Array.isArray(data?.answers?.Requirements) ? data.answers.Requirements : [];
    const parts = [
      planning ? `Planning Summary:\n${planning}` : '',
      reqs.length ? `Requirements:\n- ${reqs.join('\n- ')}` : '',
    ].filter(Boolean);
    // Include Design Q&A if present
    const answered = designQuestions
      .map((q, i) => ({ q, a: (designAnswers[i] || '').trim() }))
      .filter(x => x.a.length > 0);
    if (answered.length) {
      const qa = answered.map(x => `Q: ${x.q}\nA: ${x.a}`).join('\n\n');
      parts.push(`Design Q&A:\n${qa}`);
    }
    if (parts.length) return parts.join('\n\n');

    // 4) Last resort default
    return 'Generate the standard documents (Project Charter, SRS, SDD, Test Plan) for this project based on current context.';
  }

  async function onAIGenerateSmart() {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      // Refresh context to include any recent ChatPanel applies
      const latest = await getProjectContext(id);
      setCtx(latest);
      const prompt = buildSmartPrompt(latest);
      const req: any = { input_text: prompt, include_backlog: includeBacklog };
      if (docTypes && docTypes.length > 0 && docTypes.length < 4) req.doc_types = docTypes.slice();
      const resp = await aiGenerateDocuments(id, req);
      setDocs(resp);
      if (resp.artifacts.length > 0) setSelected(resp.artifacts[0].filename);
      setNotice(`AI-generated ${resp.artifacts.length} documents.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onCheckLLM() {
    try {
      const d = await diagLLM();
      setLlmDiag(d);
      setNotice(`LLM: provider=${d.provider}, model=${d.model}, ready=${d.ready}`);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  async function onSaveContext() {
    if (!id) return;
    try {
      setSavingCtx(true);
      const answers: Record<string, string[]> = {};
      const summaries: Record<string, string> = {};
      const reqs = ctxRequirements.split(/\r?\n/).map(s => s.trim()).filter(Boolean).map(s => {
        const lower = s.toLowerCase();
        if (lower.startsWith("the system shall") || lower.startsWith("shall ") || lower.startsWith("system shall")) return s;
        return `The system SHALL ${s}.`;
      });
      if (reqs.length) answers["Requirements"] = reqs;
      if (ctxPlanning.trim()) summaries["Planning"] = ctxPlanning.trim();
      const payload: ProjectContext = { data: {} as any };
      if (Object.keys(answers).length) (payload.data as any).answers = answers;
      if (Object.keys(summaries).length) (payload.data as any).summaries = summaries;
      const saved = await putProjectContext(id, payload);
      setCtx(saved);
      setNotice("Context saved.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setSavingCtx(false);
    }
  }

  async function onGenerateWithStoredContext() {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const resp = await generateDocuments(id, { traceability_overlay: overlayOn });
      setDocs(resp);
      if (resp.artifacts.length > 0) setSelected(resp.artifacts[0].filename);
      setNotice("Generated using stored context.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onAnalyzeImpacts() {
    if (!id) return;
    try {
      setAnalyzing(true);
      setError(null);
      const changed = frInput.split(/[\,\n]/).map(s => s.trim()).filter(Boolean);
      const resp = await computeImpacts(id, changed);
      setImpacts(resp);
      setNotice("Impact analysis complete.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setAnalyzing(false);
    }
  }

  // Build tab contents
  const OverviewTab = (
    <div>
      {project && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div><strong>ID:</strong> {project.project_id}</div>
          <div><strong>Name:</strong> {project.name}</div>
          <div><strong>Phase:</strong> {project.current_phase}</div>
        </div>
      )}
      {/* KPIs */}
      <div className="grid-3" aria-label="Project KPIs" style={{ marginBottom: 12 }}>
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>

      <div className="grid-2">
        {/* Phase Gate Summary */}
        <div className="card" aria-label="Phase Gate">
          <strong>Phase Gate</strong>
          <div style={{ marginTop: 8 }}>
            <Stepper
              steps={[
                { id: "charter", label: "Charter" },
                { id: "requirements", label: "Requirements" },
                { id: "specs", label: "Specifications" },
                { id: "design", label: "Design" },
                { id: "impl", label: "Implementation" },
                { id: "test", label: "Testing" },
                { id: "deploy", label: "Deployment" },
              ]}
              currentIndex={currentIndex}
            />
            <ul style={{ marginTop: 8 }}>
              <li>Charter approved: {charterApproved ? 'Yes' : 'No'}</li>
              <li>Requirements captured: {reqCount > 0 ? `${reqCount} item(s)` : 'No'}</li>
              <li>SRS approved: {srsApproved ? 'Yes' : 'No'}</li>
              <li>SDD approved: {sddApproved ? 'Yes' : 'No'}</li>
              <li>Test Plan approved: {testApproved ? 'Yes' : 'No'}</li>
            </ul>
          </div>
        </div>

        {/* Quick Links */}
        <div className="card" aria-label="Quick Links">
          <strong>Quick Links</strong>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            <Link className="btn btn-primary" href={`/projects/${id}?tab=Requirements`}>Open Requirements Chat</Link>
            <Link className="btn" href={`/projects/${id}?tab=Backlog`}>Open Backlog</Link>
            <Link className="btn" href={`/projects/${id}?tab=Tests`}>Open Tests</Link>
          </div>
        </div>
      </div>

      {/* Recent Artifacts */}
      <div className="card" style={{ marginTop: 12 }}>
        <strong>Recent Artifacts</strong>
        {!docs && <div className="muted">No documents generated yet.</div>}
        {docs && (
          <ul style={{ marginTop: 8 }}>
            {docs.artifacts.map(a => (
              <li key={a.filename}>
                <a href={artifactUrl(project!.project_id, a.filename)} target="_blank" rel="noreferrer">{a.filename}</a>
                {" "}
                <button className="btn" onClick={() => setSelected(a.filename)} disabled={selected === a.filename} style={{ marginLeft: 8 }}>
                  {selected === a.filename ? "Viewing" : "Preview"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );

  const hasDocs = !!docs && Array.isArray(docs.artifacts) && docs.artifacts.length > 0;

  function focusRequirements() {
    try {
      requirementsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      requirementsRef.current?.focus();
    } catch {}
  }

  const RequirementsTab = (
    <div>
      {/* KPIs */}
      <div className="grid-3" aria-label="Project KPIs" style={{ marginBottom: 12 }}>
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={hasDocs
          ? "Review generated artifacts on the right or switch to the Docs tab to manage versions and downloads."
          : "Generate documents with AI now, then refine with chat and regenerate."}
        primary={{ label: "Generate with AI", onClick: onAIGenerateSmart, variant: "primary" }}
        secondary={[
          { label: "Generate with inputs", onClick: onGenerateWithInputs },
          { label: "Regenerate", onClick: onRegenerate },
        ]}
      />
      <div className="columns-23" style={{ marginTop: 12 }}>
        {/* Left: Chat + Builder */}
        <div className="vstack" style={{ minWidth: 360 }}>
          <div className="card" style={{ marginBottom: 16 }}>
            <ChatPanel
              projectId={id}
              prefill={chipPrefill}
              onPrefillConsumed={() => setChipPrefill(undefined)}
              onRegenerateRequested={onRegenerate}
              onAIGenerateRequested={onAIGenerateSmart}
              autoGenerateDefault={true}
            />
          </div>
          <div className="card" style={{ marginBottom: 16 }}>
            <details open>
              <summary style={{ cursor: 'pointer' }}><strong>Import Existing Documents (optional)</strong></summary>
              <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                <input type="file" multiple accept=".pdf,.docx,.md,.txt" onChange={e => onUploadFilesChanged(e.target.files)} />
                {uploadMsg && <span className="muted">{uploadMsg}</span>}
                {(uploadReqs.length > 0) && (
                  <div>
                    <div className="muted" style={{ marginBottom: 6 }}>Select which extracted requirements to apply:</div>
                    <div className="card" style={{ maxHeight: 180, overflowY: 'auto' }}>
                      {uploadReqs.map((r, i) => (
                        <label key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
                          <input type="checkbox" checked={!!uploadSel[r]} onChange={e => setUploadSel(prev => ({ ...prev, [r]: e.target.checked }))} />
                          <span style={{ fontSize: 13 }}>{r}</span>
                        </label>
                      ))}
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <button className="btn" onClick={() => onApplyFromUploads(false)} disabled={uploadBusy || uploadReqs.length === 0}>{uploadBusy ? 'Applying…' : 'Apply selected'}</button>
                      <button className="btn btn-primary" onClick={() => onApplyFromUploads(true)} disabled={uploadBusy || uploadReqs.length === 0}>{uploadBusy ? 'Applying…' : 'Apply & Generate'}</button>
                    </div>
                  </div>
                )}
              </div>
            </details>
          </div>
          <div className="card">
            <details>
              <summary style={{ cursor: 'pointer' }}><strong>Requirements Builder (optional)</strong></summary>
              <textarea
                aria-label="Requirements input"
                placeholder="Optionally add or paste requirements… One per line is fine."
                value={promptText}
                onChange={e => setPromptText(e.target.value)}
                rows={8}
                ref={requirementsRef}
                style={{ width: "100%", marginTop: 8 }}
              />
              <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
                <div style={{ display: "flex", gap: 12, flexWrap: 'wrap' }}>
                  <label><input type="checkbox" checked={docTypes.includes('Project Charter')} onChange={e => setDocTypes(prev => e.target.checked ? Array.from(new Set([...prev, 'Project Charter'])) : prev.filter(x => x !== 'Project Charter'))} /> Project Charter</label>
                  <label><input type="checkbox" checked={docTypes.includes('SRS')} onChange={e => setDocTypes(prev => e.target.checked ? Array.from(new Set([...prev, 'SRS'])) : prev.filter(x => x !== 'SRS'))} /> SRS</label>
                  <label><input type="checkbox" checked={docTypes.includes('SDD')} onChange={e => setDocTypes(prev => e.target.checked ? Array.from(new Set([...prev, 'SDD'])) : prev.filter(x => x !== 'SDD'))} /> SDD</label>
                  <label><input type="checkbox" checked={docTypes.includes('Test Plan')} onChange={e => setDocTypes(prev => e.target.checked ? Array.from(new Set([...prev, 'Test Plan'])) : prev.filter(x => x !== 'Test Plan'))} /> Test Plan</label>
                </div>
                <label style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                  <input type="checkbox" checked={includeBacklog} onChange={e => setIncludeBacklog(e.target.checked)} /> Also generate Backlog (Epics → Stories with Gherkin)
                </label>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button className="btn" onClick={onEnrich} disabled={enriching || !promptText.trim()}>{enriching ? "Enriching…" : "Enrich"}</button>
                <button className="btn" onClick={onGenerateWithInputs} disabled={loading}>{loading ? "Generating…" : "Generate with inputs"}</button>
                <button className="btn btn-primary" onClick={onAIGenerate} disabled={loading || !promptText.trim()}>{loading ? "Generating…" : "Generate with AI"}</button>
                <button className="btn" onClick={onCheckLLM} disabled={loading}>Check LLM</button>
              </div>
            </details>
            {llmDiag && (
              <div className="muted" style={{ marginTop: 4 }}>Provider: {llmDiag.provider}, Model: {llmDiag.model}, Ready: {String(llmDiag.ready)}</div>
            )}
            {enriched && (
              <div style={{ marginTop: 12 }}>
                <div className="muted">Enriched preview</div>
                <div style={{ display: "grid", gap: 6 }}>
                  <div>
                    <strong>Planning Summary</strong>
                    <div style={{ whiteSpace: "pre-wrap" }}>{enriched.summaries?.Planning || ""}</div>
                  </div>
                  <div>
                    <strong>Requirements</strong>
                    <ul>
                      {(enriched.answers?.Requirements || []).map((r, i) => (<li key={i}>{r}</li>))}
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
        {/* Right: Docs preview + versions to be visible alongside chat */}
      <div className="vstack" style={{ minWidth: 320 }}>
        <div className="card" style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <strong>Artifacts</strong>
            <button className="btn" onClick={onRegenerate} disabled={loading}>{loading ? "Regenerating…" : "Regenerate"}</button>
            <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={overlayOn} onChange={e => setOverlayOn(e.target.checked)} /> Overlay
            </label>
            {project && (
              <a className="btn" href={zipUrl(project.project_id)}>Download (.zip)</a>
            )}
          </div>
          {!docs && <div className="muted">No documents generated yet.</div>}
          {docs && (
            <ul>
              {docs.artifacts.map(a => (
                <li key={a.filename}>
                  <a href={artifactUrl(project!.project_id, a.filename)} target="_blank" rel="noreferrer">{a.filename}</a>
                  {" "}
                  <button className="btn" onClick={() => setSelected(a.filename)} disabled={selected === a.filename} style={{ marginLeft: 8 }}>
                    {selected === a.filename ? "Viewing" : "Preview"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <strong>Preview</strong>
          <div style={{ position: 'relative', border: "1px solid var(--border)", borderRadius: 8, padding: 12, minHeight: 200, marginTop: 8 }} aria-busy={loading || undefined}>
            {loading && (
              <div role="status" aria-live="polite" style={{ position: 'absolute', top: 6, right: 6, background: 'var(--surface-1)', border: '1px solid var(--border)', borderRadius: 999, padding: '2px 8px', fontSize: 12, boxShadow: 'var(--shadow-sm)' }}>
                <span aria-hidden>⏳</span> Generating…
              </div>
            )}
            {selectedArtifact ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedArtifact.content}</ReactMarkdown>
            ) : (
              <p className="muted">Select a document to preview.</p>
            )}
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <strong>Version History</strong>
              <button className="btn" onClick={async () => { if (!id) return; try { const v = await listDocumentVersions(id); setVersions(v); } catch (e: any) { setError(e?.message || String(e)); } }}>Refresh</button>
            </div>
            {(!versions || !selected || !versions.versions[selected]) && (
              <div className="muted">No versions yet for the selected document.</div>
            )}
            {versions && selected && versions.versions[selected] && (
              <ul>
                {versions.versions[selected].slice().reverse().map(v => (
                  <li key={v.version}>
                    v{v.version} — {new Date(v.created_at).toLocaleString()} {previewVersion?.filename === selected && previewVersion?.version === v.version ? (
                      <span style={{ color: '#0a0', marginLeft: 8 }}>(previewing)</span>
                    ) : (
                      <button className="btn" style={{ marginLeft: 8 }} onClick={() => onPreviewVersion(selected, v.version)}>Preview v{v.version}</button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
      </div>
    </div>
  );

  const DocsTab = (
    <div style={{ display: "grid", gap: 12 }}>
      {/* KPIs + Next Actions */}
      <div className="grid-3" aria-label="Project KPIs">
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={docs && docs.artifacts.length ? "Preview, approve, or re-generate documents."
          : "No documents yet. Generate from Requirements with AI."}
        primary={docs && docs.artifacts.length
          ? { label: "Regenerate", onClick: onRegenerate }
          : { label: "Generate with AI", onClick: onAIGenerateSmart, variant: 'primary' }}
        secondary={[
          { label: "Open Requirements Chat", href: `/projects/${id}?tab=Requirements` },
          { label: "Download (.zip)", href: project ? zipUrl(project.project_id) : undefined }
        ]}
      />
      <div className="card">
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <strong>Artifacts</strong>
          <button className="btn" onClick={onRegenerate} disabled={loading}>{loading ? "Regenerating…" : "Regenerate"}</button>
          {project && (
            <a className="btn" href={zipUrl(project.project_id)}>Download (.zip)</a>
          )}
        </div>
        {!docs && <div className="muted">No documents generated yet.</div>}
        {docs && (
          <ul>
            {docs.artifacts.map(a => (
              <li key={a.filename}>
                <a href={artifactUrl(project!.project_id, a.filename)} target="_blank" rel="noreferrer">{a.filename}</a>
                {" "}
                <button className="btn" onClick={() => setSelected(a.filename)} disabled={selected === a.filename} style={{ marginLeft: 8 }}>
                  {selected === a.filename ? "Viewing" : "Preview"}
                </button>
                <button className="btn" onClick={() => setApproval(a.filename, !isApproved(a.filename))} style={{ marginLeft: 8 }}>
                  {isApproved(a.filename) ? 'Unapprove' : 'Approve'}
                </button>
                {isApproved(a.filename) && <span className="badge" style={{ marginLeft: 6 }}>Approved</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="card">
        <strong>Preview</strong>
        <div style={{ position: 'relative', border: "1px solid var(--border)", borderRadius: 8, padding: 12, minHeight: 200, marginTop: 8 }} aria-busy={loading || undefined}>
          {loading && (
            <div role="status" aria-live="polite" style={{ position: 'absolute', top: 6, right: 6, background: 'var(--surface-1)', border: '1px solid var(--border)', borderRadius: 999, padding: '2px 8px', fontSize: 12, boxShadow: 'var(--shadow-sm)' }}>
              <span aria-hidden>⏳</span> Generating…
            </div>
          )}
          {selectedArtifact ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{selectedArtifact.content}</ReactMarkdown>
          ) : (
            <p className="muted">Select a document to preview.</p>
          )}
        </div>
        {selected && (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="muted">Status: {isApproved(selected) ? 'Approved' : 'Not approved'}</span>
            <button className="btn" onClick={() => setApproval(selected!, !isApproved(selected!))}>{isApproved(selected!) ? 'Unapprove' : 'Approve'}</button>
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <strong>Version History</strong>
            <button className="btn" onClick={async () => { if (!id) return; try { const v = await listDocumentVersions(id); setVersions(v); } catch (e: any) { setError(e?.message || String(e)); } }}>Refresh</button>
          </div>
          {(!versions || !selected || !versions.versions[selected]) && (
            <div className="muted">No versions yet for the selected document.</div>
          )}
          {versions && selected && versions.versions[selected] && (
            <ul>
              {versions.versions[selected].slice().reverse().map(v => (
                <li key={v.version}>
                  v{v.version} — {new Date(v.created_at).toLocaleString()} {previewVersion?.filename === selected && previewVersion?.version === v.version ? (
                    <span style={{ color: '#0a0', marginLeft: 8 }}>(previewing)</span>
                  ) : (
                    <button className="btn" style={{ marginLeft: 8 }} onClick={() => onPreviewVersion(selected, v.version)}>Preview v{v.version}</button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );

  const DesignTab = (
    <div>
      {/* KPIs + Next Action */}
      <div className="grid-3" aria-label="Project KPIs" style={{ marginBottom: 12 }}>
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={sddArtifact ? "Answer open questions and apply them, then regenerate the SDD."
          : "No SDD yet. Generate documents from Requirements to create the initial SDD."}
        primary={sddArtifact
          ? { label: "Apply answers & Generate", onClick: applyAndGenerateFromDesign, variant: 'primary' }
          : { label: "Generate with AI", onClick: onAIGenerateSmart, variant: 'primary' }}
        secondary={[
          { label: "Regenerate SDD", onClick: onAIGenerateSDD },
          { label: "Open Requirements Chat", href: `/projects/${id}?tab=Requirements` },
        ]}
      />
      <div className="card">
        <div className="section-title">Design</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn" onClick={onAIGenerateSDD} disabled={loading}>{loading ? 'Generating…' : 'Regenerate SDD'}</button>
        </div>
        {!sddArtifact && <div className="muted">No SDD generated yet. Generate documents from Requirements.</div>}
        {sddArtifact && (
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{sddArtifact.content}</ReactMarkdown>
          </div>
        )}
        <div style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <strong>Open Questions</strong>
            <button className="btn btn-primary" onClick={applyAndGenerateFromDesign} disabled={designGenerating || designQuestions.length === 0} aria-busy={designGenerating || undefined}>
              {designGenerating ? 'Applying & Generating…' : 'Apply answers & Generate'}
            </button>
          <button className="btn" onClick={applyDesignAnswersToContext} disabled={designGenerating || designQuestions.length === 0}>Apply answers</button>
            {qaNotice && <span className="muted">{qaNotice}</span>}
          </div>
          {designQuestions.length === 0 ? (
            <div className="muted" style={{ marginTop: 8 }}>No open questions found in the SDD.</div>
          ) : (
            <div style={{ display: 'grid', gap: 12, marginTop: 8 }}>
              {designQuestions.map((q, i) => (
                <div key={i} className="card" style={{ padding: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
                    <strong>Q{i + 1}. {q}</strong>
                    <button className="btn" onClick={() => discussInChat(q)}>Discuss in Chat</button>
                  </div>
                  <label className="muted">Your answer</label>
                  <textarea value={designAnswers[i] || ''} onChange={e => onAnswerChange(i, e.target.value)} rows={3} style={{ width: '100%' }} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  const BacklogTab = (
    <div>
      {/* KPIs + Next Action */}
      <div className="grid-3" aria-label="Project KPIs" style={{ marginBottom: 12 }}>
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={includeBacklog ? "Generate or refresh backlog from the current context." : "Generate the backlog (Epics → Stories with Gherkin) with AI."}
        primary={{ label: includeBacklog ? 'AI Generate Backlog' : 'Enable & Generate Backlog', onClick: onGenerateBacklogSmart, variant: 'primary' }}
        secondary={[]}
      />
      <div className="card">
        <div className="section-title">Backlog</div>
        <div className="muted">Epics and Stories (with Gherkin) will appear here.</div>
      </div>
    </div>
  );

  const TestsTab = (
    <div>
      {/* KPIs + Next Action */}
      <div className="grid-3" aria-label="Project KPIs" style={{ marginBottom: 12 }}>
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message={testPlanArtifact ? "Review the Test Plan and approve once ready." : "No Test Plan yet. Generate documents from Requirements."}
        primary={testPlanArtifact
          ? { label: 'Regenerate Test Plan', onClick: onAIGenerateSmart }
          : { label: 'Generate with AI', onClick: onAIGenerateSmart, variant: 'primary' }}
        secondary={[]}
      />
      <div className="card">
        <div className="section-title">Tests</div>
        {!testPlanArtifact && <div className="muted">No Test Plan generated yet. Generate documents from Requirements.</div>}
        {testPlanArtifact && (
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{testPlanArtifact.content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );

  const SettingsTab = (
    <div style={{ display: 'grid', gap: 12 }}>
      {/* KPIs + Next Action */}
      <div className="grid-3" aria-label="Project KPIs">
        <Stat label="Requirements captured" value={String(reqCount)} />
        <Stat label="Documents generated" value={String(docCount || 0)} />
        <Stat label="Approved docs" value={String(approvedCount)} />
      </div>
      <NextAction
        message="Save Stored Context updates and generate documents using it."
        primary={{ label: 'Generate with stored context', onClick: onGenerateWithStoredContext, variant: 'primary' }}
        secondary={[]}
      />
      <div className="card">
        <strong>Stored Context</strong>
        <div className="muted" style={{ marginBottom: 8 }}>Saved context will be merged into document generation.</div>
        <label>Planning Summary</label>
        <textarea value={ctxPlanning} onChange={e => setCtxPlanning(e.target.value)} rows={3} style={{ width: "100%" }} />
        <label style={{ marginTop: 8, display: 'block' }}>Requirements (one per line)</label>
        <textarea value={ctxRequirements} onChange={e => setCtxRequirements(e.target.value)} rows={6} style={{ width: "100%" }} />
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="btn" onClick={onSaveContext} disabled={savingCtx}>{savingCtx ? "Saving…" : "Save context"}</button>
          <button className="btn btn-primary" onClick={onGenerateWithStoredContext} disabled={loading}>{loading ? "Generating…" : "Generate with stored context"}</button>
        </div>
      </div>
      <div className="card">
        <strong>Impact Analysis</strong>
        <div className="muted" style={{ marginBottom: 8 }}>Enter FR IDs (e.g., FR-003, FR-011) separated by commas or new lines.</div>
        <textarea value={frInput} onChange={e => setFrInput(e.target.value)} rows={4} style={{ width: "100%" }} />
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button className="btn" onClick={onAnalyzeImpacts} disabled={analyzing || !frInput.trim()}>{analyzing ? "Analyzing…" : "Analyze"}</button>
        </div>
        {impacts && impacts.impacts && impacts.impacts.length > 0 && (
          <ul style={{ marginTop: 8 }}>
            {impacts.impacts.map((it, i) => (
              <li key={i}>
                <span style={{ color: '#666' }}>{it.kind}</span>: {it.name} <span style={{ color: '#999' }}>({Math.round(it.confidence * 100)}%)</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );

  const tabs = [
    { id: 'Overview', label: 'Overview', content: OverviewTab },
    { id: 'Requirements', label: 'Requirements', content: RequirementsTab },
    { id: 'Design', label: 'Design', content: DesignTab },
    { id: 'Backlog', label: 'Backlog', content: BacklogTab },
    { id: 'Tests', label: 'Tests', content: TestsTab },
    { id: 'Docs', label: 'Docs', content: DocsTab },
    { id: 'Settings', label: 'Settings', content: SettingsTab },
  ];

  const tabParam: string | undefined = typeof router.query.tab === 'string' ? router.query.tab : undefined;
  const defaultTabId = tabParam ? (tabs.find(t => t.id.toLowerCase() === tabParam.toLowerCase())?.id ?? 'Overview') : 'Overview';

  return (
    <div>
      <p><Link href="/projects">← Back to Projects</Link></p>
      <h2>Project Workspace</h2>
      {loading && <div className="badge" role="status">Loading…</div>}
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}
      {/* Quick Start hero: scenario chips to prefill chat */}
      <div className="hero" role="region" aria-label="Quick Start">
        <div className="hero-inner">
          <div>
            <div className="hero-title">Refine requirements faster</div>
            <div className="muted">Pick a scenario to prefill the chat and start refining immediately.</div>
          </div>
          <div className="chips">
            {scenarioChips.map((label) => (
              <button
                key={label}
                className="chip"
                onClick={() => {
                  setChipPrefill(`Scenario: ${label}. Please ask clarifying questions and propose SHALL-style requirements. Then we will generate Charter, SRS, SDD, and Test Plan.`);
                  try { router.push(`/projects/${id}?tab=Requirements`); } catch {}
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <Tabs tabs={tabs} defaultTabId={defaultTabId} />
    </div>
  );
}
