import { useEffect, useState } from "react";

import { scenarioOptions } from "./constants/options";
import { checkHealth, reconcileWithMapping, suggestColumnMapping } from "./services/api";

const PAGE_UPLOAD = "upload";
const PAGE_MAPPING = "mapping";
const PAGE_RESULTS = "results";

function ConfidenceBar({ confidence }) {
  const percent = Math.max(0, Math.min(100, Math.round((Number(confidence) || 0) * 100)));
  let level = "low";
  if (percent >= 70) {
    level = "high";
  } else if (percent >= 40) {
    level = "medium";
  }

  return (
    <div className="confidence-bar">
      <div className="confidence-fill">
        <div className={`confidence-fill-inner confidence-${level}`} style={{ width: `${percent}%` }} />
      </div>
      <span className="confidence-text">{percent}%</span>
    </div>
  );
}

function renderPreviewTable(section, tone) {
  if (!section?.columns?.length) {
    return <div className="empty-state">No data available</div>;
  }

  return (
    <div className={`file-preview file-preview-${tone}`}>
      <div className="file-preview-head">
        <h3>{section.file_name}</h3>
        <span>{section.row_count} rows</span>
      </div>
      <div className="file-preview-table-wrap">
        <table className="file-preview-table">
          <thead>
            <tr>
              {section.columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {section.preview_rows?.map((row, rowIndex) => (
              <tr key={`${section.file_name}-${rowIndex}`}>
                {section.columns.map((column) => (
                  <td key={`${section.file_name}-${rowIndex}-${column}`}>{String(row[column] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function App() {
  const [connection, setConnection] = useState({
    label: "Checking...",
    ok: true
  });

  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [reconcileLoading, setReconcileLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(PAGE_UPLOAD);
  const [processingStep, setProcessingStep] = useState("");

  const [scenarioType, setScenarioType] = useState("bank_gl");
  const [createdBy, setCreatedBy] = useState("analyst");
  const [leftLabel, setLeftLabel] = useState("Bank Statement");
  const [rightLabel, setRightLabel] = useState("GL Records");
  const [leftFile, setLeftFile] = useState(null);
  const [rightFile, setRightFile] = useState(null);

  const [mappingData, setMappingData] = useState(null);
  const [mappingRows, setMappingRows] = useState([]);
  const [reconResult, setReconResult] = useState(null);
  const [selectedDiscrepancyId, setSelectedDiscrepancyId] = useState("");

  const [toast, setToast] = useState({ message: "", kind: "info" });
  const [logs, setLogs] = useState([]);
  const [showLogs, setShowLogs] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("darkMode");
    return saved ? JSON.parse(saved) : false;
  });

  useEffect(() => {
    localStorage.setItem("darkMode", JSON.stringify(darkMode));
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  function addLog(message, type = "info") {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { timestamp, message, type }]);
  }

  function clearLogs() {
    setLogs([]);
  }

  useEffect(() => {
    let mounted = true;

    checkHealth()
      .then(() => {
        if (!mounted) {
          return;
        }
        setConnection({ label: "System Ready", ok: true });
      })
      .catch((error) => {
        if (!mounted) {
          return;
        }
        setConnection({ label: "Offline", ok: false });
        showToast(`Connection failed: ${error.message}`, "error");
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!toast.message) {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      setToast({ message: "", kind: "info" });
    }, 3200);

    return () => window.clearTimeout(timer);
  }, [toast]);

  function showToast(message, kind = "info") {
    setToast({ message, kind });
  }

  function goToPage(nextPage) {
    if (nextPage === PAGE_MAPPING && !mappingData) {
      return;
    }
    if (nextPage === PAGE_RESULTS && !reconResult) {
      return;
    }
    setCurrentPage(nextPage);
  }

  function updateMapping(field, key, value) {
    setMappingRows((current) =>
      current.map((item) => {
        if (item.field !== field) {
          return item;
        }

        return {
          ...item,
          [key]: value || null,
          source: "manual"
        };
      })
    );
  }

  async function handleSuggestMapping(event) {
    event.preventDefault();
    if (!leftFile || !rightFile) {
      showToast("Please upload both files to continue", "error");
      return;
    }

    clearLogs();
    setSuggestionLoading(true);
    addLog("Starting column mapping process...", "info");
    
    try {
      addLog(`Reading left file: ${leftFile.name} (${(leftFile.size / 1024).toFixed(1)} KB)`, "info");
      addLog(`Reading right file: ${rightFile.name} (${(rightFile.size / 1024).toFixed(1)} KB)`, "info");
      addLog("Analyzing column structures...", "info");
      
      setProcessingStep("Running AI column mapping...");
      addLog("Sending request to LLM for column mapping suggestions...", "info");
      
      const response = await suggestColumnMapping({
        scenarioType,
        leftFile,
        rightFile
      });

      addLog(`Received ${response.suggestions?.length || 0} mapping suggestions from LLM`, "success");
      
      const mappedFields = response.suggestions?.filter(s => s.left_column && s.right_column).length || 0;
      const unmappedFields = response.suggestions?.filter(s => !s.left_column || !s.right_column).length || 0;
      addLog(`Mapping summary: ${mappedFields} fields mapped, ${unmappedFields} fields unmapped`, "info");
      
      setMappingData(response);
      setMappingRows(response.suggestions || []);
      setReconResult(null);
      setSelectedDiscrepancyId("");
      setCurrentPage(PAGE_MAPPING);
      setProcessingStep("");
      addLog("Column mapping completed successfully!", "success");
      showToast("AI mapping is ready for review", "success");
    } catch (error) {
      addLog(`Error: ${error.message}`, "error");
      setProcessingStep("");
      showToast(`Mapping failed: ${error.message}`, "error");
    } finally {
      setSuggestionLoading(false);
    }
  }

  async function handleRunReconciliation() {
    if (!leftFile || !rightFile || !mappingRows.length) {
      showToast("Complete mapping before running reconciliation", "error");
      return;
    }

    clearLogs();
    setReconcileLoading(true);
    addLog("Starting reconciliation process...", "info");
    addLog(`Left source: ${leftLabel}`, "info");
    addLog(`Right source: ${rightLabel}`, "info");
    
    try {
      setProcessingStep("Reading and parsing files...");
      addLog(`Parsing left file: ${leftFile.name}`, "info");
      addLog(`Parsing right file: ${rightFile.name}`, "info");
      await new Promise(r => setTimeout(r, 300));
      
      setProcessingStep("Normalizing left file data...");
      addLog("Normalizing left file data...", "info");
      await new Promise(r => setTimeout(r, 300));
      
      setProcessingStep("Normalizing right file data...");
      addLog("Normalizing right file data...", "info");
      await new Promise(r => setTimeout(r, 300));
      
      setProcessingStep("Running transaction matching algorithm...");
      addLog("Running AI-powered transaction matching...", "info");
      
      const response = await reconcileWithMapping({
        scenarioType,
        createdBy,
        leftLabel,
        rightLabel,
        leftFile,
        rightFile,
        mapping: { mappings: mappingRows }
      });

      addLog(`Matching complete: ${response.metrics?.matched_count || 0} matches found`, "success");
      addLog(`Exceptions: ${response.metrics?.exception_count || 0} unmatched transactions`, "info");
      
      setProcessingStep("Detecting discrepancies and building results...");
      addLog("Analyzing discrepancies...", "info");
      await new Promise(r => setTimeout(r, 300));
      
      const discrepanciesCount = response.discrepancies?.filter(d => d.issues?.length > 0).length || 0;
      addLog(`Found ${discrepanciesCount} transactions with discrepancies`, discrepanciesCount > 0 ? "warning" : "success");
      
      setReconResult(response);
      const firstDiscrepancy = response.discrepancies?.[0];
      setSelectedDiscrepancyId(firstDiscrepancy?.match_id || "");
      setCurrentPage(PAGE_RESULTS);
      setProcessingStep("");
      addLog("Reconciliation completed successfully!", "success");

      if (response.status === "mapping_failed") {
        showToast("Mapping validation failed; review issues in results", "error");
      } else {
        showToast(`Reconciliation complete: ${response.metrics?.matched_count || 0} matches`, "success");
      }
    } catch (error) {
      addLog(`Error: ${error.message}`, "error");
      setProcessingStep("");
      showToast(`Reconciliation failed: ${error.message}`, "error");
    } finally {
      setReconcileLoading(false);
    }
  }

  const selectedDiscrepancy =
    reconResult?.discrepancies?.find((item) => item.match_id === selectedDiscrepancyId) ||
    reconResult?.discrepancies?.[0] ||
    null;

  const leftColumns = mappingData?.left?.columns || [];
  const rightColumns = mappingData?.right?.columns || [];

  return (
    <div className="app-container">
      <header className="header">
        <div className="header-left">
          <div className="logo">FR</div>
          <div className="header-title">
            <h1>Financial Reconciliation</h1>
            <p>AI-powered mapping and discrepancy review</p>
          </div>
        </div>
        <div className="header-right">
          <button 
            type="button" 
            className="logs-btn" 
            onClick={() => setShowLogs(true)}
          >
            Logs {logs.length > 0 && <span className="logs-count">{logs.length}</span>}
          </button>
          <button 
            type="button" 
            className="theme-toggle" 
            onClick={() => setDarkMode(!darkMode)}
            title={darkMode ? "Switch to Light Mode" : "Switch to Dark Mode"}
          >
            {darkMode ? "[L]" : "[D]"}
          </button>
          <div className={`health-pill ${connection.ok ? "online" : "offline"}`}>{connection.label}</div>
        </div>
      </header>

      <nav className="stage-nav" aria-label="Workflow stages">
        <button
          type="button"
          className={`stage-btn ${currentPage === PAGE_UPLOAD ? "active" : ""}`}
          onClick={() => goToPage(PAGE_UPLOAD)}
        >
          1. Upload
        </button>
        <button
          type="button"
          className={`stage-btn ${currentPage === PAGE_MAPPING ? "active" : ""}`}
          onClick={() => goToPage(PAGE_MAPPING)}
          disabled={!mappingData}
        >
          2. Mapping Diff
        </button>
        <button
          type="button"
          className={`stage-btn ${currentPage === PAGE_RESULTS ? "active" : ""}`}
          onClick={() => goToPage(PAGE_RESULTS)}
          disabled={!reconResult}
        >
          3. Results
        </button>
      </nav>

      <main className="main-shell">
        <div key={currentPage} className="page-view">
          {currentPage === PAGE_UPLOAD && (
            <section className="card page-card">
              <div className="card-header">
                <div className="card-title">
                  <span className="card-title-icon">1</span>
                  <h2>Upload Source Files</h2>
                </div>
                <div className="page-actions-inline">
                  <button 
                    className="btn btn-primary" 
                    type="button"
                    onClick={handleSuggestMapping} 
                    disabled={suggestionLoading || !leftFile || !rightFile}
                  >
                    {suggestionLoading ? (
                      <>
                        <span className="loading-spinner"></span>
                        {processingStep || "Processing..."}
                      </>
                    ) : (
                      "Analyze and Continue"
                    )}
                  </button>
                </div>
              </div>

              <form>
                <div className="upload-grid">
                  <div className="form-group">
                    <label>Scenario Type</label>
                    <select value={scenarioType} onChange={(event) => setScenarioType(event.target.value)}>
                      {scenarioOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group">
                    <label>Analyst Name</label>
                    <input
                      value={createdBy}
                      onChange={(event) => setCreatedBy(event.target.value)}
                      maxLength={64}
                      placeholder="Your name"
                    />
                  </div>

                  <div className="form-group">
                    <label>Left Source Label</label>
                    <input
                      value={leftLabel}
                      onChange={(event) => setLeftLabel(event.target.value)}
                      maxLength={64}
                      placeholder="e.g., Bank Statement"
                    />
                  </div>

                  <div className="form-group">
                    <label>Right Source Label</label>
                    <input
                      value={rightLabel}
                      onChange={(event) => setRightLabel(event.target.value)}
                      maxLength={64}
                      placeholder="e.g., GL Records"
                    />
                  </div>
                </div>

                <div className="file-upload-area">
                  <label className={`file-box left ${leftFile ? "loaded" : ""}`}>
                    <input
                      type="file"
                      accept=".csv,.xlsx,.xls"
                      onChange={(event) => setLeftFile(event.target.files?.[0] || null)}
                    />
                    <div className="file-box-content">
                      <span className="file-box-icon">{leftFile ? "OK" : "L"}</span>
                      <span className="file-box-text">{leftFile ? leftFile.name : leftLabel}</span>
                      <span className="file-box-subtext">
                        {leftFile ? `${(leftFile.size / 1024).toFixed(1)} KB` : "Drop or click to upload"}
                      </span>
                    </div>
                  </label>

                  <label className={`file-box right ${rightFile ? "loaded" : ""}`}>
                    <input
                      type="file"
                      accept=".csv,.xlsx,.xls"
                      onChange={(event) => setRightFile(event.target.files?.[0] || null)}
                    />
                    <div className="file-box-content">
                      <span className="file-box-icon">{rightFile ? "OK" : "R"}</span>
                      <span className="file-box-text">{rightFile ? rightFile.name : rightLabel}</span>
                      <span className="file-box-subtext">
                        {rightFile ? `${(rightFile.size / 1024).toFixed(1)} KB` : "Drop or click to upload"}
                      </span>
                    </div>
                  </label>
                </div>
              </form>
            </section>
          )}

          {currentPage === PAGE_MAPPING && (
            <section className="page-stack">
              {mappingData ? (
                <>
                  <div className="card page-card">
                    <div className="card-header">
                      <div className="card-title">
                        <span className="card-title-icon">2</span>
                        <h2>Column Mapping Diff</h2>
                      </div>
                      <div className="page-actions-inline">
                        <button className="btn btn-secondary" type="button" onClick={() => goToPage(PAGE_UPLOAD)}>
                          Back to Upload
                        </button>
                        <button
                          className="btn btn-primary"
                          type="button"
                          onClick={handleRunReconciliation}
                          disabled={reconcileLoading}
                        >
                          {reconcileLoading ? (
                            <>
                              <span className="loading-spinner"></span>
                              Processing...
                            </>
                          ) : (
                            "Run Reconciliation"
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="mapping-top-grid">
                      <div>{renderPreviewTable(mappingData.left, "left")}</div>
                      <div>{renderPreviewTable(mappingData.right, "right")}</div>
                    </div>
                  </div>

                  <div className="card page-card mapping-editor-card">
                    <div className="mapping-editor-header">
                      <h3>
                        <span className="llm-badge">AI</span>
                        Merge Conflict Style Mapping
                      </h3>
                      <p>Resolve each field by selecting the matching columns on both sides.</p>
                    </div>

                    <div className="merge-list">
                      {mappingRows.length ? (
                        mappingRows.map((row) => (
                          <article key={row.field} className={`merge-card ${row.source === "manual" ? "manual" : "ai"}`}>
                            <div className="merge-card-header">
                              <div className="merge-field-meta">
                                <code>{row.field}</code>
                                <strong>{row.label}</strong>
                                {row.required && <span className="required-tag">Required</span>}
                              </div>
                              <div className="merge-field-score">
                                <span className="source-pill">{row.source === "manual" ? "Manual" : "AI"}</span>
                                <ConfidenceBar confidence={row.confidence || 0} />
                              </div>
                            </div>

                            {row.rationale && <p className="merge-rationale">{row.rationale}</p>}

                            <div className="conflict-block">
                              <div className="conflict-marker left">&lt;&lt;&lt;&lt;&lt;&lt;&lt; {leftLabel}</div>
                              <div className="conflict-input left">
                                <label htmlFor={`${row.field}-left`}>Left Column</label>
                                <select
                                  id={`${row.field}-left`}
                                  value={row.left_column || ""}
                                  onChange={(event) => updateMapping(row.field, "left_column", event.target.value)}
                                >
                                  <option value="">-- Not mapped --</option>
                                  {leftColumns.map((column) => (
                                    <option key={`${row.field}-left-${column}`} value={column}>
                                      {column}
                                    </option>
                                  ))}
                                </select>
                              </div>

                              <div className="conflict-marker middle">======= Resolve Mapping</div>

                              <div className="conflict-input right">
                                <label htmlFor={`${row.field}-right`}>Right Column</label>
                                <select
                                  id={`${row.field}-right`}
                                  value={row.right_column || ""}
                                  onChange={(event) => updateMapping(row.field, "right_column", event.target.value)}
                                >
                                  <option value="">-- Not mapped --</option>
                                  {rightColumns.map((column) => (
                                    <option key={`${row.field}-right-${column}`} value={column}>
                                      {column}
                                    </option>
                                  ))}
                                </select>
                              </div>

                              <div className="conflict-marker right">&gt;&gt;&gt;&gt;&gt;&gt;&gt; {rightLabel}</div>
                            </div>
                          </article>
                        ))
                      ) : (
                        <div className="empty-state">No mapping suggestions were returned.</div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="card page-card">
                  <div className="empty-state">Run mapping from the upload page first.</div>
                </div>
              )}
            </section>
          )}

          {currentPage === PAGE_RESULTS && (
            <section className="results-section">
              {reconResult ? (
                <div className="card page-card">
                  <div className="card-header">
                    <div className="card-title">
                      <span className="card-title-icon">3</span>
                      <h2>Reconciliation Results</h2>
                    </div>
                    <button className="btn btn-secondary" type="button" onClick={() => goToPage(PAGE_MAPPING)}>
                      Back to Mapping
                    </button>
                  </div>

                  {reconResult.mapping_issues?.length > 0 && (
                    <div className="issues-banner">
                      <h3>Mapping Issues Detected</h3>
                      <ul>
                        {reconResult.mapping_issues.map((issue, index) => (
                          <li key={index}>
                            {issue.side ? `${issue.side.toUpperCase()} | ` : ""}
                            {issue.field ? `${issue.field}: ` : ""}
                            {issue.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="metrics-grid">
                    <div className="metric-card">
                      <div className="metric-card-label">Left Records</div>
                      <div className="metric-card-value">{reconResult.left_file?.valid_rows ?? 0}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">Right Records</div>
                      <div className="metric-card-value">{reconResult.right_file?.valid_rows ?? 0}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">Matches</div>
                      <div className="metric-card-value success">{reconResult.metrics?.matched_count ?? 0}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">Exceptions</div>
                      <div className="metric-card-value warning">{reconResult.metrics?.exception_count ?? 0}</div>
                    </div>
                    <div className="metric-card">
                      <div className="metric-card-label">Match Rate</div>
                      <div className="metric-card-value">{reconResult.metrics?.matched_pct ?? 0}%</div>
                    </div>
                  </div>

                  <div className="table-container">
                    <div className="table-header">
                      <h3>Matched Transactions</h3>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Match ID</th>
                            <th>Left</th>
                            <th>Right</th>
                            <th>Amount Delta</th>
                            <th>Date Delta</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reconResult.matches?.length ? (
                            reconResult.matches.map((match) => {
                              const discrepancy = reconResult.discrepancies?.find((item) => item.match_id === match.id);
                              const issueCount = discrepancy?.issues?.length || 0;

                              return (
                                <tr key={match.id}>
                                  <td>
                                    <strong>{match.id}</strong>
                                  </td>
                                  <td>{match.left?.id || match.a}</td>
                                  <td>{match.right?.id || match.b}</td>
                                  <td>{match.amount_delta || "0.00"}</td>
                                  <td>{match.date_delta_days ?? 0}d</td>
                                  <td>
                                    <button
                                      type="button"
                                      className={`discrepancy-btn ${issueCount > 0 ? "alert" : "aligned"}`}
                                      onClick={() => setSelectedDiscrepancyId(match.id)}
                                    >
                                      {issueCount > 0 ? `${issueCount} issue(s)` : "Aligned"}
                                    </button>
                                  </td>
                                </tr>
                              );
                            })
                          ) : (
                            <tr>
                              <td colSpan={6} className="empty-state">
                                No matches found
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="diff-workbench">
                    <div className="diff-list">
                      <div className="diff-list-header">
                        <h3>Discrepancy Inspector</h3>
                      </div>
                      <ul>
                        {reconResult.discrepancies?.length ? (
                          reconResult.discrepancies.map((item) => (
                            <li key={item.match_id}>
                              <button
                                type="button"
                                className={selectedDiscrepancy?.match_id === item.match_id ? "active" : ""}
                                onClick={() => setSelectedDiscrepancyId(item.match_id)}
                              >
                                <span>{item.match_id}</span>
                                <small>{item.issues?.length ? `${item.issues.length} diffs` : "Aligned"}</small>
                              </button>
                            </li>
                          ))
                        ) : (
                          <div className="empty-state compact">All matched pairs are aligned.</div>
                        )}
                      </ul>
                    </div>

                    <div className="diff-detail">
                      {selectedDiscrepancy ? (
                        <>
                          <div className="diff-detail-header">
                            <h3>Match Details: {selectedDiscrepancy.match_id}</h3>
                            <p>Side-by-side snapshot comparison</p>
                          </div>
                          <div className="diff-columns">
                            <div className="diff-side left">
                              <div className="diff-side-header">{leftLabel}</div>
                              <pre>{JSON.stringify(selectedDiscrepancy.left_snapshot || {}, null, 2)}</pre>
                            </div>
                            <div className="diff-side right">
                              <div className="diff-side-header">{rightLabel}</div>
                              <pre>{JSON.stringify(selectedDiscrepancy.right_snapshot || {}, null, 2)}</pre>
                            </div>
                          </div>
                          <div className="issue-list">
                            <h4>Detected Discrepancies</h4>
                            {selectedDiscrepancy.issues?.length ? (
                              <ul>
                                {selectedDiscrepancy.issues.map((issue, index) => (
                                  <li key={index} className={issue.severity || "medium"}>
                                    <strong>{issue.field}</strong>: {issue.note}
                                    <br />
                                    <span className="issue-values">
                                      {issue.left} vs {issue.right}
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="aligned-note">No discrepancies found for this match.</p>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="empty-state">
                          <p>Select a matched pair to inspect differences.</p>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="table-container">
                    <div className="table-header">
                      <h3>Unmatched / Exception Transactions</h3>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>ID</th>
                            <th>Transaction</th>
                            <th>Status</th>
                            <th>Reason</th>
                            <th>Recommended Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reconResult.exceptions?.length ? (
                            reconResult.exceptions.map((exception) => (
                              <tr key={exception.id}>
                                <td>
                                  <strong>{exception.id}</strong>
                                </td>
                                <td>{exception.transaction?.transaction_id || exception.txn}</td>
                                <td>
                                  <span className={`discrepancy-btn ${exception.status === "no_candidate" ? "alert" : ""}`}>
                                    {exception.status}
                                  </span>
                                </td>
                                <td>{exception.reason}</td>
                                <td>{exception.recommended_action || "Review source data and mapping"}</td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={5} className="empty-state">
                                No exceptions. All transactions matched.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card page-card">
                  <div className="empty-state">Run reconciliation from the mapping page first.</div>
                </div>
              )}
            </section>
          )}
        </div>
      </main>

      {showLogs && (
        <div className="logs-overlay" onClick={() => setShowLogs(false)}>
          <div className="logs-modal" onClick={e => e.stopPropagation()}>
            <div className="logs-header">
              <h3>Process Logs</h3>
              <button type="button" className="logs-close" onClick={() => setShowLogs(false)}>×</button>
            </div>
            <div className="logs-content">
              {logs.length === 0 ? (
                <div className="logs-empty">No logs yet. Run a process to see logs.</div>
              ) : (
                logs.map((log, index) => (
                  <div key={index} className={`log-entry log-${log.type}`}>
                    <span className="log-time">{log.timestamp}</span>
                    <span className="log-message">{log.message}</span>
                  </div>
                ))
              )}
            </div>
            <div className="logs-footer">
              <button type="button" className="btn btn-secondary" onClick={clearLogs}>Clear Logs</button>
              <button type="button" className="btn btn-primary" onClick={() => setShowLogs(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      <div className={`toast ${toast.message ? "show" : ""} ${toast.kind}`}>{toast.message}</div>
    </div>
  );
}
