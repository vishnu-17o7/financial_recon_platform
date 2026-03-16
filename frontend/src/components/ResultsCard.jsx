import Card from "./common/Card";
import StatusPill from "./common/StatusPill";
import ExceptionsTable from "./ExceptionsTable";
import MatchesTable from "./MatchesTable";
import MetricsCards from "./MetricsCards";

export default function ResultsCard({ status, metrics, matches, exceptions, onExplainMatch, onToggleMatch, onExplainException }) {
  return (
    <Card className="card-metrics">
      <div className="section-head">
        <h2>Results</h2>
        <StatusPill status={status} />
      </div>

      <MetricsCards metrics={metrics} />

      <div className="table-wrap">
        <h3>Matches</h3>
        <table>
          <thead>
            <tr>
              <th>Match ID</th>
              <th>A Side</th>
              <th>B Side</th>
              <th>Confidence</th>
              <th>Algorithm</th>
              <th>Auto Accepted</th>
              <th>Actions</th>
            </tr>
          </thead>
          <MatchesTable matches={matches} onExplain={onExplainMatch} onToggle={onToggleMatch} />
        </table>
      </div>

      <div className="table-wrap">
        <h3>Exceptions</h3>
        <table>
          <thead>
            <tr>
              <th>Exception ID</th>
              <th>Transaction</th>
              <th>Status</th>
              <th>Reason</th>
              <th>Actions</th>
            </tr>
          </thead>
          <ExceptionsTable exceptions={exceptions} onExplain={onExplainException} />
        </table>
      </div>
    </Card>
  );
}
