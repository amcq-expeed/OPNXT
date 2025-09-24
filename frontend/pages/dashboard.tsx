import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Card from "../components/ui/Card";
import Stat from "../components/ui/Stat";
import NextAction from "../components/ui/NextAction";
import Stepper from "../components/ui/Stepper";
import { listProjects, getProjectContext, Project, ProjectContext } from "../lib/api";

export default function DashboardPage() {
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [ctx, setCtx] = useState<ProjectContext | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const ps = await listProjects();
        setProjects(ps);
        if (ps.length && !selected) setSelected(ps[0].project_id);
      } catch {}
    })();
  }, []);

  useEffect(() => {
    if (!selected) return;
    (async () => {
      try {
        setLoading(true);
        const c = await getProjectContext(selected);
        setCtx(c);
      } catch {}
      finally { setLoading(false); }
    })();
  }, [selected]);

  const approvals = useMemo(() => (ctx as any)?.data?.approvals || {}, [ctx]);
  const answers = useMemo(() => (ctx as any)?.data?.answers || {}, [ctx]);
  const reqCount = useMemo(() => Array.isArray(answers?.Requirements) ? answers.Requirements.length : 0, [answers]);
  const charterApproved = !!approvals?.["ProjectCharter.md"]?.approved;
  const srsApproved = !!approvals?.["SRS.md"]?.approved;
  const sddApproved = !!approvals?.["SDD.md"]?.approved;
  const testApproved = !!approvals?.["TestPlan.md"]?.approved;

  // Gate logic → derive the current step index
  const currentIndex = useMemo(() => {
    let idx = 0; // Charter
    if (charterApproved) idx = 1; // Requirements
    if (reqCount > 0) idx = 2; // Specifications
    if (srsApproved) idx = 3; // Design
    if (sddApproved) idx = 4; // Implementation
    if (testApproved) idx = 6; // Deployment
    return idx;
  }, [charterApproved, reqCount, srsApproved, sddApproved, testApproved]);

  useEffect(() => {
    // Future: fetch KPIs and activity
  }, []);

  return (
    <div>
      <h2>Dashboard</h2>
      {loading && <div className="badge" role="status">Loading…</div>}

      <NextAction
        message={projects.length ? "Select a project to view its Phase Gate status." : "Create a project to get started."}
        primary={projects.length ? { label: "Go to Projects", href: "/projects", variant: "primary" } : { label: "Create Project", href: "/projects", variant: "primary" }}
        secondary={selected ? [{ label: "Open Project", href: `/projects/${selected}` }] : []}
      />

      <div className="grid-2" aria-label="KPI Cards">
        <Stat label="Projects" value={String(projects.length || "—")} />
        <Stat label="Requirements (stored)" value={selected ? String(reqCount) : "—"} />
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <Card title="Recent Activity" ariaLabel="Recent Activity">
          <ul style={{ margin: 0 }}>
            <li className="muted">No recent activity.</li>
          </ul>
        </Card>
        <Card title="Phase Gate" ariaLabel="Phase Gate">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <label className="muted">Project</label>
            <select className="select" value={selected || ''} onChange={e => setSelected(e.target.value || null)}>
              <option value="" disabled>Choose…</option>
              {projects.map(p => <option key={p.project_id} value={p.project_id}>{p.name || p.project_id}</option>)}
            </select>
            {selected && <Link href={`/projects/${selected}`} className="btn">Open</Link>}
          </div>
          <Stepper
            steps={[
              { id: "charter", label: "Charter" },
              { id: "requirements", label: "Requirements" },
              { id: "specs", label: "Specifications" },
              { id: "design", label: "Design" },
              { id: "impl", label: "Implementation" },
              { id: "test", label: "Testing" },
              { id: "deploy", label: "Deployment" },
            ]}
            currentIndex={currentIndex}
          />
          {selected && (
            <ul style={{ marginTop: 8 }}>
              <li>Charter approved: {charterApproved ? 'Yes' : 'No'}</li>
              <li>Requirements captured: {reqCount > 0 ? `${reqCount} item(s)` : 'No'}</li>
              <li>SRS approved: {srsApproved ? 'Yes' : 'No'}</li>
              <li>SDD approved: {sddApproved ? 'Yes' : 'No'}</li>
              <li>Test Plan approved: {testApproved ? 'Yes' : 'No'}</li>
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
