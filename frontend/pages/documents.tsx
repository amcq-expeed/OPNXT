import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  listProjects,
  Project,
  listDocumentVersions,
  DocumentVersionsResponse,
} from "../lib/api";

export default function DocumentsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [versions, setVersions] = useState<DocumentVersionsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const project = useMemo(
    () => projects.find((p) => p.project_id === selected) || null,
    [projects, selected],
  );
  const fileNames = useMemo(
    () => Object.keys(versions?.versions || {}),
    [versions],
  );

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
    <div className="workspace-page" aria-live="polite">
      <section className="launch-hero launch-hero--wide documents-hero" aria-label="Documents workspace overview">
        <div className="launch-hero__card">
          <div className="launch-hero__intro">
            <span className="launch-hero__badge badge">Documents Workspace</span>
            <h1 className="launch-hero__title">Stay aligned with every revision</h1>
            <p className="launch-hero__subtitle">
              Review generated artifacts, compare revisions, and jump straight into the project workspace for inline editing and approvals.
            </p>
            <ul className="launch-hero__list" aria-label="Workspace highlights">
              <li>
                <strong>Projects tracked</strong>
                <span>{projects.length}</span>
              </li>
              <li>
                <strong>Latest selection</strong>
                <span>{project ? project.name : "Choose a project"}</span>
              </li>
            </ul>
            <div className="workspace-hero__actions" role="navigation" aria-label="Documents quick actions">
              <button
                type="button"
                className="workspace-hero__action"
                onClick={() => {
                  if (!selected && projects[0]) setSelected(projects[0].project_id);
                  if (selected) {
                    void loadVersions(selected);
                  }
                }}
              >
                <span className="workspace-hero__action-label">Refresh versions</span>
                <span className="workspace-hero__action-desc">Pull the newest artifacts for the selected project.</span>
              </button>
              <button
                type="button"
                className="workspace-hero__action"
                onClick={() => {
                  if (!selected && projects[0]) setSelected(projects[0].project_id);
                  if (selected) {
                    const target = `/projects/${encodeURIComponent(selected)}?tab=Docs`;
                    void window.open(target, "_blank");
                  }
                }}
                disabled={!selected}
              >
                <span className="workspace-hero__action-label">Open project workspace</span>
                <span className="workspace-hero__action-desc">Navigate to the live workspace to edit and approve documents.</span>
              </button>
            </div>
          </div>

          <div className="launch-hero__panel">
            <span className="launch-hero__panel-label">Choose a project</span>
            <div className="documents-hero__selector">
              <label htmlFor="documents-project-select" className="visually-hidden">
                Project
              </label>
              <select
                id="documents-project-select"
                className="select"
                aria-label="Select project for document history"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.name} ({p.project_id})
                  </option>
                ))}
              </select>
              {project && (
                <p className="documents-hero__selector-footer">
                  Viewing versions for <strong>{project.name}</strong>
                </p>
              )}
            </div>
          </div>
        </div>
      </section>

      {error && <div className="workspace-banner workspace-banner--error">{error}</div>}
      {loading && (
        <div className="workspace-banner" role="status">
          Loading document history…
        </div>
      )}

      <section className="workspace-section" aria-label="Document version timeline">
        <header className="workspace-section__header">
          <div>
            <h2>Version history</h2>
            <p className="muted">
              Track revisions across Charter, SRS, SDD, Test Plan, and custom artifacts. Select a version to inspect or open it in the project workspace.
            </p>
          </div>
          {project && (
            <Link className="btn" href={`/projects/${encodeURIComponent(project.project_id)}?tab=Docs`}>
              Go to Docs tab
            </Link>
          )}
        </header>

        {!loading && (!versions || fileNames.length === 0) && (
          <div className="workspace-empty">
            <p>No version history available yet. Generate documents from the project workspace to populate this list.</p>
          </div>
        )}

        <div className="workspace-card-grid">
          {fileNames.map((fname) => {
            const arr = versions!.versions[fname];
            const latest = arr[arr.length - 1];
            return (
              <article key={fname} className="workspace-card">
                <header className="workspace-card__header">
                  <h3>{fname}</h3>
                  <span className="workspace-card__badge">Latest v{latest.version}</span>
                </header>
                <p className="workspace-card__meta">
                  Updated {new Date(latest.created_at).toLocaleString()}
                </p>
                <div className="workspace-card__actions">
                  <Link
                    className="btn btn-primary"
                    href={`/projects/${encodeURIComponent(selected)}?tab=Docs&file=${encodeURIComponent(fname)}&version=${latest.version}`}
                  >
                    Open in workspace
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
