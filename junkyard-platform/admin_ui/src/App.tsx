import { Link, useLocation } from "./router.tsx";
import { ToastHost } from "./util.tsx";
import { DiscrepanciesPage } from "./DiscrepanciesPage.tsx";
import { MappingsPage } from "./MappingsPage.tsx";

export default function App() {
  const loc = useLocation();
  const page = loc.path === "/mappings" ? <MappingsPage /> : <DiscrepanciesPage />;
  return (
    <ToastHost>
      <header className="topbar">
        <Link to="/" className="brand">junkyard admin</Link>
        <nav>
          <Link to="/" className={loc.path === "/" ? "on" : ""}>Discrepancies</Link>
          <Link to="/mappings" className={loc.path === "/mappings" ? "on" : ""}>Mappings &amp; rules</Link>
        </nav>
        <div className="grow" />
        <a href="/admin/ui/discrepancies" className="muted" title="The old pages, until the rewrite replaces them">old admin</a>
      </header>
      <main className="page">{page}</main>
    </ToastHost>
  );
}
