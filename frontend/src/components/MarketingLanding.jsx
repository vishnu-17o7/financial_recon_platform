const SWITCH_PILLARS = [
  {
    icon: "visibility",
    title: "Command-grade visibility",
    description:
      "Every transaction, from every source, unified in a single ledger view with sub-second filtering."
  },
  {
    icon: "auto_awesome",
    title: "AI where ambiguity starts",
    description:
      "Traditional rules match the 80%. Our LLM-powered engine interprets the messy 20% that others flag as manual exceptions."
  },
  {
    icon: "history_edu",
    title: "Audit trail by design",
    description:
      "No black boxes. Every match score comes with a transparent rationale and a complete versioned history for external auditors."
  }
];

const WORKFLOW_STEPS = [
  {
    label: "01 / Ingest",
    icon: "upload_file",
    title: "Upload source files",
    detail: "Bank • GL • PSP",
    description: "Direct connections or secure exports from any institutional source."
  },
  {
    label: "02 / Normalize",
    icon: "grid_view",
    title: "Unify fields",
    detail: "Canonical schema",
    description: "Schema-matching maps disparate headers into a single, standardized format."
  },
  {
    label: "03 / Match",
    icon: "link",
    title: "Score candidates",
    detail: "Score 99.8",
    description: "Deterministic rules paired with vector embeddings for high-confidence pairing.",
    featured: true
  },
  {
    label: "04 / Resolve",
    icon: "done_all",
    title: "Push outcomes",
    detail: "Exception queue",
    description: "Review the small queue of exceptions and export signed-off journals."
  }
];

const TRUST_ITEMS = [
  {
    icon: "settings_suggest",
    title: "Scenario-aware matching",
    description:
      "Define custom rulesets for intercompany, payroll, or vendor settlement flows without writing code."
  },
  {
    icon: "analytics",
    title: "Confidence scoring",
    description:
      "Every automated match includes a rationale statement detailing why the engine linked the records."
  },
  {
    icon: "format_paint",
    title: "Executive aesthetics",
    description:
      "Experience precision in your preferred environment with full dark/light mode support tailored for long-hour cycles."
  }
];

const TIMELINE_ITEMS = [
  { time: "08:20", note: "Source files ingested and profiled" },
  { time: "08:31", note: "Mapping suggestions accepted by analyst" },
  { time: "08:44", note: "312 matches posted, 19 exceptions queued" }
];

const HERO_SIGNALS = [
  { icon: "verified_user", text: "Audit-ready lineage" },
  { icon: "psychology", text: "LLM mapping support" },
  { icon: "priority_high", text: "Exception-first review" }
];

function launchDashboard(event, onGetStarted) {
  if (event) {
    event.preventDefault();
  }
  onGetStarted();
}

function TrustPreviewRow({ date, description, amount, status, statusTone }) {
  return (
    <div className={`aa-preview-row ${statusTone ? `aa-preview-row-${statusTone}` : ""}`}>
      <span>{date}</span>
      <span className="aa-preview-main">{description}</span>
      <span>{amount}</span>
      <div className="aa-preview-status">
        <span>{status}</span>
        <i aria-hidden="true" />
      </div>
    </div>
  );
}

