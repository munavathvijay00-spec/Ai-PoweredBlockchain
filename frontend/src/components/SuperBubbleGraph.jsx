import { useEffect, useMemo, useRef, useState } from 'react';

const norm = value => (value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 6)}…${value.slice(-4)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const PALETTE = ['#f10da9', '#0dd9f5', '#8b5cf6', '#22c98b', '#ff9f43', '#4f8cff', '#fb7185'];
const MUTED = '#243147';

function rgb(hex) {
  const n = Number.parseInt(hex.replace('#', ''), 16);
  return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255];
}

function valueOf(value) {
  const parsed = Number.parseFloat(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function noise(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) % 10000) / 10000;
}

function buildNetwork(transactions, root) {
  const rootId = norm(root);
  const nodes = new Map();
  const edges = new Map();
  const adjacency = new Map();

  const ensureNode = id => {
    const key = norm(id);
    if (!key) return null;
    if (!nodes.has(key)) {
      nodes.set(key, {
        id: key,
        incoming: 0,
        outgoing: 0,
        txCount: 0,
        counterparties: new Set(),
        inByAsset: {},
        outByAsset: {},
        maxRisk: null,
      });
      adjacency.set(key, new Set());
    }
    return nodes.get(key);
  };

  for (const tx of transactions || []) {
    const source = norm(tx.from_address);
    const target = norm(tx.to_address);
    if (!source || !target || !tx.hash) continue;
    const asset = tx.asset || 'ETH';
    const amount = valueOf(tx.value);
    const edgeKey = `${source}|${target}|${asset}`;

    if (!edges.has(edgeKey)) {
      edges.set(edgeKey, {
        id: edgeKey,
        source,
        target,
        asset,
        totalValue: 0,
        txCount: 0,
        maxRisk: null,
        transactions: [],
      });
    }
    const edge = edges.get(edgeKey);
    edge.totalValue += amount;
    edge.txCount += 1;
    edge.transactions.push(tx);
    if (tx.risk_score != null) edge.maxRisk = Math.max(edge.maxRisk ?? 0, Number(tx.risk_score) || 0);

    const from = ensureNode(source);
    const to = ensureNode(target);
    from.outgoing += 1;
    from.txCount += 1;
    from.counterparties.add(target);
    from.outByAsset[asset] = (from.outByAsset[asset] || 0) + amount;
    to.incoming += 1;
    to.txCount += 1;
    to.counterparties.add(source);
    to.inByAsset[asset] = (to.inByAsset[asset] || 0) + amount;
    if (tx.risk_score != null) {
      const score = Number(tx.risk_score) || 0;
      from.maxRisk = Math.max(from.maxRisk ?? 0, score);
      to.maxRisk = Math.max(to.maxRisk ?? 0, score);
    }
    adjacency.get(source).add(target);
    adjacency.get(target).add(source);
  }

  const depth = new Map();
  const cluster = new Map();
  if (rootId && nodes.has(rootId)) {
    depth.set(rootId, 0);
    cluster.set(rootId, -1);
    const firstHop = [...(adjacency.get(rootId) || [])]
      .sort((a, b) => (nodes.get(b)?.txCount || 0) - (nodes.get(a)?.txCount || 0));
    const queue = [];
    firstHop.forEach((id, index) => {
      depth.set(id, 1);
      cluster.set(id, index);
      queue.push(id);
    });
    for (let i = 0; i < queue.length; i += 1) {
      const current = queue[i];
      for (const neighbor of adjacency.get(current) || []) {
        if (neighbor === rootId || depth.has(neighbor)) continue;
        depth.set(neighbor, (depth.get(current) || 1) + 1);
        cluster.set(neighbor, cluster.get(current));
        queue.push(neighbor);
      }
    }
  }

  let looseCluster = 1000;
  const seenLoose = new Set();
  for (const start of nodes.keys()) {
    if (depth.has(start) || seenLoose.has(start)) continue;
    const queue = [start];
    seenLoose.add(start);
    while (queue.length) {
      const current = queue.shift();
      depth.set(current, 1);
      cluster.set(current, looseCluster);
      for (const neighbor of adjacency.get(current) || []) {
        if (!seenLoose.has(neighbor) && !depth.has(neighbor)) {
          seenLoose.add(neighbor);
          queue.push(neighbor);
        }
      }
    }
    looseCluster += 1;
  }

  const groups = new Map();
  for (const node of nodes.values()) {
    const clusterId = cluster.get(node.id) ?? 9999;
    if (!groups.has(clusterId)) groups.set(clusterId, []);
    groups.get(clusterId).push(node);
  }

  const stats = [...groups.entries()]
    .filter(([id]) => id !== -1)
    .map(([id, list]) => ({ id, activity: list.reduce((sum, node) => sum + node.txCount, 0), count: list.length }))
    .sort((a, b) => b.activity - a.activity || b.count - a.count);
  const rank = new Map(stats.map((item, index) => [item.id, index]));
  const positioned = [];

  const rootNode = nodes.get(rootId);
  if (rootNode) positioned.push({ ...rootNode, x: 0, y: 0, z: 0, depth: 0, clusterId: -1, clusterRank: -1, isRoot: true });

  for (const [clusterId, group] of groups.entries()) {
    if (clusterId === -1) continue;
    const clusterRank = rank.get(clusterId) ?? 99;
    const theta = clusterRank * 2.399963229728653;
    const ring = clusterRank < 2 ? 250 : 380 + 72 * Math.floor((clusterRank - 2) / 6);
    const center = {
      x: Math.cos(theta) * ring,
      y: Math.sin(theta) * ring * 0.62,
      z: (noise(String(clusterId)) - 0.5) * 110,
    };
    [...group].sort((a, b) => b.txCount - a.txCount).forEach((node, index) => {
      const localTheta = index * 2.399963229728653 + noise(node.id) * 0.7;
      const localRadius = index === 0 ? 0 : 26 + 23 * Math.sqrt(index);
      positioned.push({
        ...node,
        x: center.x + Math.cos(localTheta) * localRadius,
        y: center.y + Math.sin(localTheta) * localRadius,
        z: center.z + (noise(`${node.id}:z`) - 0.5) * 95,
        depth: depth.get(node.id) ?? 1,
        clusterId,
        clusterRank,
        isRoot: false,
      });
    });
  }

  if (!rootNode && positioned.length === 0) {
    [...nodes.values()].forEach((node, index) => {
      const theta = index * 2.399963229728653;
      const radius = 55 + 32 * Math.sqrt(index + 1);
      positioned.push({ ...node, x: Math.cos(theta) * radius, y: Math.sin(theta) * radius, z: 0, depth: 1, clusterId: index, clusterRank: index, isRoot: false });
    });
  }

  return { nodes: positioned, edges: [...edges.values()], adjacency, root: rootId };
}

