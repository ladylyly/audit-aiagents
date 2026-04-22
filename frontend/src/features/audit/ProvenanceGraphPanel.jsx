function computeLevels(view) {
  const nodes = Array.isArray(view?.nodes) ? view.nodes : [];
  const edges = Array.isArray(view?.edges) ? view.edges : [];
  const rootId = view?.rootCid;

  const incomingCount = new Map();
  const children = new Map();
  for (const n of nodes) {
    incomingCount.set(n.id, 0);
    children.set(n.id, []);
  }
  for (const e of edges) {
    if (!incomingCount.has(e.target)) incomingCount.set(e.target, 0);
    incomingCount.set(e.target, (incomingCount.get(e.target) || 0) + 1);
    if (!children.has(e.source)) children.set(e.source, []);
    children.get(e.source).push(e.target);
  }

  const roots = [];
  if (rootId && incomingCount.has(rootId)) roots.push(rootId);
  for (const [id, deg] of incomingCount.entries()) {
    if (deg === 0 && id !== rootId) roots.push(id);
  }

  const levelById = new Map();
  const queue = roots.map((id) => [id, 0]);
  while (queue.length > 0) {
    const [id, level] = queue.shift();
    const current = levelById.get(id);
    if (current !== undefined && current <= level) continue;
    levelById.set(id, level);
    for (const child of children.get(id) || []) queue.push([child, level + 1]);
  }

  const grouped = new Map();
  for (const n of nodes) {
    const level = levelById.get(n.id) ?? 0;
    if (!grouped.has(level)) grouped.set(level, []);
    grouped.get(level).push(n);
  }
  return grouped;
}

function buildLayout(view) {
  const levels = computeLevels(view);
  const levelKeys = Array.from(levels.keys()).sort((a, b) => a - b);
  const xGap = 220;
  const yGap = 100;
  const margin = 40;

  const positions = new Map();
  levelKeys.forEach((level, idx) => {
    const row = levels.get(level) || [];
    row.forEach((node, rowIndex) => {
      const x = margin + idx * xGap;
      const y = margin + rowIndex * yGap;
      positions.set(node.id, { x, y, node });
    });
  });

  const maxRow = Math.max(1, ...levelKeys.map((k) => (levels.get(k) || []).length));
  const width = margin * 2 + Math.max(1, levelKeys.length) * xGap;
  const height = margin * 2 + maxRow * yGap;
  return { positions, width, height };
}

export default function ProvenanceGraphPanel({
  graphPayload,
  loading,
  error,
  selectedCid = null,
  onNodeSelect = null,
}) {
  const view = graphPayload?.view;
  const nodes = Array.isArray(view?.nodes) ? view.nodes : [];
  const edges = Array.isArray(view?.edges) ? view.edges : [];
  const { positions, width, height } = buildLayout(view);

  return (
    <div className="graph-panel">
      <div className="section-heading">Provenance graph</div>
      {loading && <div className="graph-note">Building graph...</div>}
      {error && <div className="graph-error">{error}</div>}
      {!loading && !error && nodes.length === 0 && (
        <div className="graph-note">No graph data yet.</div>
      )}
      {!loading && !error && nodes.length > 0 && (
        <div className="graph-svg-wrap">
          <svg
            className="graph-svg"
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="xMinYMin meet"
          >
            {edges.map((e) => {
              const s = positions.get(e.source);
              const t = positions.get(e.target);
              if (!s || !t) return null;
              return (
                <line
                  key={e.id}
                  x1={s.x + 151}
                  y1={s.y + 18}
                  x2={t.x - 1}
                  y2={t.y + 18}
                  stroke="#8c867f"
                  strokeWidth="1.4"
                />
              );
            })}
            {nodes.map((n) => {
              const p = positions.get(n.id);
              if (!p) return null;
              const isRoot = n.cid === view.rootCid;
              const isSelected = n.cid === selectedCid;
              return (
                <g
                  key={n.id}
                  transform={`translate(${p.x}, ${p.y})`}
                  className={onNodeSelect ? "graph-node is-clickable" : "graph-node"}
                  onClick={onNodeSelect ? () => onNodeSelect(n.cid) : undefined}
                  role={onNodeSelect ? "button" : undefined}
                  tabIndex={onNodeSelect ? 0 : undefined}
                  onKeyDown={onNodeSelect ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onNodeSelect(n.cid);
                    }
                  } : undefined}
                >
                  <rect
                    width="150"
                    height="36"
                    rx="10"
                    fill={isSelected ? "rgba(37,99,235,0.12)" : isRoot ? "rgba(184,64,42,0.12)" : "rgba(255,253,250,0.95)"}
                    stroke={isSelected ? "rgba(37,99,235,0.6)" : isRoot ? "rgba(184,64,42,0.55)" : "rgba(32,27,23,0.2)"}
                    strokeWidth={isSelected ? "2" : "1"}
                  />
                  <text x="10" y="22" fontSize="11" fill="#201b17" fontFamily="IBM Plex Mono, monospace">
                    {(n.cid || "").slice(0, 14)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
}
