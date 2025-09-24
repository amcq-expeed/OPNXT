import type { ReactNode } from "react";

interface Action {
  label: string;
  onClick?: () => void;
  href?: string;
  variant?: "primary" | "default";
}

interface NextActionProps {
  title?: ReactNode;
  message: ReactNode;
  primary: Action;
  secondary?: Action[];
  className?: string;
}

export default function NextAction({ title = "Next best action", message, primary, secondary = [], className = "" }: NextActionProps) {
  return (
    <section className={("next-action " + className).trim()} role="region" aria-label="Next best action">
      <div className="next-action__content">
        <div className="next-action__title">{title}</div>
        <div className="next-action__msg">{message}</div>
      </div>
      <div className="next-action__actions">
        {primary.href ? (
          <a className={`btn ${primary.variant === 'primary' ? 'btn-primary' : ''}`} href={primary.href}>{primary.label}</a>
        ) : (
          <button className={`btn ${primary.variant === 'primary' ? 'btn-primary' : ''}`} onClick={primary.onClick}>{primary.label}</button>
        )}
        {secondary.map((a, i) => (
          a.href ? (
            <a key={i} className="btn" href={a.href}>{a.label}</a>
          ) : (
            <button key={i} className="btn" onClick={a.onClick}>{a.label}</button>
          )
        ))}
      </div>
    </section>
  );
}
