import type { ReactNode } from "react";

interface ResultBannerProps {
  title: string;
  subtitle?: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
  role?: string;
}

const TONE_CLASS_MAP: Record<NonNullable<ResultBannerProps["tone"]>, string> = {
  default: "result-banner--default",
  success: "result-banner--success",
  warning: "result-banner--warning",
  danger: "result-banner--danger",
  info: "result-banner--info",
};

export function ResultBanner({
  title,
  subtitle,
  tone = "default",
  action,
  children,
  className,
  role,
}: ResultBannerProps) {
  const toneClass = TONE_CLASS_MAP[tone] ?? TONE_CLASS_MAP.default;
  return (
    <section className={`result-banner ${toneClass} ${className ?? ""}`.trim()} role={role ?? "status"}>
      <header className="result-banner__header">
        <div className="result-banner__heading">
          <h3 className="result-banner__title">{title}</h3>
          {subtitle ? <p className="result-banner__subtitle">{subtitle}</p> : null}
        </div>
        {action ? <div className="result-banner__action">{action}</div> : null}
      </header>
      {children ? <div className="result-banner__body">{children}</div> : null}
    </section>
  );
}

ResultBanner.displayName = "ResultBanner";

export default ResultBanner;
