import Image from "next/image";
import { FormEvent, useState } from "react";
import { login } from "../lib/api";
import logoFull from "../public/logo-full.svg";

export default function LoginPage() {
  const [email, setEmail] = useState("adam.thacker@expeed.com");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setLoading(true);
      await login(email, password);
      if (typeof window !== "undefined") {
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
      }
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-landing" aria-live="polite">
      <div className="auth-card auth-card--centered" aria-label="Sign in">
        <div className="auth-card__brand" aria-hidden="true">
          <Image src={logoFull} alt="OPNXT" priority />
          <span>Concept → Delivery Control Centre</span>
        </div>

        <div className="auth-card__heading">
          <p className="auth-card__eyebrow">Welcome back</p>
          <h1>Sign in to continue</h1>
          <p>Access portfolio governance, synced requirements, and AI documents.</p>
        </div>

        {error && (
          <div className="auth-card__banner" role="alert">
            {error}
          </div>
        )}

        <form className="auth-card__form" onSubmit={onSubmit}>
          <label className="auth-card__field" htmlFor="email">
            <span>Email address</span>
            <input
              className="input input--auth"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              disabled={loading}
              id="email"
            />
          </label>
          <label className="auth-card__field" htmlFor="password">
            <span>Password</span>
            <div className="auth-card__input-wrap">
              <input
                className="input input--auth"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                disabled={loading}
                id="password"
              />
              <button
                type="button"
                className="auth-card__toggle"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-pressed={showPassword}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <button
            className="btn-gradient auth-card__submit"
            type="submit"
            disabled={loading}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <footer className="auth-card__footer">
          <button
            className="auth-card__link"
            type="button"
            onClick={(e) => e.preventDefault()}
          >
            Forgot your password?
          </button>
          <code className="auth-card__hint">
            adam.thacker@expeed.com · Password#1
          </code>
        </footer>
      </div>
    </div>
  );
}
