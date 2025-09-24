import type { ReactNode } from "react";

interface StatProps {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  className?: string;
}

export default function Stat({ label, value, hint, className = "" }: StatProps) {
  return (
    <div className={("card " + className).trim()} role="region" aria-label={`${String(label)} Stat`}>
      <div className="muted" style={{ marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1 }}>{value}</div>
      {hint ? <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>{hint}</div> : null}
    </div>
  );
}
