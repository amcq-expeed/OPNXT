import type { ReactNode } from "react";

export interface KpiCardProps {
  title: string;
  value: ReactNode;
  description?: ReactNode;
  trendLabel?: string;
  trendDirection?: "up" | "down" | "flat";
  onClick?: () => void;
  className?: string;
}

export default function KpiCard({
  title,
  value,
  description,
  trendLabel,
  trendDirection = "flat",
  onClick,
  className = "",
}: KpiCardProps) {
  const isInteractive = typeof onClick === "function";
  const Component = (isInteractive ? "button" : "div") as
    | "button"
    | "div";
  return (
    <Component
      className={("kpi-card " + className).trim()}
      {...(isInteractive ? { type: "button", onClick } : {})}
    >
      <div className="kpi-card__header">
        <span className="kpi-card__title">{title}</span>
        {trendLabel ? (
          <span
            className={`kpi-card__trend kpi-card__trend--${trendDirection}`}
            aria-label={`Trend ${trendDirection}`}
          >
            {trendLabel}
          </span>
        ) : null}
      </div>
      <div className="kpi-card__value">{value}</div>
      {description ? (
        <p className="kpi-card__description">{description}</p>
      ) : null}
    </Component>
  );
}
