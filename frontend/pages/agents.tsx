import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { Agent, AgentCreate } from "../lib/api";
import {
  listAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  me,
  User,
  canWrite,
  isAdmin,
  getAccessToken,
} from "../lib/api";

export default function AgentsPage() {
  const [items, setItems] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");

  const [creating, setCreating] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  const apiBase = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
    [],
  );

  async function refresh() {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const data = await listAgents();
      setItems(data);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (typeof window !== "undefined" && !getAccessToken()) {
      const rt = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?returnTo=${rt}`;
      return;
    }
    (async () => {
      try {
        const u = await me();
        setCurrentUser(u);
        await refresh();
      } catch (e) {
        if (typeof window !== "undefined") {
          const rt = encodeURIComponent(
            window.location.pathname + window.location.search,
          );
          window.location.href = `/login?returnTo=${rt}`;
        }
      }
    })();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    const payload: AgentCreate = {
      name,
      description: description || undefined,
      capabilities: capabilities
        ? capabilities
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [],
      endpoint_url: endpointUrl || undefined,
    };
    try {
      setCreating(true);
      const created = await createAgent(payload);
      setName("");
      setDescription("");
      setCapabilities("");
      setEndpointUrl("");
      setItems((prev) => [created, ...prev]);
      setNotice(`Agent ${created.name} created.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setCreating(false);
    }
  }

  async function onActivate(agent: Agent) {
    try {
      setUpdatingId(agent.agent_id);
      const updated = await updateAgent(agent.agent_id, {
        status: agent.status === "active" ? "inactive" : "active",
      });
      setItems((prev) =>
        prev.map((a) => (a.agent_id === agent.agent_id ? updated : a)),
      );
      setNotice(`Agent ${updated.name} is now ${updated.status}.`);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setUpdatingId(null);
    }
  }

  async function onDelete(agent_id: string) {
    if (!confirm("Delete this agent?")) return;
    try {
      setDeletingId(agent_id);
      await deleteAgent(agent_id);
      setItems((prev) => prev.filter((a) => a.agent_id !== agent_id));
      setNotice("Agent deleted.");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div>
      <h2>Agents</h2>
      <p style={{ color: "#666" }}>API: {apiBase}</p>

      {canWrite(currentUser) ? (
        <form
          onSubmit={onCreate}
          style={{ display: "grid", gap: 8, maxWidth: 520, marginBottom: 24 }}
        >
          <input
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <input
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <input
            placeholder="Capabilities (comma-separated)"
            value={capabilities}
            onChange={(e) => setCapabilities(e.target.value)}
          />
          <input
            placeholder="Endpoint URL (optional)"
            value={endpointUrl}
            onChange={(e) => setEndpointUrl(e.target.value)}
          />
          <button type="submit" disabled={creating}>
            {creating ? "Creating…" : "Create"}
          </button>
        </form>
      ) : (
        <p style={{ color: "#666" }}>You have read-only access.</p>
      )}

      {loading && <p>Loading…</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
      {notice && <p style={{ color: "#0a0" }}>{notice}</p>}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th
              style={{
                textAlign: "left",
                borderBottom: "1px solid #ddd",
                padding: 8,
              }}
            >
              ID
            </th>
            <th
              style={{
                textAlign: "left",
                borderBottom: "1px solid #ddd",
                padding: 8,
              }}
            >
              Name
            </th>
            <th
              style={{
                textAlign: "left",
                borderBottom: "1px solid #ddd",
                padding: 8,
              }}
            >
              Status
            </th>
            <th
              style={{
                textAlign: "left",
                borderBottom: "1px solid #ddd",
                padding: 8,
              }}
            >
              Capabilities
            </th>
            <th
              style={{
                textAlign: "left",
                borderBottom: "1px solid #ddd",
                padding: 8,
              }}
            >
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.agent_id}>
              <td style={{ padding: 8 }}>{a.agent_id}</td>
              <td style={{ padding: 8 }}>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <strong>{a.name}</strong>
                  {a.description && (
                    <small style={{ color: "#666" }}>{a.description}</small>
                  )}
                  {a.endpoint_url && (
                    <small>
                      <a href={a.endpoint_url} target="_blank" rel="noreferrer">
                        {a.endpoint_url}
                      </a>
                    </small>
                  )}
                </div>
              </td>
              <td style={{ padding: 8 }}>{a.status}</td>
              <td style={{ padding: 8 }}>{a.capabilities?.join(", ")}</td>
              <td
                style={{
                  padding: 8,
                  display: "flex",
                  gap: 8,
                  flexWrap: "wrap",
                  alignItems: "center",
                }}
              >
                {canWrite(currentUser) && (
                  <button
                    onClick={() => onActivate(a)}
                    disabled={updatingId === a.agent_id}
                  >
                    {updatingId === a.agent_id
                      ? "Saving…"
                      : a.status === "active"
                        ? "Deactivate"
                        : "Activate"}
                  </button>
                )}
                {isAdmin(currentUser) && (
                  <button
                    onClick={() => onDelete(a.agent_id)}
                    style={{ color: "#b00" }}
                    disabled={deletingId === a.agent_id}
                  >
                    {deletingId === a.agent_id ? "Deleting…" : "Delete"}
                  </button>
                )}
                <Link
                  href={`/projects`}
                  style={{ textDecoration: "underline" }}
                >
                  Projects
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
