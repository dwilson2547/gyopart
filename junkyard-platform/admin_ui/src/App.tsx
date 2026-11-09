import { Link, useLocation } from "./router.tsx";
import { get, post } from "./api.ts";
import type { SuggestionList } from "./types.ts";
import { ToastHost, useLoad } from "./util.tsx";
import { AgentsPage } from "./AgentsPage.tsx";
import { DiscrepanciesPage } from "./DiscrepanciesPage.tsx";
import { MappingsPage } from "./MappingsPage.tsx";
import { SuggestionsPage } from "./SuggestionsPage.tsx";
import { VehiclePage } from "./VehiclePage.tsx";
import { VehicleSearch } from "./VehicleSearch.tsx";

export default function App() {
  const loc = useLocation();
  const vehicle = loc.path.match(/^\/vehicles\/(\d+)$/);
  const page = vehicle ? <VehiclePage key={vehicle[1]} id={Number(vehicle[1])} />
    : loc.path === "/mappings" ? <MappingsPage /> : loc.path === "/agents" ? <AgentsPage />
    : loc.path === "/suggestions" ? <SuggestionsPage /> : <DiscrepanciesPage />;
  // How many suggestions wait for review, refreshed on every navigation.
  const waiting = useLoad(() => get<SuggestionList>("/api/suggestions").then((r) => r.counts.pending), loc.path + loc.search);
  return (
    <ToastHost>
      <header className="topbar">
        <Link to="/" className="brand">junkyard admin</Link>
        <nav>
          <Link to="/" className={loc.path === "/" ? "on" : ""}>Discrepancies</Link>
          <Link to="/suggestions" className={loc.path === "/suggestions" ? "on" : ""}>
            Suggestions{waiting.data ? <span className="badge">{waiting.data}</span> : null}
          </Link>
          <Link to="/mappings" className={loc.path === "/mappings" ? "on" : ""}>Mappings &amp; rules</Link>
          <Link to="/agents" className={loc.path === "/agents" ? "on" : ""}>Agents</Link>
        </nav>
        <div className="grow" />
        <VehicleSearch />
        <Account />
      </header>
      <main className="page">{page}</main>
    </ToastHost>
  );
}

type Me = { user: { name: string; email?: string } | null; oidc: boolean };

/** Who's signed in (when sign-in is on) and a way out. */
function Account() {
  const me = useLoad(() => get<Me>("/api/me"), "me");
  if (!me.data?.oidc) return null;
  if (!me.data.user) return <a href={`/api/auth/oidc/login?next=${encodeURIComponent(location.pathname)}`}>sign in</a>;
  const out = async () => {
    try { await post("/api/auth/logout"); } catch { /* cookie is cleared server-side either way */ }
    location.href = "/";
  };
  return (
    <span className="row small" style={{ gap: 6 }}>
      <span className="muted" title={me.data.user.email}>{me.data.user.name}</span>
      <button className="link" onClick={out}>sign out</button>
    </span>
  );
}
