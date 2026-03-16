export default function HeaderBar({ connection }) {
  return (
    <header className="topbar">
      <div className="brand-wrap">
        <div className="brand-mark" aria-hidden="true" />
        <div>
          <p className="eyebrow">Financial Operations Console</p>
          <h1>GenAI Reconciliation Workspace</h1>
        </div>
      </div>
      <div className={connection.ok ? "status-chip online" : "status-chip offline"}>{connection.label}</div>
    </header>
  );
}
