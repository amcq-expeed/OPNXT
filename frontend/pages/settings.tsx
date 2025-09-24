import { useEffect, useMemo, useState } from "react";
import { diagLLM, DiagLLM, updateLLMSettings, LLMUpdateRequest, me, User, isAdmin, getAccessToken } from "../lib/api";

export default function SettingsPage() {
  const [diag, setDiag] = useState<DiagLLM | null>(null);
  const [provider, setProvider] = useState<string>("openai");
  const [baseUrl, setBaseUrl] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  const admin = isAdmin(currentUser);

  useEffect(() => {
    if (typeof window !== 'undefined' && !getAccessToken()) {
      const rt = encodeURIComponent('/settings');
      window.location.href = `/login?returnTo=${rt}`;
      return;
    }
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const u = await me();
        setCurrentUser(u);
        const d = await diagLLM();
        setDiag(d);
        setProvider((d.provider || 'openai').toLowerCase());
        setBaseUrl(d.base_url || '');
        setModel(d.model || '');
      } catch (e: any) {
        setError(e?.message || String(e));
        if (typeof window !== 'undefined') {
          const rt = encodeURIComponent('/settings');
          window.location.href = `/login?returnTo=${rt}`;
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!admin) {
      setError('Only admins can update LLM settings.');
      return;
    }
    try {
      setSaving(true);
      setError(null);
      setNotice(null);
      const payload: LLMUpdateRequest = {
        provider,
        base_url: baseUrl || undefined,
        model: model || undefined,
      };
      const updated = await updateLLMSettings(payload);
      setDiag(updated);
      setNotice('Settings saved.');
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h2>Settings</h2>
      {loading && <p>Loading…</p>}
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {notice && <p style={{ color: '#0a0' }}>{notice}</p>}

      {/* Profile */}
      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card" role="region" aria-label="Profile">
          <strong>Profile</strong>
          <div style={{ display: 'grid', gap: 6, marginTop: 8 }}>
            <label style={{ display: 'grid', gap: 4 }}>
              <span>Name</span>
              <input className="input" value={currentUser?.name || ''} readOnly aria-readonly="true" />
            </label>
            <label style={{ display: 'grid', gap: 4 }}>
              <span>Email</span>
              <input className="input" value={currentUser?.email || ''} readOnly aria-readonly="true" />
            </label>
          </div>
        </div>
        <div className="card" role="region" aria-label="Security">
          <strong>Security</strong>
          <div style={{ marginTop: 8 }}>
            <div className="muted">Roles</div>
            <ul>
              {(currentUser?.roles || []).map(r => (<li key={r}>{r}</li>))}
            </ul>
            <div className="muted" style={{ fontSize: 12 }}>JWT is stored in localStorage for dev; consider rotating tokens regularly.</div>
          </div>
        </div>
      </div>

      <div style={{ border: '1px solid #eee', borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <strong>LLM Diagnostics</strong>
        {diag ? (
          <ul>
            <li>Provider: {diag.provider}</li>
            <li>Has API Key: {String(diag.has_api_key)}</li>
            <li>Base URL: {diag.base_url}</li>
            <li>Model: {diag.model}</li>
            <li>Library Present: {String(diag.library_present)}</li>
            <li>Ready: {String(diag.ready)}</li>
          </ul>
        ) : (
          <p style={{ color: '#666' }}>No diagnostics available.</p>
        )}
      </div>

      <form onSubmit={onSave} style={{ border: '1px solid #eee', borderRadius: 8, padding: 12 }}>
        <strong>LLM Settings</strong>
        {!admin && (
          <div style={{ color: '#a00', marginTop: 6 }}>You have read-only access. Contact an admin to update settings.</div>
        )}
        <div style={{ display: 'grid', gap: 8, marginTop: 8, maxWidth: 560 }}>
          <label style={{ display: 'grid', gap: 4 }}>
            <span>Provider</span>
            <select value={provider} onChange={e => setProvider(e.target.value)} disabled={!admin}>
              <option value="openai">OpenAI</option>
              <option value="xai">xAI</option>
              <option value="none">None</option>
            </select>
          </label>

          <label style={{ display: 'grid', gap: 4 }}>
            <span>Base URL</span>
            <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" disabled={!admin} />
          </label>

          <label style={{ display: 'grid', gap: 4 }}>
            <span>Model</span>
            <input value={model} onChange={e => setModel(e.target.value)} placeholder="gpt-4o-mini" disabled={!admin} />
          </label>

          <div>
            <button type="submit" disabled={!admin || saving}>{saving ? 'Saving…' : 'Save Settings'}</button>
          </div>
        </div>
      </form>

      <div style={{ color: '#666', marginTop: 12, fontSize: 12 }}>
        Note: These settings update environment overrides at runtime. API keys must be provided via environment variables.
      </div>
    </div>
  );
}
