(() => {
  const root = document.querySelector("[data-fractal-memory]");
  if (!root) return;

  const scoped = (name) => root.querySelector(`[data-fm="${name}"]`) || document.getElementById(name);
  const canvas = scoped("cortexCanvas");
  if (!canvas) return;
  const presentationRoot = root.closest(".repo-review-root");

  const STORAGE_KEY = "parallm.fractalMemory.prototype.v1";
  const KNOWLEDGEBASE_API = "/v1/knowledgebase/graph?includeRepo=1&maxEvents=30&maxSteps=30&maxArtifacts=24&maxRepoNodes=220&maxRepoFiles=2500&maxFileBytes=500000";
  const ctx = canvas.getContext("2d", { alpha: false });
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
  let activeWindowDrag = null;

  const roleColors = {
    lead: "#6bd394",
    sceptic: "#ee7f9d",
    builder: "#54d7d4",
    operator: "#e7be60",
    security: "#b59bff",
    user: "#8fb4ff"
  };

  const rolePriority = {
    lead: ["synthesis", "objective", "decision", "answer", "memory"],
    sceptic: ["risk", "contradiction", "failure", "unknown", "pressure"],
    builder: ["implementation", "scheduler", "artifact", "parser", "execution"],
    operator: ["telemetry", "recovery", "state", "checkpoint", "queue"],
    security: ["privacy", "boundary", "policy", "audit", "secret"],
    user: ["workflow", "friction", "clarity", "trust", "surface"]
  };

  const seed = {
    schemaVersion: "fractal-memory-highway/v0",
    nodes: {
      objective: {
        id: "objective",
        title: "Active Objective",
        type: "anchor",
        layer: 0,
        summary: "The operator asks for a runnable knowledgebase where each advisor lane has its own evidence trail through shared procedure and run context.",
        evidence: ["User intent: advisor-specific trails", "Constraint: AI-readable knowledge paths", "Target: execution plus recall, not static storage"],
        doors: [
          { to: "lane_keys", relation: "session keys", weight: 1.0 },
          { to: "execution_ledger", relation: "work creates knowledge", weight: 0.96 },
          { to: "retrieval_floor", relation: "knowledge feeds work", weight: 0.9 },
          { to: "cortex_map", relation: "visual topology", weight: 0.86 }
        ]
      },
      lane_keys: {
        id: "lane_keys",
        title: "Lane Key Registry",
        type: "keyspace",
        layer: 1,
        summary: "Every main/advisor thread owns a key, a private stance, and a trail of visited knowledge nodes.",
        evidence: ["Keys separate viewpoint-local context", "Shared nodes allow inevitable cross-lane correlation"],
        doors: [
          { to: "private_stance", relation: "local stance", weight: 0.94 },
          { to: "trail_marks", relation: "visited path", weight: 0.9 },
          { to: "correlation_engine", relation: "shared intersections", weight: 0.86 }
        ]
      },
      private_stance: {
        id: "private_stance",
        title: "Private Lane Stance",
        type: "interior",
        layer: 2,
        summary: "A lane can hold local notes, pressure, assumptions, and unresolved points without flattening the shared knowledgebase.",
        evidence: ["Supports adversarial independence", "Prevents every lane from averaging into the same view"],
        doors: [
          { to: "contradiction_memory", relation: "pressure path", weight: 0.9 },
          { to: "artifact_receipts", relation: "evidence path", weight: 0.78 }
        ]
      },
      trail_marks: {
        id: "trail_marks",
        title: "Key Trail",
        type: "trail",
        layer: 2,
        summary: "A durable sequence of opened nodes: what this lane saw, in what order, and where it decided to go next.",
        evidence: ["Trail becomes advisor context", "Trail can be replayed into future prompts"],
        doors: [
          { to: "checkpoint_state", relation: "resume point", weight: 0.92 },
          { to: "ai_packet", relation: "machine readout", weight: 0.82 }
        ]
      },
      execution_ledger: {
        id: "execution_ledger",
        title: "Execution Ledger",
        type: "eventspace",
        layer: 1,
        summary: "Provider calls, tool calls, tests, edits, reviews, and scheduler decisions become addressable knowledge nodes.",
        evidence: ["ParaLLM already logs jobs, artifacts, outputs, steps", "Execution nodes are born from doing work"],
        doors: [
          { to: "artifact_receipts", relation: "receipt", weight: 0.94 },
          { to: "checkpoint_state", relation: "resume", weight: 0.9 },
          { to: "scheduler_spine", relation: "dispatch", weight: 0.86 },
          { to: "telemetry_field", relation: "observe", weight: 0.74 }
        ]
      },
      retrieval_floor: {
        id: "retrieval_floor",
        title: "Raw Recall Floor",
        type: "evidence",
        layer: 1,
        summary: "Derived summaries and labels can rank or route, but raw evidence remains searchable as the floor.",
        evidence: ["Avoids lossy summary gates", "Lets lanes cite exact prior evidence"],
        doors: [
          { to: "compressed_pointers", relation: "ranking hint", weight: 0.9 },
          { to: "artifact_receipts", relation: "exact source", weight: 0.82 },
          { to: "ai_packet", relation: "context pack", weight: 0.76 }
        ]
      },
      compressed_pointers: {
        id: "compressed_pointers",
        title: "Compressed Pointer Layer",
        type: "index",
        layer: 2,
        summary: "Small references that open into larger interiors: summaries, tags, hotspots, source spans, and link hints.",
        evidence: ["Outside is compact", "Inside opens into wider context"],
        doors: [
          { to: "fractal_doors", relation: "open interior", weight: 0.96 },
          { to: "retrieval_floor", relation: "never replaces raw", weight: 0.86 }
        ]
      },
      fractal_doors: {
        id: "fractal_doors",
        title: "Linked Knowledge Spaces",
        type: "portal",
        layer: 3,
        summary: "A node can open into another navigable knowledge space, which can contain additional linked spaces.",
        evidence: ["Compact procedures can open into wider evidence", "Linked spaces are not bounded by the parent container"],
        doors: [
          { to: "cortex_map", relation: "rendered topology", weight: 0.82 },
          { to: "correlation_engine", relation: "nonlocal link", weight: 0.78 },
          { to: "execution_ledger", relation: "work loop", weight: 0.72 }
        ]
      },
      correlation_engine: {
        id: "correlation_engine",
        title: "Correlation Engine",
        type: "bridge",
        layer: 2,
        summary: "Lane trails overlap, cross, or approach each other, creating useful pressure between independent viewpoints.",
        evidence: ["Shared nodes reveal agreement", "Adjacent nodes reveal implied contradiction or dependency"],
        doors: [
          { to: "contradiction_memory", relation: "conflict", weight: 0.88 },
          { to: "synthesis_gate", relation: "merge pressure", weight: 0.86 },
          { to: "cortex_map", relation: "visible link map", weight: 0.78 }
        ]
      },
      contradiction_memory: {
        id: "contradiction_memory",
        title: "Contradiction Memory",
        type: "pressure",
        layer: 3,
        summary: "Unresolved disagreements survive across rounds and are reopened when future evidence touches them.",
        evidence: ["Do not average conflicts away", "A sceptic lane needs durable pressure points"],
        doors: [
          { to: "risk_gate", relation: "decision block", weight: 0.92 },
          { to: "artifact_receipts", relation: "prove or clear", weight: 0.82 }
        ]
      },
      artifact_receipts: {
        id: "artifact_receipts",
        title: "Artifact Receipts",
        type: "receipt",
        layer: 2,
        summary: "Exact files, commands, outputs, provider responses, and review artifacts referenced by stable IDs.",
        evidence: ["Human and AI can inspect the same receipt", "A future lane can reopen the node instead of trusting summary"],
        doors: [
          { to: "repo_graph_space", relation: "source map", weight: 0.88 },
          { to: "ai_packet", relation: "portable evidence", weight: 0.78 }
        ]
      },
      checkpoint_state: {
        id: "checkpoint_state",
        title: "Checkpoint State",
        type: "resume",
        layer: 2,
        summary: "Advisor lane state: active node, trail, private note, pending claims, and next candidate doors.",
        evidence: ["Allows lanes to resume without losing local trajectory", "Separates state from final answer"],
        doors: [
          { to: "scheduler_spine", relation: "next runnable", weight: 0.84 },
          { to: "lane_keys", relation: "owner key", weight: 0.78 }
        ]
      },
      scheduler_spine: {
        id: "scheduler_spine",
        title: "Scheduler Spine",
        type: "execution",
        layer: 2,
        summary: "Queues runnable work and chooses which lane or tool node gets compute next.",
        evidence: ["Execution substrate, not boardroom cadence", "Provider calls and local jobs need different rules"],
        doors: [
          { to: "telemetry_field", relation: "health", weight: 0.86 },
          { to: "risk_gate", relation: "limit", weight: 0.76 },
          { to: "execution_ledger", relation: "record", weight: 0.7 }
        ]
      },
      telemetry_field: {
        id: "telemetry_field",
        title: "Telemetry Field",
        type: "observe",
        layer: 3,
        summary: "Latency, cost, retries, stale state, missing evidence, and degraded lanes become visible knowledgebase signals.",
        evidence: ["Operators need failure visibility", "Future agents need health context"],
        doors: [
          { to: "risk_gate", relation: "runtime guard", weight: 0.82 },
          { to: "synthesis_gate", relation: "confidence", weight: 0.72 }
        ]
      },
      risk_gate: {
        id: "risk_gate",
        title: "Risk Gate",
        type: "guard",
        layer: 3,
        summary: "Before action, check policy, safety, provider limits, secret boundaries, and rollback state.",
        evidence: ["Action needs guardrails", "A lane can block execution if risk survives review"],
        doors: [
          { to: "synthesis_gate", relation: "go/no-go", weight: 0.86 },
          { to: "contradiction_memory", relation: "unresolved pressure", weight: 0.76 }
        ]
      },
      repo_graph_space: {
        id: "repo_graph_space",
        title: "Repo Graph Space",
        type: "source",
        layer: 3,
        summary: "Function/file/module graph acts as another interior space, with hotspots and source links as doors.",
        evidence: ["Repo nodes can be evidence", "Graph links shape test impact and refactor path"],
        doors: [
          { to: "artifact_receipts", relation: "source evidence", weight: 0.86 },
          { to: "scheduler_spine", relation: "implementation work", weight: 0.72 }
        ]
      },
      cortex_map: {
        id: "cortex_map",
        title: "Knowledge Map",
        type: "visual",
        layer: 1,
        summary: "A visual projection of independent trails, shared spaces, and linked knowledge paths.",
        evidence: ["Humans see path pressure", "AI reads the same packet as JSON"],
        doors: [
          { to: "ai_packet", relation: "machine mirror", weight: 0.88 },
          { to: "correlation_engine", relation: "trail overlay", weight: 0.8 }
        ]
      },
      ai_packet: {
        id: "ai_packet",
        title: "AI Packet",
        type: "readout",
        layer: 4,
        summary: "Compact state export for an AI lane: selected node, trails, correlations, evidence, and next doors.",
        evidence: ["If the UI can navigate it, an AI should be able to navigate it", "JSON packet is the shared control surface"],
        doors: [
          { to: "synthesis_gate", relation: "final merge", weight: 0.8 },
          { to: "retrieval_floor", relation: "evidence floor", weight: 0.72 }
        ]
      },
      synthesis_gate: {
        id: "synthesis_gate",
        title: "Synthesis Gate",
        type: "merge",
        layer: 4,
        summary: "The lead lane merges pressure only after each key trail has left receipts and unresolved contradictions are named.",
        evidence: ["Single voice final answer", "Internal disagreement remains inspectable"],
        doors: [
          { to: "objective", relation: "answer loop", weight: 0.92 },
          { to: "execution_ledger", relation: "next action", weight: 0.8 }
        ]
      }
    },
    lanes: [
      {
        id: "main",
        name: "Main Thread",
        role: "lead",
        color: roleColors.lead,
        current: "objective",
        trail: ["objective", "lane_keys"],
        note: "Lead keeps the shared answer path coherent while preserving lane pressure.",
        correlations: []
      },
      {
        id: "sceptic",
        name: "Sceptic",
        role: "sceptic",
        color: roleColors.sceptic,
        current: "contradiction_memory",
        trail: ["objective", "retrieval_floor", "compressed_pointers", "fractal_doors", "correlation_engine", "contradiction_memory"],
        note: "Pressure path checks where compressed context could hide loss or stale assumptions.",
        correlations: []
      },
      {
        id: "operator",
        name: "Operator",
        role: "operator",
        color: roleColors.operator,
        current: "scheduler_spine",
        trail: ["objective", "execution_ledger", "checkpoint_state", "scheduler_spine"],
        note: "Operator path cares about resume, queue health, and visible failure state.",
        correlations: []
      }
    ]
  };

  const state = {
    model: loadModel(),
    activeLaneId: "main",
    selectedNodeId: "objective",
    focusNodeId: "",
    scale: 1,
    panX: 0,
    panY: 0,
    dragging: false,
    lastPointer: { x: 0, y: 0 },
    nodePositions: new Map(),
    nodeRadii: new Map(),
    hydratedOnce: false,
    hydrating: false,
    kbPanelFocus: ""
  };

  const els = {
    memoryStatus: scoped("memoryStatus"),
    nodeCount: scoped("nodeCount"),
    laneCount: scoped("laneCount"),
    trailCount: scoped("trailCount"),
    activeLaneName: scoped("activeLaneName"),
    laneList: scoped("laneList"),
    laneNameInput: scoped("laneNameInput"),
    laneRoleInput: scoped("laneRoleInput"),
    spawnBtn: scoped("spawnBtn"),
    forkBtn: scoped("forkBtn"),
    resetBtn: scoped("resetBtn"),
    fitBtn: scoped("fitBtn"),
    focusBtn: scoped("focusBtn"),
    stepBtn: scoped("stepBtn"),
    correlateBtn: scoped("correlateBtn"),
    hydrateBtn: scoped("hydrateBtn"),
    exportBtn: scoped("exportBtn"),
    selectedNodeName: scoped("selectedNodeName"),
    zoomValue: scoped("zoomValue"),
    selectedNodeType: scoped("selectedNodeType"),
    selectedTitle: scoped("selectedTitle"),
    selectedSummary: scoped("selectedSummary"),
    selectedEvidence: scoped("selectedEvidence"),
    doorList: scoped("doorList"),
    trailList: scoped("trailList"),
    laneNoteInput: scoped("laneNoteInput"),
    aiPacket: scoped("aiPacket"),
    copyPacketBtn: scoped("copyPacketBtn")
  };

  init();

  function init() {
    computeLayout();
    bindEvents();
    resizeCanvas();
    fitView();
    render();
    maybeHydrateFromBackend();
  }

  function loadModel() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.schemaVersion === seed.schemaVersion && parsed.nodes && parsed.lanes) {
          return parsed;
        }
      }
    } catch (_) {
      // Seed fallback below.
    }
    return structuredClone(seed);
  }

  function saveModel() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.model));
    } catch (_) {
      // Local storage is optional for this prototype.
    }
  }

  function panelIsVisible() {
    let current = root;
    while (current && current !== document.body) {
      if (current.hidden) {
        return false;
      }
      current = current.parentElement;
    }
    return true;
  }

  function maybeHydrateFromBackend() {
    if (!state.hydratedOnce && panelIsVisible()) {
      hydrateFromBackend({ initial: true });
    }
  }

  async function hydrateFromBackend(options) {
    const settings = options || {};
    if (state.hydrating || (settings.initial && state.hydratedOnce)) {
      return;
    }
    if (!window.fetch) return;
    state.hydrating = true;
    if (els.hydrateBtn) {
      els.hydrateBtn.disabled = true;
    }
    els.memoryStatus.textContent = "syncing knowledgebase...";
    try {
      const response = await fetch(KNOWLEDGEBASE_API, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      const payload = await response.json();
      if (!mergeKnowledgebase(payload)) {
        throw new Error("knowledgebase payload missing nodes");
      }
      saveModel();
      computeLayout();
      if (!state.model.nodes[state.selectedNodeId]) {
        state.selectedNodeId = "objective";
      }
      if (!state.model.lanes.some((lane) => lane.id === state.activeLaneId)) {
        state.activeLaneId = state.model.lanes[0]?.id || "main";
      }
      fitView();
      render();
      updateKnowledgeDrawerSizing();
      const meta = payload.meta || {};
      state.hydratedOnce = true;
      els.memoryStatus.textContent = `synced ${meta.nodeCount || Object.keys(payload.nodes || {}).length} knowledge nodes`;
    } catch (_) {
      els.memoryStatus.textContent = "local knowledgebase ready";
    } finally {
      if (els.hydrateBtn) {
        els.hydrateBtn.disabled = false;
      }
      state.hydrating = false;
    }
  }

  function mergeKnowledgebase(payload) {
    if (!payload || !payload.nodes || typeof payload.nodes !== "object") {
      return false;
    }
    state.model.schemaVersion = payload.schemaVersion || state.model.schemaVersion;
    for (const [id, incoming] of Object.entries(payload.nodes)) {
      if (!incoming || typeof incoming !== "object") continue;
      state.model.nodes[id] = normalizeIncomingNode(id, incoming);
    }
    if (Array.isArray(payload.lanes)) {
      const existingById = new Map(state.model.lanes.map((lane) => [lane.id, lane]));
      for (const incoming of payload.lanes) {
        const normalized = normalizeIncomingLane(incoming);
        if (!normalized) continue;
        const existing = existingById.get(normalized.id);
        if (existing) {
          const note = existing.note && !String(existing.note).toLowerCase().includes("hydrated")
            ? existing.note
            : normalized.note;
          Object.assign(existing, normalized, { note });
        } else {
          state.model.lanes.push(normalized);
          existingById.set(normalized.id, normalized);
        }
      }
    }
    return true;
  }

  function normalizeIncomingNode(id, incoming) {
    const doors = Array.isArray(incoming.doors)
      ? incoming.doors
          .filter((door) => door && typeof door === "object" && door.to)
          .map((door) => ({
            to: String(door.to),
            relation: String(door.relation || "related"),
            weight: Math.max(0.05, Math.min(1, Number(door.weight || 0.5)))
          }))
      : [];
    return {
      id: String(incoming.id || id),
      title: String(incoming.title || id),
      type: String(incoming.type || "knowledge"),
      layer: Number.isFinite(Number(incoming.layer)) ? Number(incoming.layer) : 2,
      summary: String(incoming.summary || ""),
      evidence: Array.isArray(incoming.evidence) ? incoming.evidence.map((item) => String(item)).slice(0, 12) : [],
      doors
    };
  }

  function normalizeIncomingLane(incoming) {
    if (!incoming || typeof incoming !== "object" || !incoming.id) {
      return null;
    }
    const role = String(incoming.role || "lead");
    const trail = Array.isArray(incoming.trail)
      ? incoming.trail.map((item) => String(item)).filter((id) => state.model.nodes[id])
      : [];
    if (!trail.length) {
      trail.push("objective");
    }
    return {
      id: String(incoming.id),
      name: String(incoming.name || incoming.id),
      role,
      color: String(incoming.color || roleColors[role] || roleColors.lead),
      current: state.model.nodes[incoming.current] ? String(incoming.current) : trail[trail.length - 1],
      trail,
      note: String(incoming.note || ""),
      correlations: Array.isArray(incoming.correlations) ? incoming.correlations.slice(-20) : []
    };
  }

  function bindKnowledgePanelEvents() {
    if (!presentationRoot) {
      return;
    }
    installKnowledgeWorkbenchWindows();
    const buttons = Array.from(presentationRoot.querySelectorAll("[data-kb-toggle]"));
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.getAttribute("data-kb-toggle");
        toggleKnowledgePanel(key);
      });
    });
    presentationRoot.querySelectorAll("details.group-card").forEach((details) => {
      details.open = false;
      details.addEventListener("toggle", () => {
        const panel = details.closest("[data-kb-panel]");
        const key = panel?.getAttribute("data-kb-panel") || "";
        if (details.open) {
          state.kbPanelFocus = key;
        }
        window.setTimeout(updateKnowledgeDrawerSizing, 20);
      });
    });
    presentationRoot.addEventListener("click", (event) => {
      const item = event.target.closest(".fm-lane,.fm-door,.mini-link,.item");
      if (!item) {
        return;
      }
      const panel = item.closest("[data-kb-panel]");
      const key = panel?.getAttribute("data-kb-panel") || "";
      if (key) {
        state.kbPanelFocus = key;
        updateKnowledgeDrawerSizing();
      }
    });
    syncKnowledgePanels();
  }

  function installKnowledgeWorkbenchWindows() {
    if (!presentationRoot) {
      return;
    }
    presentationRoot.querySelectorAll("[data-kb-panel]").forEach((panel) => {
      const key = panel.getAttribute("data-kb-panel") || "";
      ensureKnowledgePanelChrome(panel, key === "inspect" ? "Inspector" : "Lanes", key);
    });
    ensureKnowledgeStageChrome();
  }

  function ensureKnowledgePanelChrome(panel, title, key) {
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
      startKnowledgeWindowDrag(event, panel, "panel");
    });
    bar.querySelector("button")?.addEventListener("click", () => {
      collapseKnowledgePanel(key);
    });
    panel.prepend(bar);
  }

  function ensureKnowledgeStageChrome() {
    const stage = canvas.closest(".stage, .fm-stage");
    if (!stage || stage.querySelector(".stage-window-bar")) {
      return;
    }
    const bar = document.createElement("div");
    bar.className = "stage-window-bar";
    bar.innerHTML = `
      <span class="stage-window-title">Knowledge Map</span>
      <div class="stage-window-controls"></div>
      <button class="stage-window-btn" type="button" aria-label="Collapse knowledge map">Min</button>
    `;
    const controls = bar.querySelector(".stage-window-controls");
    const overlay = stage.querySelector(".overlay, .fm-stage-overlay");
    const pills = overlay?.querySelector(".pill-row, .fm-mini-status");
    const actions = overlay?.querySelector(".floating-actions, .fm-tool-row");
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
      startKnowledgeWindowDrag(event, stage, "stage");
    });
    bar.querySelector("button")?.addEventListener("click", () => {
      toggleKnowledgeStageCollapsed(stage);
    });
    stage.appendChild(bar);
    updateKnowledgeWorkbenchBounds();
  }

  function collapseKnowledgePanel(key) {
    if (!presentationRoot || !key) {
      return;
    }
    presentationRoot.classList.remove(key === "inspect" ? "is-kb-inspect-open" : "is-kb-lanes-open");
    if (state.kbPanelFocus === key) {
      state.kbPanelFocus = "";
    }
    syncKnowledgePanels();
    window.setTimeout(() => {
      resizeCanvas();
      draw();
    }, 30);
  }

  function toggleKnowledgeStageCollapsed(stage) {
    if (!stage) {
      return;
    }
    const collapsed = !stage.classList.contains("is-stage-collapsed");
    stage.classList.toggle("is-stage-collapsed", collapsed);
    const button = stage.querySelector(".stage-window-btn");
    if (button) {
      button.textContent = collapsed ? "Open" : "Min";
      button.setAttribute("aria-label", collapsed ? "Expand knowledge map" : "Collapse knowledge map");
    }
    window.setTimeout(() => {
      resizeCanvas();
      updateKnowledgeWorkbenchBounds();
      draw();
    }, 40);
  }

  function startKnowledgeWindowDrag(event, target, kind) {
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
      offsetX: event.clientX - targetRect.left,
      offsetY: event.clientY - targetRect.top
    };
    target.classList.add("is-window-dragging");
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function onKnowledgeWindowMove(event) {
    if (!activeWindowDrag) {
      return;
    }
    const { target, kind, offsetX, offsetY } = activeWindowDrag;
    const layout = target.closest(".layout");
    if (!layout) {
      endKnowledgeWindowDrag();
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
    updateKnowledgeWorkbenchBounds();
  }

  function endKnowledgeWindowDrag() {
    if (!activeWindowDrag) {
      return;
    }
    activeWindowDrag.target.classList.remove("is-window-dragging");
    activeWindowDrag = null;
    resizeCanvas();
    updateKnowledgeDrawerSizing();
    updateKnowledgeWorkbenchBounds();
    draw();
  }

  function updateKnowledgeWorkbenchBounds() {
    if (!presentationRoot) {
      return;
    }
    const layout = presentationRoot.querySelector(".layout");
    if (!layout) {
      return;
    }
    const windows = Array.from(layout.querySelectorAll(".stage,[data-kb-panel]"))
      .filter((element) => !element.hidden && getComputedStyle(element).display !== "none");
    let bottom = 0;
    windows.forEach((element) => {
      bottom = Math.max(bottom, element.offsetTop + element.offsetHeight + 16);
    });
    layout.style.setProperty("--workbench-height", `${Math.ceil(bottom)}px`);
  }

  function toggleKnowledgePanel(key) {
    if (!presentationRoot || !key) {
      return;
    }
    const className = key === "inspect" ? "is-kb-inspect-open" : "is-kb-lanes-open";
    presentationRoot.classList.toggle(className);
    if (!presentationRoot.classList.contains(className) && state.kbPanelFocus === key) {
      state.kbPanelFocus = "";
    } else if (presentationRoot.classList.contains(className)) {
      state.kbPanelFocus = key;
    }
    syncKnowledgePanels();
    window.setTimeout(() => {
      resizeCanvas();
      render();
      updateKnowledgeDrawerSizing();
    }, 30);
  }

  function openKnowledgePanel(key) {
    if (!presentationRoot || !key) {
      return;
    }
    presentationRoot.classList.add(key === "inspect" ? "is-kb-inspect-open" : "is-kb-lanes-open");
    state.kbPanelFocus = key;
    syncKnowledgePanels();
  }

  function openKnowledgeDetail(name) {
    if (!presentationRoot || !name) {
      return;
    }
    const details = presentationRoot.querySelector(`[data-kb-detail="${name}"]`);
    if (details) {
      details.open = true;
    }
  }

  function updateKnowledgeDrawerSizing() {
    if (!presentationRoot) {
      return;
    }
    const stack = presentationRoot.querySelector(".drawer-stack");
    if (!stack) {
      return;
    }
    const stackHeight = Math.max(180, stack.clientHeight || 640);
    const openPanels = Array.from(presentationRoot.querySelectorAll("[data-kb-panel]")).filter((panel) => !panel.hidden);
    const hasFocus = Boolean(state.kbPanelFocus && openPanels.some((panel) => panel.getAttribute("data-kb-panel") === state.kbPanelFocus));
    stack.classList.toggle("has-drawer-focus", hasFocus);
    openPanels.forEach((panel) => {
      const key = panel.getAttribute("data-kb-panel") || "";
      const scroll = panel.querySelector(".scroll");
      const contentHeight = Math.ceil((scroll?.scrollHeight || panel.scrollHeight || 0) + 2);
      const focused = hasFocus && key === state.kbPanelFocus;
      const maxRatio = focused ? (openPanels.length > 1 ? 0.74 : 0.9) : (hasFocus ? 0.24 : 0.62);
      const minHeight = focused ? 180 : 76;
      const desired = Math.min(stackHeight * maxRatio, Math.max(minHeight, contentHeight));
      panel.style.setProperty("--window-h", `${Math.round(desired)}px`);
      panel.classList.toggle("is-drawer-focus", focused);
    });
    updateKnowledgeWorkbenchBounds();
  }

  function syncKnowledgePanels() {
    if (!presentationRoot) {
      return;
    }
    const panelState = {
      lanes: presentationRoot.classList.contains("is-kb-lanes-open"),
      inspect: presentationRoot.classList.contains("is-kb-inspect-open")
    };
    presentationRoot.querySelectorAll("[data-kb-panel]").forEach((panel) => {
      const key = panel.getAttribute("data-kb-panel");
      panel.hidden = !panelState[key];
    });
    presentationRoot.querySelectorAll("[data-kb-toggle]").forEach((button) => {
      const key = button.getAttribute("data-kb-toggle");
      const active = Boolean(panelState[key]);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    updateKnowledgeDrawerSizing();
  }

  function bindEvents() {
    window.addEventListener("resize", () => {
      resizeCanvas();
      render();
    });
    window.addEventListener("fractal-memory:layout", () => {
      resizeCanvas();
      fitView();
      render();
      maybeHydrateFromBackend();
    });
    bindKnowledgePanelEvents();
    canvas.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointermove", onKnowledgeWindowMove);
    window.addEventListener("pointerup", endKnowledgeWindowDrag);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("dblclick", () => {
      const nodeId = nearestNode(state.lastPointer.x, state.lastPointer.y);
      if (nodeId) enterNode(nodeId);
    });

    els.spawnBtn.addEventListener("click", () => spawnLane(false));
    els.forkBtn.addEventListener("click", () => spawnLane(true));
    els.resetBtn.addEventListener("click", resetSeed);
    els.fitBtn.addEventListener("click", () => {
      fitView();
      render();
    });
    els.focusBtn.addEventListener("click", () => {
      state.focusNodeId = state.focusNodeId ? "" : state.selectedNodeId;
      computeLayout();
      fitView();
      render();
    });
    els.stepBtn.addEventListener("click", stepActiveLane);
    els.correlateBtn.addEventListener("click", correlateActiveLane);
    if (els.hydrateBtn) {
      els.hydrateBtn.addEventListener("click", () => hydrateFromBackend({ manual: true }));
    }
    els.exportBtn.addEventListener("click", exportPacket);
    els.copyPacketBtn.addEventListener("click", copyPacket);
    els.laneNoteInput.addEventListener("input", () => {
      const lane = activeLane();
      lane.note = els.laneNoteInput.value;
      saveModel();
      renderPacketOnly();
    });
    if (typeof ResizeObserver !== "undefined") {
      const stage = canvas.closest(".stage, .fm-stage");
      if (stage) {
        const observer = new ResizeObserver(() => {
          resizeCanvas();
          updateKnowledgeWorkbenchBounds();
          draw();
        });
        observer.observe(stage);
        presentationRoot?.querySelectorAll("[data-kb-panel]").forEach((panel) => observer.observe(panel));
      }
    }
  }

  function resetSeed() {
    state.model = structuredClone(seed);
    state.activeLaneId = "main";
    state.selectedNodeId = "objective";
    state.focusNodeId = "";
    computeLayout();
    fitView();
    saveModel();
    render();
  }

  function nodesArray() {
    return Object.values(state.model.nodes);
  }

  function activeLane() {
    return state.model.lanes.find((lane) => lane.id === state.activeLaneId) || state.model.lanes[0];
  }

  function selectedNode() {
    return state.model.nodes[state.selectedNodeId] || state.model.nodes.objective;
  }

  function visibleNodeIds() {
    if (!state.focusNodeId) return new Set(nodesArray().map((node) => node.id));
    const ids = new Set([state.focusNodeId]);
    const focus = state.model.nodes[state.focusNodeId];
    for (const door of focus.doors || []) ids.add(door.to);
    for (const node of nodesArray()) {
      if ((node.doors || []).some((door) => door.to === state.focusNodeId)) ids.add(node.id);
    }
    for (const lane of state.model.lanes) {
      const current = lane.current;
      if (ids.has(current)) {
        for (const mark of lane.trail) ids.add(mark);
      }
    }
    return ids;
  }

  function visibleNodes() {
    const ids = visibleNodeIds();
    return nodesArray().filter((node) => ids.has(node.id));
  }

  function computeLayout() {
    state.nodePositions.clear();
    state.nodeRadii.clear();
    const nodes = visibleNodes();
    const byLayer = new Map();
    for (const node of nodes) {
      const layer = Number(node.layer || 0);
      if (!byLayer.has(layer)) byLayer.set(layer, []);
      byLayer.get(layer).push(node);
    }

    const maxLayer = Math.max(1, ...Array.from(byLayer.keys()));
    for (const [layer, items] of byLayer.entries()) {
      if (layer === 0) {
        for (const node of items) {
          state.nodePositions.set(node.id, { x: 0, y: 0 });
          state.nodeRadii.set(node.id, 19);
        }
        continue;
      }
      const radius = 160 + (layer - 1) * 132;
      const spin = layer * 0.51;
      items.sort((a, b) => a.title.localeCompare(b.title));
      items.forEach((node, index) => {
        const angle = spin + (Math.PI * 2 * index) / Math.max(1, items.length);
        const wobble = 24 * Math.sin(index + layer);
        state.nodePositions.set(node.id, {
          x: Math.cos(angle) * (radius + wobble),
          y: Math.sin(angle) * (radius + wobble)
        });
        state.nodeRadii.set(node.id, Math.max(9, 18 - layer * 1.4));
      });
    }

    const allIds = new Set(nodes.map((node) => node.id));
    for (const node of nodes) {
      for (const door of node.doors || []) {
        if (!allIds.has(door.to)) continue;
        if (!state.nodePositions.has(door.to)) {
          state.nodePositions.set(door.to, { x: 0, y: 0 });
        }
      }
    }
  }

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width * pixelRatio));
    canvas.height = Math.max(1, Math.floor(rect.height * pixelRatio));
  }

  function fitView() {
    const positions = Array.from(state.nodePositions.values());
    if (!positions.length) return;
    const rect = canvas.getBoundingClientRect();
    const minX = Math.min(...positions.map((p) => p.x));
    const maxX = Math.max(...positions.map((p) => p.x));
    const minY = Math.min(...positions.map((p) => p.y));
    const maxY = Math.max(...positions.map((p) => p.y));
    const width = Math.max(1, maxX - minX + 160);
    const height = Math.max(1, maxY - minY + 160);
    state.scale = Math.min(rect.width / width, rect.height / height, 1.25);
    state.panX = rect.width / 2 - ((minX + maxX) / 2) * state.scale;
    state.panY = rect.height / 2 - ((minY + maxY) / 2) * state.scale;
  }

  function worldToScreen(pos) {
    return {
      x: pos.x * state.scale + state.panX,
      y: pos.y * state.scale + state.panY
    };
  }

  function screenToWorld(x, y) {
    return {
      x: (x - state.panX) / state.scale,
      y: (y - state.panY) / state.scale
    };
  }

  function render() {
    updatePanels();
    draw();
    saveModel();
  }

  function draw() {
    const rect = canvas.getBoundingClientRect();
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    ctx.fillStyle = "#050b0e";
    ctx.fillRect(0, 0, rect.width, rect.height);
    drawGrid(rect);
    drawEdges();
    drawTrails();
    drawNodes();
  }

  function drawGrid(rect) {
    ctx.save();
    ctx.strokeStyle = "rgba(75, 105, 114, 0.18)";
    ctx.lineWidth = 1;
    const step = Math.max(28, 54 * state.scale);
    const ox = state.panX % step;
    const oy = state.panY % step;
    for (let x = ox; x < rect.width; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, rect.height);
      ctx.stroke();
    }
    for (let y = oy; y < rect.height; y += step) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(rect.width, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawEdges() {
    const ids = visibleNodeIds();
    ctx.save();
    for (const node of visibleNodes()) {
      const a = state.nodePositions.get(node.id);
      if (!a) continue;
      for (const door of node.doors || []) {
        if (!ids.has(door.to)) continue;
        const b = state.nodePositions.get(door.to);
        if (!b) continue;
        const p1 = worldToScreen(a);
        const p2 = worldToScreen(b);
        const weight = Number(door.weight || 0.5);
        ctx.strokeStyle = `rgba(84, 215, 212, ${0.08 + weight * 0.18})`;
        ctx.lineWidth = 0.8 + weight * 1.2;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        const mx = (p1.x + p2.x) / 2;
        const my = (p1.y + p2.y) / 2;
        const bend = 18 * state.scale;
        ctx.quadraticCurveTo(mx + bend, my - bend, p2.x, p2.y);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawTrails() {
    ctx.save();
    for (const lane of state.model.lanes) {
      const points = lane.trail
        .map((id) => state.nodePositions.get(id))
        .filter(Boolean)
        .map(worldToScreen);
      if (points.length < 2) continue;
      ctx.strokeStyle = lane.color;
      ctx.globalAlpha = lane.id === state.activeLaneId ? 0.82 : 0.34;
      ctx.lineWidth = lane.id === state.activeLaneId ? 4 : 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      points.forEach((point, index) => {
        if (index === 0) ctx.moveTo(point.x, point.y);
        else ctx.lineTo(point.x, point.y);
      });
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawNodes() {
    ctx.save();
    const selected = state.selectedNodeId;
    const lane = activeLane();
    for (const node of visibleNodes()) {
      const pos = state.nodePositions.get(node.id);
      if (!pos) continue;
      const point = worldToScreen(pos);
      const radius = (state.nodeRadii.get(node.id) || 12) * Math.sqrt(state.scale);
      const isSelected = node.id === selected;
      const isCurrent = state.model.lanes.some((item) => item.current === node.id);
      const isTrail = lane.trail.includes(node.id);

      ctx.beginPath();
      ctx.arc(point.x, point.y, radius + (isSelected ? 7 : 0), 0, Math.PI * 2);
      ctx.fillStyle = isSelected ? "rgba(238, 248, 246, 0.16)" : "rgba(84, 215, 212, 0.07)";
      ctx.fill();

      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = typeColor(node.type);
      ctx.globalAlpha = isTrail ? 1 : 0.78;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.lineWidth = isCurrent ? 3 : 1;
      ctx.strokeStyle = isCurrent ? "#eef8f6" : "rgba(238, 248, 246, 0.42)";
      ctx.stroke();

      if (state.scale > 0.45 || isSelected) {
        ctx.font = `${isSelected ? 13 : 11}px ${getComputedStyle(document.body).fontFamily}`;
        ctx.fillStyle = isSelected ? "#eef8f6" : "#9bb4b2";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        wrapLabel(node.title, point.x, point.y + radius + 8, isSelected ? 130 : 104);
      }
    }
    ctx.restore();
  }

  function wrapLabel(text, x, y, maxWidth) {
    const words = text.split(/\s+/);
    let line = "";
    let offset = 0;
    for (const word of words) {
      const test = line ? `${line} ${word}` : word;
      if (ctx.measureText(test).width > maxWidth && line) {
        ctx.fillText(line, x, y + offset);
        line = word;
        offset += 14;
      } else {
        line = test;
      }
    }
    if (line) ctx.fillText(line, x, y + offset);
  }

  function typeColor(type) {
    const map = {
      anchor: "#6bd394",
      keyspace: "#54d7d4",
      interior: "#8fb4ff",
      trail: "#e7be60",
      eventspace: "#b59bff",
      evidence: "#eef8f6",
      index: "#7ac7a6",
      portal: "#ee7f9d",
      bridge: "#e7be60",
      pressure: "#ff7b7b",
      receipt: "#91c9ff",
      resume: "#a5e879",
      execution: "#d3a2ff",
      observe: "#f4d17b",
      guard: "#ff9a7a",
      source: "#78d2ff",
      visual: "#54d7d4",
      readout: "#b9f8dc",
      merge: "#6bd394"
    };
    return map[type] || "#54d7d4";
  }

  function updatePanels() {
    const lanes = state.model.lanes;
    const lane = activeLane();
    const node = selectedNode();
    const trailMarks = lanes.reduce((sum, item) => sum + item.trail.length, 0);
    els.nodeCount.textContent = String(Object.keys(state.model.nodes).length);
    els.laneCount.textContent = String(lanes.length);
    els.trailCount.textContent = String(trailMarks);
    els.activeLaneName.textContent = lane.name;
    els.selectedNodeName.textContent = node.id;
    els.zoomValue.textContent = `${Math.round(state.scale * 100)}%`;
    els.memoryStatus.textContent = state.focusNodeId ? `focused on ${state.focusNodeId}` : "knowledgebase ready";
    els.focusBtn.textContent = state.focusNodeId ? "All" : "Focus";

    renderLaneList();
    renderNodeInspector(node);
    renderTrail(lane);
    renderPacketOnly();
  }

  function renderLaneList() {
    els.laneList.innerHTML = "";
    for (const lane of state.model.lanes) {
      const button = document.createElement("button");
      button.className = `fm-lane${lane.id === state.activeLaneId ? " is-active" : ""}`;
      button.style.setProperty("--lane-color", lane.color);
      button.type = "button";
      button.innerHTML = `
        <div class="fm-lane-title"><span>${escapeHtml(lane.name)}</span><span class="fm-key-dot"></span></div>
        <div class="fm-lane-meta">${escapeHtml(lane.role)} key -> ${escapeHtml(lane.current)}<br>${lane.trail.length} trail marks</div>
      `;
      button.addEventListener("click", () => {
        state.activeLaneId = lane.id;
        state.selectedNodeId = lane.current;
        render();
        openKnowledgePanel("inspect");
        openKnowledgeDetail("selected");
        openKnowledgeDetail("trail");
        updateKnowledgeDrawerSizing();
      });
      els.laneList.appendChild(button);
    }
  }

  function renderNodeInspector(node) {
    els.selectedNodeType.textContent = node.type;
    els.selectedTitle.textContent = node.title;
    els.selectedSummary.textContent = node.summary;
    els.selectedEvidence.innerHTML = "";
    for (const item of node.evidence || []) {
      const div = document.createElement("div");
      div.textContent = item;
      els.selectedEvidence.appendChild(div);
    }

    els.doorList.innerHTML = "";
    for (const door of node.doors || []) {
      const target = state.model.nodes[door.to];
      if (!target) continue;
      const button = document.createElement("button");
      button.className = "fm-door";
      button.type = "button";
      button.innerHTML = `
        <span class="fm-door-title">${escapeHtml(target.title)}<span>${Math.round((door.weight || 0) * 100)}%</span></span>
        <span class="fm-door-meta">${escapeHtml(door.relation || "door")} -> ${escapeHtml(target.type)}</span>
      `;
      button.addEventListener("click", () => enterNode(door.to));
      els.doorList.appendChild(button);
    }
    if (!els.doorList.children.length) {
      const empty = document.createElement("div");
      empty.className = "fm-door-meta";
      empty.textContent = "No outgoing doors.";
      els.doorList.appendChild(empty);
    }
  }

  function renderTrail(lane) {
    els.laneNoteInput.value = lane.note || "";
    els.trailList.innerHTML = "";
    lane.trail.forEach((id, index) => {
      const node = state.model.nodes[id];
      const li = document.createElement("li");
      li.innerHTML = `<strong>${index + 1}.</strong> ${escapeHtml(node ? node.title : id)}`;
      els.trailList.appendChild(li);
    });
  }

  function renderPacketOnly() {
    els.aiPacket.textContent = JSON.stringify(buildAiPacket(), null, 2);
  }

  function buildAiPacket() {
    const lane = activeLane();
    const node = selectedNode();
    return {
      schemaVersion: state.model.schemaVersion,
      purpose: "MSP Knowledgebase packet for independent advisor-lane recall, eval judging context, and evidence-linked execution review.",
      claimCalibration: {
        fact: "Nodes, doors, lane trails, private notes, and correlations are explicit UI state.",
        inference: "Trail intersections indicate useful agreement, dependency, or conflict review points.",
        assumption: "A future runtime can hydrate node evidence from real artifacts, logs, provider calls, and repo graph records.",
        unknown: "Persistence, permissions, and multi-process writes are prototype gaps in this static build."
      },
      activeLane: summarizeLane(lane),
      selectedNode: summarizeNode(node),
      visibleMode: state.focusNodeId ? { focusNodeId: state.focusNodeId } : { focusNodeId: null },
      lanes: state.model.lanes.map(summarizeLane),
      correlations: collectCorrelations(),
      nextDoors: (node.doors || []).map((door) => ({
        to: door.to,
        relation: door.relation,
        weight: door.weight,
        targetTitle: state.model.nodes[door.to]?.title || door.to
      })),
      suggestedAgentMoves: [
        "Open the selected node's highest-weight door if it supports the lane role.",
        "Correlate after each lane reaches a guard, contradiction, artifact, or synthesis node.",
        "Prefer raw evidence nodes over compressed pointers when making factual claims.",
        "Keep lane-local notes separate until synthesis."
      ]
    };
  }

  function summarizeLane(lane) {
    return {
      id: lane.id,
      name: lane.name,
      role: lane.role,
      current: lane.current,
      trail: lane.trail.slice(),
      note: lane.note || "",
      trailTitles: lane.trail.map((id) => state.model.nodes[id]?.title || id)
    };
  }

  function summarizeNode(node) {
    return {
      id: node.id,
      title: node.title,
      type: node.type,
      layer: node.layer,
      summary: node.summary,
      evidence: (node.evidence || []).slice(),
      doors: (node.doors || []).map((door) => ({
        to: door.to,
        relation: door.relation,
        weight: door.weight
      }))
    };
  }

  function collectCorrelations() {
    const out = [];
    for (const lane of state.model.lanes) {
      for (const record of lane.correlations || []) out.push(record);
    }
    return out.slice(-20);
  }

  function enterNode(nodeId) {
    if (!state.model.nodes[nodeId]) return;
    const lane = activeLane();
    state.selectedNodeId = nodeId;
    lane.current = nodeId;
    if (lane.trail[lane.trail.length - 1] !== nodeId) {
      lane.trail.push(nodeId);
    }
    computeLayout();
    render();
    openKnowledgePanel("inspect");
    openKnowledgeDetail("selected");
    openKnowledgeDetail("doors");
    openKnowledgeDetail("trail");
    updateKnowledgeDrawerSizing();
  }

  function stepActiveLane() {
    const lane = activeLane();
    const node = state.model.nodes[lane.current] || selectedNode();
    const doors = (node.doors || []).filter((door) => state.model.nodes[door.to]);
    if (!doors.length) return;
    const priorities = rolePriority[lane.role] || [];
    const visited = new Set(lane.trail);
    let best = doors[0];
    let bestScore = -Infinity;
    for (const door of doors) {
      const target = state.model.nodes[door.to];
      const haystack = `${door.relation} ${target.title} ${target.type} ${target.summary}`.toLowerCase();
      let score = Number(door.weight || 0);
      if (!visited.has(door.to)) score += 0.45;
      for (const term of priorities) {
        if (haystack.includes(term)) score += 0.22;
      }
      if (score > bestScore) {
        bestScore = score;
        best = door;
      }
    }
    enterNode(best.to);
  }

  function correlateActiveLane() {
    const lane = activeLane();
    const laneTrail = new Set(lane.trail);
    const records = [];
    for (const other of state.model.lanes) {
      if (other.id === lane.id) continue;
      const shared = other.trail.filter((id) => laneTrail.has(id));
      const adjacent = adjacentTrailNodes(lane.trail, other.trail);
      if (shared.length || adjacent.length) {
        records.push({
          at: new Date().toISOString(),
          sourceLane: lane.id,
          targetLane: other.id,
          shared,
          adjacent,
          readout: shared.length
            ? "trail intersection"
            : "nearby door relation"
        });
      }
    }
    lane.correlations = [...(lane.correlations || []), ...records].slice(-24);
    els.memoryStatus.textContent = records.length ? `${records.length} correlation(s) added` : "no correlation found";
    saveModel();
    render();
  }

  function adjacentTrailNodes(aTrail, bTrail) {
    const bSet = new Set(bTrail);
    const hits = [];
    for (const id of aTrail) {
      const node = state.model.nodes[id];
      for (const door of node?.doors || []) {
        if (bSet.has(door.to)) hits.push({ from: id, to: door.to, relation: door.relation });
      }
    }
    return hits.slice(0, 6);
  }

  function spawnLane(fork) {
    const source = activeLane();
    const role = els.laneRoleInput.value || "sceptic";
    const baseName = (els.laneNameInput.value || "").trim() || `${role}-${state.model.lanes.length + 1}`;
    const id = uniqueId(baseName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "lane");
    const start = fork ? source.current : state.selectedNodeId;
    const lane = {
      id,
      name: baseName,
      role,
      color: roleColors[role] || roleColors.builder,
      current: start,
      trail: fork ? source.trail.slice() : [start],
      note: fork ? `Duplicated from ${source.name}.` : "New advisor lane.",
      correlations: []
    };
    state.model.lanes.push(lane);
    state.activeLaneId = lane.id;
    state.selectedNodeId = start;
    els.laneNameInput.value = "";
    render();
  }

  function uniqueId(base) {
    let id = base;
    let n = 2;
    const exists = () => state.model.lanes.some((lane) => lane.id === id);
    while (exists()) {
      id = `${base}-${n}`;
      n += 1;
    }
    return id;
  }

  function exportPacket() {
    const payload = JSON.stringify(buildAiPacket(), null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "msp-knowledgebase-ai-packet.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function copyPacket() {
    const payload = JSON.stringify(buildAiPacket(), null, 2);
    try {
      await navigator.clipboard.writeText(payload);
      els.memoryStatus.textContent = "AI packet copied";
    } catch (_) {
      els.memoryStatus.textContent = "copy unavailable";
    }
  }

  function onPointerDown(event) {
    canvas.setPointerCapture?.(event.pointerId);
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    state.lastPointer = { x, y };
    const nodeId = nearestNode(x, y);
    if (nodeId) {
      state.selectedNodeId = nodeId;
      render();
    } else {
      state.dragging = true;
    }
  }

  function onPointerMove(event) {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    if (state.dragging) {
      state.panX += x - state.lastPointer.x;
      state.panY += y - state.lastPointer.y;
      state.lastPointer = { x, y };
      draw();
    } else {
      state.lastPointer = { x, y };
    }
  }

  function onPointerUp() {
    state.dragging = false;
  }

  function onWheel(event) {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const before = screenToWorld(x, y);
    const factor = event.deltaY < 0 ? 1.08 : 0.92;
    state.scale = clamp(state.scale * factor, 0.22, 2.4);
    const after = worldToScreen(before);
    state.panX += x - after.x;
    state.panY += y - after.y;
    els.zoomValue.textContent = `${Math.round(state.scale * 100)}%`;
    draw();
  }

  function nearestNode(x, y) {
    let best = "";
    let bestDist = Infinity;
    for (const node of visibleNodes()) {
      const pos = state.nodePositions.get(node.id);
      if (!pos) continue;
      const point = worldToScreen(pos);
      const radius = (state.nodeRadii.get(node.id) || 12) * Math.sqrt(state.scale) + 12;
      const dx = point.x - x;
      const dy = point.y - y;
      const dist = Math.hypot(dx, dy);
      if (dist < radius && dist < bestDist) {
        best = node.id;
        bestDist = dist;
      }
    }
    return best;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
