import Head from "next/head";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useState } from "react";
import FreemiumHero from "../../components/FreemiumHero";
import MVPChat from "../../components/MVPChat";
import {
  getProject,
  Project,
  getAccessToken,
  TOKEN_CHANGE_EVENT,
} from "../../lib/api";
import { getAuth } from "firebase/auth";

const GUEST_SESSION_KEY = "opnxt_guest_session_id";

function ensureGuestSession() {
  if (typeof window === "undefined") return;
  try {
    const existing = window.localStorage.getItem(GUEST_SESSION_KEY);
    if (existing) return;
    const random = Math.random().toString(36).slice(2);
    window.localStorage.setItem(GUEST_SESSION_KEY, `guest-${random}`);
  } catch {
    // ignore storage errors; session will fall back to stateless mode
  }
}

export default function GuestStartPage() {
  const router = useRouter();
  const projectId =
    typeof router.query.project_id === "string" ? router.query.project_id : "";

  const [project, setProject] = useState<Project | null>(null);
  const [prefill, setPrefill] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean>(false);
  const firebaseConfig = useMemo(() => {
    if (typeof window === "undefined") return undefined;
    const cfg = (window as any).__OPNXT_FIREBASE__;
    return cfg && typeof cfg === "object" ? cfg : undefined;
  }, []);

  useEffect(() => {
    ensureGuestSession();
  }, []);

  // Track auth status so the hero can hide the Freemium badge when signed in
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
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("storage", sync);
        window.removeEventListener(TOKEN_CHANGE_EVENT, sync as EventListener);
      }
    };
  }, []);

  useEffect(() => {
    const q = router.query.prefill;
    if (typeof q === "string") {
      try {
        setPrefill(decodeURIComponent(q));
      } catch {
        setPrefill(q);
      }
    }
  }, [router.query.prefill]);

  useEffect(() => {
    if (!projectId) return;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const p = await getProject(projectId);
        setProject(p);
      } catch (e: any) {
        setError(e?.message || String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  const handleUpgradeRequested = useCallback(async () => {
    const auth = getAuth();
    const guest = auth.currentUser;
    const guestUid = guest?.uid ?? "";

    if (guest && !guest.isAnonymous) {
      const token = await guest.getIdToken();
      return { token, user: { uid: guest.uid } };
    }

    if (typeof window !== "undefined") {
      const bridge = (window as any).hostUpgradeBridge;
      if (bridge && typeof bridge.onUpgradeRequested === "function") {
        const result = await bridge.onUpgradeRequested({
          guestUserId: guestUid,
          projectId,
        });
        if (result && result.token && result.user) {
          return result;
        }
      }
    }

    console.warn(
      "[GuestStart] Upgrade flow not fully implemented. Returning null to keep paywall active.",
    );
    return null;
  }, [projectId]);

  const handleMigrationRequested = useCallback(
    async ({
      guestUserId,
      projectId: migratingProjectId,
      permanentToken,
    }: {
      guestUserId: string;
      projectId: string;
      permanentToken: string;
    }) => {
      try {
        const res = await fetch("/api/migrate-project", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${permanentToken}`,
          },
          body: JSON.stringify({ guestUserId, projectId: migratingProjectId }),
        });
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(
            detail || `Migration failed with status ${res.status}`,
          );
        }
      } catch (err) {
        console.error("[GuestStart] Migration request failed", err);
        throw err;
      }
    },
    [],
  );

  const heroFeatures = useMemo(
    () => [
      {
        title: "Chat-first requirements",
        description:
          "Capture problem framing, stakeholders, risks, and readiness in a single conversational flow.",
      },
      {
        title: "AI-generated SDLC artifacts",
        description:
          "Generate PD-001, RE-001, SRS, and Test Plans once the readiness score unlocks full docs.",
      },
      {
        title: "Baseline when you are ready",
        description:
          "Upgrade to preserve history, phase approvals, and governance sign-offs when you approve PD-001.",
      },
    ],
    [],
  );

  const headline = project
    ? `Guest workspace for ${project.name}`
    : "Guest project workspace";

  return (
    <div
      className="mvp-start"
      role="region"
      aria-label="Guest project workspace"
    >
      <Head>
        <title>OPNXT Guest Workspace</title>
        <link rel="preload" as="image" href="/home_grid.png" />
      </Head>
      <FreemiumHero
        authed={authed}
        variant="compact"
        headline={headline}
        subtitle="Guide discovery conversations, capture SHALL requirements, and unlock SDLC bundles without creating an account."
        features={heroFeatures}
        loading={loading}
        error={error}
        sessionReady={!loading && !error}
        footer={
          projectId && !error ? (
            <div className="mvp-chat-shell">
              <div className="card card--elevated" style={{ padding: 0 }}>
                <MVPChat
                  projectId={projectId}
                  initialPrompt={prefill}
                  firebaseConfig={firebaseConfig}
                  onUpgradeRequested={handleUpgradeRequested}
                  onMigrationRequested={handleMigrationRequested}
                />
              </div>
            </div>
          ) : null
        }
      ></FreemiumHero>
      <style jsx global>{`
        .mvp-start .freemium-hero {
          grid-template-columns: 1fr !important;
          justify-items: center !important;
          width: min(1100px, 96vw) !important;
          margin-left: auto !important;
          margin-right: auto !important;
          gap: clamp(18px, 4vw, 32px) !important;
        }
        .mvp-start .freemium-hero__headline-row {
          grid-template-columns: 1fr !important;
          text-align: center !important;
        }
        .mvp-start .freemium-hero__pitch,
        .mvp-start .freemium-hero__interactive,
        .mvp-start .freemium-hero__footer {
          width: min(100%, 1024px) !important;
          margin-left: auto !important;
          margin-right: auto !important;
        }
        .mvp-start .freemium-hero__interactive {
          justify-self: stretch !important;
        }

        .mvp-start .mvp-chat-shell {
          width: min(1100px, 96vw) !important;
          margin-left: auto !important;
          margin-right: auto !important;
          padding: clamp(16px, 3.2vw, 28px) clamp(12px, 3.6vw, 24px)
            clamp(24px, 5vh, 40px) !important;
        }
        .mvp-start .mvp-chat__history {
          gap: clamp(10px, 2vw, 16px) !important;
          max-height: min(50vh, 520px) !important;
          padding-bottom: 12px !important;
        }
        .mvp-start .mvp-chat__composer {
          position: static !important;
          bottom: auto !important;
          gap: clamp(12px, 2vw, 18px) !important;
          padding-top: clamp(8px, 1.6vw, 12px) !important;
        }
        .mvp-start .mvp-chat__textarea {
          min-height: 88px !important;
          max-height: 240px !important;
          font-size: 14px !important;
          padding: 12px 14px !important;
        }
        .mvp-start .mvp-chat__send {
          padding: 10px 16px !important;
          border-radius: 14px !important;
        }
        .mvp-start .mvp-chat__meta {
          gap: clamp(8px, 2vw, 14px) !important;
        }
      `}</style>
    </div>
  );
}
