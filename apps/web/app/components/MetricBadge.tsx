export function CoverageBar({ label }: { label: string }) {
  // label form: "N of M concepts"
  const match = label.match(/(\d+)\s+of\s+(\d+)/);
  const covered = match ? parseInt(match[1], 10) : 0;
  const total = match ? parseInt(match[2], 10) : 1;
  const pct = total > 0 ? Math.round((covered / total) * 100) : 0;

  return (
    <>
      <div className="coverage-bar" aria-label={`Coverage: ${label}`}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <span className="metric-label">{label}</span>
    </>
  );
}

export function RelevanceBadge({ score }: { score: number }) {
  return <span className="metric-label">relevance {score.toFixed(2)}</span>;
}
