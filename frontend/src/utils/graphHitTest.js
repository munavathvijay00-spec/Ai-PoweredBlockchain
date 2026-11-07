/** Find the closest visible directed transfer at a canvas point. */
export function nearestEdgeAt(points, edges, x, y, threshold = 11) {
  const coordinates = new Map(points.map(point => [point.id, point]));
  let nearest = null;
  let minimum = threshold;
  for (const edge of edges.slice(0, 12000)) {
    const a = coordinates.get(edge.from);
    const b = coordinates.get(edge.to);
    if (!a || !b) continue;
    const vx = b.x - a.x;
    const vy = b.y - a.y;
    const length = vx * vx + vy * vy;
    if (length < 1) continue;
    const t = Math.max(0, Math.min(1, ((x - a.x) * vx + (y - a.y) * vy) / length));
    const distance = Math.hypot(x - (a.x + t * vx), y - (a.y + t * vy));
    if (distance < minimum) { minimum = distance; nearest = edge; }
  }
  return nearest;
}
