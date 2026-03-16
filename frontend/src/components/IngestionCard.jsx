import { useState } from "react";

import Card from "./common/Card";

export default function IngestionCard({ parserOptions, scenarioOptions, loading, summary, onSubmit }) {
  const [parserKey, setParserKey] = useState(parserOptions[0]?.value || "bank_csv");
  const [scenarioType, setScenarioType] = useState(scenarioOptions[0]?.value || "bank_gl");
  const [sourceFile, setSourceFile] = useState(null);

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!sourceFile) {
      return;
    }

    onSubmit({ parserKey, scenarioType, file: sourceFile });
  };

  return (
    <Card className="card-upload">
      <h2>Ingestion</h2>
      <p className="hint">Upload source files and normalize them into the transaction pipeline.</p>

      <form className="form-grid" onSubmit={handleSubmit}>
        <label>
          Parser
          <select value={parserKey} onChange={(event) => setParserKey(event.target.value)} required>
            {parserOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

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

        <label className="full-width file-field">
          Source File
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            required
            onChange={(event) => setSourceFile(event.target.files?.[0] || null)}
          />
        </label>

        <button className="btn btn-primary" type="submit" disabled={loading || !sourceFile}>
          {loading ? "Processing..." : "Ingest & Normalize"}
        </button>
      </form>

      <div className="panel muted">{summary}</div>
    </Card>
  );
}
