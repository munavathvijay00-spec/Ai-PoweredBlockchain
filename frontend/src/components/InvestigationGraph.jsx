import { useEffect, useMemo, useRef, useState } from 'react';

const short = value => value ? `${value.slice(0, 8)}…${value.slice(-5)}` : '—';
const normalized = value => String(value || '').toLowerCase();
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const clusterPalette = [
  [0.22, 0.74, 0.97], [0.65, 0.55, 0.98], [0.20, 0.83, 0.60], [0.98, 0.73, 0.16],
  [0.98, 0.45, 0.56], [0.18, 0.83, 0.75], [0.38, 0.65, 0.98], [0.85, 0.48, 0.95],
];

function stableHash(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function numberValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.abs(number) : 0;
}

function timestampValue(tx) {
  const raw = tx.timestamp || tx.time || tx.block_time || tx.datetime;
  if (!raw) return null;
  if (typeof raw === 'number') return raw > 1e12 ? raw : raw * 1000;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function assetName(tx) {
  return String(tx.asset || (tx.category === 'erc20' ? 'TOKEN' : 'ETH')).toUpperCase();
}

function detectNodeKind(labels = []) {
  const text = labels.map(label => `${label.entity_name || ''} ${label.entity_id || ''} ${label.category || ''}`).join(' ').toLowerCase();
  if (/exchange|binance|coinbase|kraken|okx|bybit|cex/.test(text)) return 'exchange';
  if (/uniswap|aave|lido|dex|router|factory|swap/.test(text)) return 'protocol';
  if (/token|usdc|usdt|link|steth|wsteth/.test(text)) return 'token';
  if (/contract|market|vault|pool/.test(text)) return 'contract';
  return 'wallet';
}

function buildNetwork(transactions, nodeContext, rootAddress) {
  const rawEdges = transactions
    .filter(tx => tx.from_address && tx.to_address && tx.hash)
    .map((tx, index) => ({
      id: `${tx.hash}-${tx.category || tx.asset || 'tx'}-${index}`,
      from: normalized(tx.from_address),
      to: normalized(tx.to_address),
      tx,
      value: numberValue(tx.value),
      asset: assetName(tx),
      risk: Number(tx.risk_score || 0),
      time: timestampValue(tx),
    }));

  const ids = [...new Set(rawEdges.flatMap(edge => [edge.from, edge.to]))];
  const nodeMap = new Map();
  ids.forEach((id, index) => {
    const seed = stableHash(id);
    const theta = ((seed % 10000) / 10000) * Math.PI * 2;
    const phi = (((seed >>> 8) % 10000) / 10000 - 0.5) * Math.PI;
    const radius = 90 + (seed % 180);
    const labels = nodeContext[id]?.entityLabels || [];
    nodeMap.set(id, {
      id,
      index,
      x: Math.cos(theta) * Math.cos(phi) * radius,
      y: Math.sin(phi) * radius,
      z: Math.sin(theta) * Math.cos(phi) * radius,
      vx: 0,
      vy: 0,
      vz: 0,
      cluster: index,
      labels,
      kind: id === normalized(rootAddress) ? 'root' : detectNodeKind(labels),
    });
  });

  const pairWeights = new Map();
  rawEdges.forEach(edge => {
    const pair = [edge.from, edge.to].sort().join('|');
    pairWeights.set(pair, (pairWeights.get(pair) || 0) + 1);
  });

  // Strong-link clustering. Repeated interactions form visible groups; one-off links
  // remain separate so a giant connected graph does not collapse into one color.
  const parent = new Map(ids.map(id => [id, id]));
  const find = id => {
    let current = id;
    while (parent.get(current) !== current) current = parent.get(current);
    let cursor = id;
    while (parent.get(cursor) !== cursor) {
      const next = parent.get(cursor);
      parent.set(cursor, current);
      cursor = next;
    }
    return current;
  };
  const union = (a, b) => {
    const ra = find(a), rb = find(b);
    if (ra !== rb) parent.set(rb, ra);
  };
  pairWeights.forEach((weight, pair) => {
    if (weight >= 2) {
      const [a, b] = pair.split('|');
      union(a, b);
    }
  });
  const clusterIds = new Map();
  ids.forEach(id => {
    const root = find(id);
    if (!clusterIds.has(root)) clusterIds.set(root, clusterIds.size);
    nodeMap.get(id).cluster = clusterIds.get(root);
  });

  const nodes = [...nodeMap.values()];
  const edges = rawEdges.map(edge => ({ ...edge, source: nodeMap.get(edge.from), target: nodeMap.get(edge.to) }));

  // Bounded 3D force solve. It runs only when the loaded evidence changes, not every frame.
  const iterations = Math.min(170, 70 + nodes.length);
  for (let tick = 0; tick < iterations; tick += 1) {
    const cooling = 1 - tick / iterations;
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      a.vx += -a.x * 0.00055;
      a.vy += -a.y * 0.00055;
      a.vz += -a.z * 0.00055;
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const dist2 = Math.max(64, dx * dx + dy * dy + dz * dz);
        const dist = Math.sqrt(dist2);
        const repulsion = (a.cluster === b.cluster ? 700 : 1350) / dist2;
        dx /= dist; dy /= dist; dz /= dist;
        a.vx += dx * repulsion; a.vy += dy * repulsion; a.vz += dz * repulsion;
        b.vx -= dx * repulsion; b.vy -= dy * repulsion; b.vz -= dz * repulsion;
      }
    }
    edges.forEach(edge => {
      const a = edge.source, b = edge.target;
      let dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
      const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy + dz * dz));
      const desired = edge.source.cluster === edge.target.cluster ? 62 : 105;
      const force = (dist - desired) * 0.0016 * Math.min(3, 1 + pairWeights.get([edge.from, edge.to].sort().join('|')) * 0.25);
      dx /= dist; dy /= dist; dz /= dist;
      a.vx += dx * force; a.vy += dy * force; a.vz += dz * force;
      b.vx -= dx * force; b.vy -= dy * force; b.vz -= dz * force;
    });
    nodes.forEach(node => {
      node.vx *= 0.84; node.vy *= 0.84; node.vz *= 0.84;
      node.x += node.vx * cooling * 13;
      node.y += node.vy * cooling * 13;
      node.z += node.vz * cooling * 13;
    });
  }

  return { nodes, edges, nodeMap, clusterCount: clusterIds.size };
}

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'WebGL shader compilation failed');
  return shader;
}

