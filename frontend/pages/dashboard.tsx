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
import logoFull from "../public/logo-full.svg";

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

  const phaseLabels = [
    "Charter",
    "Specifications",
    "Design",
    "Implementation",
    "Testing",
    "Deployment",
  ];

  const currentIndex = useMemo(() => {
    let idx = 0; // Charter (default)
    if (charterApproved) idx = 1;
    if (reqCount > 0) idx = 2;
    if (srsApproved) idx = 3;
    if (sddApproved) idx = 4;
    if (testApproved) idx = 5;
    return Math.min(idx, phaseLabels.length - 1);
  }, [charterApproved, reqCount, srsApproved, sddApproved, testApproved]);

  const currentPhaseLabel = phaseLabels[currentIndex] ?? phaseLabels[0];

  const selectedProject = useMemo(
    () => projects.find((p) => p.project_id === selected) || null,
    [projects, selected],
  );

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
          onClick: handleOpenProjects,
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
      <div className="dashboard-landing">
        <header className="dashboard-landing__top">
          <div
            className="dashboard-landing__brand"
            aria-label="OPNXT portfolio pulse"
          >
            <Image
              src={logoFull}
              alt="OPNXT"
              priority
              className="dashboard-landing__logo"
            />
            <span>Concept → Delivery mission control</span>
          </div>
          <div className="dashboard-landing__links">
            <Link href="/projects" className="btn btn-secondary">
              Create project
            </Link>
            <button type="button" className="btn" onClick={openAssistant}>
              Open MVP assistant
            </button>
          </div>
        </header>
        <div className="dashboard-landing__grid">
          <section className="dashboard-pulse" aria-labelledby="portfolio-pulse">
            <header className="dashboard-pulse__header">
              <span className="badge">Portfolio pulse</span>
              <h1 id="portfolio-pulse">Track readiness from concept to launch</h1>
              <p>
                AI keeps requirements, approvals, and delivery telemetry synchronized so
                nothing falls through.
              </p>
            </header>
            <div className="dashboard-pulse__stats" role="list">
              {[
                {
                  title: "Active initiatives",
                  value: projects.length
                    ? projects.length.toString().padStart(2, "0")
                    : "—",
                },
                {
                  title: "Requirements captured",
                  value: reqCount ? reqCount.toString().padStart(2, "0") : "—",
                },
                {
                  title: "Current phase gate",
                  value: currentPhaseLabel,
                },
              ].map((stat) => (
                <article key={stat.title} className="dashboard-pulse__stat" role="listitem">
                  <span>{stat.title}</span>
                  <strong>{stat.value}</strong>
                </article>
              ))}
            </div>
          </section>

          <aside className="assistant-callout" aria-labelledby="assistant-callout-title">
            <header>
              <h2 id="assistant-callout-title">MVP assistant</h2>
              <p>
                Launch a quick session to capture discovery details and generate documentation
                without leaving the dashboard.
              </p>
            </header>
            <div className="assistant-callout__actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={openAssistant}
              >
                Start new session
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleOpenProjects}
              >
                View projects
              </button>
            </div>
            <div className="assistant-callout__scenarios" aria-label="Popular assistant prompts">
              {assistantScenarios.map((scenario) => (
                <button
                  key={scenario.label}
                  type="button"
                  onClick={() => launchAssistant(scenario.value)}
                  className="assistant-callout__chip"
                  disabled={assistantLoading}
                >
                  {assistantLoading ? "Starting…" : scenario.label}
                </button>
              ))}
            </div>
            {assistantError && !assistantOpen && (
              <p className="assistant-callout__error" role="alert">
                {assistantError}
              </p>
            )}
          </aside>
        </div>
      </div>

      <section className="dashboard-panels" aria-label="Delivery insights">
        <div className="panel panel--wide">
          <header>
            <div>
              <h2>Next best action</h2>
              <p>AI guidance on what to move forward next.</p>
            </div>
            <button
              className="btn btn-tertiary"
              type="button"
              onClick={() => router.push("/projects")}
            >
              View portfolio
            </button>
          </header>
          <div className="panel__body">
            <NextAction
              message={nextActionConfig.message}
              primary={nextActionConfig.primary}
              secondary={nextActionConfig.secondary}
            />
          </div>
        </div>

        <div className="panel">
          <header>
            <h2>Projects</h2>
            <p>Select an initiative to review context.</p>
          </header>
          <div className="panel__body">
            <ul className="panel-list">
              {projects.map((p) => (
                <li key={p.project_id}>
                  <button
                    type="button"
                    onClick={() => setSelected(p.project_id)}
                    className={
                      selected === p.project_id
                        ? "panel-list__item panel-list__item--active"
                        : "panel-list__item"
                    }
                  >
                    <div>
                      <strong>{p.name}</strong>
                      <span>{p.current_phase || p.status}</span>
                    </div>
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path
                        d="M8 5l8 7-8 7"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        fill="none"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </li>
              ))}
              {!projects.length && (
                <li className="panel-list__empty">
                  No projects yet. Launch your first initiative from the MVP.
                </li>
              )}
            </ul>
          </div>
        </div>

        <div className="panel">
          <header>
            <h2>Recent activity</h2>
            <p>Latest AI assists, approvals, and document drops.</p>
          </header>
          <div className="panel__body">
            <p className="muted">
              No recent activity. Engage the MVP assistant to kickstart
              delivery.
            </p>
          </div>
        </div>

        <div className="panel panel--wide">
          <header>
            <h2>Phase gate readiness</h2>
            <p>
              Follow the enterprise checkpoints as you move from concept to
              launch.
            </p>
          </header>
          <div className="panel__body">
            <ol className="phase-track">
              {phaseLabels.map((label, idx) => (
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
        </div>
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
