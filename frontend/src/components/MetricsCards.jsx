function formatCurrency(value) {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return "-";
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2
  }).format(parsed);
}

export default function MetricsCards({ metrics }) {
  const cards = [
    { label: "A Side Records", value: metrics?.side_a_count ?? 0 },
    { label: "B Side Records", value: metrics?.side_b_count ?? 0 },
    { label: "Matches", value: metrics?.matched_count ?? 0 },
    { label: "Match Rate", value: `${metrics?.matched_pct ?? 0}%` },
    { label: "Exceptions", value: metrics?.exception_count ?? 0 },
    {
      label: "Delta Amount",
      value: formatCurrency(metrics?.reconciled_amount_delta_total ?? 0)
    }
  ];

  return (
    <div className="metrics-grid">
      {cards.map((card) => (
        <article className="metric" key={card.label}>
          <div className="label">{card.label}</div>
          <div className="value">{card.value}</div>
        </article>
      ))}
    </div>
  );
}
