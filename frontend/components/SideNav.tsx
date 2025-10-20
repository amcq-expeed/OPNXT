import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./SideNav.module.css";
import type { User, WorkspaceSummary, ChatSession } from "../lib/api";
import { getWorkspaceSummary, listRecentChatSessions } from "../lib/api";

type NavItem = {
  href: string;
  label: string;
  match: (path: string) => boolean;
  icon: string;
};

const baseNavItems: NavItem[] = [
  {
    href: "/dashboard",
    label: "Chats",
    match: (path: string) => path.startsWith("/dashboard"),
    icon: "💬",
  },
  {
    href: "/projects",
    label: "Documents",
    match: (path: string) => path.startsWith("/projects"),
    icon: "📄",
  },
  {
    href: "/start",
    label: "Projects",
    match: (path: string) => path.startsWith("/start"),
    icon: "🧭",
  },
  {
    href: "/templates",
    label: "Templates",
    match: (path: string) => path.startsWith("/templates"),
    icon: "📦",
  },
];

type SideNavProps = {
  collapsed?: boolean;
  onToggle?: () => void;
  user: User | null;
};

export default function SideNav({ collapsed = false, onToggle, user }: SideNavProps) {
  const router = useRouter();
  const activeHref = router.pathname;
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement | null>(null);
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null);
  const [recentChats, setRecentChats] = useState<ChatSession[]>([]);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [loadingSummary, setLoadingSummary] = useState<boolean>(false);
  const [loadingRecents, setLoadingRecents] = useState<boolean>(false);

  const items = useMemo(() => baseNavItems, []);

  useEffect(() => {
    let cancelled = false;
    setLoadingSummary(true);
    setSummaryError(null);
    getWorkspaceSummary()
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((error: any) => {
        if (!cancelled) setSummaryError(error?.message || "Unable to load workspace summary.");
      })
      .finally(() => {
        if (!cancelled) setLoadingSummary(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoadingRecents(true);
    listRecentChatSessions(6)
      .then((sessions) => {
        if (!cancelled) setRecentChats(sessions ?? []);
      })
      .catch(() => {
        if (!cancelled) setRecentChats([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingRecents(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!accountOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!accountRef.current) return;
      if (!accountRef.current.contains(event.target as Node)) {
        setAccountOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [accountOpen]);

  useEffect(() => {
    if (collapsed) setAccountOpen(false);
  }, [collapsed]);

  return (
    <aside
      className={`${styles.sideNav} ${collapsed ? styles.collapsed : ""}`.trim()}
      aria-label="Primary"
    >
      <div className={styles.topRow}>
        <Link href="/" className={styles.brand} aria-label="OPNXT home">
          <Image
            src="/logo-full.svg"
            alt="Expeed Software"
            className={styles.brandLogo}
            width={132}
            height={28}
            priority
          />
        </Link>
      </div>
      <div className={styles.workspaceSelect}>
        <button type="button" aria-haspopup="listbox">
          <span>{user?.name || "Personal account"}</span>
          <span aria-hidden="true">▾</span>
        </button>
      </div>
      <Link href="/dashboard" className={styles.primaryAction}>
        <span aria-hidden="true">＋</span>
        <span>Start New Chat</span>
      </Link>
      <nav className={styles.nav}>
        <ul className={styles.navList}>
          {items.map((item) => {
            const isActive = item.match(activeHref);
            return (
              <li key={item.href} className={styles.navItem}>
                <Link
                  href={item.href}
                  className={`${styles.navLink} ${isActive ? styles.navLinkActive : ""}`.trim()}
                  aria-current={isActive ? "page" : undefined}
                >
                  <span className={styles.navIcon} aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className={styles.navLabel}>{item.label}</span>
                  {summary ? (
                    item.href === "/dashboard" ? (
                      <span className={styles.navBadge}>{summary.chat_sessions}</span>
                    ) : item.href === "/projects" ? (
                      <span className={styles.navBadge}>{summary.documents}</span>
                    ) : null
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className={styles.usageCard}>
        <div className={styles.usageHeader}>
          <span className={styles.usageLabel}>Chats used</span>
          <span className={styles.usageValue}>
            {summary ? `${Math.min(summary.chat_sessions, 3)} / 3` : loadingSummary ? "Loading…" : "—"}
          </span>
        </div>
        <div className={styles.usageMeter}>
          <span
            style={{
              width: summary ? `${Math.min((summary.chat_sessions / 3) * 100, 100)}%` : "0%",
            }}
          />
        </div>
        <Link href="/billing" className={styles.usageUpgrade}>
          Upgrade for unlimited
        </Link>
      </div>
      <div className={styles.recents}>
        <div className={styles.recentsHeader}>
          <button type="button" className={styles.recentsTab}>
            Recent
          </button>
          <button type="button" className={styles.recentsDropdown}>
            All chats ▾
          </button>
        </div>
        <div className={styles.searchHint}>
          Press <kbd>⌘</kbd>
          <kbd>K</kbd> to search
        </div>
        {loadingRecents ? (
          <p className={styles.recentsEmpty}>Loading…</p>
        ) : recentChats.length ? (
          <ul className={styles.recentsList}>
            {recentChats.map((chat) => (
              <li key={chat.session_id}>
                <button
                  type="button"
                  className={styles.recentsItem}
                  onClick={() => {
                    if (chat.kind === "project" && chat.project_id) {
                      router.push(`/projects/${chat.project_id}?session=${chat.session_id}`);
                      return;
                    }
                    router.push(`/dashboard?session=${chat.session_id}`);
                  }}
                >
                  <span className={styles.recentsTitle}>{chat.title}</span>
                  <span className={styles.recentsSubtitle}>
                    {chat.persona ? chat.persona.toUpperCase() : chat.kind === "guest" ? "Guest" : "Project"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.recentsEmpty}>No chats yet.</p>
        )}
        {summaryError && <p className={styles.recentsEmpty}>{summaryError}</p>}
      </div>
      <div
        className={`${styles.account} ${accountOpen ? styles.accountOpen : ""}`.trim()}
        ref={accountRef}
      >
        <button
          type="button"
          className={styles.accountButton}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setAccountOpen((prev) => !prev);
          }}
          aria-haspopup="menu"
          aria-expanded={accountOpen}
        >
          <span className={styles.avatar} aria-hidden="true">
            {(user?.name || user?.email || "?").slice(0, 2).toUpperCase()}
          </span>
          <div className={styles.accountCopy}>
            <span className={styles.accountName}>{user?.name?.trim() || "Account"}</span>
            <span className={styles.accountPlan}>{user?.email || "Free tier"}</span>
          </div>
        </button>
        <div className={styles.accountMenu} role="menu">
          <div className={styles.accountMenuHeader} aria-hidden="true">
            <span className={styles.accountMenuTitle}>My account</span>
          </div>
          <Link
            href="/account"
            role="menuitem"
            tabIndex={accountOpen ? 0 : -1}
            className={styles.accountMenuItem}
          >
            Profile &amp; billing
          </Link>
          <Link
            href="/settings"
            role="menuitem"
            tabIndex={accountOpen ? 0 : -1}
            className={styles.accountMenuItem}
          >
            Workspace settings
          </Link>
          <Link
            href="/logout"
            role="menuitem"
            tabIndex={accountOpen ? 0 : -1}
            className={styles.accountMenuItem}
          >
            Sign out
          </Link>
        </div>
      </div>
    </aside>
  );
}
