import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import Image from "next/image";
import {
  listProjects,
  getProjectContext,
  getAccessToken,
  setAccessToken,
  me,
  Project,
  ProjectContext,
  createProject,
  ProjectCreate,
} from "../lib/api";
import NextAction from "../components/ui/NextAction";
import KpiCard from "../components/ui/KpiCard";
import logoFull from "../public/logo-full.svg";

const PHASE_LABELS = [
  "Charter",
  "Specifications",
  "Design",
  "Implementation",
  "Testing",
  "Deployment",
];

export default function DashboardPage() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [ctx, setCtx] = useState<ProjectContext | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantIdea, setAssistantIdea] = useState("");
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [assistantError, setAssistantError] = useState<string | null>(null);
  const [phaseFilter, setPhaseFilter] = useState<string>("All");

  useEffect(() => {
    (async () => {
      const token = getAccessToken();
      if (!token) {
        setAuthed(false);
        setAuthChecked(true);
        router.replace("/mvp");
        return;
      }
      try {
        await me();
        setAuthed(true);
      } catch {
        setAccessToken(null);
        setAuthed(false);
        router.replace("/mvp");
      } finally {
        setAuthChecked(true);
      }
    })();
  }, [router]);

  useEffect(() => {
    if (!authed) {
      setProjects([]);
      setSelected(null);
      return;
    }
    (async () => {
      try {
        const ps = await listProjects();
        setProjects(ps);
        if (ps.length && !selected) setSelected(ps[0].project_id);
      } catch {}
    })();
  }, [authed]);

  useEffect(() => {
    if (!authed || !selected) return;
    (async () => {
      try {
        setLoading(true);
        const c = await getProjectContext(selected);
        setCtx(c);
      } catch {
      } finally {
        setLoading(false);
      }
    })();
  }, [authed, selected]);

  const approvals = useMemo(() => (ctx as any)?.data?.approvals || {}, [ctx]);
  const answers = useMemo(() => (ctx as any)?.data?.answers || {}, [ctx]);
  const reqCount = useMemo(
    () =>
      Array.isArray(answers?.Requirements) ? answers.Requirements.length : 0,
    [answers],
  );
  const charterApproved = !!approvals?.["ProjectCharter.md"]?.approved;
  const srsApproved = !!approvals?.["SRS.md"]?.approved;
  const sddApproved = !!approvals?.["SDD.md"]?.approved;
  const testApproved = !!approvals?.["TestPlan.md"]?.approved;

  const normalizedPhase = (phase: string | undefined, status: string | undefined) => {
    const value = (phase || status || "").toLowerCase();
    const match = PHASE_LABELS.find((label) => value.includes(label.toLowerCase()));
    return match ?? PHASE_LABELS[0];
  };

  const phaseCounts = useMemo(() => {
    const counts = new Map<string, number>();
    PHASE_LABELS.forEach((label) => counts.set(label, 0));
    projects.forEach((project) => {
      const phase = normalizedPhase(project.current_phase, project.status);
      counts.set(phase, (counts.get(phase) ?? 0) + 1);
    });
    return counts;
  }, [projects]);

  const engagedPhaseCount = useMemo(
    () => Array.from(phaseCounts.values()).filter((count) => count > 0).length,
    [phaseCounts],
  );

  const dominantPhase = useMemo(() => {
    let maxPhase = PHASE_LABELS[0];
    let max = -1;
    PHASE_LABELS.forEach((label) => {
      const value = phaseCounts.get(label) ?? 0;
      if (value > max) {
        max = value;
        maxPhase = label;
      }
    });
    return maxPhase;
  }, [phaseCounts]);

  const dominantPhaseCount = useMemo(
    () => phaseCounts.get(dominantPhase) ?? 0,
    [phaseCounts, dominantPhase],
  );

  const testingReadyCount = useMemo(
    () =>
      projects.filter((project) => {
        const phase = normalizedPhase(project.current_phase, project.status);
        return phase === "Testing" || phase === "Deployment";
      }).length,
    [projects],
  );

  const engagedPhasePercent = useMemo(() => {
    if (!projects.length) return 0;
    return Math.round((engagedPhaseCount / PHASE_LABELS.length) * 100);
  }, [projects.length, engagedPhaseCount]);

  const phaseFilters = useMemo(() => ["All", ...PHASE_LABELS], []);

  const filteredProjects = useMemo(() => {
    if (phaseFilter === "All") return projects;
    return projects.filter((project) =>
      normalizedPhase(project.current_phase, project.status) === phaseFilter,
    );
  }, [projects, phaseFilter]);

  const latestUpdatedProject = useMemo(() => {
    if (!projects.length) return null;
    return [...projects].sort((a, b) => {
      const dateA = new Date(a.updated_at || a.created_at || 0).getTime();
      const dateB = new Date(b.updated_at || b.created_at || 0).getTime();
      return dateB - dateA;
    })[0];
  }, [projects]);

  const latestUpdateLabel = useMemo(() => {
    if (!latestUpdatedProject) return "—";
    const stamp = latestUpdatedProject.updated_at || latestUpdatedProject.created_at;
    if (!stamp) return latestUpdatedProject.name;
    try {
      return new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(stamp));
    } catch {
      return latestUpdatedProject.name;
    }
  }, [latestUpdatedProject]);

  const hasProjects = projects.length > 0;

  const currentIndex = useMemo(() => {
    let idx = 0; // Charter (default)
    if (charterApproved) idx = 1;
    if (reqCount > 0) idx = 2;
    if (srsApproved) idx = 3;
    if (sddApproved) idx = 4;
    if (testApproved) idx = 5;
    return Math.min(idx, PHASE_LABELS.length - 1);
  }, [charterApproved, reqCount, srsApproved, sddApproved, testApproved]);

  const currentPhaseLabel = PHASE_LABELS[currentIndex] ?? PHASE_LABELS[0];

  const selectedProject = useMemo(
    () => projects.find((p) => p.project_id === selected) || null,
    [projects, selected],
  );

  useEffect(() => {
    if (!filteredProjects.length) {
      setSelected(null);
      return;
    }
    if (!selected || !filteredProjects.some((project) => project.project_id === selected)) {
      setSelected(filteredProjects[0].project_id);
    }
  }, [filteredProjects, selected]);

  const assistantScenarios = useMemo(
    () => [
      {
        label: "Healthcare",
        value: "Healthcare Appointment System",
      },
      { label: "Fintech", value: "Digital Banking Platform" },
      { label: "Logistics", value: "Supply Chain Visibility Hub" },
      { label: "Custom", value: "Custom AI Delivery Assistant" },
    ],
    [],
  );

  const handleOpenProjects = () => router.push("/projects");
  const handleOpenProject = (projectId: string) =>
    router.push(`/projects/${encodeURIComponent(projectId)}`);
  const handleOpenProjectTab = (tab: string) => {
    if (!selected) {
      handleOpenProjects();
      return;
    }
    router.push(
      `/projects/${encodeURIComponent(selected)}?tab=${encodeURIComponent(tab)}`,
    );
  };

  const openAssistant = () => {
    setAssistantOpen(true);
    setAssistantIdea("");
    setAssistantError(null);
  };

  const closeAssistant = () => {
    if (assistantLoading) return;
    setAssistantOpen(false);
    setAssistantIdea("");
    setAssistantError(null);
  };

  const launchAssistant = async (concept: string) => {
    const trimmed = concept.trim();
    if (!trimmed) {
      setAssistantError("Add a short description so the assistant has context.");
      return;
    }
    try {
      setAssistantLoading(true);
      setAssistantError(null);
      const payload: ProjectCreate = {
        name: trimmed.slice(0, 60),
        description: trimmed,
        features: "",
      } as ProjectCreate;
      const proj = await createProject(payload);
      const prefill = encodeURIComponent(
        `I want to build: ${trimmed}. Help capture clear, testable functional and non-functional requirements, then generate a Charter, SRS, SDD, and Test Plan.`,
      );
      setAssistantOpen(false);
      await router.push(
        `/start/${encodeURIComponent(proj.project_id)}?prefill=${prefill}`,
      );
    } catch (err: any) {
      setAssistantError(err?.message || "Unable to start assistant. Try again.");
    } finally {
      setAssistantLoading(false);
    }
  };

  const handleAssistantSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await launchAssistant(assistantIdea);
  };

  const nextActionConfig = useMemo(() => {
    if (loading) {
      return {
        message: "Analyzing portfolio telemetry…",
        primary: { label: "Refreshing", onClick: undefined },
      };
    }

    if (!projects.length) {
      return {
        message:
          "Launch your first initiative to unlock delivery governance and AI documents.",
        primary: {
          label: "Create a project",
          onClick: openAssistant,
          variant: "primary" as const,
        },
      };
    }

    if (!selectedProject) {
      return {
        message:
          "Select a project to review its readiness and next best actions.",
        primary: {
          label: "View projects",
          onClick: handleOpenProjects,
          variant: "primary" as const,
        },
      };
    }

    if (!charterApproved) {
      return {
        message: `Finalize the charter for ${selectedProject.name} to progress through phase gates.`,
        primary: {
          label: "Open charter workspace",
          onClick: () => handleOpenProjectTab("Charter"),
          variant: "primary" as const,
        },
      };
    }

    if (!reqCount) {
      return {
        message: `Capture key requirements so design, testing, and delivery can stay aligned.`,
        primary: {
          label: "Collect requirements",
          onClick: () => handleOpenProjectTab("Requirements"),
          variant: "primary" as const,
        },
      };
    }

    if (!srsApproved) {
      return {
        message: `Review and approve the Specifications (SRS) for ${selectedProject.name}.`,
        primary: {
          label: "Approve SRS",
          onClick: () => handleOpenProjectTab("Specifications"),
          variant: "primary" as const,
        },
      };
    }

    if (!sddApproved) {
      return {
        message: `Confirm the system design (SDD) to keep build teams unblocked.`,
        primary: {
          label: "Review design",
          onClick: () => handleOpenProjectTab("Design"),
          variant: "primary" as const,
        },
      };
    }

    if (!testApproved) {
      return {
        message: `Close out the Test Plan so deployment can proceed with confidence.`,
        primary: {
          label: "Finalize testing",
          onClick: () => handleOpenProjectTab("Testing"),
          variant: "primary" as const,
        },
      };
    }

    return {
      message: `All governance checkpoints are green. Keep velocity high or generate fresh docs from the MVP assistant.`,
      primary: {
        label: "Open MVP assistant",
        onClick: openAssistant,
        variant: "primary" as const,
      },
      secondary: [{ label: "View projects", onClick: handleOpenProjects }],
    };
  }, [
    loading,
    projects.length,
    selectedProject,
    charterApproved,
    reqCount,
    srsApproved,
    sddApproved,
    testApproved,
    handleOpenProjects,
    openAssistant,
  ]);

  useEffect(() => {
    // Future: fetch KPIs and activity
  }, []);

  if (!authChecked) {
    return (
      <div className="dashboard-shell" aria-live="polite">
        <section className="dashboard-hero dashboard-hero--loading">
          <div className="dashboard-hero__content">
            <div>
              <span className="badge badge--glow">Preparing dashboard…</span>
              <h1>Concept → Delivery mission control</h1>
              <p>Checking your session and loading portfolio telemetry.</p>
            </div>
          </div>
        </section>
      </div>
    );
  }

  if (!authed) {
    return null; // Redirect handled in useEffect
  }

  return (
    <div className="dashboard-shell" aria-live="polite">
      <header className="dashboard-header">
        <div
          className="dashboard-header__brand"
          aria-label="OPNXT portfolio pulse"
        >
          <Image src={logoFull} alt="OPNXT" priority className="dashboard-header__logo" />
          <div className="dashboard-header__text">
            <span className="badge">Portfolio pulse</span>
            <h1>Concept → Delivery mission control</h1>
            <p>
              AI keeps requirements, approvals, and delivery telemetry synchronized so nothing falls
              through.
            </p>
          </div>
        </div>
        <div className="dashboard-header__actions">
          <button type="button" className="btn btn-primary" onClick={openAssistant}>
            Start new initiative
          </button>
          <Link href="/projects" className="btn btn-secondary">
            View portfolio
          </Link>
        </div>
      </header>

      <section className="dashboard-ribbon" aria-label="Portfolio metrics">
        <KpiCard
          title="Active initiatives"
          value={hasProjects ? projects.length.toString().padStart(2, "0") : "—"}
          description="Currently tracked projects"
          trendLabel={hasProjects ? "Live" : undefined}
          trendDirection={hasProjects ? "up" : "down"}
          onClick={hasProjects ? handleOpenProjects : undefined}
        />
        <KpiCard
          title="Phases engaged"
          value={engagedPhaseCount ? engagedPhaseCount.toString().padStart(2, "0") : "—"}
          description="Phase gates with active work"
          trendLabel={hasProjects ? `${engagedPhasePercent}% coverage` : undefined}
          trendDirection={engagedPhaseCount ? (engagedPhaseCount >= 3 ? "up" : "flat") : "down"}
        />
        <KpiCard
          title="Dominant phase"
          value={hasProjects ? dominantPhase : "—"}
          description={hasProjects ? `${dominantPhaseCount} initiatives` : "No active phases yet"}
          trendLabel={hasProjects ? "Focus" : undefined}
          trendDirection="flat"
          onClick={hasProjects ? () => setPhaseFilter(dominantPhase) : undefined}
        />
        <KpiCard
          title="Testing runway"
          value={testingReadyCount ? testingReadyCount.toString().padStart(2, "0") : "—"}
          description="Ready for validation"
          trendLabel={testingReadyCount ? "Ready" : undefined}
          trendDirection={testingReadyCount ? "up" : "flat"}
          onClick={testingReadyCount ? () => setPhaseFilter("Testing") : undefined}
        />
        <KpiCard
          title="Latest sync"
          value={hasProjects ? latestUpdateLabel : "Awaiting kickoff"}
          description={
            latestUpdatedProject
              ? latestUpdatedProject.name
              : "Launch your first initiative to start telemetry."
          }
          trendLabel={latestUpdatedProject ? "Open" : undefined}
          trendDirection={latestUpdatedProject ? "up" : "flat"}
          onClick={
            latestUpdatedProject
              ? () => handleOpenProject(latestUpdatedProject.project_id)
              : openAssistant
          }
        />
      </section>

      <section className="dashboard-layout" aria-label="Delivery insights">
        <div className="dashboard-layout__main">
          <article className="dashboard-card dashboard-card--band">
            <NextAction
              className="next-action--fluid"
              message={nextActionConfig.message}
              primary={nextActionConfig.primary}
              secondary={nextActionConfig.secondary}
            />
          </article>

          <article className="dashboard-card">
            <header className="dashboard-card__header">
              <div>
                <h2>Initiatives</h2>
                <p>Browse active delivery workstreams by phase.</p>
              </div>
              <label className="dashboard-select">
                <span className="sr-only">Filter by phase</span>
                <select value={phaseFilter} onChange={(event) => setPhaseFilter(event.target.value)}>
                  {phaseFilters.map((phase) => (
                    <option key={phase} value={phase}>
                      {phase}
                    </option>
                  ))}
                </select>
              </label>
            </header>
            <div className="dashboard-card__body">
              {filteredProjects.length ? (
                <ul className="initiative-list">
                  {filteredProjects.map((project) => {
                    const phase = normalizedPhase(project.current_phase, project.status);
                    const timestamp = project.updated_at || project.created_at;
                    const detail = timestamp
                      ? new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(
                          new Date(timestamp),
                        )
                      : "New";
                    return (
                      <li key={project.project_id}>
                        <button
                          type="button"
                          onClick={() => handleOpenProject(project.project_id)}
                          className="initiative-list__item"
                        >
                          <div className="initiative-list__meta">
                            <span className="initiative-list__phase">{phase}</span>
                            <span className="initiative-list__updated">{detail}</span>
                          </div>
                          <div className="initiative-list__content">
                            <strong>{project.name}</strong>
                            <span>{project.description || "Awaiting charter summary."}</span>
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="initiative-empty">
                  <h3>{phaseFilter === "All" ? "No projects yet" : `No projects in ${phaseFilter}`}</h3>
                  <p>
                    {hasProjects
                      ? "Adjust filters or launch the MVP assistant to unlock new initiatives."
                      : "Kick off your first initiative to activate portfolio telemetry."}
                  </p>
                  <div className="initiative-empty__actions">
                    <button type="button" className="btn btn-primary" onClick={openAssistant}>
                      Start with MVP assistant
                    </button>
                    {phaseFilter !== "All" && (
                      <button type="button" className="btn" onClick={() => setPhaseFilter("All")}>
                        Reset filter
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </article>

          <article className="dashboard-card">
            <header className="dashboard-card__header">
              <div>
                <h2>Phase gate readiness</h2>
                <p>Follow enterprise checkpoints as you advance toward launch.</p>
              </div>
              {selectedProject ? (
                <button
                  type="button"
                  className="btn btn-tertiary"
                  onClick={() => handleOpenProject(selectedProject.project_id)}
                >
                  View project
                </button>
              ) : null}
            </header>
            <div className="dashboard-card__body">
              <ol className="phase-track phase-track--inline">
                {PHASE_LABELS.map((label, idx) => (
                  <li
                    key={label}
                    className={
                      idx <= currentIndex
                        ? "phase-track__step phase-track__step--active"
                        : "phase-track__step"
                    }
                  >
                    <span>{label}</span>
                  </li>
                ))}
              </ol>
            </div>
          </article>
        </div>

        <aside className="dashboard-layout__sidebar" aria-label="Assistant and activity">
          <article className="dashboard-card dashboard-card--assistant">
            <header className="dashboard-card__header">
              <h2>MVP assistant</h2>
              <p>Launch a guided discovery to capture requirements and generate docs.</p>
            </header>
            <div className="dashboard-card__body">
              <div className="assistant-actions">
                <button type="button" className="btn btn-primary" onClick={openAssistant}>
                  Start new session
                </button>
                <button type="button" className="btn" onClick={handleOpenProjects}>
                  View portfolio
                </button>
              </div>
              <div className="assistant-chips" aria-label="Popular assistant prompts">
                {assistantScenarios.map((scenario) => (
                  <button
                    key={scenario.label}
                    type="button"
                    onClick={() => launchAssistant(scenario.value)}
                    className="assistant-chip"
                    disabled={assistantLoading}
                  >
                    {assistantLoading ? "Starting…" : scenario.label}
                  </button>
                ))}
              </div>
              {assistantError && !assistantOpen && (
                <p className="assistant-error" role="alert">
                  {assistantError}
                </p>
              )}
            </div>
          </article>

          <article className="dashboard-card">
            <header className="dashboard-card__header">
              <div>
                <h2>Recent activity</h2>
                <p>Latest AI assists, approvals, and doc drops.</p>
              </div>
            </header>
            <div className="dashboard-card__body activity-empty">
              <p>
                No recent activity yet. Use the MVP assistant to kickstart delivery telemetry.
              </p>
            </div>
          </article>
        </aside>
      </section>

      {assistantOpen && (
        <div className="assistant-overlay" role="dialog" aria-modal="true">
          <div className="assistant-overlay__backdrop" onClick={closeAssistant} />
          <div className="assistant-overlay__panel">
            <header className="assistant-overlay__header">
              <div>
                <span className="badge">MVP assistant</span>
                <h2>What are we capturing?</h2>
                <p>
                  Describe the initiative. The assistant will create a workspace and guide you
                  through requirements, design, and documents.
                </p>
              </div>
              <button
                type="button"
                className="assistant-overlay__close"
                onClick={closeAssistant}
                aria-label="Close assistant"
              >
                ×
              </button>
            </header>
            <form className="assistant-overlay__form" onSubmit={handleAssistantSubmit}>
              <label htmlFor="assistant-idea">Initiative description</label>
              <textarea
                id="assistant-idea"
                value={assistantIdea}
                onChange={(event) => setAssistantIdea(event.target.value)}
                placeholder="e.g., Modernize patient intake with a digital triage assistant"
                disabled={assistantLoading}
                required
              />
              {assistantError && (
                <p className="assistant-overlay__error" role="alert">
                  {assistantError}
                </p>
              )}
              <div className="assistant-overlay__actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={closeAssistant}
                  disabled={assistantLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={assistantLoading || !assistantIdea.trim()}
                >
                  {assistantLoading ? "Opening…" : "Open assistant"}
                </button>
              </div>
            </form>
            <div className="assistant-overlay__suggestions" aria-label="Suggested prompts">
              {assistantScenarios.map((scenario) => (
                <button
                  key={scenario.label}
                  type="button"
                  onClick={() => {
                    setAssistantIdea(scenario.value);
                    setAssistantError(null);
                  }}
                  className="assistant-overlay__chip"
                  disabled={assistantLoading}
                >
                  {scenario.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
