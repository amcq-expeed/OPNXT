import { useMemo, useState } from "react";

const navTabs = ["Profile", "Customize", "Integrations", "Account", "Billing"];

const templateCatalog = [
  {
    name: "Requirements Blueprint",
    summary: "End-to-end specification ready for governance review.",
    tags: ["Vision", "Scope", "Traceability"],
    default: true,
  },
  {
    name: "Service Launch Playbook",
    summary: "Operational readiness plan with RACI, runbooks, and SLAs.",
    tags: ["Operations", "Support", "SLAs"],
    default: false,
  },
  {
    name: "Regulatory Compliance Checklist",
    summary: "Ensure accessibility, compliance, and audit readiness across initiatives.",
    tags: ["Controls", "Audits", "Evidence"],
    default: false,
  },
  {
    name: "Customer Journey Map",
    summary: "Map personas, journeys, and opportunity areas to drive experience design.",
    tags: ["Personas", "Journeys", "Insights"],
    default: false,
  },
  {
    name: "Go-to-Market Plan",
    summary: "Align launch goals, enablement, and channel strategy for release success.",
    tags: ["Marketing", "Launch", "Enablement"],
    default: false,
  },
  {
    name: "Innovation Canvas",
    summary: "Frame hypotheses, metrics, and experiments for discovery sprints.",
    tags: ["Hypotheses", "KPIs", "Experiments"],
    default: false,
  },
];

export default function TemplatesPage() {
  const [activeTab, setActiveTab] = useState<string>("Customize");

  const defaultTemplate = useMemo(
    () => templateCatalog.find((template) => template.default)?.name,
    [],
  );

  return (
    <div className="template-layout" aria-live="polite">
      <header className="template-header">
        <h1>Settings</h1>
        <p className="muted">
          Manage your workspace defaults, template library, and integrations so teams launch faster.
        </p>
        <nav className="template-tabs" aria-label="Settings navigation">
          {navTabs.map((tab) => {
            const isActive = activeTab === tab;
            return (
              <button
                key={tab}
                type="button"
                className={isActive ? "template-tab template-tab--active" : "template-tab"}
                onClick={() => setActiveTab(tab)}
                aria-pressed={isActive}
              >
                {tab}
              </button>
            );
          })}
        </nav>
      </header>

      {activeTab === "Customize" ? (
        <section className="template-manager" aria-label="Template management">
          <div className="template-manager__header">
            <div>
              <h2>Manage your document templates</h2>
              <p>Set defaults, preview structures, and tailor playbooks to your operating model.</p>
            </div>
            <div className="template-manager__actions">
              <button type="button">Add new template</button>
              <button type="button">Manage categories</button>
            </div>
          </div>

          <div className="template-grid">
            {templateCatalog.map((template) => (
              <article key={template.name} className="template-card">
                <div className="template-card__heading">
                  <span className="template-card__name">{template.name}</span>
                  {template.default && <span className="template-card__badge">Default</span>}
                </div>
                <p className="template-card__summary">{template.summary}</p>
                <div className="template-card__tags" aria-hidden="true">
                  {template.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
                <div className="template-card__footer">
                  <button type="button" disabled={template.default}>
                    {template.default ? "Current default" : "Make default"}
                  </button>
                  <button type="button">Preview</button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : (
        <section className="template-manager" aria-label={`${activeTab} coming soon`}>
          <div className="template-manager__header">
            <div>
              <h2>{activeTab}</h2>
              <p>We&apos;re building out this section. Check back soon for new controls.</p>
            </div>
          </div>
        </section>
      )}

      <footer className="muted" style={{ fontSize: 12 }}>
        Need help? Visit the OPNXT knowledge base or contact support for enterprise onboarding.
      </footer>
    </div>
  );
}
