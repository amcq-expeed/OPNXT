import { useEffect, useMemo, useState } from 'react';
import Head from 'next/head';
import Image, { StaticImageData } from 'next/image';
import logoPng from '../public/logo.png';
import MVPChat from '../components/MVPChat';
import {
  createProject,
  getProject,
  Project,
  getAccessToken,
  listDocumentVersions,
  DocumentVersionsResponse,
  documentDownloadUrl,
  documentDocxUrl,
  zipUrl,
} from '../lib/api';

export default function MVPPage() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [versions, setVersions] = useState<DocumentVersionsResponse | null>(null);

  // Helper to create a fresh hidden MVP project
  async function createFreshProject() {
    const now = new Date();
    const name = `MVP Session ${now.toLocaleDateString()} ${now.toLocaleTimeString()}`;
    const description = 'Ad-hoc chat-to-docs session (temporary).';
    const proj = await createProject({ name, description, type: 'mvp' } as any);
    setProjectId(proj.project_id);
    try { if (typeof window !== 'undefined') window.localStorage.setItem('opnxt_mvp_project_id', proj.project_id); } catch {}
    return proj.project_id as string;
  }

  // Fetch document versions for slideout
  async function refreshDocs() {
    if (!projectId) return;
    try {
      const v = await listDocumentVersions(projectId);
      setVersions(v);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  // Download helper with auth header when available
  async function downloadWithAuth(url: string, suggestedName: string) {
    try {
      const token = getAccessToken();
      const res = await fetch(url, { headers: token ? { 'Authorization': `Bearer ${token}` } as any : undefined });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Download failed: ${res.status} ${text || ''}`);
      }
      const blob = await res.blob();
      const link = document.createElement('a');
      const objUrl = URL.createObjectURL(blob);
      link.href = objUrl;
      link.download = suggestedName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(objUrl);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }

  // Sort documents by canonical order
  const sortedFiles = useMemo(() => {
    const files = Object.keys(versions?.versions || {});
    const order = ["ProjectCharter.md", "SRS.md", "SDD.md", "TestPlan.md", "Backlog.md", "Backlog.csv", "Backlog.json"];
    return files.sort((a, b) => {
      const ia = order.indexOf(a); const ib = order.indexOf(b);
      if (ia >= 0 && ib >= 0) return ia - ib;
      if (ia >= 0) return -1; if (ib >= 0) return 1;
      return a.localeCompare(b);
    });
  }, [versions]);

  // Document count for discoverability controls
  const docCount = useMemo(() => Object.keys(versions?.versions || {}).length, [versions]);

  // Auto-refresh versions once project exists
  useEffect(() => { if (projectId) refreshDocs(); }, [projectId]);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setError(null);
        // Reuse a locally cached MVP project if available
        let pid: string | null = null;
        try { pid = typeof window !== 'undefined' ? window.localStorage.getItem('opnxt_mvp_project_id') : null; } catch {}
        if (pid) {
          try {
            const p = await getProject(pid);
            if (p && p.project_id) {
              setProjectId(p.project_id);
            } else {
              await createFreshProject();
            }
          } catch {
            await createFreshProject();
          }
        } else {
          await createFreshProject();
        }
      } catch (e: any) {
        setError(e?.message || String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Model pill/topbar removed per clean MVP request

  // No documents panel on MVP; skip fetching versions for a clean first view

  async function startNewSession() {
    try {
      setError(null);
      setLoading(true);
      try { if (typeof window !== 'undefined') window.localStorage.removeItem('opnxt_mvp_project_id'); } catch {}
      await createFreshProject();
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  const [logoSrc, setLogoSrc] = useState<string | StaticImageData>(logoPng);

  return (
    <div className="mvp-hero-grid" role="region" aria-label="MVP Hero">
      <Head>
        <link rel="preload" as="image" href="/logo.png" />
      </Head>
      <div className="hero__stack">
        <Image
          src={logoSrc}
          alt="Logo"
          className="hero-logo"
          width={(logoPng as any).width || 768}
          height={(logoPng as any).height || 768}
          priority
          unoptimized
          sizes="(max-width: 900px) 160px, 200px"
          onError={() => { setLogoSrc('/opnxt-logo.svg'); }}
        />
        {/* Final text fallback for extreme cases */}
        {!logoSrc && (
          <span style={{ fontWeight: 800, color: '#fff' }}>OPNXT</span>
        )}
        <div className="card" style={{ width: '100%', maxWidth: 860 }}>
          {loading && <div className="badge" role="status">Preparing session…</div>}
          {error && <p className="error">{error}</p>}
          {!loading && !error && projectId && (
            <MVPChat
              projectId={projectId}
              docCount={docCount}
              onDocumentsGenerated={() => { refreshDocs(); setDrawerOpen(true); }}
            />
          )}
        </div>
      </div>
      {/* Reopen Documents button: only visible when docs exist and drawer is closed */}
      {projectId && docCount > 0 && !drawerOpen && (
        <button
          type="button"
          className="btn btn-primary"
          style={{ position: 'fixed', right: 16, bottom: 16, zIndex: 61 }}
          aria-label="Open Documents"
          title="Open Documents"
          onClick={() => { refreshDocs(); setDrawerOpen(true); }}
        >
          Documents
        </button>
      )}

      {/* Documents button intentionally hidden per UX rule (initially). We reintroduce a minimal opener above only after docs exist. */}
      {/* Slideout Drawer for Documents */}
      <div className={`drawer ${drawerOpen ? 'open' : ''}`} aria-hidden={!drawerOpen}>
        <div className="drawer__backdrop" onClick={() => setDrawerOpen(false)} />
        <aside className="drawer__panel" role="dialog" aria-label="Documents">
          <div className="drawer__header">
            <div className="section-title" style={{ margin: 0 }}>Documents</div>
            <div style={{ display: 'inline-flex', gap: 8 }}>
              {projectId && (
                <button className="btn" onClick={() => downloadWithAuth(zipUrl(projectId!), `${projectId}-docs.zip`)}>Download All (.zip)</button>
              )}
              <button className="btn-icon" onClick={() => setDrawerOpen(false)} aria-label="Close">✕</button>
            </div>
          </div>
          <div className="drawer__body">
            {!versions || Object.keys(versions.versions || {}).length === 0 ? (
              <div className="muted">No documents yet. Generate to see them here.</div>
            ) : (
              <div className="vstack">
                {sortedFiles.map(fname => {
                  const arr = versions!.versions[fname];
                  const latest = arr[arr.length - 1];
                  const isMd = fname.toLowerCase().endsWith('.md');
                  const rawUrl = documentDownloadUrl(projectId!, fname, latest.version);
                  const docxUrl = isMd ? documentDocxUrl(projectId!, fname, latest.version) : '';
                  const stamp = new Date(latest.created_at).toLocaleString();
                  return (
                    <div key={fname} className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div>
                        <div className="section-title" style={{ marginBottom: 0 }}>{fname}</div>
                        <div className="muted">Latest v{latest.version} — {stamp}</div>
                      </div>
                      <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                        <button className="btn" onClick={() => downloadWithAuth(rawUrl, fname)}>Download</button>
                        {isMd && (
                          <button className="btn" onClick={() => downloadWithAuth(docxUrl, fname.replace(/\.md$/i, '.docx'))}>.docx</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
