import { FormEvent, ReactNode, useMemo, useState } from "react";

export type LaunchScenario = {
  label: string;
  value: string;
};

type ProjectLaunchHeroProps = {
  onSubmit: (value: string) => void;
  onScenarioSelect: (scenario: LaunchScenario) => void;
  defaultValue?: string;
  value?: string;
  onChange?: (value: string) => void;
  scenarios?: LaunchScenario[];
  busy?: boolean;
  disabled?: boolean;
  badgeLabel?: string;
  title?: string;
  subtitle?: string;
  startLabel?: string;
  supportingCopy?: ReactNode;
  className?: string;
  showForm?: boolean;
  showScenarios?: boolean;
  scenariosLabel?: string;
};

export default function ProjectLaunchHero({
  onSubmit,
  onScenarioSelect,
  defaultValue = "",
  value: controlled,
  onChange,
  scenarios,
  busy = false,
  disabled = false,
  badgeLabel = "Projects Hub",
  title = "Concept to Deployment",
  subtitle = "Start with a simple idea and walk through the full engineering design process—from requirements to architecture, implementation, testing, and deployment—with SDLC documentation generated at every step.",
  startLabel = "Start",
  supportingCopy,
  className,
  showForm = true,
  showScenarios = true,
  scenariosLabel = "Or jump into a scenario:",
}: ProjectLaunchHeroProps) {
  const defaultScenarios: LaunchScenario[] = useMemo(
    () => [
      { label: "Healthcare", value: "Healthcare Appointment System" },
      { label: "Banking", value: "Bank Payment Platform" },
      { label: "E-commerce", value: "E-commerce Store" },
      { label: "Custom", value: "Custom Application" },
    ],
    [],
  );

  const chipScenarios =
    scenarios && scenarios.length > 0 ? scenarios : defaultScenarios;

  const [internal, setInternal] = useState(defaultValue);
  const currentValue = controlled !== undefined ? controlled : internal;

  const setValue = (next: string) => {
    if (controlled === undefined) {
      setInternal(next);
    }
    onChange?.(next);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = currentValue.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
  };

  const renderScenarios = showScenarios && chipScenarios.length > 0;
  const renderForm = showForm;
  const hasPanelContent = renderForm || renderScenarios;

  const sectionClasses = ["launch-hero"];
  if (!hasPanelContent) {
    sectionClasses.push("launch-hero--single");
  }
  if (className) {
    sectionClasses.push(className);
  }

  return (
    <section
      className={sectionClasses.join(" ")}
      role="region"
      aria-label="Projects Hub"
    >
      <div className="launch-hero__card">
        <div className="launch-hero__intro">
          <span className="launch-hero__badge badge">{badgeLabel}</span>
          <h1 className="launch-hero__title">{title}</h1>
          <p className="launch-hero__subtitle">{subtitle}</p>
          {supportingCopy && (
            <div className="launch-hero__supporting">{supportingCopy}</div>
          )}
        </div>

        {hasPanelContent && (
          <div className="launch-hero__panel">
            {renderForm && (
              <form className="launch-hero__form" onSubmit={handleSubmit}>
                <label
                  className="launch-hero__panel-label"
                  htmlFor="project-idea"
                >
                  What are you building?
                </label>
                <div className="launch-hero__input-row">
                  <input
                    id="project-idea"
                    type="text"
                    className="launch-hero__input"
                    placeholder="e.g., Healthcare Appointment System"
                    value={currentValue}
                    onChange={(event) => setValue(event.target.value)}
                    disabled={disabled || busy}
                    aria-label="Project idea"
                  />
                  <button
                    type="submit"
                    className="launch-hero__start"
                    disabled={disabled || busy || !currentValue.trim()}
                  >
                    {busy ? "Starting…" : startLabel}
                  </button>
                </div>
              </form>
            )}

            {renderScenarios && (
              <div
                className="launch-hero__scenarios"
                aria-label="Scenario shortcuts"
              >
                <span className="launch-hero__chip-label">
                  {scenariosLabel}
                </span>
                <div className="launch-hero__chip-group">
                  {chipScenarios.map((scenario) => (
                    <button
                      key={scenario.label}
                      type="button"
                      className="launch-hero__chip"
                      onClick={() => {
                        setValue(scenario.value);
                        onScenarioSelect(scenario);
                      }}
                      disabled={disabled || busy}
                    >
                      {scenario.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
