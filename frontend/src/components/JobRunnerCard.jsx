import { useMemo, useState } from "react";

import Card from "./common/Card";

function getDefaultDates() {
  const now = new Date();
  const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

  return {
    start: firstOfMonth.toISOString().slice(0, 10),
    end: now.toISOString().slice(0, 10)
  };
}

export default function JobRunnerCard({ scenarioOptions, loading, onRunJob, onLoadJob }) {
  const defaults = useMemo(() => getDefaultDates(), []);

  const [scenarioType, setScenarioType] = useState(scenarioOptions[0]?.value || "bank_gl");
  const [periodStart, setPeriodStart] = useState(defaults.start);
  const [periodEnd, setPeriodEnd] = useState(defaults.end);
  const [createdBy, setCreatedBy] = useState("ui-analyst");
  const [jobIdInput, setJobIdInput] = useState("");

  const handleSubmit = (event) => {
    event.preventDefault();
    onRunJob({
      scenarioType,
      periodStart,
      periodEnd,
      createdBy
    });
  };

  return (
    <Card className="card-job">
      <h2>Run Reconciliation</h2>
      <p className="hint">Create a job for a period, run matching, and review confidence outcomes.</p>

      <form className="form-grid" onSubmit={handleSubmit}>
        <label>
          Scenario
          <select value={scenarioType} onChange={(event) => setScenarioType(event.target.value)} required>
            {scenarioOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Period Start
          <input type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} required />
        </label>

        <label>
          Period End
          <input type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} required />
        </label>

        <label className="full-width">
          Actor
          <input type="text" value={createdBy} maxLength={64} onChange={(event) => setCreatedBy(event.target.value)} />
        </label>

        <button className="btn btn-emerald" type="submit" disabled={loading}>
          {loading ? "Running..." : "Create & Run Job"}
        </button>
      </form>

      <div className="inline-group">
        <input
          type="text"
          placeholder="Paste existing job id"
          value={jobIdInput}
          onChange={(event) => setJobIdInput(event.target.value)}
        />
        <button
          className="btn btn-ghost"
          type="button"
          onClick={() => onLoadJob(jobIdInput.trim())}
          disabled={!jobIdInput.trim()}
        >
          Load Job
        </button>
      </div>
    </Card>
  );
}
