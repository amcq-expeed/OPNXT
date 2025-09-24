import Link from "next/link";
import { PropsWithChildren, useEffect, useState, useMemo } from "react";
import { useRouter } from "next/router";
import { getAccessToken, setAccessToken } from "../lib/api";

export default function Layout({ children }: PropsWithChildren) {
  const [hasToken, setHasToken] = useState<boolean>(false);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);
  const router = useRouter();
  const asPath = router?.asPath || '/';
  const isActive = useMemo(() => (href: string) => {
    if (!asPath) return false;
    return asPath === href || asPath.startsWith(href + '/');
  }, [asPath]);

  useEffect(() => {
    try {
      const saved = typeof window !== 'undefined' ? window.localStorage.getItem('opnxt_sidebar_open') : null;
      if (saved != null) setSidebarOpen(saved === '1');
    } catch {}
  }, []);

  useEffect(() => {
    setHasToken(!!getAccessToken());
  }, []);

  function onLogout() {
    setAccessToken(null);
    setHasToken(false);
    if (typeof window !== 'undefined') window.location.href = '/login';
  }

  function toggleSidebar() {
    const next = !sidebarOpen;
    setSidebarOpen(next);
    try { if (typeof window !== 'undefined') window.localStorage.setItem('opnxt_sidebar_open', next ? '1' : '0'); } catch {}
  }

  // Build breadcrumb from path segments
  const crumbs = useMemo(() => {
    const out: { href: string; label: string }[] = [];
    if (!asPath) return out;
    const qIndex = asPath.indexOf('?');
    const clean = qIndex >= 0 ? asPath.slice(0, qIndex) : asPath;
    const parts = clean.split('/').filter(Boolean);
    let acc = '';
    for (let i = 0; i < parts.length; i++) {
      acc += '/' + parts[i];
      const label = decodeURIComponent(parts[i]);
      out.push({ href: acc, label: label === 'projects' ? 'Projects' : (label === 'dashboard' ? 'Dashboard' : (label === 'settings' ? 'Settings' : (label === 'chat' ? 'Chat' : (label === 'documents' ? 'Documents' : label)))) });
    }
    return out;
  }, [asPath]);

  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="header" role="banner">
        <div className="header-inner">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              aria-label="Toggle sidebar"
              aria-controls="sidebar"
              aria-expanded={sidebarOpen}
              className="btn"
              onClick={toggleSidebar}
            >☰</button>
            <div className="brand">OPNXT</div>
          </div>
          <nav className="nav" role="navigation" aria-label="Top">
            <Link href="/dashboard" className={isActive('/dashboard') ? 'active' : ''}>Dashboard</Link>
            <Link href="/projects" className={isActive('/projects') ? 'active' : ''}>Projects</Link>
            <Link href="/chat" className={isActive('/chat') ? 'active' : ''}>Chat</Link>
            <Link href="/documents" className={isActive('/documents') ? 'active' : ''}>Documents</Link>
            <Link href="/settings" className={isActive('/settings') ? 'active' : ''}>Settings</Link>
            {hasToken ? (
              <button onClick={onLogout} className="btn">Logout</button>
            ) : (
              <Link href="/login">Login</Link>
            )}
          </nav>
        </div>
      </header>

      <div className="shell" style={{ display: 'flex', alignItems: 'stretch', gap: 0 }}>
        <aside id="sidebar" className={`sidebar ${sidebarOpen ? '' : 'collapsed'}`} aria-label="Primary" role="navigation">
          <ul className="sidebar-nav" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            <li><Link href="/dashboard" className={isActive('/dashboard') ? 'active' : ''} aria-current={isActive('/dashboard') ? 'page' : undefined}>Dashboard</Link></li>
            <li><Link href="/projects" className={isActive('/projects') ? 'active' : ''} aria-current={isActive('/projects') ? 'page' : undefined}>Projects</Link></li>
            <li><Link href="/chat" className={isActive('/chat') ? 'active' : ''} aria-current={isActive('/chat') ? 'page' : undefined}>Chat</Link></li>
            <li><Link href="/documents" className={isActive('/documents') ? 'active' : ''} aria-current={isActive('/documents') ? 'page' : undefined}>Documents</Link></li>
            <li><Link href="/settings" className={isActive('/settings') ? 'active' : ''} aria-current={isActive('/settings') ? 'page' : undefined}>Settings</Link></li>
          </ul>
        </aside>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="container">
            {/* Breadcrumb */}
            <nav className="breadcrumb" aria-label="Breadcrumb">
              <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                <li><Link href="/">Home</Link></li>
                {crumbs.map((c, i) => (
                  <li key={c.href} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <span className="muted">/</span>
                    {i < crumbs.length - 1 ? <Link href={c.href}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
                  </li>
                ))}
              </ol>
            </nav>
          </div>
          <main id="main" className="container" role="main">{children}</main>
          <footer className="container" style={{ marginTop: 24, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            <small className="muted">© {new Date().getFullYear()} OPNXT</small>
          </footer>
        </div>
      </div>
    </div>
  );
}
