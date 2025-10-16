import Head from "next/head";
import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Image from "next/image";
import { requestOtp, verifyOtp } from "../lib/api";
import logoFull from "../public/logo-full.svg";

type SocialProvider = {
  label: string;
  name: string;
  url?: string;
};

const heroHighlights = [
  {
    title: "Concept → Charter",
    copy: "Capture discovery notes, risks, and SHALL statements in minutes.",
  },
  {
    title: "Delivery cockpit",
    copy: "Navigate dashboards, approvals, and AI-generated docs from one workspace.",
  },
  {
    title: "Instant bundles",
    copy: "Export Charters, SRS, SDD, and Test Plans in your preferred formats instantly.",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("adam.thacker@expeed.com");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [socialError, setSocialError] = useState<string | null>(null);

  const socialProviders = useMemo<SocialProvider[]>(
    () => [
      {
        label: "Continue with Google",
        name: "Google",
        url: process.env.NEXT_PUBLIC_GOOGLE_OAUTH_URL,
      },
      {
        label: "Continue with Microsoft",
        name: "Microsoft",
        url: process.env.NEXT_PUBLIC_MICROSOFT_OAUTH_URL,
      },
    ],
    [],
  );

  const handleSocial = (provider: SocialProvider) => {
    setSocialError(null);
    if (provider.url) {
      if (typeof window !== "undefined") {
        window.location.href = provider.url;
      }
    } else {
      setSocialError(`${provider.name} SSO is not configured yet.`);
    }
  };

  const redirectAfterAuth = () => {
    if (typeof window === "undefined") return;
    const defaultPath = process.env.NEXT_PUBLIC_POST_LOGIN_PATH || "/dashboard";
    let target = defaultPath;
    try {
      const url = new URL(window.location.href);
      const rt = url.searchParams.get("returnTo");
      if (rt && rt !== "/" && rt.startsWith("/")) {
        target = rt;
      }
    } catch {}
    window.location.href = target;
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    try {
      setLoading(true);
      if (!codeSent) {
        await requestOtp(email);
        setCodeSent(true);
        setNotice(`We sent a six-digit code to ${email}. Enter it below to continue.`);
      } else {
        await verifyOtp(email, code.trim());
        redirectAfterAuth();
      }
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  const onResend = async () => {
    if (loading) return;
    setError(null);
    setNotice(null);
    try {
      setLoading(true);
      await requestOtp(email);
      setNotice(`We sent a fresh code to ${email}.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page auth-page--login" aria-live="polite">
      <Head>
        <title>Sign in · OPNXT</title>
      </Head>
      <div className="auth-page__panel auth-page__panel--split">
        <section className="auth-panel__main" aria-label="Sign in">
          <div className="auth-page__logo" aria-hidden="true">
            <Image src={logoFull} alt="OPNXT" priority />
          </div>
          <header className="auth-page__header">
            <span className="badge">Workspace access</span>
            <h1>Welcome back</h1>
            <p>Sign in to synchronize projects, approvals, and AI-generated documents.</p>
          </header>

          <div className="auth-page__social">
            {socialProviders.map((provider) => (
              <button
                key={provider.name}
                type="button"
                className="auth-social"
                onClick={() => handleSocial(provider)}
                disabled={loading}
              >
                <span aria-hidden="true" className="auth-social__icon">
                  {provider.name.charAt(0)}
                </span>
                {provider.label}
              </button>
            ))}
          </div>

          <div className="auth-divider" role="separator" aria-label="Email sign in">
            <span>or continue with email</span>
          </div>

          {error && (
            <div className="auth-alert auth-alert--error" role="alert">
              {error}
            </div>
          )}
          {notice && !error && (
            <div className="auth-alert auth-alert--info" role="status">
              {notice}
            </div>
          )}
          {socialError && (
            <div className="auth-alert auth-alert--info" role="status">
              {socialError}
            </div>
          )}

          <form className="auth-form" onSubmit={onSubmit}>
            <label className="auth-field" htmlFor="email">
              <span>Email address</span>
              <input
                id="email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                disabled={loading || codeSent}
              />
            </label>
            {codeSent ? (
              <label className="auth-field" htmlFor="otp">
                <span>Six-digit code</span>
                <input
                  id="otp"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  placeholder="Enter the code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  required
                  autoComplete="one-time-code"
                  disabled={loading}
                  maxLength={6}
                />
              </label>
            ) : null}

            <button type="submit" className="auth-submit" disabled={loading}>
              {loading ? "Working…" : codeSent ? "Verify code" : "Send sign-in code"}
            </button>
          </form>

          <div className="auth-page__meta">
            {codeSent ? (
              <button type="button" className="auth-link" onClick={onResend} disabled={loading}>
                Resend code
              </button>
            ) : null}
            <span>Need an account? <Link href="/signup">Create one</Link></span>
          </div>
        </section>
        <aside className="auth-panel__aside" aria-label="Highlights">
          <div className="auth-hero">
            <h2>Bring concepts to launch faster.</h2>
            <p>
              OPNXT orchestrates chartering, specifications, design, and testing with an AI-led
              delivery control centre.
            </p>
            <ul className="auth-hero__list">
              {heroHighlights.map((item) => (
                <li key={item.title}>
                  <strong>{item.title}</strong>
                  <span>{item.copy}</span>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
