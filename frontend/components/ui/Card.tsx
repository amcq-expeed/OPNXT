import type { PropsWithChildren, ReactNode } from "react";

interface CardProps extends PropsWithChildren {
  title?: ReactNode;
  className?: string;
  role?: string;
  ariaLabel?: string;
}

export default function Card({
  title,
  children,
  className = "",
  role = "region",
  ariaLabel,
}: CardProps) {
  return (
    <section
      className={("card " + className).trim()}
      role={role as any}
      aria-label={ariaLabel}
    >
      {title ? <div className="section-title">{title}</div> : null}
      {children}
    </section>
  );
}
