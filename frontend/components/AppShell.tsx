import React from "react";
import { useRouter } from "next/router";
import TopNav from "./TopNav";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = router?.pathname || "";
  const minimal = path === "/" || path.startsWith("/mvp");

  if (minimal) {
    return (
      <div className="app-shell app-shell--mvp">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <TopNav appearance="overlay" />
        {/* Full-bleed main for MVP so hero background spans edge-to-edge */}
        <main id="main" role="main" style={{ padding: 0 }}>
          {children}
        </main>
      </div>
    );
  }

  // Default shell (simple, no header for now to avoid blocking compilation)
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <TopNav />
      <main id="main" role="main" className="container">
        {children}
      </main>
    </div>
  );
}
