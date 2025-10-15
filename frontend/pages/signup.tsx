import Head from "next/head";
import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Image from "next/image";
import { register } from "../lib/api";
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
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    try {
      setLoading(true);
      await register(email, password);
      redirectAfterAuth();
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  }

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
                onChange={(event) => setEmail(event.target.value)}
                required
                autoComplete="email"
                disabled={loading}
              />
            </label>
            <label className="auth-field" htmlFor="password">
              <span>Password</span>
              <div className="auth-field__control">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Create a secure password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  autoComplete="new-password"
                  disabled={loading}
                />
                <button
                  type="button"
                  className="auth-toggle"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-pressed={showPassword}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </label>
            <label className="auth-field" htmlFor="confirm-password">
              <span>Confirm password</span>
              <input
                id="confirm-password"
                type={showPassword ? "text" : "password"}
                placeholder="Re-enter password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
                autoComplete="new-password"
                disabled={loading}
              />
            </label>

            <button type="submit" className="auth-submit" disabled={loading}>
              {loading ? "Creating account…" : "Create account"}
            </button>
          </form>

          <div className="auth-page__meta">
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
