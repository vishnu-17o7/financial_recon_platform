import Card from "./common/Card";

export default function InsightCard({ content, onClear }) {
  return (
    <Card className="card-insight">
      <div className="section-head">
        <h2>AI Insight</h2>
        <button className="btn btn-ghost" type="button" onClick={onClear}>
          Clear
        </button>
      </div>

      <div className="insight-panel">{content}</div>
    </Card>
  );
}
