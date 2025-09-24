import { FormEvent, useState } from "react";
import { login } from "../lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("adam.thacker@expeed.com");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setLoading(true);
      await login(email, password);
      if (typeof window !== 'undefined') {
        const def = process.env.NEXT_PUBLIC_POST_LOGIN_PATH || '/start';
        let target = def;
        try {
          const url = new URL(window.location.href);
          const rt = url.searchParams.get('returnTo');
          if (rt && rt.startsWith('/')) target = rt; // safety: only allow same-origin relative paths
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
    <div>
      <h2>Login</h2>
      <p>Use your dev credentials to continue.</p>
      <form onSubmit={onSubmit} style={{ display: 'grid', gap: 8, maxWidth: 360 }}>
        <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required />
        <button type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
      </form>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <div style={{ marginTop: 12, color: '#666' }}>
        <small>Dev admin: adam.thacker@expeed.com / Password#1</small>
      </div>
    </div>
  );
}