export default function MarketingLanding({ onGetStarted, darkMode = false, onToggleDarkMode = () => {} }) {
  return (
    <div className="aa-page">
      <a className="aa-skip-link" href="#main-content">
        Skip to main content
      </a>

      <nav className="aa-top-nav">
        <div className="aa-top-nav-inner">
          <div className="aa-nav-left">
            <a className="aa-brand" href="#main-content">
              The Archival Authority
            </a>
            <div className="aa-nav-links" aria-label="Homepage sections">
              <a href="#why-us">Why Teams Switch</a>
              <a href="#workflow">Workflow</a>
              <a href="#trust">Trust</a>
            </div>
          </div>
          <div className="aa-top-actions">
            <button
              type="button"
              className="aa-btn aa-btn-outline aa-theme-toggle"
              onClick={onToggleDarkMode}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                {darkMode ? "light_mode" : "dark_mode"}
              </span>
              {darkMode ? "Light" : "Dark"}
            </button>
            <button type="button" className="aa-btn aa-btn-solid" onClick={(event) => launchDashboard(event, onGetStarted)}>
              Get Started
            </button>
          </div>
        </div>
      </nav>

      <main id="main-content">
        <section className="aa-hero-section">
          <div className="aa-hero-grid">
            <div className="aa-hero-copy">
              <div className="aa-tag">Institutional Precision</div>
              <h1>
                Built for accountants and
                <br />
                bank operations teams.
              </h1>
              <p>
                Close reconciliation cycles with confidence, not spreadsheet fatigue. Move from raw
                statements to validated matches and actionable exceptions in one premium,
                audit-friendly command center.
              </p>

              <div className="aa-action-row">
                <button
                  type="button"
                  className="aa-btn aa-btn-solid aa-btn-large"
                  onClick={(event) => launchDashboard(event, onGetStarted)}
                >
                  Get Started
                </button>
                <a className="aa-btn aa-btn-outline aa-btn-large" href="#workflow">
                  Explore Workflow
                </a>
              </div>

              <div className="aa-proof-grid">
                {HERO_SIGNALS.map((signal) => (
                  <div key={signal.text} className="aa-proof-item">
                    <span className="material-symbols-outlined" aria-hidden="true">
                      {signal.icon}
                    </span>
                    <span>{signal.text}</span>
                  </div>
                ))}
              </div>
            </div>

            <aside className="aa-hero-panel" aria-label="Live operations snapshot">
              <div className="aa-panel-head">
                <h3>Live Operations Snapshot</h3>
                <div className="aa-status-dot" aria-hidden="true" />
              </div>

              <div className="aa-panel-summary">
                <div>
                  <p>Current Cycle Status</p>
                  <h4>In Progress</h4>
                </div>
                <div className="aa-panel-summary-time">
                  <p>Time Elapsed</p>
                  <h5>01:42:12</h5>
                </div>
              </div>

              <div className="aa-stat-grid">
                <article>
                  <p>Auto-match Confidence</p>
                  <h4>97.4%</h4>
                  <small>+3.2% vs last cycle</small>
                </article>
                <article>
                  <p>Analyst Review Load</p>
                  <h4>-61%</h4>
                  <small>Fewer manual checks</small>
                </article>
              </div>

              <div className="aa-cycle-card">
                <div className="aa-cycle-head">
                  <p>Cycle-close time</p>
                  <span className="material-symbols-outlined" aria-hidden="true">
                    timer
                  </span>
                </div>
                <div className="aa-cycle-value">
                  <strong>2.4h</strong>
                  <span>File drop to sign-off</span>
                </div>
              </div>

              <div className="aa-timeline-feed">
                <p>Timeline Feed</p>
                <div>
                  {TIMELINE_ITEMS.map((item) => (
                    <article key={item.time + item.note}>
                      <i aria-hidden="true" />
                      <p>
                        <strong>{item.time}</strong>
                        {item.note}
                      </p>
                    </article>
                  ))}
                </div>
              </div>
            </aside>
          </div>
        </section>

        <section className="aa-switch-section" id="why-us">
          <div className="aa-switch-head">
            <div>
              <h2>
                Enterprise depth with
                <br />
                startup velocity.
              </h2>
              <p>
                We&apos;ve replaced manual validation cycles for teams handling $50B+ in annual transaction volume.
              </p>
            </div>
            <div className="aa-section-label">Why teams switch</div>
          </div>

          <div className="aa-switch-grid">
            {SWITCH_PILLARS.map((pillar) => (
              <article key={pillar.title} className="aa-switch-card">
                <span className="material-symbols-outlined" aria-hidden="true">
                  {pillar.icon}
                </span>
                <h3>{pillar.title}</h3>
                <p>{pillar.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="aa-workflow-section" id="workflow">
          <h2>The Path to Resolution</h2>

          <div className="aa-workflow-grid">
            {WORKFLOW_STEPS.map((step) => (
              <article key={step.label} className={`aa-workflow-card ${step.featured ? "aa-workflow-card-featured" : ""}`}>
                <span className="aa-step-label">{step.label}</span>
                <div className="aa-step-icon-box">
                  <span className="material-symbols-outlined" aria-hidden="true">
                    {step.icon}
                  </span>
                  <small>{step.detail}</small>
                </div>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="aa-trust-section" id="trust">
          <div className="aa-trust-grid">
            <div className="aa-trust-copy">
              <h2>
                Rigorous by nature,
                <br />
                flexible by design.
              </h2>

              <div className="aa-trust-list">
                {TRUST_ITEMS.map((item) => (
                  <article key={item.title}>
                    <span className="material-symbols-outlined" aria-hidden="true">
                      {item.icon}
                    </span>
                    <div>
                      <h3>{item.title}</h3>
                      <p>{item.description}</p>
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <div className="aa-preview-shell">
              <div className="aa-preview-card">
                <div className="aa-preview-head">
                  <div className="aa-preview-title-wrap">
                    <div className="aa-preview-logo">
                      <span className="material-symbols-outlined" aria-hidden="true">
                        account_balance
                      </span>
                    </div>
                    <div>
                      <p>Account Reconciliation</p>
                      <h3>GL_2024_Q4_Settlements</h3>
                    </div>
                  </div>
                  <div className="aa-audit-pill">AUDIT READY</div>
                </div>

                <div className="aa-preview-table-head">
                  <span>Date</span>
                  <span>Description</span>
                  <span>Amount</span>
                  <span>Match Status</span>
                </div>

                <div className="aa-preview-rows">
                  <TrustPreviewRow
                    date="OCT 12, 2024"
                    description="STRIPE_TRX_9281"
                    amount="$12,490.00"
                    status="100%"
                  />
                  <TrustPreviewRow
                    date="OCT 12, 2024"
                    description="AMEX_STMT_REF_23"
                    amount="$2,100.00"
                    status="94.2%"
                  />
                  <TrustPreviewRow
                    date="OCT 11, 2024"
                    description="WIRE_IN_PENDING"
                    amount="$45,000.00"
                    status="EXCEPTION"
                    statusTone="alert"
                  />
                </div>

                <div className="aa-preview-footer">
                  <div className="aa-preview-metrics">
                    <article>
                      <p>Validated</p>
                      <h4>14,292</h4>
                    </article>
                    <article>
                      <p>Flagged</p>
                      <h4 className="aa-flagged">19</h4>
                    </article>
                  </div>
                  <button type="button" className="aa-btn aa-btn-solid">
                    Post to GL
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="aa-final-cta">
          <div className="aa-final-inner">
            <div className="aa-cta-icon" aria-hidden="true">
              <span className="material-symbols-outlined">rocket_launch</span>
            </div>
            <h2>Ready to run your first reconciliation cycle?</h2>
            <p>
              Launch the dashboard and start from real source files. See the precision of
              The Archival Authority for yourself.
            </p>
            <button
              type="button"
              className="aa-btn aa-btn-solid aa-btn-xl"
              onClick={(event) => launchDashboard(event, onGetStarted)}
            >
              Open Financial Reconciliation Dashboard
            </button>
          </div>
        </section>
      </main>

      <footer className="aa-footer">
        <div className="aa-footer-inner">
          <div className="aa-footer-brand">
            <span>The Archival Authority</span>
            <p>
              Copyright {new Date().getFullYear()} The Archival Authority. All rights reserved.
            </p>
          </div>

          <div className="aa-footer-links">
            <a href="#">Privacy Policy</a>
            <a href="#">Terms of Service</a>
            <a href="#">Institutional Disclosure</a>
            <a href="#">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
