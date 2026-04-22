export default function StatusCard({ label, state = "pending", detail }) {
  const detailLines = Array.isArray(detail)
    ? detail
    : detail
    ? [detail]
    : [];

  return (
    <div className={`status-card ${state === "blocked" ? "fail" : state}`}>
      <div className="card-label">{label}</div>
      <div className="card-status-row">
        <span className={`card-dot ${state === "blocked" ? "fail" : state}`} />
        <span className="card-status-text">
          {state === "pass" ? "Pass" : state === "fail" ? "Fail" : state === "uncertain" ? "Uncertain" : state === "blocked" ? "Could Not Run" : state}
        </span>
      </div>
      {detailLines.length > 0 && (
        <div className="card-detail">
          {detailLines.length === 1 ? (
            <span>{detailLines[0]}</span>
          ) : (
            <ul>
              {detailLines.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
