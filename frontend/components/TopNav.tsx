import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  getAccessToken,
  setAccessToken,
  TOKEN_CHANGE_EVENT,
  type User,
} from "../lib/api";
import styles from "./TopNav.module.css";

interface TopNavProps {
  appearance?: "standard" | "overlay" | "minimal";
  user?: User | null;
  sidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
  disableAuthButtons?: boolean;
}

export default function TopNav({
  appearance = "standard",
  user,
  sidebarCollapsed = false,
  onToggleSidebar,
  disableAuthButtons = false,
}: TopNavProps) {
  const router = useRouter();
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => {
      try {
        setAuthed(!!getAccessToken());
      } catch {
        setAuthed(false);
      }
    };
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener(TOKEN_CHANGE_EVENT, sync as EventListener);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(TOKEN_CHANGE_EVENT, sync as EventListener);
    };
  }, []);

  const onSignIn = () => {
    const current = router.asPath || "/";
    const target = `/login?returnTo=${encodeURIComponent(current)}`;
    router.push(target);
  };

  const onSignOut = () => {
    setAccessToken(null);
    try {
      if (typeof window !== "undefined")
        window.localStorage.removeItem("opnxt_mvp_project_id");
    } catch {}
    router.replace("/");
  };

  const navClass = useMemo(() => {
    const base = `top-nav ${styles.topNav}`;
    if (appearance === "overlay") {
      return `${base} top-nav--overlay ${styles.topNavOverlay}`;
    }
    if (appearance === "minimal") {
      return `${base} top-nav--minimal ${styles.topNavMinimal}`;
    }
    return `${base} ${styles.topNavStandard}`;
  }, [appearance]);

  const sectionLabel = useMemo(() => {
    if (router.pathname.startsWith("/dashboard")) return "Dashboard";
    if (router.pathname.startsWith("/projects")) return "Projects";
    if (router.pathname.startsWith("/start")) return "Quick Start";
    return "Workspace";
  }, [router.pathname]);

  const showNavigationLinks = appearance !== "minimal";
  const showAuthButtons = !disableAuthButtons;
  const showMinimalCta = appearance === "minimal" && !disableAuthButtons;

  const innerClass = useMemo(() => {
    const base = `top-nav__inner ${styles.inner}`;
    if (appearance === "minimal") {
      return `${base} ${styles.innerMinimal}`;
    }
    return base;
  }, [appearance]);

  return (
    <header className={navClass} role="banner">
      <div className={innerClass}>
        {appearance === "minimal" && onToggleSidebar ? (
          <button
            type="button"
            className={styles.sidebarToggle}
            onClick={onToggleSidebar}
            aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
          >
            <span aria-hidden="true">≡</span>
          </button>
        ) : null}
        {showNavigationLinks ? (
          <>
            <Link
              href="/"
              className={`top-nav__brand ${styles.brand}`}
              aria-label="OPNXT home"
            >
              <span className={`top-nav__brand-row ${styles.brandRow}`}>
                <img
                  src="/logo-full.svg"
                  alt="Expeed Software"
                  className={`top-nav__img ${styles.img}`}
                />
                <span className={`top-nav__logo ${styles.logo}`}>OPNXT</span>
              </span>
              <span className={`top-nav__tagline ${styles.tagline}`}>
                Concept → Delivery Control Center
              </span>
            </Link>
            <nav
              className={`top-nav__links ${styles.links}`}
              aria-label="Primary navigation"
            >
              <Link
                href="/"
                className={
                  router.pathname === "/" || router.pathname.startsWith("/mvp")
                    ? "active"
                    : ""
                }
              >
                MVP
              </Link>
              <Link
                href="/dashboard"
                className={router.pathname.startsWith("/dashboard") ? "active" : ""}
              >
                Dashboard
              </Link>
              <Link
                href="/projects"
                className={router.pathname.startsWith("/projects") ? "active" : ""}
              >
                Projects
              </Link>
            </nav>
          </>
        ) : (
          <div className={styles.minimalCrumb} aria-label="Current section">
            <Link href="/" className={styles.minimalHome} aria-label="Return to home">
              <span>OPNXT</span>
            </Link>
            <span className={styles.minimalDivider} aria-hidden="true">
              /
            </span>
            <span aria-current="page" className={styles.minimalCurrent}>
              {sectionLabel}
            </span>
          </div>
        )}
        <div className={`top-nav__actions ${styles.actions}`}>
          {showMinimalCta && (
            <Link href="/projects" className={styles.minimalPrimaryCta}>
              View projects
            </Link>
          )}
          {appearance === "minimal" && user ? (
            <div className={styles.userSummary}>
              <span className={styles.userAvatar}>{(user.name || user.email || "?").slice(0, 2).toUpperCase()}</span>
              <div className={styles.userCopy}>
                <span className={styles.userName}>{user.name || "Account"}</span>
                <span className={styles.userMeta}>{user.email}</span>
              </div>
            </div>
          ) : null}
          {showAuthButtons && authed ? (
            <button
              type="button"
              className="btn btn-secondary top-nav__action"
              onClick={onSignOut}
            >
              Sign out
            </button>
          ) : null}
          {showAuthButtons && !authed ? (
            <button
              type="button"
              className="btn btn-primary top-nav__action"
              onClick={onSignIn}
            >
              Sign in
            </button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
