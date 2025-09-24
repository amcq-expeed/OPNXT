import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { listProjects, Project, listDocumentVersions, DocumentVersionsResponse } from '../lib/api';

export default function DocumentsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [versions, setVersions] = useState<DocumentVersionsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const project = useMemo(() => projects.find(p => p.project_id === selected) || null, [projects, selected]);
  const fileNames = useMemo(() => Object.keys(versions?.versions || {}), [versions]);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const list = await listProjects();
        setProjects(list);
        if (list.length) setSelected(list[0].project_id);
      } catch (e: any) {
        setError(e?.message || String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function loadVersions(pid: string) {
    try {
      setError(null);
      setLoading(true);
      const v = await listDocumentVersions(pid);
      setVersions(v);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!selected) return;
    loadVersions(selected);
  }, [selected]);

  return (
    <div>
      <h2>Documents</h2>
      {error && <p className="error">{error}</p>}

      <div className="card" style={{ marginBottom: 12 }}>
        <label style={{ display: 'grid', gap: 6 }}>
          <span>Project</span>
          <select className="select" aria-label="Select project" value={selected} onChange={e => setSelected(e.target.value)}>
            {projects.map(p => (
              <option key={p.project_id} value={p.project_id}>{p.name} ({p.project_id})</option>
            ))}
          </select>
        </label>
      </div>

      {loading && <div className="badge" role="status">Loading…</div>}

      {!loading && (!versions || fileNames.length === 0) && (
        <div className="card"><div className="muted">No version history available.</div></div>
      )}

      <div className="grid-2">
        {fileNames.map(fname => {
          const arr = versions!.versions[fname];
          const latest = arr[arr.length - 1];
          return (
            <div key={fname} className="card">
              <div className="section-title">{fname}</div>
              <div className="muted">Latest v{latest.version} — {new Date(latest.created_at).toLocaleString()}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <Link className="btn" href={`/projects/${encodeURIComponent(selected)}?tab=Docs&file=${encodeURIComponent(fname)}&version=${latest.version}`}>Open in Workspace</Link>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
