import { useMemo } from "react";

interface DocListProps {
  artifacts: { filename: string; label?: string; status?: string }[];
  selected: string | null;
  approvals?: Record<string, { approved: boolean; approved_at?: string }>;
  onSelect: (filename: string) => void;
}

export default function DocList({
  artifacts,
  selected,
  approvals,
  onSelect,
}: DocListProps) {
  const sorted = useMemo(() => {
    return artifacts.slice().sort((a, b) => a.filename.localeCompare(b.filename));
  }, [artifacts]);

  return (
    <ul className="doc-list">
      {sorted.map((a) => {
        const state = approvals?.[a.filename];
        const label = a.label || a.filename;
        const status = a.status || (state?.approved
          ? `Approved · ${new Date(state.approved_at || "").toLocaleDateString()}`
          : undefined);
        return (
          <li key={a.filename} className={selected === a.filename ? "is-active" : ""}>
            <button type="button" onClick={() => onSelect(a.filename)}>
              <span className="doc-list__name" title={a.filename}>
                {label}
              </span>
              {status && <span className="doc-list__badge">{status}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
