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
    copy: "Guide intake and produce stakeholder-ready Charters with AI assistance.",
  },
  {
    title: "Design synchrony",
    copy: "Keep SRS, SDD, and Test Plans in lockstep from the moment you launch.",
  },
  {
    title: "Workspace momentum",
    copy: "Invite teams, track approvals, and ship documentation bundles instantly.",
  },
];

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
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
    window.location.href = defaultPath;
  };

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);

    if (!email || !name) {
      setError("Provide your name and email to continue.");
      return;
    }

    try {
      setLoading(true);
      if (!codeSent) {
        await requestOtp(email);
        setCodeSent(true);
        setNotice(`We sent a six-digit code to ${email}. Enter it below to create your workspace.`);
      } else {
        await verifyOtp(email, code.trim(), name.trim());
        redirectAfterAuth();
      }
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  const onResend = async () => {
    if (loading || !email) return;
    setError(null);
    setNotice(null);
    try {
      setLoading(true);
      await requestOtp(email);
      setNotice(`We sent a fresh code to ${email}.`);
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page auth-page--signup" aria-live="polite">
      <Head>
        <title>Create your account · OPNXT</title>
      </Head>
      <div className="auth-page__panel auth-page__panel--split">
        <section className="auth-panel__main" aria-label="Create account">
          <div className="auth-page__logo" aria-hidden="true">
            <Image src={logoFull} alt="OPNXT" priority />
          </div>
          <header className="auth-page__header">
            <span className="badge">Create a free account</span>
            <h1>Welcome to OPNXT</h1>
            <p>Launch a workspace that keeps requirements, design, and testing synchronized.</p>
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

          <div className="auth-divider" role="separator" aria-label="Email sign up">
            <span>or sign up with email</span>
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
            <label className="auth-field" htmlFor="name">
              <span>Full name</span>
              <input
                id="name"
                type="text"
                placeholder="Your name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                autoComplete="name"
                disabled={loading || codeSent}
              />
            </label>
            <label className="auth-field" htmlFor="email">
              <span>Email address</span>
              <input
                id="email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
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
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                  required
                  autoComplete="one-time-code"
                  disabled={loading}
                  maxLength={6}
                />
              </label>
            ) : null}

            <button type="submit" className="auth-submit" disabled={loading}>
              {loading ? "Working…" : codeSent ? "Verify code" : "Send sign-up code"}
            </button>
          </form>

          <div className="auth-page__meta">
            {codeSent ? (
              <button type="button" className="auth-link" onClick={onResend} disabled={loading}>
                Resend code
              </button>
            ) : null}
            <span>
              Already have an account? <Link href="/login">Sign in</Link>
            </span>
          </div>
        </section>
        <aside className="auth-panel__aside" aria-label="Highlights">
          <div className="auth-hero">
            <h2>Spin up your delivery cockpit today.</h2>
            <p>
              From first discovery notes to traceable approvals, OPNXT accelerates every artifact in
              your SDLC.
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
