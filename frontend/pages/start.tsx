import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import ChatPanel from "../components/ChatPanel";
import {
  listProjects,
  createProject,
  createChatSession,
  postChatMessage,
  me,
  User,
  getAccessToken,
  Project,
  generateDocuments,
  getProjectContext,
  aiGenerateDocuments,
} from "../lib/api";

export default function StartPage() {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Create-new state
  const [newName, setNewName] = useState<string>("");
  const [newIdea, setNewIdea] = useState<string>("");
  const [creating, setCreating] = useState<boolean>(false);

  // Use-existing state
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");

  async function refreshProjects() {
    try {
      setLoading(true);
      setError(null);
      const items = await listProjects();
      setProjects(items);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onRegenerateFromStart() {
    if (!selectedProjectId) return;
    try {
      // Generate docs from the latest stored context, then take the user to Docs
      await generateDocuments(selectedProjectId, { traceability_overlay: true });
      await router.push(`/projects/${encodeURIComponent(selectedProjectId)}?tab=Docs`);
    } catch (e) {
      // non-blocking; show nothing special on start page
    }
  }

  function buildPromptFromContext(c: any): string {
    const data: any = c?.data || {};
    const planning = data?.summaries?.Planning || '';
    const reqs: string[] = Array.isArray(data?.answers?.Requirements) ? data.answers.Requirements : [];
    const parts = [
      planning ? `Planning Summary:\n${planning}` : '',
      reqs.length ? `Requirements:\n- ${reqs.join('\n- ')}` : '',
    ].filter(Boolean);
    if (parts.length) return parts.join('\n\n');
    return 'Generate the standard documents (Project Charter, SRS, SDD, Test Plan) for this project based on current context.';
  }

  async function onAIGenerateFromStart() {
    if (!selectedProjectId) return;
    try {
      const latest = await getProjectContext(selectedProjectId);
      const prompt = buildPromptFromContext(latest);
      await aiGenerateDocuments(selectedProjectId, { input_text: prompt });
      await router.push(`/projects/${encodeURIComponent(selectedProjectId)}?tab=Docs`);
    } catch (e) {
      // swallow for now; UI retains context
    }
  }

  useEffect(() => {
    if (typeof window !== 'undefined' && !getAccessToken()) {
      const rt = encodeURIComponent('/start');
      window.location.href = `/login?returnTo=${rt}`;
      return;
    }
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const u = await me();
        setCurrentUser(u);
        await refreshProjects();
      } catch (e: any) {
        if (typeof window !== 'undefined') {
          const rt = encodeURIComponent('/start');
          window.location.href = `/login?returnTo=${rt}`;
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onCreateAndStart(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) { setError('Please enter a project name.'); return; }
    try {
      setCreating(true);
      setError(null);
      setNotice(null);
      const proj = await createProject({ name: newName.trim(), description: newIdea.trim() } as any);
      setSelectedProjectId(proj.project_id);
      setNotice('Project created. Starting chat…');
      // Create a chat session and seed the first message if user provided an idea
      try {
        const sess = await createChatSession(proj.project_id, 'Initial Refinement');
        if (newIdea.trim()) {
          await postChatMessage(sess.session_id, newIdea.trim());
          setNotice('Project created and first message sent.');
        }
      } catch {}
      // Clear inputs
      setNewName("");
      setNewIdea("");
      // Refresh projects so it appears in the list
      await refreshProjects();
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <div className="section-title">Start</div>
      {loading && <div className="badge">Loading…</div>}
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      <div className="grid-2">
        {/* Quick Start */}
        <div className="card">
          <div className="section-title">Quick Start</div>
          <form onSubmit={onCreateAndStart} style={{ display: 'grid', gap: 8, maxWidth: 640, marginTop: 8 }}>
            <label>
              <span className="muted">Project name</span>
              <input className="input" placeholder="e.g., Customer Portal Revamp" value={newName} onChange={e => setNewName(e.target.value)} required />
            </label>
            <label>
              <span className="muted">Kick-off idea (optional)</span>
              <textarea className="textarea" placeholder="Describe your issue or idea to kick off the chat (optional)" value={newIdea} onChange={e => setNewIdea(e.target.value)} />
            </label>
            <div>
              <button className="btn btn-primary" type="submit" disabled={creating}>{creating ? 'Creating…' : 'Create & Start Chat'}</button>
            </div>
          </form>
        </div>

        {/* Use existing project */}
        <div className="card">
          <div className="section-title">Use Existing Project</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
            <select className="select" value={selectedProjectId} onChange={e => setSelectedProjectId(e.target.value)} aria-label="Select project">
              <option value="">Choose a project…</option>
              {projects.map(p => (
                <option key={p.project_id} value={p.project_id}>{p.name} ({p.project_id})</option>
              ))}
            </select>
            {selectedProjectId && (
              <Link href={`/projects/${encodeURIComponent(selectedProjectId)}`} className="btn">Open project details</Link>
            )}
          </div>
        </div>

        {/* Chat panel (full-width row) */}
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          {selectedProjectId ? (
            <ChatPanel projectId={selectedProjectId} onAIGenerateRequested={onAIGenerateFromStart} onRegenerateRequested={onRegenerateFromStart} autoGenerateDefault={true} />
          ) : (
            <div className="muted">Select or create a project to start chatting.</div>
          )}
        </div>

      </div>
    </div>
  );
}
