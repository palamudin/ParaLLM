(() => {
    if (!document.getElementById("graphCanvas")) {
      return;
    }

    const palette = [
      "#3be0d2", "#8ab4ff", "#ffe082", "#ff9fbc", "#9ff0b8", "#c792ea",
      "#f4b46c", "#90dbf4", "#e9c46a", "#a8dadc", "#d0ff8f", "#ffb4a2"
    ];

    const state = {
      graph: null,
      nodes: [],
      edges: [],
      nodeById: new Map(),
      visibleNodes: [],
      visibleEdges: [],
      selectedId: "",
      hoveredId: "",
      query: "",
      minDegree: 0,
      maxVisible: 850,
      showOrphans: false,
      showLabels: true,
      paused: false,
      scale: 1,
      panX: 0,
      panY: 0,
      draggingNode: null,
      panning: false,
      lastPointer: { x: 0, y: 0 },
      layoutEnergy: 0,
      needsDraw: true,
      frame: 0,
      fpsLastTime: performance.now(),
      fpsFrames: 0,
      fps: 0,
      started: false,
      panels: {
        lens: false,
        inspect: false,
      },
      panelFocus: ""
    };

    const els = {
      root: document.querySelector(".repo-review-root"),
      status: document.getElementById("status"),
      searchInput: document.getElementById("searchInput"),
      minDegreeRange: document.getElementById("minDegreeRange"),
      minDegreeValue: document.getElementById("minDegreeValue"),
      maxVisibleInput: document.getElementById("maxVisibleInput"),
      showOrphansInput: document.getElementById("showOrphansInput"),
      labelsInput: document.getElementById("labelsInput"),
      ambiguousInput: document.getElementById("ambiguousInput"),
      refreshBtn: document.getElementById("refreshBtn"),
      copyAiBtn: document.getElementById("copyAiBtn"),
      exportBtn: document.getElementById("exportBtn"),
      fitBtn: document.getElementById("fitBtn"),
      pauseBtn: document.getElementById("pauseBtn"),
      canvas: document.getElementById("graphCanvas"),
      stage: document.getElementById("stage"),
      emptyState: document.getElementById("emptyState"),
      hotspotList: document.getElementById("hotspotList"),
      selectedPanel: document.getElementById("selectedPanel"),
      aiPacket: document.getElementById("aiPacket"),
      mFiles: document.getElementById("mFiles"),
      mFunctions: document.getElementById("mFunctions"),
      mEdges: document.getElementById("mEdges"),
      mVisible: document.getElementById("mVisible"),
      visibleNodeCount: document.getElementById("visibleNodeCount"),
      visibleEdgeCount: document.getElementById("visibleEdgeCount"),
      zoomValue: document.getElementById("zoomValue"),
      fpsValue: document.getElementById("fpsValue"),
      panelToggles: Array.from(document.querySelectorAll("[data-repo-toggle]"))
    };

    if (!els.canvas || !els.stage) {
      return;
    }

    const renderPixelRatio = Math.min(window.devicePixelRatio || 1, 1.25);
    const ctx = els.canvas.getContext("2d", { alpha: false });
    let activeWindowDrag = null;

    init();

    function init() {
      bindEvents();
      tryStart();
    }

    function bindEvents() {
      installWorkbenchWindows();
      if (els.refreshBtn) els.refreshBtn.addEventListener("click", fetchGraph);
      if (els.copyAiBtn) els.copyAiBtn.addEventListener("click", copyAiPacket);
      if (els.exportBtn) els.exportBtn.addEventListener("click", exportJson);
      els.fitBtn.addEventListener("click", fitGraph);
      els.pauseBtn.addEventListener("click", () => {
        state.paused = !state.paused;
        els.pauseBtn.textContent = state.paused ? "Resume" : "Pause";
        requestDraw();
      });
      els.panelToggles.forEach((button) => {
        button.addEventListener("click", () => {
          const key = button.getAttribute("data-repo-toggle");
          togglePanel(key);
        });
      });
      bindDrawerExpansion();
      els.searchInput.addEventListener("input", debounce(() => {
        state.query = els.searchInput.value.trim().toLowerCase();
        rebuildVisibleGraph(false);
      }, 120));
      els.minDegreeRange.addEventListener("input", () => {
        state.minDegree = Number(els.minDegreeRange.value || 0);
        els.minDegreeValue.textContent = String(state.minDegree);
        rebuildVisibleGraph(false);
      });
      els.maxVisibleInput.addEventListener("change", () => {
        state.maxVisible = clamp(Number(els.maxVisibleInput.value || 850), 40, 2400);
        els.maxVisibleInput.value = String(state.maxVisible);
        rebuildVisibleGraph(false);
      });
      els.showOrphansInput.addEventListener("change", () => {
        state.showOrphans = els.showOrphansInput.checked;
        rebuildVisibleGraph(false);
      });
      els.labelsInput.addEventListener("change", () => {
        state.showLabels = els.labelsInput.checked;
        draw();
      });
      els.canvas.addEventListener("wheel", onWheel, { passive: false });
      els.canvas.addEventListener("pointerdown", onPointerDown);
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
      window.addEventListener("pointermove", onWorkbenchWindowMove);
      window.addEventListener("pointerup", endWorkbenchWindowDrag);
      els.canvas.addEventListener("dblclick", fitGraph);
      window.addEventListener("resize", resizeCanvas);
      window.addEventListener("repo-review:layout", () => {
        if (tryStart()) {
          return;
        }
        resizeCanvas();
        if (state.visibleNodes.length) {
          fitGraph();
        }
        requestDraw();
      });
      if (typeof ResizeObserver !== "undefined") {
        const observer = new ResizeObserver(() => {
        if (tryStart()) {
          return;
        }
        resizeCanvas();
        updateWorkbenchBounds();
        requestDraw();
      });
      observer.observe(els.stage);
      els.root.querySelectorAll("[data-repo-panel]").forEach((panel) => observer.observe(panel));
    }
      applyPanelVisibility(false);
    }

    function tryStart() {
      if (state.started || !stageHasViewport()) {
        return false;
      }
      state.started = true;
      resizeCanvas();
      fetchGraph();
      requestAnimationFrame(loop);
      return true;
    }

    function stageHasViewport() {
      const rect = els.stage.getBoundingClientRect();
      return rect.width > 40 && rect.height > 40;
    }

    async function fetchGraph() {
      setStatus("Scanning repo root through /v1/repo/graph...");
      els.emptyState.hidden = false;
      try {
        const params = new URLSearchParams({
          maxNodes: "2400",
          includeAmbiguous: els.ambiguousInput.checked ? "true" : "false"
        });
        const response = await fetch(`/v1/repo/graph?${params.toString()}`, { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const graph = await response.json();
        hydrateGraph(graph);
        setStatus(`Loaded ${fmt(graph.stats.nodesReturned)} returned nodes from ${fmt(graph.stats.filesScanned)} files. ${graph.truncated ? "Graph is capped for speed." : "Full graph returned."}`);
      } catch (error) {
        setStatus(`Graph load failed: ${error.message || error}. Open this page through the Python backend, not as a file:// document.`);
        els.emptyState.textContent = "Graph load failed.";
      }
    }

    function hydrateGraph(graph) {
      state.graph = graph;
      state.selectedId = "";
      state.hoveredId = "";
      state.nodeById = new Map();
      state.nodes = (graph.nodes || []).map((node, index) => {
        const hydrated = {
          ...node,
          index,
          x: 0,
          y: 0,
          vx: 0,
          vy: 0,
          r: 4.5 + Math.sqrt(Number(node.degree || 0) + 1) * 1.8,
          color: colorForModule(node.module || node.file || ""),
          cluster: node.module || ".",
          visible: false,
          pinned: false
        };
        state.nodeById.set(hydrated.id, hydrated);
        return hydrated;
      });
      state.edges = (graph.edges || []).map(edge => ({
        ...edge,
        source: state.nodeById.get(edge.sourceId),
        target: state.nodeById.get(edge.targetId),
        weight: Number(edge.weight || 1)
      })).filter(edge => edge.source && edge.target);
      renderMetrics();
      renderAiPacket();
      renderHotspots();
      rebuildVisibleGraph(true);
      setTimeout(fitGraph, 80);
      requestDraw();
    }

    function rebuildVisibleGraph(resetPositions) {
      const query = state.query;
      const matches = new Set();
      const selectedNeighbors = new Set();
      if (state.selectedId) {
        selectedNeighbors.add(state.selectedId);
        const selected = state.nodeById.get(state.selectedId);
        if (selected) {
          (selected.callers || []).forEach(id => selectedNeighbors.add(id));
          (selected.callees || []).forEach(id => selectedNeighbors.add(id));
        }
      }

      for (const node of state.nodes) {
        const searchable = `${node.name} ${node.file} ${node.module} ${node.lang} ${node.type} ${node.signature}`.toLowerCase();
        const isMatch = !query || searchable.includes(query);
        if (isMatch) matches.add(node.id);
      }

      let visible = state.nodes.filter(node => {
        if (!state.showOrphans && Number(node.degree || 0) === 0 && !matches.has(node.id)) return false;
        if (Number(node.degree || 0) < state.minDegree && !matches.has(node.id) && !selectedNeighbors.has(node.id)) return false;
        return matches.has(node.id) || selectedNeighbors.has(node.id) || !query;
      });

      visible.sort((a, b) => {
        const am = matches.has(a.id) ? 1 : 0;
        const bm = matches.has(b.id) ? 1 : 0;
        const as = selectedNeighbors.has(a.id) ? 1 : 0;
        const bs = selectedNeighbors.has(b.id) ? 1 : 0;
        return bs - as || bm - am || Number(b.degree || 0) - Number(a.degree || 0) || String(a.file).localeCompare(String(b.file));
      });
      visible = visible.slice(0, state.maxVisible);

      const visibleIds = new Set(visible.map(node => node.id));
      state.visibleNodes = visible;
      state.visibleEdges = state.edges.filter(edge => visibleIds.has(edge.sourceId) && visibleIds.has(edge.targetId));
      for (const node of state.nodes) node.visible = visibleIds.has(node.id);
      if (resetPositions || visible.some(node => !Number.isFinite(node.x) || (node.x === 0 && node.y === 0))) seedLayout();
      state.layoutEnergy = Math.max(state.layoutEnergy, 1);
      renderMetrics();
      renderSelectedPanel();
      renderHotspots();
      els.emptyState.hidden = state.visibleNodes.length > 0;
      requestDraw();
    }

    function seedLayout() {
      const modules = [...new Set(state.visibleNodes.map(node => node.cluster))].sort();
      const centers = new Map();
      const outer = Math.max(180, Math.sqrt(state.visibleNodes.length) * 54);
      modules.forEach((module, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(1, modules.length);
        centers.set(module, { x: Math.cos(angle) * outer, y: Math.sin(angle) * outer });
      });
      const counts = new Map();
      for (const node of state.visibleNodes) {
        const count = counts.get(node.cluster) || 0;
        counts.set(node.cluster, count + 1);
        const center = centers.get(node.cluster) || { x: 0, y: 0 };
        const angle = count * 2.399963;
        const radius = 18 + Math.sqrt(count + 1) * 18;
        node.x = center.x + Math.cos(angle) * radius;
        node.y = center.y + Math.sin(angle) * radius;
        node.vx = 0;
        node.vy = 0;
      }
    }

    function loop(now) {
      let rendered = false;
      if (!state.paused && state.visibleNodes.length && state.layoutEnergy > 0.012) {
        simulate();
        state.layoutEnergy *= 0.986;
        state.needsDraw = true;
      }
      if (state.needsDraw) {
        draw();
        state.needsDraw = false;
        rendered = true;
      }
      updateFps(now, rendered);
      requestAnimationFrame(loop);
    }

    function simulate() {
      const nodes = state.visibleNodes;
      const edges = state.visibleEdges;
      const cellSize = 84;
      const grid = new Map();
      for (const node of nodes) {
        const key = gridKey(node.x, node.y, cellSize);
        if (!grid.has(key)) grid.set(key, []);
        grid.get(key).push(node);
      }

      for (const node of nodes) {
        const cx = Math.floor(node.x / cellSize);
        const cy = Math.floor(node.y / cellSize);
        for (let gx = cx - 1; gx <= cx + 1; gx++) {
          for (let gy = cy - 1; gy <= cy + 1; gy++) {
            const bucket = grid.get(`${gx}:${gy}`);
            if (!bucket) continue;
            for (const other of bucket) {
              if (other.index <= node.index) continue;
              let dx = node.x - other.x;
              let dy = node.y - other.y;
              let dist2 = dx * dx + dy * dy;
              if (dist2 < 0.01) {
                dx = 0.1 + Math.random() * 0.1;
                dy = 0.1 + Math.random() * 0.1;
                dist2 = dx * dx + dy * dy;
              }
              if (dist2 > 12000) continue;
              const force = 1600 / Math.max(80, dist2);
              const fx = dx * force;
              const fy = dy * force;
              if (!node.pinned) { node.vx += fx; node.vy += fy; }
              if (!other.pinned) { other.vx -= fx; other.vy -= fy; }
            }
          }
        }
      }

      const edgeLimit = simulationEdgeLimit(edges.length, nodes.length);
      for (let index = 0; index < edgeLimit; index++) {
        const edge = edges[index];
        const a = edge.source;
        const b = edge.target;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(1, Math.hypot(dx, dy));
        const desired = 70 + Math.min(80, (a.r + b.r) * 2.2);
        const strength = 0.004 + Math.min(edge.weight, 6) * 0.0008;
        const force = (dist - desired) * strength;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        if (!a.pinned) { a.vx += fx; a.vy += fy; }
        if (!b.pinned) { b.vx -= fx; b.vy -= fy; }
      }

      for (const node of nodes) {
        if (node.pinned) continue;
        const center = clusterCenter(node.cluster);
        node.vx += (center.x - node.x) * 0.00035;
        node.vy += (center.y - node.y) * 0.00035;
        node.vx += -node.x * 0.00012;
        node.vy += -node.y * 0.00012;
        node.vx *= 0.84;
        node.vy *= 0.84;
        node.x += clamp(node.vx, -7, 7);
        node.y += clamp(node.vy, -7, 7);
      }
    }

    function draw() {
      const canvas = els.canvas;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = "#030c0f";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      ctx.scale(renderPixelRatio, renderPixelRatio);
      drawGrid(w, h);
      ctx.translate(w / 2 + state.panX, h / 2 + state.panY);
      ctx.scale(state.scale, state.scale);
      const selected = state.selectedId ? state.nodeById.get(state.selectedId) : null;
      const hover = state.hoveredId ? state.nodeById.get(state.hoveredId) : null;
      const highlight = relatedIds(selected);
      drawEdges(selected, hover, highlight);
      drawNodes(selected, hover, highlight);
      ctx.restore();
      els.zoomValue.textContent = `${Math.round(state.scale * 100)}%`;
    }

    function drawGrid(w, h) {
      const grid = 36 * state.scale;
      if (state.visibleNodes.length > 650) return;
      if (grid < 14) return;
      const ox = (w / 2 + state.panX) % grid;
      const oy = (h / 2 + state.panY) % grid;
      ctx.save();
      ctx.strokeStyle = "rgba(128,232,218,0.035)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = ox; x < w; x += grid) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
      for (let y = oy; y < h; y += grid) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
      ctx.stroke();
      ctx.restore();
    }

    function drawEdges(selected, hover, highlight) {
      const edges = state.visibleEdges;
      const selectedMode = Boolean(selected);
      const drawLimit = selectedMode ? edges.length : edgeDrawLimit(edges.length, state.visibleNodes.length, state.fps);
      ctx.save();
      ctx.lineCap = "round";
      for (let index = 0; index < drawLimit; index++) {
        const edge = edges[index];
        const active = selected && (edge.sourceId === selected.id || edge.targetId === selected.id);
        const hot = hover && (edge.sourceId === hover.id || edge.targetId === hover.id);
        if (selectedMode && !active) continue;
        const alpha = active ? 0.78 : hot ? 0.48 : 0.16;
        ctx.strokeStyle = edge.ambiguous ? `rgba(255,224,130,${alpha})` : `rgba(128,232,218,${alpha})`;
        ctx.lineWidth = (active ? 2.4 : Math.min(2.2, 0.7 + Math.log2(edge.weight + 1) * 0.25)) / state.scale;
        ctx.beginPath();
        ctx.moveTo(edge.source.x, edge.source.y);
        const mx = (edge.source.x + edge.target.x) / 2;
        const my = (edge.source.y + edge.target.y) / 2;
        const dx = edge.target.x - edge.source.x;
        const dy = edge.target.y - edge.source.y;
        const len = Math.max(1, Math.hypot(dx, dy));
        const curve = Math.min(28, len * 0.06);
        ctx.quadraticCurveTo(mx - (dy / len) * curve, my + (dx / len) * curve, edge.target.x, edge.target.y);
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawNodes(selected, hover, highlight) {
      const labelsAllowed = state.showLabels && state.visibleNodes.length < 900 && (state.fps === 0 || state.fps >= 22);
      ctx.save();
      for (const node of state.visibleNodes) {
        const isSelected = selected && selected.id === node.id;
        const isHover = hover && hover.id === node.id;
        const dim = selected && !highlight.has(node.id);
        const radius = node.r * (isSelected ? 1.45 : isHover ? 1.24 : 1);
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 4 / state.scale, 0, Math.PI * 2);
        ctx.fillStyle = dim ? "rgba(255,255,255,0.035)" : "rgba(128,232,218,0.08)";
        ctx.fill();
        ctx.fillStyle = dim ? "rgba(60,78,80,0.7)" : node.color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = isSelected ? "#ffffff" : isHover ? "rgba(255,255,255,0.8)" : "rgba(128,232,218,0.36)";
        ctx.lineWidth = (isSelected ? 2.6 : 1.1) / state.scale;
        ctx.stroke();
        if (labelsAllowed && (isSelected || isHover || state.scale > 0.72 || Number(node.degree || 0) >= 8)) {
          drawLabel(node, isSelected || isHover);
        }
      }
      ctx.restore();
    }

    function drawLabel(node, strong) {
      const text = node.name;
      ctx.save();
      ctx.font = `${strong ? 12 : 10}px ${getComputedStyle(document.documentElement).getPropertyValue("--mono")}`;
      const width = ctx.measureText(text).width;
      const x = node.x + node.r + 6;
      const y = node.y - 6;
      roundRect(ctx, x - 5, y - 12, width + 10, 18, 5);
      ctx.fillStyle = strong ? "rgba(2,14,17,0.86)" : "rgba(2,14,17,0.58)";
      ctx.fill();
      ctx.fillStyle = strong ? "#ffffff" : "rgba(236,255,251,0.78)";
      ctx.fillText(text, x, y + 1);
      ctx.restore();
    }

    function renderMetrics() {
      const stats = (state.graph && state.graph.stats) || {};
      els.mFiles.textContent = fmt(stats.filesScanned || 0);
      els.mFunctions.textContent = fmt(stats.functionsFound || 0);
      els.mEdges.textContent = fmt(stats.internalEdges || 0);
      els.mVisible.textContent = fmt(state.visibleNodes.length || 0);
      els.visibleNodeCount.textContent = fmt(state.visibleNodes.length || 0);
      els.visibleEdgeCount.textContent = fmt(state.visibleEdges.length || 0);
    }

    function renderAiPacket() {
      const packet = {
        schemaVersion: state.graph?.schemaVersion,
        generatedAt: state.graph?.generatedAt,
        root: state.graph?.root,
        stats: state.graph?.stats,
        aiReadout: state.graph?.aiReadout
      };
      els.aiPacket.textContent = JSON.stringify(packet, null, 2);
    }

    function renderHotspots() {
      els.hotspotList.innerHTML = "";
      const source = ((state.graph || {}).aiReadout || {}).topHotspots || [];
      if (!source.length) {
        els.hotspotList.innerHTML = `<div class="status">No hotspot data yet.</div>`;
        return;
      }
      for (const hotspot of source.slice(0, 16)) {
        const node = state.nodeById.get(hotspot.id);
        const item = document.createElement("div");
        item.className = `item ${state.selectedId === hotspot.id ? "active" : ""}`;
        item.innerHTML = `
          <div class="item-title"><span>${escapeHtml(hotspot.name)}</span><span class="badge">${hotspot.degree}</span></div>
          <div class="item-sub">${escapeHtml(shortPath(hotspot.file))}:${hotspot.line}</div>
        `;
        item.addEventListener("click", () => selectNode(hotspot.id, true));
        if (!node) item.style.opacity = "0.55";
        els.hotspotList.appendChild(item);
      }
    }

    function renderSelectedPanel() {
      const node = state.selectedId ? state.nodeById.get(state.selectedId) : null;
      if (!node) {
        els.selectedPanel.className = "status";
        els.selectedPanel.innerHTML = "Click a node or hotspot to inspect callers, callees, unresolved calls, and ambiguity.";
        return;
      }
      els.selectedPanel.className = "";
      const callers = (node.callers || []).map(id => state.nodeById.get(id)).filter(Boolean).sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0));
      const callees = (node.callees || []).map(id => state.nodeById.get(id)).filter(Boolean).sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0));
      els.selectedPanel.innerHTML = `
        <div class="selected-title">
          <h2>${escapeHtml(node.name)}</h2>
          <span class="badge">${node.degree || 0}</span>
        </div>
        <div class="kv"><div class="k">File</div><div class="v">${escapeHtml(node.file)}</div></div>
        <div class="kv"><div class="k">Line</div><div class="v">${node.line}</div></div>
        <div class="kv"><div class="k">Module</div><div class="v">${escapeHtml(node.module || ".")}</div></div>
        <div class="kv"><div class="k">Kind</div><div class="v">${escapeHtml(node.lang)} / ${escapeHtml(node.type)}</div></div>
        <div class="code-line">${escapeHtml(node.signature || node.name)}</div>
      `;
      els.selectedPanel.appendChild(sectionList("Calls Internal", callees));
      els.selectedPanel.appendChild(sectionList("Called By", callers));
      els.selectedPanel.appendChild(callList("Unresolved / Library Calls", node.externalCalls || []));
      els.selectedPanel.appendChild(callList("Ambiguous Call Names", node.ambiguousCalls || []));
    }

    function sectionList(title, nodes) {
      const block = document.createElement("div");
      block.className = "section";
      block.innerHTML = `<h3>${escapeHtml(title)}</h3>`;
      const list = document.createElement("div");
      list.className = "list";
      if (!nodes.length) {
        list.innerHTML = `<div class="status">None resolved in returned graph.</div>`;
      } else {
        for (const node of nodes.slice(0, 40)) {
          const row = document.createElement("div");
          row.className = "mini-link";
          row.innerHTML = `<div class="mini-title"><span>${escapeHtml(node.name)}</span><span class="badge">${node.degree || 0}</span></div><div class="path">${escapeHtml(shortPath(node.file))}:${node.line}</div>`;
          row.addEventListener("click", () => selectNode(node.id, true));
          list.appendChild(row);
        }
      }
      block.appendChild(list);
      return block;
    }

    function callList(title, calls) {
      const block = document.createElement("div");
      block.className = "section";
      block.innerHTML = `<h3>${escapeHtml(title)}</h3>`;
      const list = document.createElement("div");
      list.className = "list";
      if (!calls.length) {
        list.innerHTML = `<div class="status">None.</div>`;
      } else {
        for (const call of calls.slice(0, 24)) {
          const row = document.createElement("div");
          row.className = "mini-link";
          row.innerHTML = `<div class="mini-title"><span>${escapeHtml(call.name)}</span><span class="badge">${call.count || 0}</span></div>`;
          list.appendChild(row);
        }
      }
      block.appendChild(list);
      return block;
    }

    function selectNode(id, center) {
      state.selectedId = id || "";
      const node = state.nodeById.get(state.selectedId);
      if (center && node) {
        state.panX = -node.x * state.scale;
        state.panY = -node.y * state.scale;
        state.scale = Math.max(state.scale, 0.72);
      }
      rebuildVisibleGraph(false);
      renderSelectedPanel();
      renderHotspots();
      if (node) {
        state.panels.inspect = true;
        state.panelFocus = "inspect";
        openRepoDetail("selected");
        applyPanelVisibility(false);
        updateDrawerSizing();
      }
      requestDraw();
    }

    function onWheel(event) {
      event.preventDefault();
      const rect = els.canvas.getBoundingClientRect();
      const sx = event.clientX - rect.left;
      const sy = event.clientY - rect.top;
      const before = screenToWorld(sx, sy);
      const factor = event.deltaY < 0 ? 1.12 : 0.9;
      state.scale = clamp(state.scale * factor, 0.08, 5);
      const after = screenToWorld(sx, sy);
      state.panX += (after.x - before.x) * state.scale;
      state.panY += (after.y - before.y) * state.scale;
      requestDraw();
    }

    function onPointerDown(event) {
      const rect = els.canvas.getBoundingClientRect();
      const sx = event.clientX - rect.left;
      const sy = event.clientY - rect.top;
      const node = findNodeAt(sx, sy);
      state.lastPointer = { x: event.clientX, y: event.clientY };
      els.canvas.classList.add("dragging");
      if (node) {
        state.draggingNode = node;
        node.pinned = true;
        selectNode(node.id, false);
      } else {
        state.panning = true;
      }
      requestDraw();
    }

    function onPointerMove(event) {
      const dx = event.clientX - state.lastPointer.x;
      const dy = event.clientY - state.lastPointer.y;
      state.lastPointer = { x: event.clientX, y: event.clientY };
      const rect = els.canvas.getBoundingClientRect();
      const sx = event.clientX - rect.left;
      const sy = event.clientY - rect.top;
      if (state.draggingNode) {
        const pos = screenToWorld(sx, sy);
        state.draggingNode.x = pos.x;
        state.draggingNode.y = pos.y;
        state.draggingNode.vx = 0;
        state.draggingNode.vy = 0;
        state.layoutEnergy = Math.max(state.layoutEnergy, 0.2);
        requestDraw();
        return;
      }
      if (state.panning) {
        state.panX += dx;
        state.panY += dy;
        requestDraw();
        return;
      }
      const hover = findNodeAt(sx, sy);
      const nextHover = hover ? hover.id : "";
      if (nextHover !== state.hoveredId) {
        state.hoveredId = nextHover;
        requestDraw();
      }
    }

    function onPointerUp() {
      if (state.draggingNode) {
        state.draggingNode.pinned = false;
        state.draggingNode = null;
      }
      state.panning = false;
      els.canvas.classList.remove("dragging");
      requestDraw();
    }

    function findNodeAt(screenX, screenY) {
      const pos = screenToWorld(screenX, screenY);
      let best = null;
      let bestDist = Infinity;
      for (const node of state.visibleNodes) {
        const dist = Math.hypot(pos.x - node.x, pos.y - node.y);
        const hit = node.r + 8 / state.scale;
        if (dist <= hit && dist < bestDist) {
          best = node;
          bestDist = dist;
        }
      }
      return best;
    }

    function screenToWorld(x, y) {
      const rect = els.canvas.getBoundingClientRect();
      return {
        x: (x - rect.width / 2 - state.panX) / state.scale,
        y: (y - rect.height / 2 - state.panY) / state.scale
      };
    }

    function fitGraph() {
      const nodes = state.visibleNodes;
      if (!nodes.length) return;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const node of nodes) {
        minX = Math.min(minX, node.x - node.r);
        minY = Math.min(minY, node.y - node.r);
        maxX = Math.max(maxX, node.x + node.r);
        maxY = Math.max(maxY, node.y + node.r);
      }
      const rect = els.canvas.getBoundingClientRect();
      const width = Math.max(1, maxX - minX);
      const height = Math.max(1, maxY - minY);
      state.scale = clamp(Math.min((rect.width - 90) / width, (rect.height - 110) / height), 0.1, 2.4);
      state.panX = -((minX + maxX) / 2) * state.scale;
      state.panY = -((minY + maxY) / 2) * state.scale;
      requestDraw();
    }

    function resizeCanvas() {
      const rect = els.canvas.getBoundingClientRect();
      els.canvas.width = Math.max(1, Math.floor(rect.width * renderPixelRatio));
      els.canvas.height = Math.max(1, Math.floor(rect.height * renderPixelRatio));
      requestDraw();
    }

    function exportJson() {
      if (!state.graph) return;
      const blob = new Blob([JSON.stringify(state.graph, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "repo-webview-graph.json";
      link.click();
      URL.revokeObjectURL(url);
    }

    async function copyAiPacket() {
      const text = els.aiPacket.textContent || "{}";
      try {
        await navigator.clipboard.writeText(text);
        setStatus("AI packet copied.");
      } catch (_) {
        setStatus("Clipboard copy was blocked by the browser. Select the AI Packet text manually.");
      }
    }

    function updateFps(now, rendered) {
      if (rendered) {
        state.fpsFrames += 1;
      }
      if (now - state.fpsLastTime >= 500) {
        state.fps = Math.round((state.fpsFrames * 1000) / Math.max(1, now - state.fpsLastTime));
        state.fpsFrames = 0;
        state.fpsLastTime = now;
        els.fpsValue.textContent = String(state.fps);
      }
    }

    function relatedIds(node) {
      const ids = new Set();
      if (!node) return ids;
      ids.add(node.id);
      (node.callers || []).forEach(id => ids.add(id));
      (node.callees || []).forEach(id => ids.add(id));
      return ids;
    }

    function clusterCenter(module) {
      const modules = [...new Set(state.visibleNodes.map(node => node.cluster))].sort();
      const index = Math.max(0, modules.indexOf(module));
      const angle = (Math.PI * 2 * index) / Math.max(1, modules.length);
      const radius = Math.max(120, Math.sqrt(state.visibleNodes.length) * 45);
      return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
    }

    function gridKey(x, y, size) {
      return `${Math.floor(x / size)}:${Math.floor(y / size)}`;
    }

    function requestDraw() {
      state.needsDraw = true;
    }

    function installWorkbenchWindows() {
      if (!els.root) {
        return;
      }
      els.root.querySelectorAll("[data-repo-panel]").forEach((panel) => {
        const key = panel.getAttribute("data-repo-panel") || "";
        ensurePanelChrome(panel, key === "inspect" ? "Inspector" : "Lens", key);
      });
      ensureStageChrome();
    }

    function ensurePanelChrome(panel, title, key) {
      if (!panel || panel.querySelector(".panel-window-bar")) {
        return;
      }
      const bar = document.createElement("div");
      bar.className = "panel-window-bar";
      bar.innerHTML = `
        <span class="panel-window-title">${escapeHtml(title)}</span>
        <button class="panel-window-btn" type="button" aria-label="Hide ${escapeHtml(title)}">Hide</button>
      `;
      bar.addEventListener("pointerdown", (event) => {
        if (event.target.closest("button")) {
          return;
        }
        startWorkbenchWindowDrag(event, panel, "panel");
      });
      bar.querySelector("button")?.addEventListener("click", () => {
        if (key in state.panels) {
          state.panels[key] = false;
          if (state.panelFocus === key) {
            state.panelFocus = "";
          }
          applyPanelVisibility();
        }
      });
      panel.prepend(bar);
    }

    function ensureStageChrome() {
      if (!els.stage || els.stage.querySelector(".stage-window-bar")) {
        return;
      }
      const bar = document.createElement("div");
      bar.className = "stage-window-bar";
      bar.innerHTML = `
        <span class="stage-window-title">Canvas</span>
        <div class="stage-window-controls"></div>
        <button class="stage-window-btn" type="button" aria-label="Collapse canvas">Min</button>
      `;
      const controls = bar.querySelector(".stage-window-controls");
      const overlay = els.stage.querySelector(".overlay");
      const pills = overlay?.querySelector(".pill-row");
      const actions = overlay?.querySelector(".floating-actions");
      if (controls && pills) {
        controls.appendChild(pills);
      }
      if (controls && actions) {
        controls.appendChild(actions);
      }
      bar.addEventListener("pointerdown", (event) => {
        if (event.target.closest("button,input,select,textarea,a,.stage-window-controls")) {
          return;
        }
        startWorkbenchWindowDrag(event, els.stage, "stage");
      });
      bar.querySelector("button")?.addEventListener("click", () => {
        toggleStageCollapsed();
      });
      els.stage.appendChild(bar);
      updateWorkbenchBounds();
    }

    function toggleStageCollapsed() {
      if (!els.stage) {
        return;
      }
      const collapsed = !els.stage.classList.contains("is-stage-collapsed");
      els.stage.classList.toggle("is-stage-collapsed", collapsed);
      const button = els.stage.querySelector(".stage-window-btn");
      if (button) {
        button.textContent = collapsed ? "Open" : "Min";
        button.setAttribute("aria-label", collapsed ? "Expand canvas" : "Collapse canvas");
      }
      window.setTimeout(() => {
        resizeCanvas();
        updateWorkbenchBounds();
        requestDraw();
      }, 40);
    }

    function startWorkbenchWindowDrag(event, target, kind) {
      if (!target || event.button !== 0) {
        return;
      }
      const layout = target.closest(".layout");
      if (!layout) {
        return;
      }
      const targetRect = target.getBoundingClientRect();
      activeWindowDrag = {
        target,
        kind,
        pointerId: event.pointerId,
        offsetX: event.clientX - targetRect.left,
        offsetY: event.clientY - targetRect.top
      };
      target.classList.add("is-window-dragging");
      event.currentTarget.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    }

    function onWorkbenchWindowMove(event) {
      if (!activeWindowDrag) {
        return;
      }
      const { target, kind, offsetX, offsetY } = activeWindowDrag;
      const layout = target.closest(".layout");
      if (!layout) {
        endWorkbenchWindowDrag();
        return;
      }
      const layoutRect = layout.getBoundingClientRect();
      const width = Math.min(target.offsetWidth || target.getBoundingClientRect().width, layoutRect.width);
      const height = Math.min(target.offsetHeight || target.getBoundingClientRect().height, layoutRect.height);
      const maxX = Math.max(0, layoutRect.width - width);
      const verticalLimit = Math.max(layoutRect.height + 1200, window.innerHeight * 2, 2400);
      const maxY = Math.max(0, verticalLimit - height);
      const x = clamp(event.clientX - layoutRect.left - offsetX, 0, maxX);
      const y = clamp(event.clientY - layoutRect.top - offsetY, 0, maxY);
      if (kind === "stage") {
        target.style.setProperty("--stage-x", `${Math.round(x)}px`);
        target.style.setProperty("--stage-y", `${Math.round(y)}px`);
        const availableWidth = Math.max(180, layoutRect.width - x);
        const availableHeight = Math.max(46, layoutRect.height - y);
        if (target.offsetWidth > availableWidth + 1) {
          target.style.setProperty("--stage-w", `${Math.round(availableWidth)}px`);
        }
        if (!target.classList.contains("is-stage-collapsed") && target.offsetHeight > availableHeight + 1) {
          target.style.setProperty("--stage-h", `${Math.round(availableHeight)}px`);
        }
      } else {
        target.style.setProperty("--window-x", `${Math.round(x)}px`);
        target.style.setProperty("--window-y", `${Math.round(y)}px`);
      }
      updateWorkbenchBounds();
    }

    function endWorkbenchWindowDrag() {
      if (!activeWindowDrag) {
        return;
      }
      activeWindowDrag.target.classList.remove("is-window-dragging");
      activeWindowDrag = null;
      resizeCanvas();
      updateDrawerSizing();
      updateWorkbenchBounds();
      requestDraw();
    }

    function updateWorkbenchBounds() {
      if (!els.root) {
        return;
      }
      const layout = els.root.querySelector(".layout");
      if (!layout) {
        return;
      }
      const windows = Array.from(layout.querySelectorAll(".stage,[data-repo-panel]"))
        .filter((element) => !element.hidden && getComputedStyle(element).display !== "none");
      let bottom = 0;
      windows.forEach((element) => {
        bottom = Math.max(bottom, element.offsetTop + element.offsetHeight + 16);
      });
      layout.style.setProperty("--workbench-height", `${Math.ceil(bottom)}px`);
    }

    function togglePanel(key) {
      if (!(key in state.panels)) {
        return;
      }
      state.panels[key] = !state.panels[key];
      if (!state.panels[key] && state.panelFocus === key) {
        state.panelFocus = "";
      } else if (state.panels[key]) {
        state.panelFocus = key;
      }
      applyPanelVisibility();
    }

    function bindDrawerExpansion() {
      if (!els.root) {
        return;
      }
      els.root.querySelectorAll("details.group-card").forEach((details) => {
        details.open = false;
        details.addEventListener("toggle", () => {
          const panel = details.closest("[data-repo-panel]");
          const key = panel?.getAttribute("data-repo-panel") || "";
          if (details.open && key in state.panels) {
            state.panelFocus = key;
          }
          window.setTimeout(updateDrawerSizing, 20);
        });
      });
      els.root.addEventListener("click", (event) => {
        const item = event.target.closest(".item,.mini-link");
        if (!item) {
          return;
        }
        const panel = item.closest("[data-repo-panel]");
        const key = panel?.getAttribute("data-repo-panel") || "";
        if (key in state.panels) {
          state.panelFocus = key;
          updateDrawerSizing();
        }
      });
    }

    function openRepoDetail(name) {
      if (!els.root || !name) {
        return;
      }
      const details = els.root.querySelector(`[data-repo-detail="${name}"]`);
      if (details) {
        details.open = true;
      }
    }

    function focusRepoPanel(key) {
      if (!(key in state.panels)) {
        return;
      }
      state.panels[key] = true;
      state.panelFocus = key;
      applyPanelVisibility();
    }

    function updateDrawerSizing() {
      if (!els.root) {
        return;
      }
      const stack = els.root.querySelector(".drawer-stack");
      if (!stack) {
        return;
      }
      const stackHeight = Math.max(180, stack.clientHeight || 640);
      const openPanels = Array.from(els.root.querySelectorAll("[data-repo-panel]")).filter((panel) => !panel.hidden);
      const hasFocus = Boolean(state.panelFocus && state.panels[state.panelFocus]);
      stack.classList.toggle("has-drawer-focus", hasFocus);
      openPanels.forEach((panel) => {
        const key = panel.getAttribute("data-repo-panel") || "";
        const scroll = panel.querySelector(".scroll");
        const contentHeight = Math.ceil((scroll?.scrollHeight || panel.scrollHeight || 0) + 2);
        const focused = hasFocus && key === state.panelFocus;
        const maxRatio = focused ? (openPanels.length > 1 ? 0.74 : 0.9) : (hasFocus ? 0.24 : 0.62);
        const minHeight = focused ? 180 : 76;
        const desired = Math.min(stackHeight * maxRatio, Math.max(minHeight, contentHeight));
        panel.style.setProperty("--window-h", `${Math.round(desired)}px`);
        panel.classList.toggle("is-drawer-focus", focused);
      });
      updateWorkbenchBounds();
    }

    function applyPanelVisibility(relayout = true) {
      if (!els.root) {
        return;
      }
      els.root.classList.toggle("is-lens-open", state.panels.lens);
      els.root.classList.toggle("is-inspect-open", state.panels.inspect);
      els.root.querySelectorAll("[data-repo-panel]").forEach((panel) => {
        const key = panel.getAttribute("data-repo-panel");
        panel.hidden = !state.panels[key];
      });
      els.panelToggles.forEach((button) => {
        const key = button.getAttribute("data-repo-toggle");
        const active = Boolean(state.panels[key]);
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      if (relayout) {
        setTimeout(() => {
          resizeCanvas();
          updateDrawerSizing();
        }, 30);
      }
      updateDrawerSizing();
      updateWorkbenchBounds();
      requestDraw();
    }

    function edgeDrawLimit(edgeCount, nodeCount, fps) {
      if (fps && fps < 22) return Math.min(edgeCount, 1800);
      if (nodeCount > 700) return Math.min(edgeCount, 2400);
      if (nodeCount > 500) return Math.min(edgeCount, 3200);
      return Math.min(edgeCount, 5200);
    }

    function simulationEdgeLimit(edgeCount, nodeCount) {
      if (nodeCount > 700) return Math.min(edgeCount, 2600);
      if (nodeCount > 500) return Math.min(edgeCount, 4200);
      return Math.min(edgeCount, 7000);
    }

    function colorForModule(module) {
      let hash = 0;
      const text = String(module || ".");
      for (let index = 0; index < text.length; index++) hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
      return palette[Math.abs(hash) % palette.length];
    }

    function shortPath(path) {
      const parts = String(path || "").split("/");
      return parts.length <= 3 ? String(path || "") : `.../${parts.slice(-3).join("/")}`;
    }

    function setStatus(text) {
      els.status.textContent = text;
    }

    function fmt(value) {
      return Number(value || 0).toLocaleString();
    }

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function roundRect(context, x, y, w, h, r) {
      const radius = Math.min(r, w / 2, h / 2);
      context.beginPath();
      context.moveTo(x + radius, y);
      context.arcTo(x + w, y, x + w, y + h, radius);
      context.arcTo(x + w, y + h, x, y + h, radius);
      context.arcTo(x, y + h, x, y, radius);
      context.arcTo(x, y, x + w, y, radius);
      context.closePath();
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>'"]/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        "\"": "&quot;"
      }[char]));
    }

    function debounce(fn, ms) {
      let timer;
      return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
      };
    }
})();
