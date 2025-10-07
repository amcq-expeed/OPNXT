import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { getAccessToken, setAccessToken, TOKEN_CHANGE_EVENT } from "../lib/api";
import styles from "./TopNav.module.css";

interface TopNavProps {
  appearance?: "standard" | "overlay";
}

export default function TopNav({ appearance = "standard" }: TopNavProps) {
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
    return appearance === "overlay"
      ? `${base} top-nav--overlay ${styles.topNavOverlay}`
      : base;
  }, [appearance]);

  return (
    <header className={navClass} role="banner">
      <div className={`top-nav__inner ${styles.inner}`}>
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
        <div className={`top-nav__actions ${styles.actions}`}>
          {authed ? (
            <button
              type="button"
              className="btn btn-secondary top-nav__action"
              onClick={onSignOut}
            >
              Sign out
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary top-nav__action"
              onClick={onSignIn}
            >
              Sign in
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
