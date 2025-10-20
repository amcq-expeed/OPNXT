import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import ProjectLaunchHero from "../components/ui/ProjectLaunchHero";
import {
  Project,
  ProjectCreate,
  listProjects,
  createProject,
  advanceProject,
  deleteProject,
  isFinalPhase,
  generateDocuments,
  artifactUrl,
  DocGenResponse,
  zipUrl,
  me,
  User,
  canWrite,
  isAdmin,
  getAccessToken,
} from "../lib/api";

export default function ProjectsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [q, setQ] = useState<string>("");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [features, setFeatures] = useState("");
  const [creating, setCreating] = useState<boolean>(false);
  const [advancingId, setAdvancingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [docMap, setDocMap] = useState<Record<string, DocGenResponse>>({});
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [showAdvancedCreate, setShowAdvancedCreate] = useState<boolean>(false);

  // Quick Start (chat-first) input + scenario chips
  const [quickText, setQuickText] = useState<string>("");
  const [startingQuick, setStartingQuick] = useState<boolean>(false);

  // Traceability overlay toggle for doc generation
  const [traceOverlay, setTraceOverlay] = useState<boolean>(true);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return items;
    return items.filter(
      (p) =>
        p.name.toLowerCase().includes(term) ||
        p.project_id.toLowerCase().includes(term),
    );
  }, [q, items]);

  async function refresh() {
    try {
      setLoading(true);
      setError(null);
      setNotice(null);
      const data = await listProjects();
      setItems(data);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function onGenerateDocs(id: string) {
    try {
      setGeneratingId(id);
      const resp = await generateDocuments(id, {
        traceability_overlay: traceOverlay,
      });
      setDocMap((prev) => ({ ...prev, [id]: resp }));
      setNotice(`Generated ${resp.artifacts.length} documents.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setGeneratingId(null);
    }
  }

  useEffect(() => {
    (async () => {
      try {
        if (!getAccessToken()) {
          if (typeof window !== "undefined") {
            const rt = encodeURIComponent("/start");
            window.location.href = `/login?returnTo=${rt}`;
          }
          return;
        }
        const u = await me();
        setCurrentUser(u);
        await refresh();
      } catch (e: any) {
        // Likely 401; send to login
        if (typeof window !== "undefined") {
          const rt = encodeURIComponent("/start");
          window.location.href = `/login?returnTo=${rt}`;
        }
      }
    })();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    const payload: ProjectCreate = {
      name,
      description,
      features,
    } as ProjectCreate;
    try {
      setCreating(true);
      const proj = await createProject(payload);
      setItems((prev) => [
        proj,
        ...prev.filter((p) => p.project_id !== proj.project_id),
      ]);
      setName("");
      setDescription("");
      setFeatures("");
      // Redirect to the new project's workspace (Requirements tab) for immediate setup
      try {
        await router.push(
          `/projects/${encodeURIComponent(proj.project_id)}?tab=Requirements`,
        );
        return; // No need to refresh this list view
      } catch {
        // Fallback: refresh list and show notice
        await refresh();
        setNotice("Project created.");
      }
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setCreating(false);
    }
  }

  async function onQuickStartSubmit(input?: string) {
    const text = (typeof input === "string" ? input : quickText).trim();
    if (!text) return;
    try {
      setStartingQuick(true);
      const payload: ProjectCreate = {
        name: text.length > 60 ? text.slice(0, 60) : text,
        description: text,
        features: "",
      } as ProjectCreate;
      const proj = await createProject(payload);
      setItems((prev) => [
        proj,
        ...prev.filter((p) => p.project_id !== proj.project_id),
      ]);
      const prefill = encodeURIComponent(
        `I want to build: ${text}. Please help capture clear, testable requirements (FR and NFR), then generate a Charter, SRS, SDD, and Test Plan.`,
      );
      await router.push(
        `/projects/${encodeURIComponent(proj.project_id)}?tab=Requirements&prefill=${prefill}`,
      );
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setStartingQuick(false);
      if (!input) {
        setQuickText("");
      }
    }
  }

  async function onQuickStartScenario(scenario: string) {
    try {
      setStartingQuick(true);
      const payload: ProjectCreate = {
        name: scenario,
        description: `Quick Start: ${scenario}`,
        features: "",
      } as ProjectCreate;
      const proj = await createProject(payload);
      setItems((prev) => [
        proj,
        ...prev.filter((p) => p.project_id !== proj.project_id),
      ]);
      const prefill = encodeURIComponent(
        `Let's build a ${scenario}. Start by asking me clarifying questions and propose SHALL-style requirements. Then generate the core documents.`,
      );
      await router.push(
        `/projects/${encodeURIComponent(proj.project_id)}?tab=Requirements&prefill=${prefill}`,
      );
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setStartingQuick(false);
    }
  }

  async function onAdvance(id: string, currentPhase: string) {
    if (isFinalPhase(currentPhase)) {
      setNotice("Already at final phase.");
      return;
    }
    try {
      setAdvancingId(id);
      const updated = await advanceProject(id);
      // Optimistic update
      setItems((prev) => prev.map((p) => (p.project_id === id ? updated : p)));
      setNotice(`Advanced to ${updated.current_phase}.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setAdvancingId(null);
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Delete this project?")) return;
    try {
      setDeletingId(id);
      await deleteProject(id);
      // Optimistic remove
      setItems((prev) => prev.filter((p) => p.project_id !== id));
      setNotice("Project deleted.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="projects-shell">
      <header
        className="projects-hero"
        role="region"
        aria-label="Projects quick start"
      >
        <ProjectLaunchHero
          className="launch-hero--spotlight launch-hero--wide"
          badgeLabel="Projects Hub"
          title="Concept → Delivery projects"
          subtitle="Capture initiatives, seed requirements, and jump straight into the chat capability palette with history search so every document, readiness signal, and approval stays synchronized."
          value={quickText}
          onChange={setQuickText}
          disabled={startingQuick}
          busy={startingQuick}
          startLabel={startingQuick ? "Starting…" : "Start"}
          onSubmit={(value) => onQuickStartSubmit(value)}
          onScenarioSelect={(scenario) =>
            onQuickStartScenario(
              typeof scenario === "string" ? scenario : scenario.value,
            )
          }
          supportingCopy={
            <ul className="launch-hero__list" aria-label="Portfolio metrics">
              {[
                {
                  title: "Active initiatives",
                  description: items.length
                    ? items.length.toString().padStart(2, "0")
                    : "—",
                },
                {
                  title: "Traceability overlay",
                  description: traceOverlay ? "Enabled" : "Disabled",
                },
                {
                  title: "Quick starts today",
                  description: startingQuick ? "Launching…" : "Ready",
                },
                {
                  title: "Chat insight library",
                  description: "Templates & history search available",
                },
              ].map((stat) => (
                <li key={stat.title}>
                  <strong>{stat.title}</strong>
                  <span>{stat.description}</span>
                </li>
              ))}
            </ul>
          }
        />
      </header>

      <section className="projects-body" aria-label="Manage projects">
        <div className="card projects-search">
          <label style={{ display: "grid", gap: 4 }}>
            <span>Search</span>
            <input
              className="input"
              aria-label="Search projects"
              placeholder="Search by name or ID"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
        </div>

        <label className="projects-toggle">
          <input
            type="checkbox"
            checked={traceOverlay}
            onChange={(e) => setTraceOverlay(e.target.checked)}
          />
          <span className="muted">
            Include traceability map inside generated documents
          </span>
        </label>

        {loading && <div className="badge">Loading…</div>}
        {error && <p className="error">{error}</p>}
        {notice && <p className="notice">{notice}</p>}

        <div className="card projects-table">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Phase</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.project_id}>
                  <td>{p.project_id}</td>
                  <td>{p.name}</td>
                  <td>{p.current_phase}</td>
                  <td>
                    <div
                      style={{
                        display: "flex",
                        gap: 8,
                        flexWrap: "wrap",
                        alignItems: "center",
                      }}
                    >
                      {canWrite(currentUser) && (
                        <button
                          className="btn"
                          onClick={() =>
                            onAdvance(p.project_id, p.current_phase)
                          }
                          disabled={
                            isFinalPhase(p.current_phase) ||
                            advancingId === p.project_id
                          }
                        >
                          {advancingId === p.project_id
                            ? "Advancing…"
                            : isFinalPhase(p.current_phase)
                              ? "At Final"
                              : "Advance"}
                        </button>
                      )}
                      {canWrite(currentUser) && (
                        <button
                          className="btn"
                          onClick={() => onGenerateDocs(p.project_id)}
                          disabled={
                            generatingId === p.project_id ||
                            deletingId === p.project_id
                          }
                        >
                          {generatingId === p.project_id
                            ? "Generating…"
                            : "Generate Docs"}
                        </button>
                      )}
                      {isAdmin(currentUser) && (
                        <button
                          className="btn btn-danger"
                          onClick={() => onDelete(p.project_id)}
                          disabled={
                            deletingId === p.project_id ||
                            advancingId === p.project_id
                          }
                        >
                          {deletingId === p.project_id ? "Deleting…" : "Delete"}
                        </button>
                      )}
                      <Link
                        href={`/projects/${encodeURIComponent(p.project_id)}`}
                        className="btn"
                      >
                        Details
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Documents panel */}
        {items.map((p) => {
          const docs = docMap[p.project_id];
          if (!docs) return null;
          return (
            <div
              key={`${p.project_id}-docs`}
              className="card projects-docs"
              style={{ marginTop: 16 }}
            >
              <strong>
                Documents for {p.name} ({p.project_id})
              </strong>
              {docs.saved_to && (
                <p className="muted" style={{ margin: 0 }}>
                  Saved under: {docs.saved_to}
                </p>
              )}
              <p style={{ marginTop: 8 }}>
                <a href={zipUrl(p.project_id)} className="btn">
                  Download all (.zip)
                </a>
              </p>
              <ul>
                {docs.artifacts.map((a) => (
                  <li key={a.filename}>
                    <a
                      href={artifactUrl(p.project_id, a.filename)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {a.filename}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}

        {canWrite(currentUser) ? (
          <div className="projects-create-wrapper">
            <div className="projects-create__toggle">
              <button
                type="button"
                className="btn"
                onClick={() => setShowAdvancedCreate((prev) => !prev)}
              >
                {showAdvancedCreate ? "Hide advanced create" : "Manual project entry"}
              </button>
            </div>
            {showAdvancedCreate && (
              <form onSubmit={onCreate} className="card projects-create">
                <p className="muted" style={{ marginTop: 0 }}>
                  Prefer the chat-first quick start above. Use this manual form only when you need to pre-seed description or feature bullets.
                </p>
                <input
                  className="input"
                  placeholder="Name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
                <textarea
                  className="textarea"
                  placeholder="Description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  required
                />
                <textarea
                  className="textarea"
                  placeholder="Features (one per line)"
                  value={features}
                  onChange={(e) => setFeatures(e.target.value)}
                  rows={4}
                />
                <div className="projects-create__actions">
                  <button
                    className="btn"
                    type="button"
                    onClick={() => {
                      setShowAdvancedCreate(false);
                      setName("");
                      setDescription("");
                      setFeatures("");
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary"
                    type="submit"
                    disabled={creating}
                  >
                    {creating ? "Creating…" : "Create"}
                  </button>
                </div>
              </form>
            )}
          </div>
        ) : (
          <p className="muted">You have read-only access.</p>
        )}
      </section>
    </div>
  );
}