function nodeMetric(node) {
  return Math.log10(1 + node.txCount * 2 + node.counterparties.size * 3);
}

function nodeRadius(node, minMetric, maxMetric) {
  const range = Math.max(0.001, maxMetric - minMetric);
  const normalized = (nodeMetric(node) - minMetric) / range;
  return node.isRoot ? 19 : 8 + normalized * 13;
}

function nodeColor(node) {
  if (node.isRoot) return '#22c98b';
  if (node.clusterRank >= 0 && node.clusterRank < PALETTE.length) return PALETTE[node.clusterRank];
  return MUTED;
}

function rotate(point, yaw, pitch, target) {
  const px = point.x - target.x;
  const py = point.y - target.y;
  const pz = point.z - target.z;
  const cosy = Math.cos(yaw);
  const siny = Math.sin(yaw);
  const x1 = px * cosy - pz * siny;
  const z1 = px * siny + pz * cosy;
  const cosp = Math.cos(pitch);
  const sinp = Math.sin(pitch);
  return { x: x1, y: py * cosp - z1 * sinp, z: py * sinp + z1 * cosp };
}

function project(point, width, height, camera) {
  const p = rotate(point, camera.yaw, camera.pitch, camera.target);
  const distance = 1080;
  const depth = Math.max(300, distance + p.z);
  const scale = distance / depth * camera.zoom;
  return { x: width / 2 + p.x * scale, y: height / 2 + p.y * scale, z: p.z, scale };
}

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const error = gl.getShaderInfoLog(shader) || 'Shader compile failed';
    gl.deleteShader(shader);
    throw new Error(error);
  }
  return shader;
}

