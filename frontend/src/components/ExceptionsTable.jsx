export default function ExceptionsTable({ exceptions, onExplain }) {
  if (!exceptions?.length) {
    return (
      <tbody>
        <tr>
          <td colSpan={5} className="empty">
            No exceptions generated yet.
          </td>
        </tr>
      </tbody>
    );
  }

  return (
    <tbody>
      {exceptions.map((exception) => (
        <tr key={exception.id}>
          <td>{exception.id}</td>
          <td>{exception.txn}</td>
          <td>{exception.status}</td>
          <td>{exception.reason}</td>
          <td>
            <button className="action-btn" type="button" onClick={() => onExplain(exception)}>
              Explain
            </button>
          </td>
        </tr>
      ))}
    </tbody>
  );
}
