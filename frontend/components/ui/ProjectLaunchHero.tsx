import { FormEvent, useMemo, useState } from 'react';

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
};

export default function ProjectLaunchHero({
  onSubmit,
  onScenarioSelect,
  defaultValue = '',
  value: controlled,
  onChange,
  scenarios,
  busy = false,
  disabled = false,
}: ProjectLaunchHeroProps) {
  const defaultScenarios: LaunchScenario[] = useMemo(
    () => [
      { label: 'Healthcare', value: 'Healthcare Appointment System' },
      { label: 'Banking', value: 'Bank Payment Platform' },
      { label: 'E-commerce', value: 'E-commerce Store' },
      { label: 'Custom', value: 'Custom Application' },
    ],
    [],
  );

  const chipScenarios = scenarios && scenarios.length > 0 ? scenarios : defaultScenarios;

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

  return (
    <section className="launch-hero" role="region" aria-label="Projects Hub">
      <div className="launch-hero__body">
        <div className="launch-hero__intro">
          <span className="launch-hero__badge badge">Projects Hub</span>
          <h1 className="launch-hero__title">Concept → Delivery projects</h1>
          <p className="launch-hero__subtitle">
            Capture initiatives, seed requirements, and jump straight into the AI workspace. Every project keeps
            documents, readiness, and approvals synchronized.
          </p>
        </div>

        <div className="launch-hero__panel">
          <form className="launch-hero__form" onSubmit={handleSubmit}>
            <span className="launch-hero__panel-label">What are you building?</span>
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
              <button type="submit" className="launch-hero__start" disabled={disabled || busy || !currentValue.trim()}>
                {busy ? 'Starting…' : 'Start'}
              </button>
            </div>
          </form>

          <div className="launch-hero__scenarios" aria-label="Scenario shortcuts">
            <span className="launch-hero__chip-label">Or jump into a scenario:</span>
            <div className="launch-hero__chip-group">
              {chipScenarios.map((scenario) => (
                <button
                  key={scenario.label}
                  type="button"
                  className="launch-hero__chip chip"
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
        </div>
      </div>
    </section>
  );
}