function program(gl, vertexSource, fragmentSource) {
  const result = gl.createProgram();
  gl.attachShader(result, compile(gl, gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(result, compile(gl, gl.FRAGMENT_SHADER, fragmentSource));
  gl.linkProgram(result);
  if (!gl.getProgramParameter(result, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(result) || 'Program link failed');
  return result;
}

function initRenderer(gl) {
  const nodes = program(gl, `#version 300 es
    precision highp float;
    in vec2 a_position;
    in vec3 a_color;
    in float a_size;
    in float a_alpha;
    in float a_state;
    out vec3 v_color;
    out float v_alpha;
    out float v_state;
    void main(){
      gl_Position=vec4(a_position,0.0,1.0);
      gl_PointSize=a_size;
      v_color=a_color;
      v_alpha=a_alpha;
      v_state=a_state;
    }
  `, `#version 300 es
    precision highp float;
    in vec3 v_color;
    in float v_alpha;
    in float v_state;
    out vec4 outColor;
    void main(){
      vec2 p=gl_PointCoord*2.0-1.0;
      float r=length(p);
      if(r>1.0) discard;
      float z=sqrt(max(0.0,1.0-dot(p,p)));
      vec3 normal=normalize(vec3(p.x,-p.y,z));
      vec3 light=normalize(vec3(-0.45,0.62,0.82));
      float diffuse=max(dot(normal,light),0.0);
      float fresnel=pow(1.0-z,2.7);
      float gloss=pow(max(dot(normal,normalize(vec3(-0.55,0.65,0.95))),0.0),18.0);
      vec3 color=mix(v_color*0.14,v_color,0.28+0.72*diffuse);
      color+=v_color*fresnel*(0.42+0.4*v_state)+vec3(gloss)*0.68;
      float rim=smoothstep(0.74,0.99,r);
      color+=v_color*rim*(0.28+0.45*v_state);
      float alpha=v_alpha*smoothstep(1.0,0.88,r);
      outColor=vec4(color,alpha);
    }
  `);
  const edges = program(gl, `#version 300 es
    precision highp float;
    in vec2 a_position;
    in vec4 a_color;
    out vec4 v_color;
    void main(){gl_Position=vec4(a_position,0.0,1.0);v_color=a_color;}
  `, `#version 300 es
    precision highp float;
    in vec4 v_color;
    out vec4 outColor;
    void main(){outColor=v_color;}
  `);
  return { nodes, edges, nodeBuffer: gl.createBuffer(), edgeBuffer: gl.createBuffer() };
}

function assetRows(node) {
  const assets = new Set([...Object.keys(node.inByAsset), ...Object.keys(node.outByAsset)]);
  return [...assets].map(asset => ({ asset, incoming: node.inByAsset[asset] || 0, outgoing: node.outByAsset[asset] || 0 }));
}

function segmentDistance(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len = dx * dx + dy * dy || 1;
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / len, 0, 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export default function SuperBubbleGraph({ transactions = [], root, onSelect }) {
  const canvasRef = useRef(null);
  const frameRef = useRef(null);
  const dragRef = useRef(null);
  const hitRef = useRef({ nodes: [], edges: [] });
  const cameraRef = useRef({ yaw: -0.12, pitch: 0.08, zoom: 0.9, target: { x: 0, y: 0, z: 0 }, goalTarget: { x: 0, y: 0, z: 0 }, goalZoom: 0.9 });

  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const [query, setQuery] = useState('');
  const [minValue, setMinValue] = useState(0);
  const [maxDepth, setMaxDepth] = useState(3);
  const [mode, setMode] = useState('graph');
  const [showFlow, setShowFlow] = useState(true);
  const [addressList, setAddressList] = useState(false);
  const [listQuery, setListQuery] = useState('');
  const [rendererError, setRendererError] = useState('');

  const network = useMemo(() => buildNetwork(transactions, root), [transactions, root]);
  const metrics = useMemo(() => {
    const values = network.nodes.map(nodeMetric);
    return { min: Math.min(...values, 0), max: Math.max(...values, 1) };
  }, [network.nodes]);
  const nodeById = useMemo(() => new Map(network.nodes.map(node => [node.id, node])), [network.nodes]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const edges = network.edges.filter(edge => {
      if (edge.totalValue < Number(minValue || 0)) return false;
      if ((nodeById.get(edge.source)?.depth ?? 9) > maxDepth || (nodeById.get(edge.target)?.depth ?? 9) > maxDepth) return false;
      if (!q) return true;
      return edge.source.includes(q) || edge.target.includes(q) || edge.transactions.some(tx => String(tx.hash).toLowerCase().includes(q));
    });
    const visible = new Set();
    edges.forEach(edge => { visible.add(edge.source); visible.add(edge.target); });
    if (!q) network.nodes.filter(node => node.depth <= maxDepth).forEach(node => visible.add(node.id));
    return { nodes: network.nodes.filter(node => visible.has(node.id)), edges };
  }, [network, nodeById, query, minValue, maxDepth]);

  const selectedNode = selected?.kind === 'node' ? nodeById.get(selected.id) : null;
  const selectedEdge = selected?.kind === 'edge' ? network.edges.find(edge => edge.id === selected.id) : null;
  const connectedIds = useMemo(() => selectedNode ? new Set(network.adjacency.get(selectedNode.id) || []) : new Set(), [selectedNode, network.adjacency]);

  useEffect(() => {
    if (mode !== 'graph') return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: false, premultipliedAlpha: false });
    if (!gl) {
      setRendererError('WebGL2 is unavailable. Use the evidence table or enable hardware acceleration.');
      return undefined;
    }

    let resources;
    try {
      resources = initRenderer(gl);
      setRendererError('');
    } catch (error) {
      setRendererError(`GPU renderer initialization failed: ${error.message}`);
      return undefined;
    }

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    let running = true;

    const draw = time => {
      if (!running) return;
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      const pixelWidth = Math.floor(width * dpr);
      const pixelHeight = Math.floor(height * dpr);
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth;
        canvas.height = pixelHeight;
      }
      gl.viewport(0, 0, pixelWidth, pixelHeight);
      gl.clearColor(0.023, 0.035, 0.073, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);

      const camera = cameraRef.current;
      camera.target.x += (camera.goalTarget.x - camera.target.x) * 0.085;
      camera.target.y += (camera.goalTarget.y - camera.target.y) * 0.085;
      camera.target.z += (camera.goalTarget.z - camera.target.z) * 0.085;
      camera.zoom += (camera.goalZoom - camera.zoom) * 0.085;

      const projection = new Map();
      filtered.nodes.forEach(node => projection.set(node.id, project(node, width, height, camera)));

      const edgeData = [];
      const edgeHits = [];
      for (const edge of filtered.edges) {
        const a = projection.get(edge.source);
        const b = projection.get(edge.target);
        if (!a || !b) continue;
        const touches = selectedNode && (edge.source === selectedNode.id || edge.target === selectedNode.id);
        const active = selectedEdge?.id === edge.id;
        const dim = selectedNode && !touches;
        const source = nodeById.get(edge.source);
        const color = active ? [1, 1, 1] : rgb(touches && source ? nodeColor(source) : '#53627a');
        const alpha = active ? 0.96 : touches ? 0.72 : dim ? 0.035 : 0.14;
        edgeData.push(a.x / width * 2 - 1, 1 - a.y / height * 2, ...color, alpha);
        edgeData.push(b.x / width * 2 - 1, 1 - b.y / height * 2, ...color, alpha);
        edgeHits.push({ id: edge.id, ax: a.x, ay: a.y, bx: b.x, by: b.y });
      }

      gl.useProgram(resources.edges);
      gl.bindBuffer(gl.ARRAY_BUFFER, resources.edgeBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(edgeData), gl.DYNAMIC_DRAW);
      const edgeStride = 6 * 4;
      const edgePos = gl.getAttribLocation(resources.edges, 'a_position');
      const edgeColor = gl.getAttribLocation(resources.edges, 'a_color');
      gl.enableVertexAttribArray(edgePos);
      gl.vertexAttribPointer(edgePos, 2, gl.FLOAT, false, edgeStride, 0);
      gl.enableVertexAttribArray(edgeColor);
      gl.vertexAttribPointer(edgeColor, 4, gl.FLOAT, false, edgeStride, 2 * 4);
      gl.drawArrays(gl.LINES, 0, edgeData.length / 6);

      const ordered = [...filtered.nodes].sort((a, b) => (projection.get(a.id)?.z || 0) - (projection.get(b.id)?.z || 0));
      const nodeData = [];
      const nodeHits = [];
      for (const node of ordered) {
        const p = projection.get(node.id);
        if (!p) continue;
        const isSelected = selectedNode?.id === node.id;
        const isHovered = hovered?.kind === 'node' && hovered.id === node.id;
        const connected = selectedNode ? connectedIds.has(node.id) : false;
        const dim = selectedNode && !isSelected && !connected;
        const base = clamp(nodeRadius(node, metrics.min, metrics.max) * 2 * p.scale, 8, node.isRoot ? 76 : 58);
        const size = base * (isSelected ? 1.22 : isHovered ? 1.08 : 1);
        const color = rgb(nodeColor(node));
        const alpha = dim ? 0.14 : nodeColor(node) === MUTED ? 0.44 : isSelected || isHovered ? 1 : 0.88;
        const state = isSelected ? 1 : isHovered ? 0.72 : connected ? 0.4 : 0;
        nodeData.push(p.x / width * 2 - 1, 1 - p.y / height * 2, ...color, size * dpr, alpha, state);
        nodeHits.push({ id: node.id, x: p.x, y: p.y, r: size / 2 + 7 });
      }

      gl.useProgram(resources.nodes);
      gl.bindBuffer(gl.ARRAY_BUFFER, resources.nodeBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(nodeData), gl.DYNAMIC_DRAW);
      const stride = 8 * 4;
      const positionLoc = gl.getAttribLocation(resources.nodes, 'a_position');
      const colorLoc = gl.getAttribLocation(resources.nodes, 'a_color');
      const sizeLoc = gl.getAttribLocation(resources.nodes, 'a_size');
      const alphaLoc = gl.getAttribLocation(resources.nodes, 'a_alpha');
      const stateLoc = gl.getAttribLocation(resources.nodes, 'a_state');
      gl.enableVertexAttribArray(positionLoc); gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, stride, 0);
      gl.enableVertexAttribArray(colorLoc); gl.vertexAttribPointer(colorLoc, 3, gl.FLOAT, false, stride, 2 * 4);
      gl.enableVertexAttribArray(sizeLoc); gl.vertexAttribPointer(sizeLoc, 1, gl.FLOAT, false, stride, 5 * 4);
      gl.enableVertexAttribArray(alphaLoc); gl.vertexAttribPointer(alphaLoc, 1, gl.FLOAT, false, stride, 6 * 4);
      gl.enableVertexAttribArray(stateLoc); gl.vertexAttribPointer(stateLoc, 1, gl.FLOAT, false, stride, 7 * 4);
      gl.drawArrays(gl.POINTS, 0, nodeData.length / 8);

      if (showFlow) {
        const particles = [];
        filtered.edges.forEach((edge, index) => {
          const a = projection.get(edge.source);
          const b = projection.get(edge.target);
          if (!a || !b) return;
          if (selectedNode && edge.source !== selectedNode.id && edge.target !== selectedNode.id) return;
          const phase = (time * 0.00011 + index * 0.173) % 1;
          const x = a.x + (b.x - a.x) * phase;
          const y = a.y + (b.y - a.y) * phase;
          particles.push(x / width * 2 - 1, 1 - y / height * 2, 0.05, 0.85, 0.96, 5 * dpr, selectedNode ? 0.95 : 0.48, 0.7);
        });
        if (particles.length) {
          gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(particles), gl.DYNAMIC_DRAW);
          gl.drawArrays(gl.POINTS, 0, particles.length / 8);
        }
      }

      hitRef.current = { nodes: nodeHits, edges: edgeHits };
      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => {
      running = false;
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      gl.deleteProgram(resources.nodes);
      gl.deleteProgram(resources.edges);
      gl.deleteBuffer(resources.nodeBuffer);
      gl.deleteBuffer(resources.edgeBuffer);
    };
  }, [filtered, nodeById, selectedNode, selectedEdge, connectedIds, hovered, metrics, showFlow, mode]);

  const pointer = event => {
    const rect = canvasRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const hitAt = event => {
    const p = pointer(event);
    const node = [...hitRef.current.nodes].reverse().find(hit => Math.hypot(p.x - hit.x, p.y - hit.y) <= hit.r);
    if (node) return { kind: 'node', id: node.id };
    const edge = [...hitRef.current.edges].reverse().find(hit => segmentDistance(p.x, p.y, hit.ax, hit.ay, hit.bx, hit.by) <= 6);
    return edge ? { kind: 'edge', id: edge.id } : null;
  };

  const focusNode = (node, zoom = 1.55) => {
    const camera = cameraRef.current;
    camera.goalTarget = { x: node.x, y: node.y, z: node.z };
    camera.goalZoom = clamp(zoom, 0.32, 3.2);
  };

  const selectNode = id => {
    const node = nodeById.get(id);
    if (!node) return;
    setSelected({ kind: 'node', id });
    focusNode(node);
    setTooltip(null);
  };

  const onPointerDown = event => {
    const hit = hitAt(event);
    if (hit) {
      if (hit.kind === 'node') selectNode(hit.id);
      else setSelected(hit);
      return;
    }
    setSelected(null);
    dragRef.current = { x: event.clientX, y: event.clientY, yaw: cameraRef.current.yaw, pitch: cameraRef.current.pitch };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const onPointerMove = event => {
    if (dragRef.current) {
      cameraRef.current.yaw = dragRef.current.yaw + (event.clientX - dragRef.current.x) * 0.006;
      cameraRef.current.pitch = clamp(dragRef.current.pitch + (event.clientY - dragRef.current.y) * 0.005, -0.92, 0.92);
      return;
    }
    const hit = hitAt(event);
    setHovered(hit);
    setTooltip(hit?.kind === 'node' ? { x: event.clientX, y: event.clientY, node: nodeById.get(hit.id) } : null);
  };

  const resetView = () => {
    const camera = cameraRef.current;
    camera.goalTarget = { x: 0, y: 0, z: 0 };
    camera.goalZoom = 0.9;
    camera.yaw = -0.12;
    camera.pitch = 0.08;
    setSelected(null);
  };

  const searchGraph = event => {
    event.preventDefault();
    const q = query.trim().toLowerCase();
    if (!q) return;
    const match = network.nodes.find(node => node.id === q) || network.nodes.find(node => node.id.includes(q));
    if (match) selectNode(match.id);
  };

  const toggleFullscreen = async () => {
    const element = canvasRef.current?.closest('section');
    if (!element) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await element.requestFullscreen?.();
  };

  const list = filtered.nodes
    .filter(node => !listQuery || node.id.includes(listQuery.toLowerCase()))
    .sort((a, b) => b.txCount - a.txCount || b.counterparties.size - a.counterparties.size);

  return <section className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#060913] shadow-2xl shadow-black/40">
    <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#080b14] px-4 py-3">
      <div><p className="text-[10px] font-semibold uppercase tracking-[.26em] text-slate-500">3D flow intelligence</p><h3 className="mt-1 text-sm font-semibold text-slate-100">Wallet network investigation</h3></div>
      <div className="flex items-center gap-2"><span className="hidden text-[11px] text-slate-500 sm:inline">{filtered.nodes.length} wallets · {filtered.edges.length} relationships</span><button type="button" onClick={() => setAddressList(value => !value)} className="rounded-lg border border-white/[0.08] bg-[#11141d] px-3 py-2 text-xs text-slate-300">Address List</button><button type="button" onClick={toggleFullscreen} className="rounded-lg border border-white/[0.08] bg-[#11141d] px-3 py-2 text-xs text-slate-300">Fullscreen</button></div>
    </div>

    <div className="relative min-h-[720px] bg-[#060913]">
      <div className="absolute left-3 top-3 z-20 max-w-[calc(100%-24px)] rounded-xl border border-white/[0.08] bg-[#11141d]/95 p-2 shadow-2xl backdrop-blur-xl">
        <div className="flex flex-wrap items-center gap-2">
          <div className="rounded-lg border border-cyan-400/15 bg-cyan-400/[0.04] px-3 py-2"><p className="text-[9px] uppercase tracking-[.2em] text-slate-500">Ethereum</p><p className="font-mono text-[11px] text-cyan-300">{root ? short(root) : 'Loaded evidence'}</p></div>
          <form onSubmit={searchGraph} className="flex gap-2"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Address or tx hash" className="h-9 w-48 rounded-lg border border-slate-700 bg-[#0b0e17] px-3 font-mono text-[11px] text-slate-200 outline-none" /><button className="rounded-lg border border-slate-700 bg-[#151821] px-3 text-xs text-slate-300">Find</button></form>
          <input type="number" min="0" step="0.01" value={minValue} onChange={event => setMinValue(event.target.value)} title="Minimum observed transfer value" className="h-9 w-24 rounded-lg border border-slate-700 bg-[#0b0e17] px-3 text-[11px] text-slate-200 outline-none" />
          <select value={maxDepth} onChange={event => setMaxDepth(Number(event.target.value))} className="h-9 rounded-lg border border-slate-700 bg-[#0b0e17] px-2 text-[11px] text-slate-200"><option value={1}>1 hop</option><option value={2}>2 hops</option><option value={3}>3 hops</option><option value={9}>All loaded</option></select>
          <button type="button" onClick={resetView} className="h-9 rounded-lg border border-slate-700 bg-[#151821] px-3 text-xs text-slate-300">Reset</button>
          <button type="button" onClick={() => { const camera = cameraRef.current; camera.goalZoom = clamp(camera.goalZoom * 1.2, 0.32, 3.2); }} className="h-9 rounded-lg border border-slate-700 bg-[#151821] px-3 text-sm text-slate-300">+</button>
          <button type="button" onClick={() => { const camera = cameraRef.current; camera.goalZoom = clamp(camera.goalZoom * 0.82, 0.32, 3.2); }} className="h-9 rounded-lg border border-slate-700 bg-[#151821] px-3 text-sm text-slate-300">−</button>
          <button type="button" onClick={() => setShowFlow(value => !value)} className="h-9 rounded-lg border border-slate-700 bg-[#151821] px-3 text-xs text-slate-300">Flow {showFlow ? 'on' : 'off'}</button>
          <button type="button" onClick={() => setMode(mode === 'graph' ? 'table' : 'graph')} className="h-9 rounded-lg border border-slate-700 bg-[#151821] px-3 text-xs text-slate-300">{mode === 'graph' ? 'Table' : '3D'}</button>
        </div>
      </div>

      {mode === 'graph' ? <>
        <canvas ref={canvasRef} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => { dragRef.current = null; }} onPointerCancel={() => { dragRef.current = null; }} onPointerLeave={() => { setHovered(null); setTooltip(null); }} onDoubleClick={event => { const hit = hitAt(event); if (hit?.kind === 'node') { const node = nodeById.get(hit.id); if (node) focusNode(node, 2.1); } }} onWheel={event => { event.preventDefault(); const camera = cameraRef.current; camera.goalZoom = clamp(camera.goalZoom * (event.deltaY < 0 ? 1.12 : 0.89), 0.32, 3.2); }} className="h-[720px] w-full touch-none cursor-grab active:cursor-grabbing" />
        {rendererError && <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#060913] p-8 text-center text-sm text-rose-300">{rendererError}</div>}
        {!filtered.nodes.length && !rendererError && <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500">No loaded evidence matches these filters.</div>}
        {tooltip?.node && <div className="pointer-events-none fixed z-[80] -translate-y-full rounded-lg border border-white/[0.08] bg-[#11131a]/95 px-3 py-2 shadow-xl backdrop-blur" style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}><p className="font-mono text-[11px] text-slate-100">{short(tooltip.node.id)}</p><p className="mt-1 text-[10px] text-slate-400">{tooltip.node.txCount} observed transfers · {tooltip.node.counterparties.size} counterparties</p></div>}

        {selectedNode && <div className="absolute left-4 top-24 z-20 w-[340px] max-w-[calc(100%-32px)] rounded-xl border border-white/[0.09] bg-[#11131a]/95 p-4 shadow-2xl backdrop-blur-xl">
          <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] uppercase tracking-[.22em] text-slate-500">Wallet #{Math.max(1, selectedNode.clusterRank + 1)}</p><p className="mt-1 break-all font-mono text-xs text-slate-100">{selectedNode.id}</p></div><button type="button" onClick={() => setSelected(null)} className="text-slate-500 hover:text-white">×</button></div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center"><div className="rounded-lg border border-white/[0.06] bg-[#0b0e17] p-2"><p className="text-lg font-semibold text-white">{selectedNode.txCount}</p><p className="text-[10px] text-slate-500">Transfers</p></div><div className="rounded-lg border border-white/[0.06] bg-[#0b0e17] p-2"><p className="text-lg font-semibold text-white">{selectedNode.counterparties.size}</p><p className="text-[10px] text-slate-500">Addresses</p></div><div className="rounded-lg border border-white/[0.06] bg-[#0b0e17] p-2"><p className="text-lg font-semibold text-white">{selectedNode.depth}</p><p className="text-[10px] text-slate-500">Hop</p></div></div>
          <div className="mt-3 rounded-lg border border-amber-400/10 bg-amber-400/[0.025] p-3 text-[11px] text-amber-200/80"><span className="font-medium">Balance:</span> not loaded by the current graph API. No value is invented.</div>
          <div className="mt-3 space-y-2">{assetRows(selectedNode).slice(0, 4).map(row => <div key={row.asset} className="rounded-lg border border-white/[0.06] bg-[#0b0e17] px-3 py-2 text-xs"><div className="flex items-center justify-between"><span className="font-medium text-slate-200">{row.asset}</span><span className="text-slate-500">observed</span></div><div className="mt-1 flex justify-between text-[11px] text-slate-400"><span>IN {row.incoming.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span><span>OUT {row.outgoing.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span></div></div>)}</div>
          <div className="mt-3 flex items-center justify-between text-xs"><span className="text-slate-500">Highest loaded risk</span><span className="text-slate-200">{selectedNode.maxRisk == null ? 'Not assessed' : selectedNode.maxRisk}</span></div>
          <a href={`https://etherscan.io/address/${selectedNode.id}`} target="_blank" rel="noreferrer" className="mt-4 inline-flex rounded-lg border border-cyan-400/20 bg-cyan-400/[0.05] px-3 py-2 text-xs text-cyan-300">View address evidence ↗</a>
        </div>}

        {selectedEdge && <div className="absolute left-4 top-24 z-20 w-[340px] max-w-[calc(100%-32px)] rounded-xl border border-white/[0.09] bg-[#11131a]/95 p-4 shadow-2xl backdrop-blur-xl">
          <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] uppercase tracking-[.22em] text-slate-500">Observed relationship</p><p className="mt-1 font-mono text-xs text-slate-100">{short(selectedEdge.source)} → {short(selectedEdge.target)}</p></div><button type="button" onClick={() => setSelected(null)} className="text-slate-500 hover:text-white">×</button></div>
          <div className="mt-4 rounded-lg border border-white/[0.06] bg-[#0b0e17] p-3"><p className="text-[10px] uppercase tracking-wider text-slate-500">Loaded aggregate</p><p className="mt-1 text-xl font-semibold text-white">{selectedEdge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedEdge.asset}</p><p className="mt-1 text-[11px] text-slate-500">{selectedEdge.txCount} evidence transaction{selectedEdge.txCount === 1 ? '' : 's'}</p></div>
          <div className="mt-3 max-h-44 space-y-1 overflow-auto">{selectedEdge.transactions.map(tx => <button key={`${tx.hash}-${tx.category}-${tx.value}`} type="button" onClick={() => onSelect?.(tx)} className="w-full rounded-lg border border-white/[0.05] bg-[#0b0e17] px-3 py-2 text-left hover:border-cyan-400/20"><span className="font-mono text-[11px] text-cyan-300">{short(tx.hash)}</span><span className="mt-1 block text-[10px] text-slate-500">{tx.value} {tx.asset || ''} · {tx.category || 'transfer'}</span></button>)}</div>
        </div>}
        <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-white/[0.08] bg-[#0b0e17]/90 px-3 py-2 text-[11px] text-slate-500">Drag to orbit · wheel to zoom · click wallet · double-click to focus</div>
      </> : <div className="max-h-[720px] overflow-auto pt-20"><table className="min-w-full text-left text-xs"><thead className="sticky top-0 border-y border-slate-800 bg-[#080b14] text-slate-500"><tr><th className="px-4 py-3">From</th><th className="px-4 py-3">To</th><th className="px-4 py-3">Observed value</th><th className="px-4 py-3">Tx count</th><th className="px-4 py-3">Evidence</th></tr></thead><tbody>{filtered.edges.map(edge => <tr key={edge.id} className="border-b border-slate-900 text-slate-300"><td className="px-4 py-3 font-mono">{short(edge.source)}</td><td className="px-4 py-3 font-mono">{short(edge.target)}</td><td className="px-4 py-3">{edge.totalValue.toLocaleString(undefined, { maximumFractionDigits: 8 })} {edge.asset}</td><td className="px-4 py-3">{edge.txCount}</td><td className="px-4 py-3"><button type="button" onClick={() => { setSelected({ kind: 'edge', id: edge.id }); setMode('graph'); }} className="text-cyan-300 hover:underline">Inspect</button></td></tr>)}</tbody></table></div>}

      {addressList && <div className="absolute right-3 top-16 z-30 w-[360px] max-w-[calc(100%-24px)] rounded-xl border border-white/[0.09] bg-[#11131a]/97 p-3 shadow-2xl backdrop-blur-xl"><div className="flex items-center justify-between"><div><p className="text-[10px] uppercase tracking-[.22em] text-slate-500">Address List</p><p className="mt-1 text-xs text-slate-300">Loaded evidence only</p></div><button type="button" onClick={() => setAddressList(false)} className="text-slate-500 hover:text-white">×</button></div><input value={listQuery} onChange={event => setListQuery(event.target.value)} placeholder="Filter address" className="mt-3 h-9 w-full rounded-lg border border-slate-700 bg-[#0b0e17] px-3 font-mono text-[11px] text-slate-200 outline-none" /><div className="mt-3 max-h-[480px] space-y-1 overflow-auto pr-1">{list.map(node => <button key={node.id} type="button" onClick={() => { selectNode(node.id); setAddressList(false); }} className="w-full rounded-lg border border-transparent bg-[#0b0e17] px-3 py-2 text-left hover:border-cyan-400/20"><div className="flex items-center justify-between gap-2"><span className="font-mono text-[11px] text-slate-200">{short(node.id)}</span><span className="text-[10px] text-slate-500">{node.txCount} tx</span></div><div className="mt-1 flex items-center justify-between text-[10px] text-slate-600"><span>Cluster {node.clusterRank + 1}</span><span>{node.counterparties.size} links</span></div></button>)}</div></div>}
    </div>

    <div className="border-t border-amber-500/10 bg-amber-400/[0.025] px-4 py-3 text-[11px] leading-5 text-amber-200/75">Observed loaded ChainScope evidence only. Bubble size uses loaded activity and connectivity with logarithmic scaling. Cluster placement visualizes observed graph structure; it does not prove common ownership, intent, or complete fund provenance.</div>
  </section>;
}
