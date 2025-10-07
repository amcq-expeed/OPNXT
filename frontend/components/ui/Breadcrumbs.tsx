import Link from "next/link";
import { useRouter } from "next/router";

export default function Breadcrumbs() {
  const router = useRouter();
  const asPath = router?.asPath || "/";
  const qIndex = asPath.indexOf("?");
  const clean = qIndex >= 0 ? asPath.slice(0, qIndex) : asPath;
  const parts = clean.split("/").filter(Boolean);
  const items = parts.map((p, i) => {
    const href = "/" + parts.slice(0, i + 1).join("/");
    const label = decodeURIComponent(p);
    const friendly =
      label === "dashboard"
        ? "Dashboard"
        : label === "projects"
          ? "Projects"
          : label === "chat"
            ? "Chat"
            : label === "documents"
              ? "Documents"
              : label === "settings"
                ? "Settings"
                : label;
    return { href, label: friendly };
  });

  if (items.length === 0) return null;

  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
        }}
      >
        <li>
          <Link href="/">Home</Link>
        </li>
        {items.map((c, i) => (
          <li
            key={c.href}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <span className="muted">/</span>
            {i < items.length - 1 ? (
              <Link href={c.href}>{c.label}</Link>
            ) : (
              <span aria-current="page">{c.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
