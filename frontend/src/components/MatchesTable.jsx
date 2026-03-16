function confidencePercent(raw) {
  const parsed = Number(raw);
  if (Number.isNaN(parsed)) {
    return "-";
  }
  return `${(parsed * 100).toFixed(2)}%`;
}

export default function MatchesTable({ matches, onExplain, onToggle }) {
  if (!matches?.length) {
    return (
      <tbody>
        <tr>
          <td colSpan={7} className="empty">
            No match results yet.
          </td>
        </tr>
      </tbody>
    );
  }

  return (
    <tbody>
      {matches.map((match) => (
        <tr key={match.id}>
          <td>{match.id}</td>
          <td>{match.a}</td>
          <td>{match.b}</td>
          <td>{confidencePercent(match.confidence)}</td>
          <td>{match.algo}</td>
          <td>
            <span className={`chip ${match.auto_accepted ? "yes" : "no"}`}>{match.auto_accepted ? "Yes" : "No"}</span>
          </td>
          <td>
            <div className="actions">
              <button className="action-btn" type="button" onClick={() => onExplain(match)}>
                Explain
              </button>
              <button className="action-btn warn" type="button" onClick={() => onToggle(match)}>
                {match.auto_accepted ? "Set Manual" : "Auto Accept"}
              </button>
            </div>
          </td>
        </tr>
      ))}
    </tbody>
  );
}
