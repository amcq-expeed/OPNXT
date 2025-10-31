import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import TopNav from "./TopNav";
import SideNav from "./SideNav";
import SupportWidget from "./SupportWidget";
import {
  derivePersonaFromRoles,
  getAccessToken,
  me,
  setAccessToken,
  type User,
} from "../lib/api";
import { UserContext } from "../lib/user-context";

const PUBLIC_MODE =
  process.env.NEXT_PUBLIC_PUBLIC_MODE === "1" ||
  process.env.NEXT_PUBLIC_PUBLIC_MODE === "true";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = router?.pathname || "";
  const authRoute =
    path.startsWith("/login") || path.startsWith("/signup") || path.startsWith("/logout");
  const minimal = path === "/" || path.startsWith("/mvp") || authRoute;
  const guardEnabled = !(minimal || authRoute) && !PUBLIC_MODE;
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState<boolean>(!guardEnabled);

  const loginRedirect = useMemo(() => {
    const target = router?.asPath || "/";
    return `/login?returnTo=${encodeURIComponent(target)}`;
  }, [router?.asPath]);

  useEffect(() => {
    if (!guardEnabled) {
      setAuthChecked(true);
      setUser(null);
      return;
    }
    const token = getAccessToken();
    if (!token) {
      setAuthChecked(true);
      router.replace(loginRedirect);
      return;
    }

    let ignore = false;
    (async () => {
      try {
        const current = await me();
        if (!ignore) {
          setUser(current);
          setAuthChecked(true);
        }
      } catch {
        if (!ignore) {
          setUser(null);
          setAccessToken(null);
          setAuthChecked(true);
          router.replace(loginRedirect);
        }
      }
    })();

    return () => {
      ignore = true;
    };
  }, [guardEnabled, loginRedirect, router]);

  const toggleSidebar = () => setSidebarCollapsed((prev) => !prev);

  const shellClass = useMemo(() => {
    const classes = ["app-shell", "app-shell--sidebar"];
    if (sidebarCollapsed) classes.push("app-shell--sidebar-collapsed");
    return classes.join(" ");
  }, [sidebarCollapsed]);

  const isDashboard = router.pathname.startsWith("/dashboard");
  const isAccelerator = router.pathname.startsWith("/accelerators");
  const isProject = router.pathname.startsWith("/projects");

  const contentClass = useMemo(() => {
    const classes = ["app-shell__content"];
    if (isDashboard) {
      classes.push("app-shell__content--dashboard");
    }
    if (isAccelerator) {
      classes.push("app-shell__content--accelerator");
    }
    if (isProject) {
      classes.push("app-shell__content--project");
    }
    return classes.join(" ");
  }, [isDashboard, isAccelerator, isProject]);

  const mainClass = useMemo(
    () => (isAccelerator ? "accelerator-container" : "container"),
    [isAccelerator],
  );

  if (!minimal && !authRoute && !authChecked) {
    return null;
  }

  if (authRoute) {
    return (
      <div className="app-shell app-shell--auth">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <main id="main" role="main" className="auth-container">
          {children}
        </main>
        <SupportWidget collapsedLabel="Ask OPNXT" />
      </div>
    );
  }

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
        <SupportWidget collapsedLabel="Ask OPNXT" userName={user?.name} />
      </div>
    );
  }

  const persona = derivePersonaFromRoles(user?.roles);

  return (
    <UserContext.Provider value={{ user, persona }}>
      <div className={shellClass}>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <SideNav
          collapsed={sidebarCollapsed}
          onToggle={toggleSidebar}
          user={user}
        />
        <div className={contentClass}>
          {!isDashboard && !isAccelerator && (
            <TopNav
              appearance="minimal"
              user={user}
              sidebarCollapsed={sidebarCollapsed}
              onToggleSidebar={toggleSidebar}
              disableAuthButtons={authRoute}
            />
          )}
          {isDashboard && (
            <button
              type="button"
              className="dashboard-fab-toggle"
              onClick={toggleSidebar}
              aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                focusable="false"
                role="img"
              >
                <path
                  d="M5.25 5A1.75 1.75 0 0 0 3.5 6.75v10.5A1.75 1.75 0 0 0 5.25 19h9.5A1.75 1.75 0 0 0 16.5 17.25V6.75A1.75 1.75 0 0 0 14.75 5h-9.5ZM5 6.75c0-.138.112-.25.25-.25h4v11h-4a.25.25 0 0 1-.25-.25V6.75Zm10 10.5a.25.25 0 0 1-.25.25h-4v-11h4c.138 0 .25.112.25.25v10.5Zm2.5-9h1.5a.75.75 0 0 1 0 1.5H17.5a.75.75 0 0 1 0-1.5Zm0 4h1.5a.75.75 0 0 1 0 1.5H17.5a.75.75 0 0 1 0-1.5Zm0 4h1.5a.75.75 0 0 1 0 1.5H17.5a.75.75 0 0 1 0-1.5Z"
                  fill="currentColor"
                />
              </svg>
            </button>
          )}
          <main id="main" role="main" className={mainClass}>
            {children}
          </main>
        </div>
        <SupportWidget collapsedLabel="Ask OPNXT" userName={user?.name} />
      </div>
    </UserContext.Provider>
  );
}
