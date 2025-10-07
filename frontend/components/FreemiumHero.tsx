import React from "react";
import styles from "./FreemiumHero.module.css";

interface Feature {
  title: string;
  description: string;
}

interface FreemiumHeroProps {
  authed: boolean;
  heroVisual?: React.ReactNode;
  onPrimaryAction?: () => void;
  primaryLabel?: string;
  primaryDisabled?: boolean;
  secondaryLabel?: string;
  onSecondaryAction?: () => void;
  features: Feature[];
  loading?: boolean;
  error?: string | null;
  sessionReady?: boolean;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  headline?: string;
  subtitle?: string;
  className?: string;
  variant?: "default" | "compact";
}

export default function FreemiumHero({
  authed,
  heroVisual,
  onPrimaryAction,
  primaryLabel,
  primaryDisabled,
  secondaryLabel,
  onSecondaryAction,
  features,
  loading,
  error,
  sessionReady,
  children,
  footer,
  headline = "Ship enterprise-grade SDLC docs in days, not weeks.",
  subtitle = "Capture discovery notes, watch AI assemble Project Charters, SRS, SDD, and Test Plans, then govern delivery through approvals and phase gates.",
  className,
  variant = "default",
}: FreemiumHeroProps) {
  const showPrimary = Boolean(primaryLabel && onPrimaryAction);
  const showSecondary = Boolean(secondaryLabel && onSecondaryAction);

  const renderLaunchArea = () => {
    if (!children) return null;

    return (
      <div className="freemium-hero__launch" aria-live="polite">
        {authed && loading && (
          <div className="badge" role="status">
            Preparing session…
          </div>
        )}
        {authed && error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {authed && !loading && !error && !sessionReady && (
          <div className="muted">Connecting to your workspace…</div>
        )}
        {(!authed || !loading) &&
          (!authed || !error) &&
          (authed ? sessionReady : true) && (
            <div className="freemium-hero__launch-inner">{children}</div>
          )}
      </div>
    );
  };

  const launchContent = renderLaunchArea();

  const heroClasses = ["freemium-hero", styles.hero];
  if (variant === "compact") {
    heroClasses.push("freemium-hero--compact", styles.compact);
  }
  if (!launchContent) {
    heroClasses.push("freemium-hero--single");
  }
  if (className) {
    heroClasses.push(className);
  }

  const isCompact = variant === "compact";

  return (
    <section className={heroClasses.join(" ")} aria-label="AI SDLC launchpad">
      <div
        className={`freemium-hero__pitch ${isCompact ? styles.cluster : ""}`}
      >
        <div
          className={`freemium-hero__headline-row ${isCompact ? styles.headlineRow : ""}`}
        >
          {heroVisual && (
            <div className="freemium-hero__visual">{heroVisual}</div>
          )}
          <div className="freemium-hero__headline-copy">
            {!authed && (
              <span className="badge freemium-hero__badge">
                Freemium preview
              </span>
            )}
            <h1 className="freemium-hero__title">{headline}</h1>
            <p className="freemium-hero__subtitle">{subtitle}</p>
          </div>
        </div>
        <ul
          className={`freemium-hero__features ${styles.features}`}
          aria-label="Highlights"
        >
          {features.map((feature) => (
            <li key={feature.title}>
              <strong>{feature.title}</strong>
              <span>{feature.description}</span>
            </li>
          ))}
        </ul>
        {(showPrimary || showSecondary) && (
          <div className="freemium-hero__actions">
            {showPrimary && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={onPrimaryAction}
                disabled={primaryDisabled}
              >
                {primaryLabel}
              </button>
            )}
            {showSecondary && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onSecondaryAction}
              >
                {secondaryLabel}
              </button>
            )}
          </div>
        )}
        {(showPrimary || showSecondary) && (
          <p className="freemium-hero__footnote">
            No credit card required · Keep your progress when you upgrade.
          </p>
        )}
        {footer && (
          <div
            className={`freemium-hero__footer ${isCompact ? styles.cluster : ""}`}
          >
            {footer}
          </div>
        )}
      </div>

      {launchContent && (
        <div
          className={`freemium-hero__interactive ${isCompact ? styles.cluster : ""}`}
        >
          {launchContent}
        </div>
      )}
    </section>
  );
}
