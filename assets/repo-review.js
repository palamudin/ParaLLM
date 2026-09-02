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
      files: [],
      functions: [],
      edges: [],
      nodeById: new Map(),
      visibleNodes: [],
      visibleEdges: [],
      selectedId: "",
      hoveredId: "",
      query: "",
      repoRoot: ".",
      graphMode: "overview",
      projection: "flat",
      minDegree: 0,
      maxVisible: 850,
      showOrphans: false,
      showLabels: true,
      scale: 1,
      panX: 0,
      panY: 0,
      panning: false,
      lastPointer: { x: 0, y: 0 },
      needsDraw: true,
      frameRequest: 0,
      threeView: null,
      threeViewLoading: null,
      architectureByModule: new Map(),
      flatLayers: [],
      layoutDiagnostics: {},
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
      repoRootSelect: document.getElementById("repoRootSelect"),
      searchInput: document.getElementById("searchInput"),
      graphModeSelect: document.getElementById("graphModeSelect"),
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
      canvas: document.getElementById("graphCanvas"),
      threeViewport: document.getElementById("repo3dViewport"),
      stage: document.getElementById("stage"),
      emptyState: document.getElementById("emptyState"),
      hotspotList: document.getElementById("hotspotList"),
      selectedPanel: document.getElementById("selectedPanel"),
      aiPacket: document.getElementById("aiPacket"),
      mFiles: document.getElementById("mFiles"),
      mFunctions: document.getElementById("mFunctions"),
      mEdges: document.getElementById("mEdges"),
      mVisible: document.getElementById("mVisible"),
      mModules: document.getElementById("mModules"),
      mDependencies: document.getElementById("mDependencies"),
      architectureHealth: document.getElementById("architectureHealth"),
      visibleNodeCount: document.getElementById("visibleNodeCount"),
      visibleEdgeCount: document.getElementById("visibleEdgeCount"),
      visibleModuleCount: document.getElementById("visibleModuleCount"),
      projectionValue: document.getElementById("projectionValue"),
      zoomValue: document.getElementById("zoomValue"),
      panelToggles: Array.from(document.querySelectorAll("[data-repo-toggle]")),
      projectionButtons: Array.from(document.querySelectorAll("[data-repo-projection]"))
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
      if (els.repoRootSelect) {
        els.repoRootSelect.addEventListener("change", () => {
          state.repoRoot = els.repoRootSelect.value || ".";
          fetchGraph();
        });
      }
      if (els.copyAiBtn) els.copyAiBtn.addEventListener("click", copyAiPacket);
      if (els.exportBtn) els.exportBtn.addEventListener("click", exportJson);
      els.fitBtn.addEventListener("click", fitGraph);
      els.projectionButtons.forEach((button) => {
        button.addEventListener("click", () => setProjection(button.getAttribute("data-repo-projection") || "flat"));
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
      if (els.graphModeSelect) {
        els.graphModeSelect.addEventListener("change", () => {
          state.graphMode = els.graphModeSelect.value || "overview";
          rebuildVisibleGraph(true);
          setTimeout(fitGraph, 40);
        });
      }
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
        syncThreeView();
        requestDraw();
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
      const themeObserver = new MutationObserver(() => {
        state.threeView?.applyTheme();
        syncThreeView();
        requestDraw();
      });
      themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-bs-theme"]
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
      fetchRepoRoots();
      fetchGraph();
      return true;
    }

    async function fetchRepoRoots() {
      if (!els.repoRootSelect) return;
      try {
        const response = await fetch("/v1/repo/roots", { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        const roots = Array.isArray(payload.roots) ? payload.roots : [];
        const current = state.repoRoot || ".";
        els.repoRootSelect.innerHTML = "";
        for (const root of roots) {
          const option = document.createElement("option");
          option.value = root.value || ".";
          option.textContent = root.label || root.value || "Repository root";
          els.repoRootSelect.appendChild(option);
        }
        els.repoRootSelect.value = roots.some(root => root.value === current) ? current : ".";
        state.repoRoot = els.repoRootSelect.value || ".";
      } catch (error) {
        setStatus(`Folder list unavailable: ${error.message || error}`);
      }
    }

    function stageHasViewport() {
      const rect = els.stage.getBoundingClientRect();
      return rect.width > 40 && rect.height > 40;
    }

    async function setProjection(requested) {
      const projection = ["flat", "isometric", "spatial"].includes(requested) ? requested : "flat";
      if (state.projection === projection && (projection === "flat" || state.threeView)) {
        return;
      }
      state.projection = projection;
      if (state.nodes.length) rebuildVisibleGraph(false);
      els.projectionValue.textContent = projection;
      els.projectionButtons.forEach(button => {
        const active = button.getAttribute("data-repo-projection") === projection;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
      const flat = projection === "flat";
      els.canvas.hidden = !flat;
      if (els.threeViewport) els.threeViewport.hidden = flat;
      els.stage.classList.toggle("is-3d-view", !flat);
      if (flat) {
        resizeCanvas();
        requestDraw();
        fitGraph();
        return;
      }
      setStatus(`Loading ${projection} architecture projection...`);
      try {
        await ensureThreeView();
        syncThreeView();
        state.threeView?.fit();
        setStatus(`${projection === "isometric" ? "Isometric" : "Spatial"} architecture projection ready. Positions are deterministic; only the camera moves.`);
      } catch (error) {
        setStatus(`3D renderer unavailable: ${error.message || error}`);
        state.projection = "flat";
        els.canvas.hidden = false;
        if (els.threeViewport) els.threeViewport.hidden = true;
        els.stage.classList.remove("is-3d-view");
        els.projectionValue.textContent = "flat";
        els.projectionButtons.forEach(button => {
          const active = button.getAttribute("data-repo-projection") === "flat";
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-pressed", active ? "true" : "false");
        });
        resizeCanvas();
        fitGraph();
      }
    }

    async function ensureThreeView() {
      if (state.threeView) return state.threeView;
      if (state.threeViewLoading) return state.threeViewLoading;
      if (!els.threeViewport) throw new Error("3D viewport is missing.");
      state.threeViewLoading = import("/assets/repo-review-3d.js?v=20260829-001")
        .then(module => {
          state.threeView = new module.RepoSpatialRenderer(els.threeViewport, {
            onSelect: id => selectNode(id, false),
            onHover: id => {
              state.hoveredId = id || "";
            },
            onZoom: value => {
              els.zoomValue.textContent = `${Math.round(value * 100)}%`;
            }
          });
          return state.threeView;
        })
        .finally(() => {
          state.threeViewLoading = null;
        });
      return state.threeViewLoading;
    }

    function syncThreeView() {
      if (!state.threeView || state.projection === "flat") return;
      state.threeView.setData({
        nodes: state.visibleNodes,
        edges: state.visibleEdges,
        projection: state.projection,
        detailMode: state.graphMode,
        selectedId: state.selectedId,
        hoveredId: state.hoveredId,
        showLabels: state.showLabels
      });
    }

    async function fetchGraph() {
      setStatus("Scanning repo root through /v1/repo/graph...");
      els.emptyState.hidden = false;
      try {
        const params = new URLSearchParams({
          root: state.repoRoot || ".",
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
      state.files = graph.files || [];
      state.functions = graph.nodes || [];
      state.architectureByModule = new Map(
        ((graph.architecture || {}).modules || []).map(item => [item.module, item])
      );
      const built = buildOversightGraph(graph);
      state.nodes = built.nodes;
      state.edges = built.edges;
      renderMetrics();
      renderArchitectureHealth();
      renderAiPacket();
      renderHotspots();
      rebuildVisibleGraph(true);
      setTimeout(fitGraph, 80);
      requestDraw();
    }

    function buildOversightGraph(graph) {
      const nodes = [];
      const edges = [];
      const moduleStats = new Map();
      const files = graph.files || [];
      const functions = graph.nodes || [];

      for (const file of files) {
        const module = file.module || ".";
        const stat = moduleStats.get(module) || {
          module,
          files: 0,
          functions: 0,
          inbound: 0,
          outbound: 0
        };
        stat.files += 1;
        stat.functions += Number(file.functionCount || 0);
        stat.inbound += Number(file.inboundInternalEdges || 0);
        stat.outbound += Number(file.outboundInternalEdges || 0);
        moduleStats.set(module, stat);
      }

      for (const stat of moduleStats.values()) {
        const architecture = state.architectureByModule.get(stat.module) || {};
        addGraphNode(nodes, {
          ...architecture,
          id: `module:${stat.module}`,
          name: stat.module,
          label: stat.module,
          nodeKind: "module",
          module: stat.module,
          file: "",
          lang: "Module",
          type: "module",
          degree: stat.functions + stat.inbound + stat.outbound,
          functionCount: stat.functions,
          fileCount: stat.files,
          inboundInternalEdges: stat.inbound,
          outboundInternalEdges: stat.outbound,
          r: 18
        });
      }

      for (const file of files) {
        const module = file.module || ".";
        addGraphNode(nodes, {
          ...file,
          id: `file:${file.path}`,
          name: basename(file.path),
          label: shortPath(file.path),
          nodeKind: "file",
          file: file.path,
          type: "file",
          degree: Number(file.functionCount || 0) + Number(file.inboundInternalEdges || 0) + Number(file.outboundInternalEdges || 0),
          r: 11,
          parentModuleId: `module:${module}`
        });
        edges.push({
          id: `contains:${module}:${file.path}`,
          sourceId: `module:${module}`,
          targetId: `file:${file.path}`,
          weight: Math.max(1, Math.min(8, Number(file.functionCount || 1))),
          relation: "contains"
        });
      }

      for (const node of functions) {
        const module = node.module || ".";
        addGraphNode(nodes, {
          ...node,
          label: node.name,
          nodeKind: "function",
          degree: Number(node.degree || 0),
          r: 4.2 + Math.sqrt(Number(node.degree || 0) + 1) * 1.45,
          parentFileId: `file:${node.file}`,
          parentModuleId: `module:${module}`
        });
        edges.push({
          id: `defines:${node.file}:${node.id}`,
          sourceId: `file:${node.file}`,
          targetId: node.id,
          weight: 1,
          relation: "defines"
        });
      }

      for (const edge of graph.edges || []) {
        edges.push({
          ...edge,
          id: `calls:${edge.sourceId}:${edge.targetId}`,
          relation: edge.ambiguous ? "ambiguous" : "calls",
          weight: Number(edge.weight || 1)
        });
      }

      for (const edge of ((graph.architecture || {}).dependencies || [])) {
        edges.push({
          ...edge,
          relation: "module-call",
          weight: Number(edge.weight || 1)
        });
      }

      nodes.forEach((node, index) => {
        node.index = index;
        node.x = 0;
        node.y = 0;
        node.color = colorForModule(node.module || node.file || "");
        node.cluster = node.module || ".";
        node.visible = false;
        node.layoutReady = false;
        node.layout = {
          flat: { x: 0, y: 0, z: 0 },
          isometric: { x: 0, y: 0, z: 0 },
          spatial: { x: 0, y: 0, z: 0 }
        };
        state.nodeById.set(node.id, node);
      });

      const hydratedEdges = edges.map(edge => ({
        ...edge,
        source: state.nodeById.get(edge.sourceId),
        target: state.nodeById.get(edge.targetId),
        weight: Number(edge.weight || 1)
      })).filter(edge => edge.source && edge.target);

      return { nodes, edges: hydratedEdges };
    }

    function addGraphNode(nodes, node) {
      nodes.push({
        callers: [],
        callees: [],
        externalCalls: [],
        ambiguousCalls: [],
        ...node
      });
    }

    function rebuildVisibleGraph(resetPositions) {
      const query = state.query;
      const matches = new Set();
      const selectedNeighbors = new Set();
      if (state.selectedId) {
        const selected = state.nodeById.get(state.selectedId);
        addNeighborhood(selected, selectedNeighbors);
      }

      for (const node of state.nodes) {
        const searchable = `${node.name} ${node.label} ${node.file} ${node.module} ${node.lang} ${node.type} ${node.signature}`.toLowerCase();
        const isMatch = Boolean(query && searchable.includes(query));
        if (isMatch) matches.add(node.id);
      }

      let visible = state.nodes.filter(node => {
        const structural = node.nodeKind === "module" || node.nodeKind === "file";
        const matched = matches.has(node.id);
        const neighbor = selectedNeighbors.has(node.id);
        if (state.graphMode === "selected") {
          return neighbor || matched;
        }
        if (state.graphMode === "functions") {
          if (node.nodeKind !== "function") return neighbor || matched;
          if (!state.showOrphans && Number(node.degree || 0) === 0 && !matched) return false;
          if (Number(node.degree || 0) < state.minDegree && !matched && !neighbor) return false;
          return matched || neighbor || !query;
        }
        if (state.projection === "flat") {
          return node.nodeKind === "module" || matched || neighbor;
        }
        if (state.projection === "isometric") {
          return structural || matched || neighbor;
        }
        if (structural) {
          return matched || neighbor || !query || Number(node.degree || 0) >= state.minDegree;
        }
        if (!state.showOrphans && Number(node.degree || 0) === 0 && !matched && !neighbor) return false;
        if (Number(node.degree || 0) < state.minDegree && !matched && !neighbor) return false;
        return matched || neighbor || Boolean(query) || Number(node.degree || 0) >= 8;
      });

      visible.sort((a, b) => {
        return nodePriority(b, matches, selectedNeighbors) - nodePriority(a, matches, selectedNeighbors)
          || Number(b.degree || 0) - Number(a.degree || 0)
          || String(a.file || a.name).localeCompare(String(b.file || b.name));
      });
      visible = capVisibleNodes(visible, matches, selectedNeighbors);

      const visibleIds = new Set(visible.map(node => node.id));
      state.visibleNodes = visible;
      state.visibleEdges = state.edges.filter(edge => visibleIds.has(edge.sourceId) && visibleIds.has(edge.targetId));
      for (const node of state.nodes) node.visible = visibleIds.has(node.id);
      assignDeterministicLayout();
      renderMetrics();
      renderArchitectureHealth();
      renderAiPacket();
      renderSelectedPanel();
      renderHotspots();
      els.emptyState.hidden = state.visibleNodes.length > 0;
      syncThreeView();
      requestDraw();
    }

    function nodePriority(node, matches, selectedNeighbors) {
      let score = 0;
      if (selectedNeighbors.has(node.id)) score += 1000;
      if (matches.has(node.id)) score += 700;
      if (node.nodeKind === "module") score += 260;
      if (node.nodeKind === "file") score += 160;
      if (node.nodeKind === "function") score += 20;
      return score;
    }

    function capVisibleNodes(nodes, matches, selectedNeighbors) {
      if (nodes.length <= state.maxVisible) return nodes;
      if (state.graphMode !== "overview") return nodes.slice(0, state.maxVisible);
      const modules = nodes.filter(node => node.nodeKind === "module");
      const files = nodes.filter(node => node.nodeKind === "file");
      const functions = nodes.filter(node => node.nodeKind === "function");
      const structuralLimit = Math.min(state.maxVisible, Math.max(120, Math.floor(state.maxVisible * 0.62)));
      const structural = [...modules, ...files].slice(0, structuralLimit);
      const remaining = Math.max(0, state.maxVisible - structural.length);
      const importantFunctions = functions.filter(node => matches.has(node.id) || selectedNeighbors.has(node.id) || Number(node.degree || 0) >= 8);
      return [...structural, ...importantFunctions.slice(0, remaining)];
    }

    function addNeighborhood(node, ids) {
      if (!node) return;
      ids.add(node.id);
      if (node.parentFileId) ids.add(node.parentFileId);
      if (node.parentModuleId) ids.add(node.parentModuleId);
      if (node.nodeKind === "module") {
        for (const candidate of state.nodes) {
          if (candidate.parentModuleId === node.id || candidate.module === node.module) {
            if (candidate.nodeKind !== "function" || Number(candidate.degree || 0) >= 6) ids.add(candidate.id);
          }
        }
      } else if (node.nodeKind === "file") {
        if (node.parentModuleId) ids.add(node.parentModuleId);
        state.nodes
          .filter(candidate => candidate.parentFileId === node.id)
          .sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0))
          .slice(0, 80)
          .forEach(candidate => ids.add(candidate.id));
      } else {
        (node.callers || []).forEach(id => {
          ids.add(id);
          const caller = state.nodeById.get(id);
          if (caller?.parentFileId) ids.add(caller.parentFileId);
        });
        (node.callees || []).forEach(id => {
          ids.add(id);
          const callee = state.nodeById.get(id);
          if (callee?.parentFileId) ids.add(callee.parentFileId);
        });
      }
    }

    function assignDeterministicLayout() {
      const moduleNodes = state.nodes
        .filter(node => node.nodeKind === "module")
        .sort((a, b) => Number(a.layer || 0) - Number(b.layer || 0)
          || Number(a.order || 0) - Number(b.order || 0)
          || String(a.module).localeCompare(String(b.module)));
      const modulesByLayer = new Map();
      for (const moduleNode of moduleNodes) {
        const layer = Number(moduleNode.layer || 0);
        if (!modulesByLayer.has(layer)) modulesByLayer.set(layer, []);
        modulesByLayer.get(layer).push(moduleNode);
      }
      const layers = [...modulesByLayer.keys()].sort((a, b) => a - b);
      const maxLayer = layers.length ? Math.max(...layers) : 0;
      let flatLayerCursor = 0;
      const modulePlans = [];

      for (const layer of layers) {
        const modules = modulesByLayer.get(layer) || [];
        const blocks = modules.map(moduleNode => {
          const files = state.nodes
            .filter(node => node.nodeKind === "file" && node.parentModuleId === moduleNode.id)
            .sort((a, b) => String(a.file).localeCompare(String(b.file)));
          const columns = files.length > 16 ? 3 : files.length > 1 ? 2 : 1;
          const rows = Math.max(1, Math.ceil(files.length / columns));
          return {
            moduleNode,
            files,
            columns,
            height: Math.max(104, 58 + rows * 34)
          };
        });
        const flatColumns = Math.min(6, Math.max(1, Math.ceil(Math.sqrt(blocks.length * 0.8))));
        const flatRows = Math.max(1, Math.ceil(blocks.length / flatColumns));
        const flatCellWidth = 420;
        const flatCellHeight = Math.max(178, ...blocks.map(block => block.height + 70));
        const isoColumns = Math.min(6, Math.max(1, Math.ceil(Math.sqrt(blocks.length * 0.9))));
        const isoRows = Math.max(1, Math.ceil(blocks.length / isoColumns));
        blocks.forEach((block, blockIndex) => {
          const { moduleNode, files, columns, height } = block;
          const flatColumn = blockIndex % flatColumns;
          const flatRow = Math.floor(blockIndex / flatColumns);
          const flatCellCenterY = (flatRow - (flatRows - 1) / 2) * flatCellHeight;
          const flatX = flatLayerCursor + flatColumn * flatCellWidth;
          const flatY = flatCellCenterY - height / 2 + 20;
          const isoColumn = blockIndex % isoColumns;
          const isoRow = Math.floor(blockIndex / isoColumns);
          const localX = (isoColumn - (isoColumns - 1) / 2);
          const localZ = (isoRow - (isoRows - 1) / 2);
          const inbound = Number(moduleNode.inboundCalls || 0);
          const outbound = Number(moduleNode.outboundCalls || 0);
          const flowElevation = clamp(Math.log1p(inbound) - Math.log1p(outbound), -3, 3) * 10
            + Math.log1p(inbound + outbound) * 8;
          setNodeLayout(moduleNode, "flat", flatX, flatY, 0);
          setNodeLayout(moduleNode, "isometric", (layer - maxLayer / 2) * 68 + localX * 18, 0, localZ * 24);
          setNodeLayout(moduleNode, "spatial", (layer - maxLayer / 2) * 96 + localX * 28, flowElevation, localZ * 34);
          modulePlans.push({ moduleNode, files, columns });
        });
        flatLayerCursor += Math.max(0, flatColumns - 1) * flatCellWidth + 620;
      }

      const collisionSpaces = createCollisionSpaces();
      for (const moduleNode of moduleNodes) {
        if (!moduleNode.visible) continue;
        placeCollisionFree(moduleNode, "flat", collisionSpaces.flat);
        placeCollisionFree(moduleNode, "isometric", collisionSpaces.isometric);
        placeCollisionFree(moduleNode, "spatial", collisionSpaces.spatial);
      }

      for (const plan of modulePlans) {
        placeModuleFiles(plan.moduleNode, plan.files, plan.columns);
      }
      const fileNodes = state.nodes
        .filter(node => node.nodeKind === "file")
        .sort((a, b) => String(a.module).localeCompare(String(b.module)) || String(a.file).localeCompare(String(b.file)));
      for (const fileNode of fileNodes) {
        if (!fileNode.visible) continue;
        placeCollisionFree(fileNode, "flat", collisionSpaces.flat);
        placeCollisionFree(fileNode, "isometric", collisionSpaces.isometric);
        placeCollisionFree(fileNode, "spatial", collisionSpaces.spatial);
      }

      const functionsByFile = new Map();
      for (const node of state.nodes) {
        if (node.nodeKind !== "function") continue;
        if (!functionsByFile.has(node.parentFileId)) functionsByFile.set(node.parentFileId, []);
        functionsByFile.get(node.parentFileId).push(node);
      }
      for (const functions of functionsByFile.values()) {
        functions.sort((a, b) => Number(a.line || 0) - Number(b.line || 0) || String(a.name).localeCompare(String(b.name)));
        const grid = functionGridFor(functions);
        functions.forEach((node, index) => {
          placeFileFunction(node, index, grid);
          if (!node.visible) return;
          placeCollisionFree(node, "flat", collisionSpaces.flat);
          placeCollisionFree(node, "isometric", collisionSpaces.isometric);
          placeCollisionFree(node, "spatial", collisionSpaces.spatial);
        });
      }

      for (const node of state.nodes) {
        node.x = node.layout.flat.x;
        node.y = node.layout.flat.y;
        node.layoutReady = true;
      }
      state.layoutDiagnostics = buildLayoutDiagnostics(collisionSpaces);
      publishLayoutDiagnostics();
      buildFlatLayerBands(moduleNodes);
    }

    function placeModuleFiles(moduleNode, files, columns) {
      const flatColumnGap = Math.max(252, ...files.map(node => structuralNodeWidth(node) + 22));
      const flatStartX = moduleNode.layout.flat.x - ((columns - 1) * flatColumnGap) / 2;
      const flatStartY = moduleNode.layout.flat.y + 42;
      const moduleIsoSize = isometricNodeDimensions(moduleNode);
      files.forEach((node, index) => {
        const column = index % columns;
        const row = Math.floor(index / columns);
        setNodeLayout(node, "flat", flatStartX + column * flatColumnGap, flatStartY + row * 34, 0);

        const isoColumns = Math.min(4, Math.max(1, files.length));
        const isoColumn = index % isoColumns;
        const isoRow = Math.floor(index / isoColumns);
        setNodeLayout(
          node,
          "isometric",
          moduleNode.layout.isometric.x + (isoColumn - (isoColumns - 1) / 2) * 3.2,
          moduleNode.layout.isometric.y + moduleIsoSize.height + 0.85,
          moduleNode.layout.isometric.z + 3.2 + isoRow * 2.4
        );

        const angle = index * 2.399963 + stableUnit(node.id, 1) * 0.8;
        const radius = 7 + Math.sqrt(index + 1) * 2.6;
        setNodeLayout(
          node,
          "spatial",
          moduleNode.layout.spatial.x + Math.cos(angle) * radius,
          moduleNode.layout.spatial.y + (stableUnit(node.id, 2) - 0.5) * 7,
          moduleNode.layout.spatial.z + Math.sin(angle) * radius
        );
      });
    }

    function buildFlatLayerBands(moduleNodes) {
      const layerByModule = new Map(moduleNodes.map(node => [node.module, Number(node.layer || 0)]));
      const bands = new Map();
      for (const node of state.visibleNodes) {
        const layer = layerByModule.get(node.module);
        if (!Number.isFinite(layer)) continue;
        const bounds = nodeBounds(node);
        const band = bands.get(layer) || {
          layer,
          moduleIds: new Set(),
          minX: Infinity,
          minY: Infinity,
          maxX: -Infinity,
          maxY: -Infinity
        };
        band.moduleIds.add(node.module);
        band.minX = Math.min(band.minX, bounds.minX);
        band.minY = Math.min(band.minY, bounds.minY);
        band.maxX = Math.max(band.maxX, bounds.maxX);
        band.maxY = Math.max(band.maxY, bounds.maxY);
        bands.set(layer, band);
      }
      state.flatLayers = [...bands.values()]
        .sort((a, b) => a.layer - b.layer)
        .map(band => ({
          ...band,
          moduleCount: band.moduleIds.size,
          minX: band.minX - 34,
          minY: band.minY - 56,
          maxX: band.maxX + 34,
          maxY: band.maxY + 34
        }));
    }

    function placeFileFunction(node, index, grid) {
      const parent = state.nodeById.get(node.parentFileId);
      const moduleNode = state.nodeById.get(node.parentModuleId);
      const anchor = parent || moduleNode;
      if (!anchor) return;
      const column = index % grid.columns;
      const row = Math.floor(index / grid.columns);
      setNodeLayout(
        node,
        "flat",
        anchor.layout.flat.x + structuralNodeWidth(anchor) / 2 + grid.radius + 18 + column * grid.spacing,
        anchor.layout.flat.y + (row - (grid.rows - 1) / 2) * grid.spacing,
        0
      );
      setNodeLayout(
        node,
        "isometric",
        anchor.layout.isometric.x + ((index % 4) - 1.5) * 0.58,
        3 + Math.floor(index / 4) * 0.34,
        anchor.layout.isometric.z + (Math.floor(index / 4) - 0.5) * 0.62
      );
      const theta = stableUnit(node.id, 3) * Math.PI * 2;
      const phi = Math.acos(2 * stableUnit(node.id, 4) - 1);
      const radius = 1.8 + Math.sqrt(index + 1) * 0.42;
      setNodeLayout(
        node,
        "spatial",
        anchor.layout.spatial.x + Math.sin(phi) * Math.cos(theta) * radius,
        anchor.layout.spatial.y + Math.cos(phi) * radius,
        anchor.layout.spatial.z + Math.sin(phi) * Math.sin(theta) * radius
      );
    }

    function functionGridFor(nodes) {
      const count = Math.max(1, nodes.length);
      const radius = Math.max(6, ...nodes.map(node => Number(node.r || 6) + 4));
      const columns = Math.min(8, Math.max(1, Math.ceil(Math.sqrt(count * 1.65))));
      return {
        columns,
        rows: Math.max(1, Math.ceil(count / columns)),
        radius,
        spacing: radius * 2 + 8
      };
    }

    function createCollisionSpaces() {
      return {
        flat: [],
        isometric: [],
        spatial: []
      };
    }

    function placeCollisionFree(node, projection, space) {
      const desired = node.layout[projection];
      const position = { x: desired.x, y: desired.y, z: desired.z || 0 };
      const own = collisionFootprint(node, projection, position);
      let displaced = false;
      for (let attempt = 0; attempt <= space.length + 2; attempt++) {
        const footprint = collisionFootprint(node, projection, position);
        const conflict = space.find(item => collisionItemsOverlap(projection, footprint, item));
        if (!conflict) {
          setNodeLayout(node, projection, position.x, position.y, position.z);
          space.push({
            ...footprint,
            nodeId: node.id,
            nodeKind: node.nodeKind,
            displaced
          });
          return;
        }
        displaced = true;
        if (projection === "flat") {
          const halfHeight = (own.maxY - own.minY) / 2;
          position.y = conflict.maxY + halfHeight + 8;
        } else if (projection === "isometric") {
          const halfDepth = (own.maxZ - own.minZ) / 2;
          position.z = conflict.maxZ + halfDepth + 1.2;
        } else {
          position.y = conflict.y + conflict.radius + own.radius + 0.55;
        }
      }
      throw new Error(`Unable to place ${node.id} without a ${projection} collision.`);
    }

    function collisionFootprint(node, projection, position) {
      if (projection === "flat") {
        const structural = node.nodeKind === "module" || node.nodeKind === "file";
        const width = structural ? structuralNodeWidth(node) + 14 : (Number(node.r || 6) + 6) * 2;
        const height = structural ? (node.nodeKind === "module" ? 48 : 39) : (Number(node.r || 6) + 6) * 2;
        return {
          x: position.x,
          y: position.y,
          z: 0,
          minX: position.x - width / 2,
          minY: position.y - height / 2,
          maxX: position.x + width / 2,
          maxY: position.y + height / 2
        };
      }
      if (projection === "isometric") {
        const size = isometricNodeDimensions(node);
        const width = Math.max(size.width, node.nodeKind === "module" ? 16 : 3.2) + 0.7;
        const height = size.height + 0.7;
        const depth = size.depth + 0.7;
        const centerY = position.y + size.height / 2;
        return {
          x: position.x,
          y: centerY,
          z: position.z,
          minX: position.x - width / 2,
          minY: centerY - height / 2,
          minZ: position.z - depth / 2,
          maxX: position.x + width / 2,
          maxY: centerY + height / 2,
          maxZ: position.z + depth / 2
        };
      }
      const radius = spatialCollisionRadius(node) + 0.35;
      return {
        x: position.x,
        y: position.y,
        z: position.z,
        radius
      };
    }

    function collisionItemsOverlap(projection, left, right) {
      if (projection === "flat") {
        return left.minX < right.maxX && left.maxX > right.minX
          && left.minY < right.maxY && left.maxY > right.minY;
      }
      if (projection === "isometric") {
        return left.minX < right.maxX && left.maxX > right.minX
          && left.minY < right.maxY && left.maxY > right.minY
          && left.minZ < right.maxZ && left.maxZ > right.minZ;
      }
      return Math.hypot(left.x - right.x, left.y - right.y, left.z - right.z) < left.radius + right.radius;
    }

    function isometricNodeDimensions(node) {
      if (node.nodeKind === "module") {
        return {
          width: 5.2 + Math.min(6, Math.sqrt(Number(node.fileCount || 0) + 1) * 1.1),
          height: 1.2 + Math.min(3.2, Math.log1p(Number(node.functionCount || 0)) * 0.48),
          depth: 4.2 + Math.min(5, Math.sqrt(Number(node.fileCount || 0) + 1) * 0.9)
        };
      }
      if (node.nodeKind === "file") {
        return {
          width: 2.5,
          height: 0.55 + Math.min(1.8, Math.log1p(Number(node.functionCount || 0)) * 0.3),
          depth: 1.45
        };
      }
      const radius = 0.18 + Math.min(0.36, Math.sqrt(Number(node.degree || 0) + 1) * 0.045);
      return { width: radius * 2, height: radius * 2, depth: radius * 2 };
    }

    function spatialCollisionRadius(node) {
      if (node.nodeKind === "module") {
        return 1.8 + Math.min(2.2, Math.log1p(Number(node.functionCount || 0)) * 0.34);
      }
      if (node.nodeKind === "file") {
        const scale = 0.62 + Math.min(0.9, Math.log1p(Number(node.functionCount || 0)) * 0.15);
        return scale * Math.sqrt(3);
      }
      return 0.16 + Math.min(0.34, Math.sqrt(Number(node.degree || 0) + 1) * 0.04);
    }

    function buildLayoutDiagnostics(spaces) {
      const projections = {};
      for (const [projection, items] of Object.entries(spaces)) {
        let overlapPairs = 0;
        const coincident = new Map();
        for (let index = 0; index < items.length; index++) {
          const item = items[index];
          const key = `${item.x.toFixed(4)}:${item.y.toFixed(4)}:${item.z.toFixed(4)}`;
          coincident.set(key, (coincident.get(key) || 0) + 1);
          for (let otherIndex = index + 1; otherIndex < items.length; otherIndex++) {
            if (collisionItemsOverlap(projection, item, items[otherIndex])) overlapPairs += 1;
          }
        }
        projections[projection] = {
          nodesChecked: items.length,
          overlapPairs,
          coincidentPositions: [...coincident.values()].filter(count => count > 1).reduce((total, count) => total + count, 0),
          displacedNodes: items.filter(item => item.displaced).length
        };
      }
      const edgePairs = new Map();
      for (const edge of state.edges) {
        const key = `${edge.sourceId}\u0000${edge.targetId}`;
        edgePairs.set(key, (edgePairs.get(key) || 0) + 1);
      }
      return {
        schemaVersion: "repo-layout-diagnostics/v1",
        ...projections,
        bundledEdgePairs: [...edgePairs.values()].filter(count => count > 1).length
      };
    }

    function publishLayoutDiagnostics() {
      const diagnostics = JSON.parse(JSON.stringify(state.layoutDiagnostics));
      if (els.root) {
        els.root.dataset.flatOverlapPairs = String(diagnostics.flat?.overlapPairs || 0);
        els.root.dataset.isometricOverlapPairs = String(diagnostics.isometric?.overlapPairs || 0);
        els.root.dataset.spatialOverlapPairs = String(diagnostics.spatial?.overlapPairs || 0);
      }
      window.ParaLLMRepoMap = {
        schemaVersion: "parallm-repo-map/v1",
        layout: diagnostics
      };
    }

    function setNodeLayout(node, projection, x, y, z) {
      node.layout[projection] = { x, y, z };
    }

    function stableUnit(value, salt) {
      let hash = 2166136261 ^ Number(salt || 0);
      const text = String(value || "");
      for (let index = 0; index < text.length; index++) {
        hash ^= text.charCodeAt(index);
        hash = Math.imul(hash, 16777619);
      }
      return (hash >>> 0) / 4294967295;
    }

    function nodeHasLayout(node) {
      return Boolean(node && node.layoutReady && Number.isFinite(node.x) && Number.isFinite(node.y));
    }

    function draw() {
      if (state.projection !== "flat") return;
      const canvas = els.canvas;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const lightTheme = document.documentElement.getAttribute("data-bs-theme") === "light";
      ctx.fillStyle = lightTheme ? "#e8f0f7" : "#030c0f";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      ctx.scale(renderPixelRatio, renderPixelRatio);
      drawGrid(w, h);
      ctx.translate(w / 2 + state.panX, h / 2 + state.panY);
      ctx.scale(state.scale, state.scale);
      drawLayerBands(lightTheme);
      const selected = state.selectedId ? state.nodeById.get(state.selectedId) : null;
      const hover = state.hoveredId ? state.nodeById.get(state.hoveredId) : null;
      const highlight = relatedIds(selected);
      drawEdges(selected, hover, highlight);
      drawNodes(selected, hover, highlight);
      ctx.restore();
      els.zoomValue.textContent = `${Math.round(state.scale * 100)}%`;
    }

    function drawLayerBands(lightTheme) {
      if (state.graphMode !== "overview") return;
      ctx.save();
      for (const band of state.flatLayers) {
        const width = Math.max(1, band.maxX - band.minX);
        const height = Math.max(1, band.maxY - band.minY);
        roundRect(ctx, band.minX, band.minY, width, height, 4);
        ctx.fillStyle = lightTheme ? "rgba(25, 93, 137, 0.035)" : "rgba(80, 151, 199, 0.025)";
        ctx.fill();
        ctx.strokeStyle = lightTheme ? "rgba(25, 93, 137, 0.16)" : "rgba(128, 232, 218, 0.1)";
        ctx.lineWidth = 1 / state.scale;
        ctx.stroke();
        ctx.font = `700 ${11 / state.scale}px ${getComputedStyle(document.documentElement).getPropertyValue("--mono")}`;
        ctx.fillStyle = lightTheme ? "rgba(18, 71, 105, 0.72)" : "rgba(138, 180, 255, 0.68)";
        ctx.textBaseline = "top";
        ctx.fillText(`LAYER ${band.layer}  |  ${band.moduleCount} MODULES`, band.minX + 12 / state.scale, band.minY + 10 / state.scale);
      }
      ctx.restore();
    }

    function drawGrid(w, h) {
      const grid = 36 * state.scale;
      if (state.visibleNodes.length > 650) return;
      if (grid < 14) return;
      const ox = (w / 2 + state.panX) % grid;
      const oy = (h / 2 + state.panY) % grid;
      ctx.save();
      ctx.strokeStyle = document.documentElement.getAttribute("data-bs-theme") === "light"
        ? "rgba(24, 92, 132, 0.09)"
        : "rgba(128,232,218,0.035)";
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
      const drawLimit = selectedMode ? edges.length : edgeDrawLimit(edges.length, state.visibleNodes.length);
      const renderEdges = edges.slice(0, drawLimit).filter(edge => !selectedMode || edge.sourceId === selected.id || edge.targetId === selected.id);
      const routes = buildFlatEdgeRoutes(renderEdges);
      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      for (const edge of renderEdges) {
        const active = selected && (edge.sourceId === selected.id || edge.targetId === selected.id);
        const hot = hover && (edge.sourceId === hover.id || edge.targetId === hover.id);
        const alpha = active ? 0.78 : hot ? 0.48 : edge.relation === "module-call" ? 0.42 : edge.relation === "contains" ? 0.2 : edge.relation === "defines" ? 0.08 : 0.14;
        const stroke = edge.relation === "contains"
          ? `rgba(138,180,255,${alpha})`
          : edge.relation === "module-call"
            ? `rgba(255,224,130,${alpha})`
          : edge.relation === "defines"
            ? `rgba(128,232,218,${alpha})`
            : edge.ambiguous || edge.relation === "ambiguous"
              ? `rgba(255,224,130,${alpha})`
              : `rgba(128,232,218,${alpha})`;
        ctx.strokeStyle = stroke;
        ctx.lineWidth = (active ? 2.4 : edge.relation === "module-call" ? Math.min(2.6, 1.15 + Math.log2(edge.weight + 1) * 0.24) : edge.relation === "defines" ? 0.65 : Math.min(2.2, 0.7 + Math.log2(edge.weight + 1) * 0.25)) / state.scale;
        const route = routes.get(edge);
        if (!route) continue;
        ctx.beginPath();
        ctx.moveTo(route.start.x, route.start.y);
        if (route.points) {
          for (const point of route.points) ctx.lineTo(point.x, point.y);
        } else {
          ctx.bezierCurveTo(route.controlA.x, route.controlA.y, route.controlB.x, route.controlB.y, route.end.x, route.end.y);
        }
        ctx.stroke();
        if (edge.relation === "module-call" || active) {
          drawArrowHeadAt(route.arrowFrom, route.end, stroke, active ? 7 : 5);
        }
      }
      ctx.restore();
    }

    function buildFlatEdgeRoutes(edges) {
      const sourceOffsets = assignEdgePortOffsets(edges, "source");
      const targetOffsets = assignEdgePortOffsets(edges, "target");
      const tracks = assignModuleTracks(edges);
      const duplicateLanes = assignDuplicateEdgeLanes(edges);
      const routes = new Map();
      for (const edge of edges) {
        const start = edgeAnchor(edge.source, edge.target, sourceOffsets.get(edge) || 0);
        const end = edgeAnchor(edge.target, edge.source, targetOffsets.get(edge) || 0);
        const track = tracks.get(edge);
        if (track && Number.isFinite(track.x)) {
          const direction = Math.sign(end.x - start.x) || 1;
          const neck = Math.min(22, Math.max(10, Math.abs(end.x - start.x) * 0.08));
          const points = [
            { x: start.x + direction * neck, y: start.y },
            { x: start.x + direction * neck, y: track.sourceChannel },
            { x: track.x, y: track.sourceChannel },
            { x: track.x, y: track.targetChannel },
            { x: end.x - direction * neck, y: track.targetChannel },
            { x: end.x - direction * neck, y: end.y },
            end
          ];
          routes.set(edge, { start, end, points, arrowFrom: points[points.length - 2] });
          continue;
        }
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const length = Math.max(1, Math.hypot(dx, dy));
        const lane = duplicateLanes.get(edge) || 0;
        const offsetX = (-dy / length) * lane;
        const offsetY = (dx / length) * lane;
        const controlA = { x: start.x + dx * 0.35 + offsetX, y: start.y + dy * 0.12 + offsetY };
        const controlB = { x: end.x - dx * 0.35 + offsetX, y: end.y - dy * 0.12 + offsetY };
        routes.set(edge, { start, end, controlA, controlB, arrowFrom: controlB });
      }
      return routes;
    }

    function assignEdgePortOffsets(edges, endpoint) {
      const groups = new Map();
      for (const edge of edges) {
        const node = endpoint === "source" ? edge.source : edge.target;
        const other = endpoint === "source" ? edge.target : edge.source;
        if (!groups.has(node.id)) groups.set(node.id, []);
        groups.get(node.id).push({ edge, other });
      }
      const offsets = new Map();
      for (const entries of groups.values()) {
        entries.sort((a, b) => a.other.y - b.other.y || a.other.x - b.other.x || String(a.edge.id).localeCompare(String(b.edge.id)));
        const node = endpoint === "source" ? entries[0].edge.source : entries[0].edge.target;
        const span = node.nodeKind === "module" ? 25 : node.nodeKind === "file" ? 17 : Math.max(8, Number(node.r || 5) * 1.5);
        entries.forEach((entry, index) => {
          const ratio = entries.length === 1 ? 0 : index / (entries.length - 1) - 0.5;
          offsets.set(entry.edge, ratio * span);
        });
      }
      return offsets;
    }

    function assignModuleTracks(edges) {
      const groups = new Map();
      for (const edge of edges) {
        if (edge.relation !== "module-call") continue;
        const direction = Math.sign(edge.target.x - edge.source.x);
        if (!direction) continue;
        const key = `${Number(edge.source.layer || 0)}:${Number(edge.target.layer || 0)}:${direction}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(edge);
      }
      const tracks = new Map();
      const bands = [...state.flatLayers].sort((a, b) => a.minX - b.minX);
      const bandByLayer = new Map(bands.map(band => [Number(band.layer), band]));
      for (const group of groups.values()) {
        group.sort((a, b) => a.source.y - b.source.y || a.target.y - b.target.y || String(a.id).localeCompare(String(b.id)));
        const direction = Math.sign(group[0].target.x - group[0].source.x) || 1;
        const sourceLayer = Number(group[0].source.layer || 0);
        const targetLayer = Number(group[0].target.layer || 0);
        const sourceBand = bandByLayer.get(sourceLayer);
        const targetBand = bandByLayer.get(targetLayer);
        const nextBand = direction > 0
          ? bands.find(band => sourceBand && band.minX > sourceBand.maxX)
          : [...bands].reverse().find(band => sourceBand && band.maxX < sourceBand.minX);
        const startBoundary = sourceBand
          ? (direction > 0 ? sourceBand.maxX : sourceBand.minX)
          : (direction > 0
            ? Math.max(...group.map(edge => edge.source.x + structuralNodeWidth(edge.source) / 2))
            : Math.min(...group.map(edge => edge.source.x - structuralNodeWidth(edge.source) / 2)));
        const laneBoundary = nextBand || targetBand;
        const endBoundary = laneBoundary
          ? (direction > 0 ? laneBoundary.minX : laneBoundary.maxX)
          : (direction > 0
            ? Math.min(...group.map(edge => edge.target.x - structuralNodeWidth(edge.target) / 2))
            : Math.max(...group.map(edge => edge.target.x + structuralNodeWidth(edge.target) / 2)));
        const gap = endBoundary - startBoundary;
        if (Math.sign(gap) !== direction || Math.abs(gap) < 36) continue;
        group.forEach((edge, index) => {
          const x = startBoundary + gap * ((index + 1) / (group.length + 1));
          tracks.set(edge, {
            x,
            sourceChannel: findClearHorizontalChannel(edge.source, edge.target, edge.source.x, x, index),
            targetChannel: findClearHorizontalChannel(edge.target, edge.source, x, edge.target.x, index + group.length)
          });
        });
      }
      return tracks;
    }

    function findClearHorizontalChannel(node, other, fromX, toX, slot) {
      const height = node.nodeKind === "module" ? 34 : node.nodeKind === "file" ? 25 : (Number(node.r || 5) + 4) * 2;
      const preferredSign = stableUnit(`${node.id}:${other.id}`, 17) >= 0.5 ? 1 : -1;
      const minX = Math.min(fromX, toX);
      const maxX = Math.max(fromX, toX);
      for (let ring = 0; ring < 120; ring++) {
        const sign = ring % 2 === 0 ? preferredSign : -preferredSign;
        const distance = height / 2 + 12 + (Math.floor(ring / 2) + slot) * 7;
        const candidate = node.y + sign * distance;
        if (horizontalChannelClear(candidate, minX, maxX, node.id, other.id)) return candidate;
      }
      const visibleBounds = state.visibleNodes
        .filter(candidate => candidate.nodeKind === "module" || candidate.nodeKind === "file")
        .map(nodeBounds);
      return Math.max(...visibleBounds.map(bounds => bounds.maxY), node.y) + 24 + slot * 7;
    }

    function horizontalChannelClear(y, minX, maxX, sourceId, targetId) {
      for (const candidate of state.visibleNodes) {
        if (candidate.id === sourceId || candidate.id === targetId) continue;
        if (candidate.nodeKind !== "module" && candidate.nodeKind !== "file") continue;
        const bounds = nodeBounds(candidate);
        const crossesX = bounds.maxX + 7 >= minX && bounds.minX - 7 <= maxX;
        const crossesY = y >= bounds.minY - 7 && y <= bounds.maxY + 7;
        if (crossesX && crossesY) return false;
      }
      return true;
    }

    function assignDuplicateEdgeLanes(edges) {
      const groups = new Map();
      for (const edge of edges) {
        const key = `${edge.sourceId}\u0000${edge.targetId}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(edge);
      }
      const lanes = new Map();
      for (const group of groups.values()) {
        group.sort((a, b) => String(a.relation).localeCompare(String(b.relation)) || String(a.id).localeCompare(String(b.id)));
        group.forEach((edge, index) => lanes.set(edge, (index - (group.length - 1) / 2) * 12));
      }
      return lanes;
    }

    function edgeAnchor(node, other, offset) {
      const dx = other.x - node.x;
      const dy = other.y - node.y;
      if (node.nodeKind === "module" || node.nodeKind === "file") {
        const width = structuralNodeWidth(node);
        const height = node.nodeKind === "module" ? 34 : 25;
        if (Math.abs(dx) >= Math.abs(dy)) {
          return {
            x: node.x + (Math.sign(dx) || 1) * width / 2,
            y: node.y + clamp(offset, -height * 0.42, height * 0.42)
          };
        }
        return {
          x: node.x + clamp(offset, -width * 0.42, width * 0.42),
          y: node.y + (Math.sign(dy) || 1) * height / 2
        };
      }
      const length = Math.max(1, Math.hypot(dx, dy));
      const unitX = dx / length;
      const unitY = dy / length;
      const radius = Number(node.r || 5) + 2;
      return {
        x: node.x + unitX * radius - unitY * offset,
        y: node.y + unitY * radius + unitX * offset
      };
    }

    function drawArrowHeadAt(source, target, color, size) {
      const angle = Math.atan2(target.y - source.y, target.x - source.x);
      const x = target.x;
      const y = target.y;
      const scaledSize = size / state.scale;
      ctx.save();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(
        x - Math.cos(angle - Math.PI / 6) * scaledSize,
        y - Math.sin(angle - Math.PI / 6) * scaledSize
      );
      ctx.lineTo(
        x - Math.cos(angle + Math.PI / 6) * scaledSize,
        y - Math.sin(angle + Math.PI / 6) * scaledSize
      );
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }

    function drawNodes(selected, hover, highlight) {
      const labelsAllowed = state.showLabels && state.visibleNodes.length < 900;
      ctx.save();
      for (const node of state.visibleNodes) {
        const isSelected = selected && selected.id === node.id;
        const isHover = hover && hover.id === node.id;
        const dim = selected && !highlight.has(node.id);
        if (node.nodeKind === "module" || node.nodeKind === "file") {
          drawStructuralNode(node, { selected: isSelected, hover: isHover, dim });
          continue;
        }
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

    function drawStructuralNode(node, flags) {
      const width = structuralNodeWidth(node);
      const height = node.nodeKind === "module" ? 34 : 25;
      node.hitW = width;
      node.hitH = height;
      const x = node.x - width / 2;
      const y = node.y - height / 2;
      const alpha = flags.dim ? 0.38 : 1;
      ctx.save();
      ctx.globalAlpha = alpha;
      roundRect(ctx, x - 4 / state.scale, y - 4 / state.scale, width + 8 / state.scale, height + 8 / state.scale, 4);
      ctx.fillStyle = flags.selected
        ? "rgba(138,180,255,0.18)"
        : flags.hover
          ? "rgba(128,232,218,0.14)"
          : "rgba(8,22,30,0.62)";
      ctx.fill();
      const gradient = ctx.createLinearGradient(x, y, x, y + height);
      gradient.addColorStop(0, node.nodeKind === "module" ? "rgba(30,69,95,0.92)" : "rgba(17,39,54,0.92)");
      gradient.addColorStop(1, node.nodeKind === "module" ? "rgba(8,21,35,0.96)" : "rgba(6,16,26,0.96)");
      roundRect(ctx, x, y, width, height, 4);
      ctx.fillStyle = gradient;
      ctx.fill();
      ctx.strokeStyle = flags.selected ? "#ffffff" : flags.hover ? "rgba(236,255,251,0.82)" : "rgba(128,232,218,0.28)";
      ctx.lineWidth = (flags.selected ? 2 : 1) / state.scale;
      ctx.stroke();
      ctx.font = `${node.nodeKind === "module" ? 11 : 10}px ${getComputedStyle(document.documentElement).getPropertyValue("--mono")}`;
      ctx.fillStyle = flags.selected ? "#ffffff" : "rgba(236,255,251,0.86)";
      ctx.textBaseline = "middle";
      const label = node.nodeKind === "module" ? String(node.label || node.name).toUpperCase() : shortPath(node.file || node.name);
      const metric = node.nodeKind === "module" ? `${node.fileCount || 0} files` : `${node.functionCount || 0} fn`;
      ctx.fillText(trimCanvasText(label, width - 62), x + 10, node.y);
      ctx.fillStyle = "rgba(138,180,255,0.78)";
      ctx.font = `9px ${getComputedStyle(document.documentElement).getPropertyValue("--mono")}`;
      ctx.textAlign = "right";
      ctx.fillText(metric, x + width - 9, node.y);
      ctx.textAlign = "left";
      ctx.restore();
    }

    function drawLabel(node, strong) {
      const text = node.label || node.name;
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
      const architecture = ((state.graph || {}).architecture || {}).summary || {};
      els.mFiles.textContent = fmt(stats.filesScanned || 0);
      els.mFunctions.textContent = fmt(stats.functionsFound || 0);
      els.mEdges.textContent = fmt(stats.internalEdges || 0);
      els.mVisible.textContent = fmt(state.visibleNodes.length || 0);
      if (els.mModules) els.mModules.textContent = fmt(architecture.moduleCount || 0);
      if (els.mDependencies) els.mDependencies.textContent = fmt(architecture.dependencyCount || 0);
      els.visibleNodeCount.textContent = fmt(state.visibleNodes.length || 0);
      els.visibleEdgeCount.textContent = fmt(state.visibleEdges.length || 0);
      if (els.visibleModuleCount) {
        els.visibleModuleCount.textContent = fmt(state.visibleNodes.filter(node => node.nodeKind === "module").length);
      }
    }

    function renderArchitectureHealth() {
      if (!els.architectureHealth) return;
      const architecture = (state.graph || {}).architecture || {};
      const summary = architecture.summary || {};
      const scanSignals = summary.scanSignals || [];
      const modules = architecture.modules || [];
      const moduleSignalCount = modules.reduce((total, item) => total + (item.signals || []).length, 0);
      const scanClear = Number(summary.parseErrorCount || 0) === 0
        && !scanSignals.some(signal => signal.kind === "readErrors" || signal.kind === "maxFilesHit");
      const statusClass = scanClear ? "is-observed" : "is-attention";
      const statusText = scanClear ? "scan complete" : "coverage attention";
      els.architectureHealth.innerHTML = `
        <div class="repo-health-status ${statusClass}">
          <strong>${escapeHtml(statusText)}</strong>
          <span>${fmt(summary.layerCount || 0)} dependency layers</span>
        </div>
        <div class="repo-health-grid">
          <div><strong>${fmt(summary.cyclicModuleCount || 0)}</strong><span>modules in cycles</span></div>
          <div><strong>${fmt(summary.hotspotCount || 0)}</strong><span>high-degree functions</span></div>
          <div><strong>${fmt(summary.isolatedFunctionCount || 0)}</strong><span>isolated functions</span></div>
          <div><strong>${fmt(moduleSignalCount)}</strong><span>module review signals</span></div>
          <div><strong>${fmt((state.layoutDiagnostics.flat || {}).overlapPairs || 0)}</strong><span>flat layout overlaps</span></div>
          <div><strong>${fmt(((state.layoutDiagnostics.isometric || {}).overlapPairs || 0) + ((state.layoutDiagnostics.spatial || {}).overlapPairs || 0))}</strong><span>3D layout overlaps</span></div>
        </div>
        <div class="repo-health-signals">
          ${scanSignals.length
            ? scanSignals.map(signal => `<span class="repo-health-signal" data-severity="${escapeHtml(signal.severity || "review")}">${escapeHtml(signal.kind)} ${fmt(signal.count || 0)}</span>`).join("")
            : '<span class="repo-health-signal" data-severity="observed">No scanner errors observed</span>'}
        </div>
        <p class="repo-health-caveat">Signals identify review surfaces. They do not prove a defect, dead code, or runtime reachability.</p>
      `;
    }

    function renderAiPacket() {
      const packet = {
        schemaVersion: state.graph?.schemaVersion,
        generatedAt: state.graph?.generatedAt,
        root: state.graph?.root,
        stats: state.graph?.stats,
        architecture: state.graph?.architecture,
        layout: state.layoutDiagnostics,
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
      if (node.nodeKind === "module") {
        renderModulePanel(node);
        return;
      }
      if (node.nodeKind === "file") {
        renderFilePanel(node);
        return;
      }
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

    function renderModulePanel(node) {
      const files = state.nodes
        .filter(candidate => candidate.nodeKind === "file" && candidate.module === node.module)
        .sort((a, b) => Number(b.functionCount || 0) - Number(a.functionCount || 0));
      els.selectedPanel.innerHTML = `
        <div class="selected-title">
          <h2>${escapeHtml(node.name)}</h2>
          <span class="badge">${node.fileCount || 0} files</span>
        </div>
        <div class="kv"><div class="k">Functions</div><div class="v">${fmt(node.functionCount || 0)}</div></div>
        <div class="kv"><div class="k">Layer</div><div class="v">${fmt(node.layer || 0)}</div></div>
        <div class="kv"><div class="k">Flow</div><div class="v">${fmt(node.inboundDependencies || 0)} in / ${fmt(node.outboundDependencies || 0)} out</div></div>
        <div class="kv"><div class="k">Cycle</div><div class="v">${node.cyclic ? "Detected module cycle" : "No cross-module cycle detected"}</div></div>
        <div class="kv"><div class="k">Internal edges</div><div class="v">${fmt((node.inboundInternalEdges || 0) + (node.outboundInternalEdges || 0))}</div></div>
        <div class="kv"><div class="k">Role</div><div class="v">Module boundary / file cluster</div></div>
      `;
      if ((node.signals || []).length) {
        const signals = document.createElement("div");
        signals.className = "repo-health-signals section";
        signals.innerHTML = (node.signals || [])
          .map(signal => `<span class="repo-health-signal" data-severity="${escapeHtml(signal.severity || "review")}">${escapeHtml(signal.kind)} ${fmt(signal.count || 0)}</span>`)
          .join("");
        els.selectedPanel.appendChild(signals);
      }
      els.selectedPanel.appendChild(sectionList("Files In Module", files));
    }

    function renderFilePanel(node) {
      const functions = state.nodes
        .filter(candidate => candidate.nodeKind === "function" && candidate.file === node.file)
        .sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0));
      els.selectedPanel.innerHTML = `
        <div class="selected-title">
          <h2>${escapeHtml(basename(node.file))}</h2>
          <span class="badge">${node.functionCount || 0} fn</span>
        </div>
        <div class="kv"><div class="k">File</div><div class="v">${escapeHtml(node.file)}</div></div>
        <div class="kv"><div class="k">Module</div><div class="v">${escapeHtml(node.module || ".")}</div></div>
        <div class="kv"><div class="k">Language</div><div class="v">${escapeHtml(node.lang || "")}</div></div>
        <div class="kv"><div class="k">Internal edges</div><div class="v">${fmt((node.inboundInternalEdges || 0) + (node.outboundInternalEdges || 0))}</div></div>
      `;
      els.selectedPanel.appendChild(sectionList("Functions In File", functions));
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
          const metric = node.nodeKind === "file" ? `${node.functionCount || 0} fn` : `${node.degree || 0}`;
          const path = node.nodeKind === "file" ? node.file : `${shortPath(node.file)}:${node.line || ""}`;
          row.innerHTML = `<div class="mini-title"><span>${escapeHtml(node.name)}</span><span class="badge">${escapeHtml(metric)}</span></div><div class="path">${escapeHtml(path)}</div>`;
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
      rebuildVisibleGraph(false);
      const node = state.nodeById.get(state.selectedId);
      if (center && state.projection === "flat" && nodeHasLayout(node)) {
        state.panX = -node.x * state.scale;
        state.panY = -node.y * state.scale;
        state.scale = Math.max(state.scale, 0.72);
      } else if (center && node && state.threeView) {
        state.threeView.focus(node.id);
      }
      renderSelectedPanel();
      renderHotspots();
      if (node) {
        state.panels.inspect = true;
        state.panelFocus = "inspect";
        openRepoDetail("selected");
        applyPanelVisibility(false);
        updateDrawerSizing();
      }
      syncThreeView();
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
      if (node) {
        selectNode(node.id, false);
      } else {
        state.panning = true;
        els.canvas.classList.add("dragging");
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
      state.panning = false;
      els.canvas.classList.remove("dragging");
      requestDraw();
    }

    function findNodeAt(screenX, screenY) {
      const pos = screenToWorld(screenX, screenY);
      let best = null;
      let bestDist = Infinity;
      for (const node of state.visibleNodes) {
        if (node.nodeKind === "module" || node.nodeKind === "file") {
          const width = node.hitW || structuralNodeWidth(node);
          const height = node.hitH || (node.nodeKind === "module" ? 34 : 25);
          if (Math.abs(pos.x - node.x) <= width / 2 + 7 / state.scale && Math.abs(pos.y - node.y) <= height / 2 + 7 / state.scale) {
            const dist = Math.hypot(pos.x - node.x, pos.y - node.y);
            if (dist < bestDist) {
              best = node;
              bestDist = dist;
            }
          }
          continue;
        }
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
      if (state.projection !== "flat") {
        state.threeView?.fit();
        return;
      }
      const nodes = state.visibleNodes;
      if (!nodes.length) return;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const node of nodes) {
        const bounds = nodeBounds(node);
        minX = Math.min(minX, bounds.minX);
        minY = Math.min(minY, bounds.minY);
        maxX = Math.max(maxX, bounds.maxX);
        maxY = Math.max(maxY, bounds.maxY);
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
      state.threeView?.resize();
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

    function relatedIds(node) {
      const ids = new Set();
      if (!node) return ids;
      addNeighborhood(node, ids);
      return ids;
    }

    function requestDraw() {
      state.needsDraw = true;
      if (state.projection !== "flat") {
        state.threeView?.render();
        return;
      }
      if (state.frameRequest) return;
      state.frameRequest = requestAnimationFrame(() => {
        state.frameRequest = 0;
        if (!state.needsDraw || state.projection !== "flat") return;
        draw();
        state.needsDraw = false;
      });
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
      const syncStageChromeHeight = () => {
        const height = Math.ceil(bar.getBoundingClientRect().height);
        els.stage.style.setProperty("--stage-chrome-height", `${height}px`);
        resizeCanvas();
      };
      if (typeof ResizeObserver !== "undefined") {
        const barObserver = new ResizeObserver(syncStageChromeHeight);
        barObserver.observe(bar);
      }
      syncStageChromeHeight();
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

    function edgeDrawLimit(edgeCount, nodeCount) {
      if (nodeCount > 700) return Math.min(edgeCount, 2400);
      if (nodeCount > 500) return Math.min(edgeCount, 3200);
      return Math.min(edgeCount, 5200);
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

    function basename(path) {
      const parts = String(path || "").split("/");
      return parts[parts.length - 1] || String(path || "");
    }

    function structuralNodeWidth(node) {
      const label = node.nodeKind === "module" ? String(node.label || node.name).toUpperCase() : shortPath(node.file || node.name);
      return clamp(82 + label.length * 6.2, node.nodeKind === "module" ? 132 : 118, node.nodeKind === "module" ? 260 : 230);
    }

    function nodeBounds(node) {
      if (node.nodeKind === "module" || node.nodeKind === "file") {
        const width = node.hitW || structuralNodeWidth(node);
        const height = node.hitH || (node.nodeKind === "module" ? 34 : 25);
        return {
          minX: node.x - width / 2,
          minY: node.y - height / 2,
          maxX: node.x + width / 2,
          maxY: node.y + height / 2
        };
      }
      const radius = node.r || 8;
      return {
        minX: node.x - radius,
        minY: node.y - radius,
        maxX: node.x + radius,
        maxY: node.y + radius
      };
    }

    function trimCanvasText(text, maxWidth) {
      const raw = String(text || "");
      if (ctx.measureText(raw).width <= maxWidth) return raw;
      let trimmed = raw;
      while (trimmed.length > 4 && ctx.measureText(`${trimmed}...`).width > maxWidth) {
        trimmed = trimmed.slice(0, -1);
      }
      return `${trimmed}...`;
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
