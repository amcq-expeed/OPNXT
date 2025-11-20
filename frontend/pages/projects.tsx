import Link from "next/link";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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

type WorkspaceStat = {
  label: string;
  value: string;
};

type WorkspaceScenario = {
  label: string;
  description: string;
  prompt: string;
};

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
  const [startingQuick, setStartingQuick] = useState<boolean>(false);
  const [quickDraft, setQuickDraft] = useState<string>("");

  // Traceability overlay toggle for doc generation
  const [traceOverlay, setTraceOverlay] = useState<boolean>(true);

  const buildQuickStartName = useCallback((base: string) => {
    const stamp = new Date()
      .toISOString()
      .replace(/[:.]/g, "-")
      .replace("T", " ")
      .replace(/Z$/, "");
    const candidate = `${base} Quick Start ${stamp}`.trim();
    return candidate.length > 80 ? candidate.slice(0, 80) : candidate;
  }, []);

  const composerRef = useRef<HTMLTextAreaElement | null>(null);

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

  const navigateToWorkspace = useCallback(
    async (payload: ProjectCreate, prefill: string) => {
      try {
        setStartingQuick(true);
        const proj = await createProject(payload);
        setItems((prev) => [
          proj,
          ...prev.filter((p) => p.project_id !== proj.project_id),
        ]);
        await router.push(
          `/projects/${encodeURIComponent(proj.project_id)}?tab=Requirements&prefill=${encodeURIComponent(prefill)}`,
        );
      } catch (e: any) {
        const detail = e?.message || "We couldn't start that quick capture. Try again.";
        setError(detail);
        setNotice(null);
      } finally {
        setStartingQuick(false);
        setQuickDraft("");
      }
    },
    [router],
  );

  const onQuickStartSubmit = useCallback(() => {
    const text = quickDraft.trim();
    if (!text) return;
    const payload: ProjectCreate = {
      name: buildQuickStartName(text.length > 60 ? text.slice(0, 60) : text),
      description: text,
      features: "",
    } as ProjectCreate;
    const prefill = `Concept to Deployment: ${text}. Lead me from discovery through architecture, implementation, testing, and deployment. Capture functional and non-functional requirements, propose architecture decisions, outline implementation steps, recommend testing strategy, and prepare Charter, SRS, SDD, and Test Plan milestones as we progress.`;
    void navigateToWorkspace(payload, prefill);
  }, [buildQuickStartName, navigateToWorkspace, quickDraft]);

  const onQuickStartScenario = useCallback(
    (scenario: WorkspaceScenario) => {
      const payload: ProjectCreate = {
        name: buildQuickStartName(scenario.label),
        description: `Quick Start: ${scenario.label}`,
        features: "",
      } as ProjectCreate;
      void navigateToWorkspace(payload, scenario.prompt);
    },
    [buildQuickStartName, navigateToWorkspace],
  );

  const workspaceStats = useMemo<WorkspaceStat[]>(
    () => [
      {
        label: "Active initiatives",
        value: items.length ? items.length.toString().padStart(2, "0") : "—",
      },
      {
        label: "Traceability overlay",
        value: traceOverlay ? "Enabled" : "Disabled",
      },
      {
        label: "Quick starts today",
        value: startingQuick ? "Launching…" : "Ready",
      },
      {
        label: "Chat insight library",
        value: "Templates & history search available",
      },
    ],
    [items.length, traceOverlay, startingQuick],
  );

  const workspaceScenarios = useMemo<WorkspaceScenario[]>(
    () => [
      {
        label: "Healthcare",
        description: "Patient access, scheduling, and compliance ready.",
        prompt:
          "Concept to Deployment scenario: Healthcare Appointment System. Confirm regulatory context, then guide requirements, architecture, implementation, testing, and deployment readiness. Produce Charter, SRS, SDD, and Test Plan milestones.",
      },
      {
        label: "Banking",
        description: "Payments, authentication, audit controls, SLAs.",
        prompt:
          "Concept to Deployment scenario: Bank Payment Platform. Capture compliance constraints, then lead me through requirements, architecture guidance, implementation plan, testing, and deployment readiness with Charter, SRS, SDD, and Test Plan outputs.",
      },
      {
        label: "E-commerce",
        description: "Catalog, checkout, fulfillment, and analytics.",
        prompt:
          "Concept to Deployment scenario: E-commerce Store. Gather product and fulfillment context, then drive requirements, architecture, implementation, testing, and deployment plan with Charter, SRS, SDD, and Test Plan milestones.",
      },
      {
        label: "Custom",
        description: "Use your own initiative and tailor the journey instantly.",
        prompt:
          "Concept to Deployment workspace kickoff. Ask for critical context, then guide requirements, architecture, implementation, testing, and deployment readiness. Produce Charter, SRS, SDD, and Test Plan as gates are met.",
      },
    ],
    [],
  );

  const scrollToComposer = useCallback(() => {
    requestAnimationFrame(() => {
      composerRef.current?.focus();
      composerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, []);

  const scenarioIcons = useMemo<Record<string, string>>(
    () => ({
      Healthcare: "🏥",
      Banking: "🏦",
      "E-commerce": "🛒",
      Custom: "⚙️",
    }),
    [],
  );

  const quickCards = useMemo(
    () =>
      [
        {
          key: "custom",
          title: "Custom workspace",
          description: "Bring your own initiative and capture requirements in a guided chat.",
          icon: "🧭",
          onClick: () => {
            setShowAdvancedCreate(false);
            scrollToComposer();
          },
        },
        ...workspaceScenarios.map((scenario) => ({
          key: scenario.label,
          title: scenario.label,
          description: scenario.description,
          icon: scenarioIcons[scenario.label] ?? "✨",
          onClick: () => onQuickStartScenario(scenario),
        })),
      ],
    [onQuickStartScenario, scenarioIcons, scrollToComposer, workspaceScenarios],
  );

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

  const hasProjects = filtered.length > 0;

  return (
    <div className="dashboard-shell projects-shell" aria-live="polite">
      <header className="dashboard-hero projects-hero">
        <span className="dashboard-hero__eyebrow">Projects workspace</span>
        <div className="dashboard-hero__title">
          <h1 className="dashboard-hero__headline">Launch, orchestrate, and approve</h1>
          <p className="dashboard-hero__copy">
            Create new initiatives, advance SDLC phases, and jump into live workspaces for inline editing and approvals.
          </p>
        </div>
        <ul className="projects-hero__metrics" aria-label="Workspace metrics">
          {workspaceStats.map((stat) => (
            <li key={stat.label}>
              <span className="projects-hero__metric-value">{stat.value}</span>
              <span className="projects-hero__metric-label">{stat.label}</span>
            </li>
          ))}
        </ul>
        <div className="projects-hero__actions" role="navigation" aria-label="Quick links">
          <button type="button" onClick={() => router.push("/documents")}>
            <span>Review documents</span>
          </button>
          <button type="button" onClick={() => router.push("/templates")}>
            <span>Manage templates</span>
          </button>
        </div>
      </header>

      {loading && (
        <div className="dashboard-status" role="status">
          Loading projects…
        </div>
      )}
      {notice && (
        <div className="dashboard-status" role="status">
          {notice}
        </div>
      )}
      {error && (
        <div className="dashboard-status dashboard-status--error" role="alert">
          {error}
        </div>
      )}

      <main className="dashboard-main projects-main">
        <section className="projects-quick-start" aria-label="Quick start accelerators">
          <div className="dashboard-actions__panel" role="list">
            {quickCards.map((card) => (
              <button
                key={card.key}
                type="button"
                className="quick-card"
                onClick={card.onClick}
                disabled={startingQuick}
              >
                <span className="quick-card__icon" aria-hidden="true">
                  {card.icon}
                </span>
                <span className="quick-card__body">
                  <span className="quick-card__title">{card.title}</span>
                  <span className="quick-card__description">{card.description}</span>
                </span>
                <span className="quick-card__cta" aria-hidden="true">
                  {startingQuick ? "Working…" : "Launch"}
                  <svg viewBox="0 0 20 20" focusable="false" aria-hidden="true">
                    <path
                      d="M7.5 5l4.5 5-4.5 5"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="projects-composer" aria-label="Describe your initiative">
          <form
            className="projects-composer__form"
            onSubmit={(event) => {
              event.preventDefault();
              onQuickStartSubmit();
            }}
          >
            <label htmlFor="project-quick-draft" className="projects-composer__label">
              Describe your initiative
            </label>
            <textarea
              id="project-quick-draft"
              ref={composerRef}
              className="projects-composer__textarea"
              placeholder="Outline the product, goal, or challenge you want to tackle…"
              value={quickDraft}
              onChange={(e) => setQuickDraft(e.target.value)}
              rows={4}
              disabled={startingQuick}
            />
            <div className="projects-composer__footer">
              <button
                type="submit"
                className="btn btn-primary projects-composer__submit"
                disabled={startingQuick || !quickDraft.trim()}
              >
                {startingQuick ? "Starting…" : "Launch workspace"}
              </button>
              {canWrite(currentUser) && (
                <button
                  type="button"
                  className="projects-composer__toggle"
                  onClick={() => setShowAdvancedCreate((prev) => !prev)}
                >
                  {showAdvancedCreate ? "Hide manual create" : "Manual project entry"}
                </button>
              )}
            </div>
          </form>

          {canWrite(currentUser) && showAdvancedCreate && (
            <form onSubmit={onCreate} className="projects-create-form">
              <p className="projects-create-form__hint">
                Prefer the chat-first quick starts above. Use manual entry only when you need to pre-seed details.
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
              <div className="projects-create-form__actions">
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
                <button className="btn btn-primary" type="submit" disabled={creating}>
                  {creating ? "Creating…" : "Create"}
                </button>
              </div>
            </form>
          )}
        </section>

        <section className="projects-list" aria-label="Manage projects">
          <header className="projects-list__header">
            <div>
              <h2>Projects</h2>
              <p className="projects-list__subtitle">
                Search, advance phases, regenerate documents, or jump into the live workspace for each initiative.
              </p>
            </div>
            <label className="projects-list__trace-toggle">
              <input
                type="checkbox"
                checked={traceOverlay}
                onChange={(e) => setTraceOverlay(e.target.checked)}
              />
              <span>Include traceability map when generating docs</span>
            </label>
          </header>

          <div className="projects-list__filters">
            <label className="projects-list__search">
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

          {!hasProjects && !loading && !error && (
            <div className="projects-list__empty" role="status">
              <h3>No projects yet</h3>
              <p>Use the quick start cards above to launch your first workspace.</p>
            </div>
          )}

          {hasProjects && (
            <div className="projects-list__grid">
              {filtered.map((p) => (
                <article key={p.project_id} className="projects-card">
                  <header className="projects-card__header">
                    <h3>{p.name}</h3>
                    <span className="projects-card__badge">{p.current_phase}</span>
                  </header>
                  <p className="projects-card__meta">ID: {p.project_id}</p>
                  <div className="projects-card__actions">
                    <Link className="btn" href={`/projects/${encodeURIComponent(p.project_id)}`}>
                      Open workspace
                    </Link>
                    {canWrite(currentUser) && (
                      <button
                        className="btn"
                        onClick={() => onAdvance(p.project_id, p.current_phase)}
                        disabled={
                          isFinalPhase(p.current_phase) || advancingId === p.project_id
                        }
                      >
                        {advancingId === p.project_id
                          ? "Advancing…"
                          : isFinalPhase(p.current_phase)
                            ? "At final gate"
                            : "Advance phase"}
                      </button>
                    )}
                    {canWrite(currentUser) && (
                      <button
                        className="btn"
                        onClick={() => onGenerateDocs(p.project_id)}
                        disabled={generatingId === p.project_id}
                      >
                        {generatingId === p.project_id ? "Generating…" : "Generate docs"}
                      </button>
                    )}
                    {isAdmin(currentUser) && (
                      <button
                        className="btn btn-danger"
                        onClick={() => onDelete(p.project_id)}
                        disabled={deletingId === p.project_id}
                      >
                        {deletingId === p.project_id ? "Deleting…" : "Delete"}
                      </button>
                    )}
                  </div>
                  {docMap[p.project_id] && (
                    <div className="projects-card__docs">
                      <p>Recently generated artifacts:</p>
                      <ul>
                        {docMap[p.project_id].artifacts.map((artifact) => (
                          <li key={artifact.filename}>
                            <a
                              href={artifactUrl(p.project_id, artifact.filename)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {artifact.filename}
                            </a>
                          </li>
                        ))}
                      </ul>
                      <a className="btn btn-inline" href={zipUrl(p.project_id)}>
                        Download bundle
                      </a>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      </main>

      {!canWrite(currentUser) && (
        <p className="projects-readonly">You have read-only access.</p>
      )}
    </div>
  );
}
