function normalize(status) {
  const lower = String(status || "idle").toLowerCase();
  if (lower === "running") return "running";
  if (lower === "completed") return "completed";
  if (lower === "failed") return "failed";
  return "idle";
}

export default function StatusPill({ status }) {
  const normalized = normalize(status);
  return <span className={`status-pill ${normalized}`}>{normalized}</span>;
}
