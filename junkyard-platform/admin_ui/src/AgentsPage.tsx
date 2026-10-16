import { useState } from "react";
import { ApiError, del, get } from "./api.ts";
import { Empty, ErrorBanner, Loading, useLoad, useToast } from "./util.tsx";

type Agent = { id: string; clientName: string; user: string; createdAt: string; lastUsedAt: string | null };
type Agents = { agents: Agent[]; mcpUrl: string };

/** The discrepancy-fix MCP (admin_api/mcp): where to point an agent, and the agents connected as you. */
export function AgentsPage() {
  const agents = useLoad(() => get<Agents>("/api/agents"), "agents");
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const off = agents.error != null && /404|not found/i.test(agents.error);

  const disconnect = async (a: Agent) => {
    try {
      await del(`/api/agents/${a.id}`);
      agents.setData({ ...agents.data!, agents: agents.data!.agents.filter((x) => x.id !== a.id) });
      toast(`Disconnected ${a.clientName}.`);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : String(e));
    }
  };
  const copy = async (url: string) => {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* the URL is selectable anyway */ }
  };

  return (
    <div className="stack">
      <h1>Agents</h1>
      <section className="panel stack">
        <div>
          <h2>Connect an agent</h2>
          <p className="muted small" style={{ margin: 0 }}>
            Add this MCP server to your agent's harness. It opens a browser to sign in here and asks you to allow it.
            An agent can read discrepancies, vehicles, VIN decodes and the catalogue, and create mappings, yard rules
            and ignores (always previewed first). It can't match cars by hand, trigger scrapes, or delete your mappings.
          </p>
        </div>
        {off ? <Empty>The MCP server is off here (it needs sign-in and the public https address).</Empty>
          : agents.data ? (
            <div className="row">
              <code className="grow" style={{ userSelect: "all" }}>{agents.data.mcpUrl}</code>
              <button onClick={() => copy(agents.data!.mcpUrl)}>{copied ? "Copied" : "Copy"}</button>
            </div>
          ) : null}
      </section>
      {!off && (
        <section className="panel stack">
          <h2>Connected</h2>
          {agents.error && <ErrorBanner error={`Agents didn't load: ${agents.error}`} onRetry={agents.reload} />}
          {agents.data == null ? (agents.error ? null : <Loading />) : agents.data.agents.length === 0 ? (
            <Empty>No agents connected.</Empty>
          ) : (
            <table className="list">
              <thead><tr><th>App</th><th>Connected</th><th>Last used</th><th /></tr></thead>
              <tbody>
                {agents.data.agents.map((a) => (
                  <tr key={a.id}>
                    <td className="gname">{a.clientName}</td>
                    <td className="muted small nowrap">{a.createdAt.slice(0, 16).replace("T", " ")}</td>
                    <td className="muted small nowrap">{a.lastUsedAt ? a.lastUsedAt.slice(0, 16).replace("T", " ") : "never"}</td>
                    <td className="nowrap"><button className="danger" onClick={() => disconnect(a)}>Disconnect</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
