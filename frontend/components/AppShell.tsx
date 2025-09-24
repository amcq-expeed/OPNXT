import React from "react";
import { useRouter } from "next/router";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const minimal = (router?.pathname || "").startsWith("/mvp");

  if (minimal) {
    return (
      <div className="app-shell app-shell--mvp">
        <a href="#main" className="skip-link">Skip to content</a>
        {/* Full-bleed main for MVP so hero background spans edge-to-edge */}
        <main id="main" role="main" style={{ padding: 0 }}>{children}</main>
      </div>
    );
  }

  // Default shell (simple, no header for now to avoid blocking compilation)
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <main id="main" role="main" className="container">
        {children}
      </main>
    </div>
  );
}
