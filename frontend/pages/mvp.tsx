import Head from "next/head";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import FreemiumHero from "../components/FreemiumHero";
import ProjectLaunchHero, {
  LaunchScenario,
} from "../components/ui/ProjectLaunchHero";
import { createProject, ProjectCreate } from "../lib/api";
import { getAccessToken, TOKEN_CHANGE_EVENT } from "../lib/api";

export default function MVPPage() {
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean>(false);

  const handleDashboard = () => {
    router.push("/dashboard");
  };

  const handleProjects = () => {
    router.push("/projects");
  };

  async function launchProject(concept: string) {
    const trimmed = concept.trim();
    if (!trimmed) return;
    try {
      setStarting(true);
      setError(null);
      const payload: ProjectCreate = {
        name: trimmed.slice(0, 60),
        description: trimmed,
        features: "",
      } as ProjectCreate;
      const proj = await createProject(payload);
      const prefill = encodeURIComponent(
        `I want to build: ${trimmed}. Help capture clear, testable functional and non-functional requirements, then generate a Charter, SRS, SDD, and Test Plan.`,
      );
      await router.push(
        `/start/${encodeURIComponent(proj.project_id)}?prefill=${prefill}`,
      );
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setStarting(false);
    }
  }

  const handleSubmit = async (value: string) => {
    setIdea(value);
    await launchProject(value);
  };

  const handleScenarioSelect = async (scenario: LaunchScenario) => {
    setIdea(scenario.value);
    await launchProject(scenario.value);
  };

  // Track auth to hide Freemium badge when signed in
  useEffect(() => {
    const sync = () => {
      try {
        setAuthed(!!getAccessToken());
      } catch {
        setAuthed(false);
      }
    };
    sync();
    if (typeof window !== "undefined") {
      window.addEventListener("storage", sync);
      window.addEventListener(TOKEN_CHANGE_EVENT, sync as EventListener);
      return () => {
        window.removeEventListener("storage", sync);
        window.removeEventListener(TOKEN_CHANGE_EVENT, sync as EventListener);
      };
    }
  }, []);

  const heroFeatures = useMemo(
    () => [
      {
        title: "Concept to Charter",
        description:
          "Capture problem framing, outcomes, and early constraints as AI extracts canonical SHALL statements.",
      },
      {
        title: "Design to Delivery",
        description:
          "Generate SRS, SDD, Test Plans, and traceability when you are ready to move past discovery.",
      },
      {
        title: "Instant artifact bundles",
        description:
          "Download Markdown, DOCX, CSV backlog, or the entire package without leaving the workspace.",
      },
    ],
    [],
  );

  return (
    <div className="mvp-landing" role="region" aria-label="MVP landing">
      <Head>
        <link rel="preload" as="image" href="/home_grid.png" />
      </Head>
      <div className="mvp-landing__shell">
        <FreemiumHero
          authed={authed}
          variant="compact"
          features={heroFeatures}
          loading={starting}
          error={error}
          sessionReady={!starting && !error}
          headline="Bring concepts to launch with an AI-led delivery cockpit."
          subtitle="Guide discovery conversations, extract requirements, and govern delivery phases with every artifact synchronized."
          footer={
            <ProjectLaunchHero
              className="launch-hero--spotlight launch-hero--wide launch-hero--compact"
              value={idea}
              onChange={setIdea}
              onSubmit={handleSubmit}
              onScenarioSelect={handleScenarioSelect}
              busy={starting}
              disabled={starting}
            />
          }
        />
      </div>
      <style jsx global>{`
        .mvp-landing .freemium-hero {
          grid-template-columns: 1fr !important;
          justify-items: center !important;
          width: min(1100px, 96vw) !important;
          margin-left: auto !important;
          margin-right: auto !important;
          gap: clamp(18px, 4vw, 32px) !important;
        }
        .mvp-landing .freemium-hero__headline-row {
          grid-template-columns: 1fr !important;
          text-align: center !important;
        }
        .mvp-landing .freemium-hero__pitch,
        .mvp-landing .freemium-hero__footer {
          width: min(100%, 1024px) !important;
          margin-left: auto !important;
          margin-right: auto !important;
        }
      `}</style>
    </div>
  );
}