function createProgram(gl, vertexSource, fragmentSource) {
  const program = gl.createProgram();
  gl.attachShader(program, compileShader(gl, gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'WebGL program link failed');
  return program;
}

function initRenderer(gl) {
  const pointProgram = createProgram(gl, `
    attribute vec2 aPosition;
    attribute float aSize;
    attribute vec3 aColor;
    attribute float aShape;
    attribute float aEmphasis;
    varying vec3 vColor;
    varying float vShape;
    varying float vEmphasis;
    void main() {
      gl_Position = vec4(aPosition, 0.0, 1.0);
      gl_PointSize = aSize;
      vColor = aColor;
      vShape = aShape;
      vEmphasis = aEmphasis;
    }
  `, `
    precision mediump float;
    varying vec3 vColor;
    varying float vShape;
    varying float vEmphasis;
    void main() {
      vec2 p = gl_PointCoord * 2.0 - 1.0;
      float d = length(p);
      float mask;
      if (vShape < 0.5) mask = 1.0 - smoothstep(0.86, 1.0, d);
      else if (vShape < 1.5) mask = 1.0 - smoothstep(0.88, 1.0, abs(p.x) + abs(p.y));
      else mask = 1.0 - smoothstep(0.90, 1.0, max(abs(p.x), abs(p.y)));
      if (mask <= 0.01) discard;
      float highlight = max(0.0, 1.0 - length(p - vec2(-0.32, -0.34)) * 1.55);
      float rim = smoothstep(0.58, 0.96, d);
      vec3 color = vColor * (0.52 + highlight * 0.72) + vec3(rim * 0.24);
      float alpha = mask * (0.86 + vEmphasis * 0.14);
      gl_FragColor = vec4(color, alpha);
    }
  `);
  const lineProgram = createProgram(gl, `
    attribute vec2 aPosition;
    attribute vec4 aColor;
    varying vec4 vColor;
    void main() { gl_Position = vec4(aPosition, 0.0, 1.0); vColor = aColor; }
  `, `
    precision mediump float;
    varying vec4 vColor;
    void main() { gl_FragColor = vColor; }
  `);
  return { pointProgram, lineProgram, buffer: gl.createBuffer() };
}

function rotate(point, camera) {
  const px = point.x - camera.center[0], py = point.y - camera.center[1], pz = point.z - camera.center[2];
  const cy = Math.cos(camera.yaw), sy = Math.sin(camera.yaw);
  const cp = Math.cos(camera.pitch), sp = Math.sin(camera.pitch);
  const x1 = px * cy + pz * sy;
  const z1 = -px * sy + pz * cy;
  return { x: x1, y: py * cp - z1 * sp, z: py * sp + z1 * cp };
}

function project(point, camera, width, height) {
  const p = rotate(point, camera);
  const depth = Math.max(190, 720 - p.z);
  const perspective = 720 / depth;
  const sx = width / 2 + p.x * perspective * camera.zoom;
  const sy = height / 2 - p.y * perspective * camera.zoom;
  return { x: sx, y: sy, z: p.z, perspective, clipX: sx / width * 2 - 1, clipY: 1 - sy / height * 2 };
}

function shortestPath(root, target, edges) {
  if (!root || !target || root === target) return [];
  const adjacency = new Map();
  edges.forEach(edge => {
    if (!adjacency.has(edge.from)) adjacency.set(edge.from, []);
    if (!adjacency.has(edge.to)) adjacency.set(edge.to, []);
    adjacency.get(edge.from).push([edge.to, edge]);
    adjacency.get(edge.to).push([edge.from, edge]);
  });
  const queue = [root], seen = new Set([root]), previous = new Map();
  for (let i = 0; i < queue.length; i += 1) {
    const current = queue[i];
    for (const [next, edge] of adjacency.get(current) || []) {
      if (seen.has(next)) continue;
      seen.add(next); previous.set(next, [current, edge]);
      if (next === target) {
        const path = [];
        let cursor = target;
        while (cursor !== root) {
          const [prior, used] = previous.get(cursor);
          path.push(used.id); cursor = prior;
        }
        return path.reverse();
      }
      queue.push(next);
    }
  }
  return [];
}

function semanticColor(node, context, selected, root) {
  if (node.id === root) return [0.22, 0.82, 0.98];
  if (selected) return [1.0, 0.78, 0.20];
  if ((context.entityLabels || []).length) return [0.18, 0.86, 0.58];
  const risk = Number(context.maxRisk || 0);
  if (risk >= 70) return [1.0, 0.28, 0.34];
  return clusterPalette[node.cluster % clusterPalette.length];
}

function shapeCode(kind) {
  if (kind === 'exchange' || kind === 'protocol') return 1;
  if (kind === 'contract' || kind === 'token') return 2;
  return 0;
}

export default function InvestigationGraph({ transactions = [], rootAddress = '', onSelect, onExpandAddress, expandingAddress = '', expandedAddresses = [], nodeContext = {} }) {
  const canvasRef = useRef(null);
  const rendererRef = useRef(null);
  const animationRef = useRef(null);
  const projectedRef = useRef(new Map());
  const pointerRef = useRef(null);
  const cameraRef = useRef({ yaw: 0.55, pitch: -0.18, zoom: 1.35, center: [0, 0, 0], target: [0, 0, 0] });

  const [mode, setMode] = useState('graph');
  const [selectedNode, setSelectedNode] = useState('');
  const [selectedEdge, setSelectedEdge] = useState('');
  const [query, setQuery] = useState('');
  const [asset, setAsset] = useState('ALL');
  const [timeWindow, setTimeWindow] = useState('ALL');
  const [minValue, setMinValue] = useState(0);
  const [minRisk, setMinRisk] = useState(0);
  const [isolate, setIsolate] = useState(false);
  const [pathMode, setPathMode] = useState(false);
  const [rendererError, setRendererError] = useState('');
  const [renderStats, setRenderStats] = useState({ nodes: 0, edges: 0 });

  const root = normalized(rootAddress);
  const expanded = useMemo(() => new Set(expandedAddresses.map(normalized)), [expandedAddresses]);
  const network = useMemo(() => buildNetwork(transactions, nodeContext, root), [transactions, nodeContext, root]);
  const assets = useMemo(() => ['ALL', ...[...new Set(network.edges.map(edge => edge.asset))].sort()], [network]);
  const newestTime = useMemo(() => Math.max(0, ...network.edges.map(edge => edge.time || 0)), [network]);

  const filteredEdges = useMemo(() => {
    const windows = { '24H': 86400000, '7D': 604800000, '30D': 2592000000 };
    const cutoff = timeWindow === 'ALL' || !newestTime ? 0 : newestTime - windows[timeWindow];
    return network.edges.filter(edge => {
      if (asset !== 'ALL' && edge.asset !== asset) return false;
      if (edge.value < Number(minValue || 0)) return false;
      if (edge.risk < Number(minRisk || 0)) return false;
      if (cutoff && edge.time && edge.time < cutoff) return false;
      return true;
    });
  }, [network, asset, minValue, minRisk, timeWindow, newestTime]);

  const pathIds = useMemo(() => pathMode && selectedNode ? new Set(shortestPath(root, selectedNode, filteredEdges)) : new Set(), [pathMode, selectedNode, root, filteredEdges]);
  const visibleEdges = useMemo(() => {
    if (pathMode && selectedNode) return filteredEdges.filter(edge => pathIds.has(edge.id));
    if (isolate && selectedNode) return filteredEdges.filter(edge => edge.from === selectedNode || edge.to === selectedNode);
    return filteredEdges;
  }, [filteredEdges, pathMode, selectedNode, pathIds, isolate]);
  const visibleNodeIds = useMemo(() => new Set(visibleEdges.flatMap(edge => [edge.from, edge.to]).concat(root ? [root] : [])), [visibleEdges, root]);
  const visibleNodes = useMemo(() => network.nodes.filter(node => visibleNodeIds.has(node.id)), [network, visibleNodeIds]);

  const nodeMetrics = useMemo(() => {
    const metrics = new Map(network.nodes.map(node => [node.id, { incoming: 0, outgoing: 0, transfers: 0, volume: 0, peers: new Set(), assets: new Set(), maxRisk: Number(nodeContext[node.id]?.maxRisk || 0) }]));
    filteredEdges.forEach(edge => {
      const from = metrics.get(edge.from), to = metrics.get(edge.to);
      from.outgoing += 1; from.transfers += 1; from.volume += edge.value; from.peers.add(edge.to); from.assets.add(edge.asset); from.maxRisk = Math.max(from.maxRisk, edge.risk);
      to.incoming += 1; to.transfers += 1; to.volume += edge.value; to.peers.add(edge.from); to.assets.add(edge.asset); to.maxRisk = Math.max(to.maxRisk, edge.risk);
    });
    return metrics;
  }, [network, filteredEdges, nodeContext]);

  const clusterSummary = useMemo(() => {
    const map = new Map();
    visibleNodes.forEach(node => {
      if (!map.has(node.cluster)) map.set(node.cluster, { id: node.cluster, nodes: 0, transfers: 0, volume: 0, risk: 0 });
      const row = map.get(node.cluster), metric = nodeMetrics.get(node.id);
      row.nodes += 1; row.volume += metric?.volume || 0; row.risk = Math.max(row.risk, metric?.maxRisk || 0);
    });
    visibleEdges.forEach(edge => {
      if (edge.source.cluster === edge.target.cluster && map.has(edge.source.cluster)) map.get(edge.source.cluster).transfers += 1;
    });
    return [...map.values()].sort((a, b) => b.nodes - a.nodes || b.volume - a.volume);
  }, [visibleNodes, visibleEdges, nodeMetrics]);

  const temporalSignal = useMemo(() => {
    const times = filteredEdges.map(edge => edge.time).filter(Boolean).sort((a, b) => a - b);
    if (times.length < 3) return null;
    let best = 0, left = 0;
    for (let right = 0; right < times.length; right += 1) {
      while (times[right] - times[left] > 10 * 60 * 1000) left += 1;
      best = Math.max(best, right - left + 1);
    }
    return { burst10m: best, timestamped: times.length };
  }, [filteredEdges]);

  useEffect(() => {
    if (asset !== 'ALL' && !assets.includes(asset)) setAsset('ALL');
  }, [assets, asset]);

  useEffect(() => {
    if (mode !== 'graph') return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const gl = canvas.getContext('webgl', { antialias: true, alpha: false, powerPreference: 'high-performance' });
    if (!gl) { setRendererError('WebGL is unavailable in this browser. Use the evidence table fallback.'); return undefined; }
    let renderer;
    try { renderer = initRenderer(gl); rendererRef.current = renderer; setRendererError(''); }
    catch (error) { setRendererError(error.message || 'Unable to initialize GPU graph renderer.'); return undefined; }

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width * dpr));
      const height = Math.max(1, Math.floor(rect.height * dpr));
      if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
      gl.viewport(0, 0, width, height);
    };
    const observer = new ResizeObserver(resize); observer.observe(canvas); resize();

    const pointPosition = gl.getAttribLocation(renderer.pointProgram, 'aPosition');
    const pointSize = gl.getAttribLocation(renderer.pointProgram, 'aSize');
    const pointColor = gl.getAttribLocation(renderer.pointProgram, 'aColor');
    const pointShape = gl.getAttribLocation(renderer.pointProgram, 'aShape');
    const pointEmphasis = gl.getAttribLocation(renderer.pointProgram, 'aEmphasis');
    const linePosition = gl.getAttribLocation(renderer.lineProgram, 'aPosition');
    const lineColor = gl.getAttribLocation(renderer.lineProgram, 'aColor');

    const drawLines = values => {
      if (!values.length) return;
      gl.useProgram(renderer.lineProgram);
      const stride = 6 * 4;
      gl.bindBuffer(gl.ARRAY_BUFFER, renderer.buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(values), gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(linePosition); gl.vertexAttribPointer(linePosition, 2, gl.FLOAT, false, stride, 0);
      gl.enableVertexAttribArray(lineColor); gl.vertexAttribPointer(lineColor, 4, gl.FLOAT, false, stride, 2 * 4);
      gl.drawArrays(gl.LINES, 0, values.length / 6);
    };
    const drawPoints = values => {
      if (!values.length) return;
      gl.useProgram(renderer.pointProgram);
      const stride = 8 * 4;
      gl.bindBuffer(gl.ARRAY_BUFFER, renderer.buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(values), gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(pointPosition); gl.vertexAttribPointer(pointPosition, 2, gl.FLOAT, false, stride, 0);
      gl.enableVertexAttribArray(pointSize); gl.vertexAttribPointer(pointSize, 1, gl.FLOAT, false, stride, 2 * 4);
      gl.enableVertexAttribArray(pointColor); gl.vertexAttribPointer(pointColor, 3, gl.FLOAT, false, stride, 3 * 4);
      gl.enableVertexAttribArray(pointShape); gl.vertexAttribPointer(pointShape, 1, gl.FLOAT, false, stride, 6 * 4);
      gl.enableVertexAttribArray(pointEmphasis); gl.vertexAttribPointer(pointEmphasis, 1, gl.FLOAT, false, stride, 7 * 4);
      gl.drawArrays(gl.POINTS, 0, values.length / 8);
    };

    let lastStats = '';
    const frame = time => {
      resize();
      const cssWidth = canvas.clientWidth || 1, cssHeight = canvas.clientHeight || 1;
      const camera = cameraRef.current;
      camera.center[0] += (camera.target[0] - camera.center[0]) * 0.09;
      camera.center[1] += (camera.target[1] - camera.center[1]) * 0.09;
      camera.center[2] += (camera.target[2] - camera.center[2]) * 0.09;

      gl.clearColor(0.018, 0.038, 0.071, 1);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

      const projected = new Map();
      visibleNodes.forEach(node => projected.set(node.id, project(node, camera, cssWidth, cssHeight)));
      projectedRef.current = projected;

      const lineValues = [];
      visibleEdges.slice(0, 5000).forEach(edge => {
        const a = projected.get(edge.from), b = projected.get(edge.to);
        if (!a || !b) return;
        const selected = edge.id === selectedEdge || pathIds.has(edge.id);
        const token = edge.tx.category === 'erc20';
        const alpha = selected ? 0.98 : token ? 0.52 : 0.32;
        const color = selected ? [1, .76, .18] : token ? [.67, .48, .96] : [.42, .57, .73];
        lineValues.push(a.clipX, a.clipY, ...color, alpha, b.clipX, b.clipY, ...color, alpha);
      });
      drawLines(lineValues);

      // Animated transfer particles on the most informative visible edges.
      const particleValues = [];
      visibleEdges.slice(0, 180).forEach((edge, index) => {
        const a = projected.get(edge.from), b = projected.get(edge.to);
        if (!a || !b) return;
        const speed = 0.00014 + (index % 7) * 0.000015;
        const t = (time * speed + (stableHash(edge.id) % 1000) / 1000) % 1;
        const x = a.clipX + (b.clipX - a.clipX) * t, y = a.clipY + (b.clipY - a.clipY) * t;
        const c = edge.tx.category === 'erc20' ? [.74, .56, 1] : [.42, .82, 1];
        particleValues.push(x, y, 4.5 * dpr, ...c, 0, .35);
      });
      drawPoints(particleValues);

      const nodeValues = [];
      visibleNodes.slice(0, 2200).forEach(node => {
        const p = projected.get(node.id), metric = nodeMetrics.get(node.id) || {};
        if (!p) return;
        const volumeSignal = Math.log10(1 + (metric.volume || 0));
        const activitySignal = Math.log2(1 + (metric.transfers || 0));
        const semanticSize = 13 + volumeSignal * 5.2 + activitySignal * 3.1 + (node.id === root ? 8 : 0);
        const size = clamp(semanticSize * clamp(p.perspective, .58, 1.65) * dpr, 8 * dpr, 72 * dpr);
        const context = { ...(nodeContext[node.id] || {}), maxRisk: metric.maxRisk };
        const color = semanticColor(node, context, node.id === selectedNode, root);
        nodeValues.push(p.clipX, p.clipY, size, ...color, shapeCode(node.kind), node.id === selectedNode || node.id === root ? 1 : 0);
      });
      drawPoints(nodeValues);

      const stats = `${visibleNodes.length}|${visibleEdges.length}`;
      if (stats !== lastStats) { lastStats = stats; setRenderStats({ nodes: visibleNodes.length, edges: visibleEdges.length }); }
      animationRef.current = requestAnimationFrame(frame);
    };
    animationRef.current = requestAnimationFrame(frame);
    return () => { observer.disconnect(); cancelAnimationFrame(animationRef.current); };
  }, [mode, visibleNodes, visibleEdges, selectedNode, selectedEdge, nodeMetrics, nodeContext, root, pathIds]);

  const selectNode = id => {
    setSelectedNode(id); setSelectedEdge('');
    const node = network.nodeMap.get(id);
    if (node) cameraRef.current.target = [node.x, node.y, node.z];
  };

  const resetView = () => {
    cameraRef.current = { yaw: 0.55, pitch: -0.18, zoom: 1.35, center: [0, 0, 0], target: [0, 0, 0] };
    setSelectedNode(''); setSelectedEdge(''); setIsolate(false); setPathMode(false); setQuery('');
  };

  const pointerDown = event => {
    if (event.button !== 0) return;
    pointerRef.current = { x: event.clientX, y: event.clientY, yaw: cameraRef.current.yaw, pitch: cameraRef.current.pitch, moved: false };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const pointerMove = event => {
    const drag = pointerRef.current; if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    cameraRef.current.yaw = drag.yaw + dx * 0.008;
    cameraRef.current.pitch = clamp(drag.pitch + dy * 0.007, -1.35, 1.35);
  };
  const pointerUp = event => {
    const drag = pointerRef.current; pointerRef.current = null;
    if (!drag || drag.moved) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    let best = null, bestDistance = 34;
    projectedRef.current.forEach((point, id) => {
      const distance = Math.hypot(point.x - x, point.y - y);
      if (distance < bestDistance) { bestDistance = distance; best = id; }
    });
    if (best) selectNode(best);
  };
  const wheel = event => {
    event.preventDefault();
    cameraRef.current.zoom = clamp(cameraRef.current.zoom * (event.deltaY > 0 ? 0.9 : 1.1), 0.55, 3.4);
  };

  const searchGraph = () => {
    const q = query.trim().toLowerCase(); if (!q) return;
    const node = network.nodes.find(item => item.id.includes(q) || (nodeContext[item.id]?.entityLabels || []).some(label => String(label.entity_name || label.entity_id || '').toLowerCase().includes(q)));
    if (node) selectNode(node.id);
  };

  const selectedMetric = selectedNode ? nodeMetrics.get(selectedNode) : null;
  const selectedContext = selectedNode ? nodeContext[selectedNode] || {} : {};
  const selectedNetworkNode = selectedNode ? network.nodeMap.get(selectedNode) : null;
  const selectedCluster = selectedNetworkNode ? clusterSummary.find(row => row.id === selectedNetworkNode.cluster) : null;
  const selectedEdgeRecord = selectedEdge ? network.edges.find(edge => edge.id === selectedEdge) : null;

  const exportEvidence = () => {
    const quote = value => {
      const raw = String(value ?? '');
      const safe = /^\s*[=+@-]/.test(raw) ? `'${raw}` : raw;
      return `"${safe.replace(/"/g, '""')}"`;
    };
    const rows = [['transaction_hash','from_address','to_address','value','asset','category','risk_score','evidence_url'], ...visibleEdges.map(edge => [edge.tx.hash, edge.from, edge.to, edge.tx.value, edge.asset, edge.tx.category, edge.risk, edge.tx.evidence_url || `https://etherscan.io/tx/${edge.tx.hash}`])];
    const blob = new Blob([rows.map(row => row.map(quote).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'chainscope-webgl-evidence.csv'; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  };

  return <section className="overflow-hidden rounded-xl border border-slate-700 bg-slate-900/70">
    <div className="border-b border-slate-700 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="eyebrow text-cyan-300">WebGL investigation engine</p><h2 className="mt-2 text-xl font-semibold text-white">Semantic 3D wallet map</h2><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Bubble size reflects observed activity/value, color reflects detected relationship clusters or risk/entity context, and animated particles show transfer direction. Spatial distance is produced by graph physics—not an ownership claim.</p></div>
        <div className="flex flex-wrap gap-2 text-xs"><span className="status-pill border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200">GPU WebGL</span><span className="status-pill border-violet-400/20 bg-violet-400/[0.06] text-violet-200">{network.clusterCount} clusters</span><span className="status-pill border-slate-700 bg-slate-950/60 text-slate-300">{renderStats.nodes} nodes · {renderStats.edges} edges</span></div>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(260px,1.5fr)_repeat(4,minmax(120px,.55fr))]">
        <div className="flex gap-2"><input aria-label="Search wallet or entity" value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') searchGraph(); }} placeholder="Find wallet or entity…" className="soft-input min-w-0 flex-1"/><button type="button" onClick={searchGraph} className="secondary-button">Focus</button></div>
        <select aria-label="Asset filter" value={asset} onChange={event => setAsset(event.target.value)} className="soft-input">{assets.map(item => <option key={item} value={item}>{item === 'ALL' ? 'All assets' : item}</option>)}</select>
        <select aria-label="Time filter" value={timeWindow} onChange={event => setTimeWindow(event.target.value)} className="soft-input"><option value="ALL">All time</option><option value="24H">24 hours</option><option value="7D">7 days</option><option value="30D">30 days</option></select>
        <input aria-label="Minimum observed amount" type="number" min="0" step="any" value={minValue} onChange={event => setMinValue(event.target.value)} className="soft-input" placeholder="Min amount" />
        <label className="rounded-lg border border-slate-700 bg-slate-950/35 px-3 py-2 text-xs text-slate-400">Risk ≥ {minRisk}<input aria-label="Minimum risk" type="range" min="0" max="100" value={minRisk} onChange={event => setMinRisk(Number(event.target.value))} className="mt-1 w-full" /></label>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={() => setIsolate(value => !value)} disabled={!selectedNode} className={`secondary-button py-2 text-xs disabled:opacity-40 ${isolate ? 'border-cyan-400/40 text-cyan-200' : ''}`}>{isolate ? 'Show full graph' : 'Isolate selected'}</button>
        <button type="button" onClick={() => setPathMode(value => !value)} disabled={!selectedNode || selectedNode === root} className={`secondary-button py-2 text-xs disabled:opacity-40 ${pathMode ? 'border-amber-400/40 text-amber-200' : ''}`}>{pathMode ? 'Exit path mode' : 'Trace root → selected'}</button>
        <button type="button" onClick={exportEvidence} disabled={!visibleEdges.length} className="secondary-button py-2 text-xs disabled:opacity-40">Export filtered evidence</button>
        <button type="button" onClick={resetView} className="secondary-button py-2 text-xs">Reset view</button>
        <div className="flex overflow-hidden rounded-lg border border-slate-700 text-xs"><button type="button" onClick={() => setMode('graph')} className={`px-3 py-2 ${mode === 'graph' ? 'bg-slate-700 text-white' : 'text-slate-400'}`}>3D map</button><button type="button" onClick={() => setMode('table')} className={`px-3 py-2 ${mode === 'table' ? 'bg-slate-700 text-white' : 'text-slate-400'}`}>Evidence</button></div>
      </div>
    </div>

    {temporalSignal && temporalSignal.burst10m >= 3 && <div className="border-b border-amber-400/15 bg-amber-400/[0.04] px-5 py-3 text-sm text-amber-100">Temporal signal: up to <strong>{temporalSignal.burst10m}</strong> timestamped transfers occurred inside a 10-minute window in the current filters. This is a coordination lead, not proof of common control.</div>}

    {mode === 'graph' ? <div className="grid lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="relative min-h-[620px] bg-[radial-gradient(circle_at_50%_48%,#132b4b_0%,#081321_50%,#03070d_100%)]">
        <canvas ref={canvasRef} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={() => { pointerRef.current = null; }} onWheel={wheel} tabIndex={0} aria-label="Interactive WebGL wallet graph. Drag to orbit, scroll to zoom, click a bubble to inspect it." className="h-[620px] w-full touch-none cursor-grab outline-none active:cursor-grabbing lg:h-[720px]" />
        {rendererError && <div role="alert" className="absolute inset-0 flex items-center justify-center bg-slate-950/90 p-8 text-center text-sm text-amber-200">{rendererError}</div>}
        <div className="pointer-events-none absolute left-4 top-4 rounded-full border border-cyan-400/15 bg-slate-950/70 px-3 py-1 text-[11px] uppercase tracking-[.15em] text-cyan-200">Drag orbit · wheel zoom · click inspect</div>
        <div className="pointer-events-none absolute bottom-4 left-4 flex max-w-[90%] flex-wrap gap-2 text-[11px] text-slate-400"><span>● cluster wallet</span><span>◇ protocol/exchange</span><span>■ contract/token</span><span className="text-red-300">● high risk</span><span className="text-emerald-300">● labeled entity</span><span className="text-cyan-300">● root</span></div>
        <div className="pointer-events-none absolute bottom-4 right-4 hidden w-40 rounded-lg border border-slate-700 bg-slate-950/70 p-2 text-[10px] text-slate-400 md:block"><p className="font-semibold text-slate-200">Cluster overview</p>{clusterSummary.slice(0, 5).map(row => <div key={row.id} className="mt-1 flex justify-between gap-2"><span>Cluster {row.id + 1}</span><span>{row.nodes} wallets</span></div>)}</div>
      </div>

      <aside className="space-y-4 border-t border-slate-700 p-5 lg:border-l lg:border-t-0">
        <h3 className="font-semibold text-white">Investigation context</h3>
        {selectedNode ? <>
          <div><p className="text-xs text-slate-500">Selected {selectedNetworkNode?.kind || 'wallet'}</p><p className="mt-1 break-all font-mono text-xs text-cyan-300">{selectedNode}</p></div>
          <div className="grid grid-cols-2 gap-2 text-xs"><div className="rounded-lg bg-slate-950/55 p-3"><p className="text-slate-500">Observed activity</p><p className="mt-1 text-xl font-semibold text-white">{selectedMetric?.transfers || 0}</p></div><div className="rounded-lg bg-slate-950/55 p-3"><p className="text-slate-500">Observed value*</p><p className="mt-1 text-xl font-semibold text-white">{Number(selectedMetric?.volume || 0).toLocaleString(undefined,{maximumFractionDigits:3})}</p></div><div className="rounded-lg bg-slate-950/55 p-3"><p className="text-slate-500">Counterparties</p><p className="mt-1 text-xl font-semibold text-white">{selectedMetric?.peers?.size || 0}</p></div><div className="rounded-lg bg-slate-950/55 p-3"><p className="text-slate-500">Max risk</p><p className="mt-1 text-xl font-semibold text-white">{selectedMetric?.maxRisk || 0}</p></div></div>
          {selectedCluster && <div className="rounded-lg border border-violet-400/15 bg-violet-400/[0.035] p-3"><p className="text-xs font-semibold uppercase tracking-[.12em] text-violet-200">Cluster {selectedCluster.id + 1}</p><p className="mt-2 text-sm text-slate-300">{selectedCluster.nodes} visible wallets · {selectedCluster.transfers} internal transfers · peak risk {selectedCluster.risk}</p><p className="mt-1 text-xs text-slate-500">Cluster color is based on repeated observed relationships, not ownership.</p></div>}
          {(selectedContext.entityLabels || []).map((label,index) => <div key={`${label.source}-${index}`} className="rounded-lg border border-emerald-400/15 bg-emerald-400/[0.035] p-3"><p className="font-medium text-emerald-200">{label.entity_name || label.entity_id}</p><p className="mt-1 text-xs text-slate-400">Source: {label.source} · confidence {label.confidence ?? '—'}</p></div>)}
          {selectedMetric?.assets?.size > 0 && <p className="text-xs text-slate-400">Assets in current filters: {[...selectedMetric.assets].slice(0,10).join(', ')}</p>}
          {onExpandAddress && selectedNode !== root && !expanded.has(selectedNode) && <button type="button" disabled={Boolean(expandingAddress)} onClick={() => onExpandAddress(selectedNode)} className="primary-button w-full disabled:opacity-50">{normalized(expandingAddress) === selectedNode ? 'Expanding evidence…' : 'Expand one observed hop'}</button>}
          {expanded.has(selectedNode) && <p className="text-xs text-amber-200">Bounded one-hop evidence for this wallet has been merged into the scene.</p>}
          <a href={`https://etherscan.io/address/${selectedNode}`} target="_blank" rel="noreferrer" className="block text-sm text-cyan-300 underline">Verify wallet on Etherscan ↗</a>
          <p className="text-[11px] leading-5 text-slate-500">*Observed value aggregates provider-normalized values across the current asset filter. Do not compare unlike assets as a common currency.</p>
        </> : selectedEdgeRecord ? <>
          <p className="text-xs text-slate-500">Selected transfer</p><p className="break-all font-mono text-xs text-slate-300">{selectedEdgeRecord.from}</p><p className="text-cyan-300">↓</p><p className="break-all font-mono text-xs text-slate-300">{selectedEdgeRecord.to}</p><div className="rounded-lg bg-slate-950/55 p-3 text-sm text-slate-300"><p>Asset: <span className="text-white">{selectedEdgeRecord.asset}</span></p><p>Value: <span className="text-white">{selectedEdgeRecord.tx.value ?? '—'}</span></p><p>Risk: <span className="text-white">{selectedEdgeRecord.risk}</span></p></div><a href={selectedEdgeRecord.tx.evidence_url || `https://etherscan.io/tx/${selectedEdgeRecord.tx.hash}`} target="_blank" rel="noreferrer" className="text-sm text-cyan-300 underline">Verify transaction ↗</a>{onSelect && <button type="button" className="secondary-button w-full" onClick={() => onSelect(selectedEdgeRecord.tx)}>Transaction details</button>}
        </> : <><p className="text-sm leading-6 text-slate-400">Select a bubble to inspect semantic size, cluster membership, risk, entity attribution and assets. Use <strong className="text-slate-200">Trace root → selected</strong> to isolate the shortest observed route.</p><div className="rounded-lg border border-slate-800 bg-slate-950/45 p-3 text-xs leading-5 text-slate-500">Large bubbles indicate more observed value/activity in the current filters. They do not imply wallet ownership, importance, or illicit behavior.</div></>}
      </aside>
    </div> : <div className="overflow-x-auto" role="region" tabIndex={0} aria-label="Filtered investigation evidence"><table className="w-full min-w-[860px] text-left text-sm"><thead className="bg-slate-950/60 text-xs text-slate-500"><tr><th className="p-4">From</th><th className="p-4">To</th><th className="p-4">Value</th><th className="p-4">Asset</th><th className="p-4">Risk</th><th className="p-4">Evidence</th></tr></thead><tbody className="divide-y divide-slate-800">{visibleEdges.map(edge => <tr key={edge.id}><td className="p-4 font-mono text-xs">{short(edge.from)}</td><td className="p-4 font-mono text-xs">{short(edge.to)}</td><td className="p-4">{edge.tx.value ?? '—'}</td><td className="p-4">{edge.asset}</td><td className="p-4">{edge.risk}</td><td className="p-4"><a href={edge.tx.evidence_url || `https://etherscan.io/tx/${edge.tx.hash}`} target="_blank" rel="noreferrer" className="text-cyan-300 underline">{short(edge.tx.hash)} ↗</a></td></tr>)}</tbody></table>{!visibleEdges.length && <p className="p-8 text-sm text-slate-400">No evidence matches the current filters.</p>}</div>}

    <div className="border-t border-slate-700 px-5 py-3 text-xs leading-5 text-slate-500">WebGL position, bubble size, clusters and animated flow are analytical visual aids over loaded evidence. They do not establish shared ownership, taint, beneficial ownership, fraud, or complete chain history.</div>
  </section>;
}
