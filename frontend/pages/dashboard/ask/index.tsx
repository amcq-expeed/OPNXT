import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  createGuestChatSession,
  type ChatSession,
  trackEvent,
} from "../../../lib/api";
import { useUserContext } from "../../../lib/user-context";

export default function AskWorkspaceBootstrapPage() {
  const router = useRouter();
  const { persona } = useUserContext();
  const [status, setStatus] = useState<string>("Preparing Ask OPNXT…");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<number>(0);

  const queryParams = useMemo(() => {
    if (!router.isReady) {
      return {
        provider: null as string | null,
        model: null as string | null,
        prefill: null as string | null,
        source: "unknown",
        autosend: false,
      };
    }

    const provider = typeof router.query.provider === "string" ? router.query.provider : null;
    const model = typeof router.query.model === "string" ? router.query.model : null;
    const prefill = typeof router.query.prefill === "string" ? router.query.prefill : null;
    const source = typeof router.query.source === "string" ? router.query.source : "unknown";
    const autosend = router.query.autosend === "1";

    return { provider, model, prefill, source, autosend };
  }, [router.isReady, router.query.autosend, router.query.model, router.query.prefill, router.query.provider, router.query.source]);

  useEffect(() => {
    if (!router.isReady) return;

    let cancelled = false;

    async function bootstrapSession() {
      setStatus("Preparing Ask OPNXT…");
      setError(null);

      const payload: {
        title: string;
        persona?: string;
        provider?: string | null;
        model?: string | null;
      } = { title: "Ask OPNXT" };

      if (persona) payload.persona = persona;
      if (queryParams.provider) payload.provider = queryParams.provider;
      if (queryParams.model) payload.model = queryParams.model;

      try {
        const response = await createGuestChatSession(payload);
        if (cancelled) return;

        const session: ChatSession | undefined = response?.session;
        if (!session?.session_id) {
          throw new Error("Unable to start Ask OPNXT session.");
        }

        const params = new URLSearchParams();
        if (queryParams.prefill) params.set("prefill", queryParams.prefill);
        if (queryParams.provider) params.set("provider", queryParams.provider);
        if (queryParams.model) params.set("model", queryParams.model);
        if (queryParams.autosend) params.set("autosend", "1");
        if (queryParams.source) params.set("source", queryParams.source);

        const target = `/dashboard/ask/${encodeURIComponent(session.session_id)}${
          params.size ? `?${params.toString()}` : ""
        }`;

        trackEvent("ask_workspace_bootstrap_redirect", {
          sessionId: session.session_id,
          source: queryParams.source,
          persona: persona ?? null,
        });

        await router.replace(target);
      } catch (err: any) {
        if (cancelled) return;
        const detail = err?.message || "We ran into a problem starting Ask OPNXT.";
        setError(detail);
        setStatus("Try again in a moment.");
        trackEvent("ask_workspace_bootstrap_failed", {
          message: detail,
          source: queryParams.source,
          persona: persona ?? null,
        });
      }
    }

    void bootstrapSession();

    return () => {
      cancelled = true;
    };
  }, [attempt, persona, queryParams.autosend, queryParams.model, queryParams.prefill, queryParams.provider, queryParams.source, router]);

  return (
    <div className="accelerator-shell ask-workspace-shell" aria-live="polite">
      <header className="accelerator-header">
        <nav className="accelerator-breadcrumb" aria-label="Breadcrumb">
          <Link href="/dashboard">Workspace</Link>
          <span aria-hidden="true">/</span>
          <span>Ask OPNXT</span>
        </nav>
        <h1>Opening Ask OPNXT…</h1>
        <p className="accelerator-subhead">
          We&apos;re setting up a fresh conversation so you can jump right into capturing updates or next steps.
        </p>
      </header>

      <main className="accelerator-main ask-workspace-main">
        <section className="accelerator-status" role={error ? "alert" : "status"}>
          {error ?? status}
        </section>
        {error ? (
          <div className="accelerator-actions" style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" className="btn btn-primary" onClick={() => setAttempt((value) => value + 1)}>
              Try again
            </button>
            <Link href="/dashboard" className="btn">
              Back to workspace
            </Link>
          </div>
        ) : null}
      </main>
    </div>
  );
}
