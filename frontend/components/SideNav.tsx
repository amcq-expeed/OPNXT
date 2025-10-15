import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./SideNav.module.css";
import type { User } from "../lib/api";

const navItems = [
  {
    href: "/dashboard",
    label: "Chats",
    match: (path: string) => path.startsWith("/dashboard"),
    icon: "💬",
    count: 0,
  },
  {
    href: "/projects",
    label: "Documents",
    match: (path: string) => path.startsWith("/projects"),
    icon: "📄",
    count: 0,
  },
  {
    href: "/start",
    label: "Projects",
    match: (path: string) => path.startsWith("/start"),
    icon: "🧭",
    count: undefined,
  },
  {
    href: "/templates",
    label: "Templates",
    match: (path: string) => path.startsWith("/templates"),
    icon: "📦",
    count: undefined,
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
  const recentChats: { id: string; title: string; subtitle: string }[] = [];

  const items = useMemo(() => navItems, []);

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
          <img src="/logo-full.svg" alt="Expeed Software" className={styles.brandLogo} />
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
                  {typeof item.count === "number" ? (
                    <span className={styles.navBadge}>{item.count}</span>
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
          <span className={styles.usageValue}>0 / 3</span>
        </div>
        <div className={styles.usageMeter}>
          <span style={{ width: "0%" }} />
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
        {recentChats.length ? (
          <ul className={styles.recentsList}>
            {recentChats.map((chat) => (
              <li key={chat.id}>
                <button type="button" className={styles.recentsItem}>
                  <span className={styles.recentsTitle}>{chat.title}</span>
                  <span className={styles.recentsSubtitle}>{chat.subtitle}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.recentsEmpty}>No chats yet.</p>
        )}
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
