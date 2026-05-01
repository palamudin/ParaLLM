(function () {
  const API = {
    state: "/v1/state",
    draft: "/v1/draft",
    frontLiveRuns: "/v1/front/live/runs",
  };

  const providerCatalog = {
    openai: {
      label: "OpenAI",
      models: [
        { value: "gpt-5-mini", label: "GPT-5 Mini" },
        { value: "gpt-5.4", label: "GPT-5.4" },
        { value: "gpt-5.4-mini", label: "GPT-5.4 Mini" },
      ],
    },
    deepseek: {
      label: "DeepSeek",
      models: [
        { value: "deepseek-v4-flash", label: "DeepSeek V4 Flash" },
        { value: "deepseek-v4-pro", label: "DeepSeek V4 Pro" },
        { value: "deepseek-chat", label: "DeepSeek Chat (Legacy)" },
      ],
    },
    anthropic: {
      label: "Anthropic",
      models: [
        { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
        { value: "claude-opus-4-7", label: "Claude Opus 4.7" },
      ],
    },
    xai: {
      label: "xAI",
      models: [
        { value: "grok-4.20-reasoning", label: "Grok 4.20 Reasoning" },
        { value: "grok-4-1-fast-reasoning", label: "Grok 4.1 Fast Reasoning" },
      ],
    },
  };

  const runtimeState = {
    backendState: null,
    draft: null,
    saveTimer: null,
    controlsLoaded: false,
  };

  const shellState = {
    sidebarCollapsed: false,
    inspectorMode: "repo",
  };
  let activeSurfaceDrag = null;

  const navButtons = Array.from(document.querySelectorAll("[data-view-target]"));
  const viewPanels = Array.from(document.querySelectorAll("[data-view-panel]"));
  const themeButtons = Array.from(document.querySelectorAll("[data-theme-option]"));
  const groupedButtons = Array.from(document.querySelectorAll("[data-group]"));
  const inspectorModeButtons = Array.from(document.querySelectorAll("[data-inspector-mode]"));
  const inspectorPanels = Array.from(document.querySelectorAll("[data-inspector-panel]"));

  const elements = {
    shellApp: document.querySelector(".replacement-shell-app"),
    sidebarToggle: document.getElementById("replacementSidebarToggle"),
    draftState: document.getElementById("previewDraftState"),
    runtimeMode: document.getElementById("previewRuntimeMode"),
    workerModel: document.getElementById("previewWorkerModel"),
    summarizerProvider: document.getElementById("previewSummarizerProvider"),
    summarizerModel: document.getElementById("previewSummarizerModel"),
    contextMode: document.getElementById("previewContextMode"),
    directBaselineMode: document.getElementById("previewDirectBaselineMode"),
    vettingEnabled: document.getElementById("previewVettingEnabled"),
    researchMode: document.getElementById("previewResearchMode"),
    objective: document.getElementById("previewObjective"),
    objectiveMirror: document.getElementById("previewObjectiveMirror"),
    sessionContext: document.getElementById("previewSessionContext"),
    constraints: document.getElementById("previewConstraints"),
    loopRounds: document.getElementById("previewLoopRounds"),
    maxCostUsd: document.getElementById("previewMaxCostUsd"),
    sendPrompt: document.getElementById("previewSendPrompt"),
    contractNarrative: document.getElementById("previewContractNarrative"),
    summaryPath: document.getElementById("previewSummaryPath"),
    summaryLimits: document.getElementById("previewSummaryLimits"),
    summaryResearch: document.getElementById("previewSummaryResearch"),
    headerTask: document.getElementById("previewHeaderTask"),
    headerRuntime: document.getElementById("previewHeaderRuntime"),
    headerBaseline: document.getElementById("previewHeaderBaseline"),
    headerProvider: document.getElementById("previewHeaderProvider"),
    headerVetting: document.getElementById("previewHeaderVetting"),
    headerProgress: document.getElementById("previewHeaderProgress"),
    headerElapsed: document.getElementById("previewHeaderElapsed"),
  };

  function applySidebarState(collapsed) {
    shellState.sidebarCollapsed = Boolean(collapsed);
    if (!elements.shellApp || !elements.sidebarToggle) {
      return;
    }
    elements.shellApp.classList.toggle("is-sidebar-collapsed", shellState.sidebarCollapsed);
    elements.sidebarToggle.setAttribute("aria-expanded", shellState.sidebarCollapsed ? "false" : "true");
    elements.sidebarToggle.setAttribute("data-shell-icon", shellState.sidebarCollapsed ? "expand" : "collapse");
    elements.sidebarToggle.setAttribute("aria-label", shellState.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar");
    elements.sidebarToggle.setAttribute("title", shellState.sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar");
  }

  function refreshRepoViewport() {
    window.dispatchEvent(new CustomEvent("repo-review:layout"));
  }

  function refreshMemoryViewport() {
    window.dispatchEvent(new CustomEvent("fractal-memory:layout"));
  }

  function refreshActiveInspector() {
    if (shellState.inspectorMode === "memory") {
      refreshMemoryViewport();
    } else {
      refreshRepoViewport();
    }
  }

  function setInspectorMode(mode) {
    const nextMode = mode === "memory" ? "memory" : "repo";
    shellState.inspectorMode = nextMode;
    inspectorModeButtons.forEach((button) => {
      const active = button.getAttribute("data-inspector-mode") === nextMode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    inspectorPanels.forEach((panel) => {
      const active = panel.getAttribute("data-inspector-panel") === nextMode;
      panel.hidden = !active;
    });
    try {
      window.localStorage.setItem("replacementShell.inspectorMode", nextMode);
    } catch (_) {}
    window.setTimeout(refreshActiveInspector, 40);
  }

  function providerLabel(providerId) {
    return providerCatalog[String(providerId || "").trim()]?.label || String(providerId || "unknown");
  }

  function modelOptions(providerId) {
    return providerCatalog[String(providerId || "").trim()]?.models || [];
  }

  function modelLabel(providerId, modelId) {
    const match = modelOptions(providerId).find((model) => model.value === modelId);
    return match ? match.label : String(modelId || "");
  }

  function toBoolString(value) {
    return value === false || value === "0" ? "0" : "1";
  }

  function splitLines(value) {
    return String(value || "")
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let message = response.status + " " + response.statusText;
      try {
        const payload = await response.json();
        if (payload && payload.detail) {
          message = String(payload.detail);
        }
      } catch (_) {}
      throw new Error(message);
    }
    return response.json();
  }

  function populateSelect(select, options, selectedValue) {
    const previousValue = String(selectedValue || "").trim();
    select.innerHTML = "";
    options.forEach((optionConfig, index) => {
      const option = document.createElement("option");
      option.value = optionConfig.value;
      option.textContent = optionConfig.label;
      select.appendChild(option);
      if (!previousValue && index === 0) {
        select.value = optionConfig.value;
      }
    });
    if (previousValue && options.some((option) => option.value === previousValue)) {
      select.value = previousValue;
    } else if (options[0]) {
      select.value = options[0].value;
    }
  }

  function setGroupedButton(group, value) {
    groupedButtons
      .filter((button) => button.getAttribute("data-group") === group)
      .forEach((button) => {
        const active = button.getAttribute("data-value") === value;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
  }

  function selectedGroupedValue(group, fallback) {
    const active = groupedButtons.find(
      (button) => button.getAttribute("data-group") === group && button.classList.contains("is-active")
    );
    return active ? active.getAttribute("data-value") : fallback;
  }

  function installMainWorkbenchPanes() {
    document.querySelectorAll(".replacement-surface").forEach((surface) => {
      if (surface.dataset.shellWorkbenchPane === "1") {
        return;
      }
      const handle = surface.querySelector(":scope > .replacement-surface-head");
      if (!handle) {
        return;
      }
      surface.dataset.shellWorkbenchPane = "1";
      surface.classList.add("replacement-workbench-pane");
      handle.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || event.target.closest("button,a,input,select,textarea,label")) {
          return;
        }
        const view = surface.closest(".replacement-view");
        if (!view) {
          return;
        }
        const currentX = parseFloat(surface.style.getPropertyValue("--rs-pane-x")) || 0;
        const currentY = parseFloat(surface.style.getPropertyValue("--rs-pane-y")) || 0;
        const rect = surface.getBoundingClientRect();
        activeSurfaceDrag = {
          surface,
          view,
          startClientX: event.clientX,
          startClientY: event.clientY,
          startX: currentX,
          startY: currentY,
          baseLeft: rect.left - currentX,
          baseTop: rect.top - currentY,
          width: rect.width,
          height: rect.height
        };
        surface.classList.add("is-shell-panel-dragging");
        handle.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      });
    });
  }

  function onMainWorkbenchPaneMove(event) {
    if (!activeSurfaceDrag) {
      return;
    }
    const drag = activeSurfaceDrag;
    const viewRect = drag.view.getBoundingClientRect();
    const proposedX = drag.startX + event.clientX - drag.startClientX;
    const proposedY = drag.startY + event.clientY - drag.startClientY;
    const minX = viewRect.left - drag.baseLeft;
    const minY = viewRect.top - drag.baseTop;
    const maxX = viewRect.right - drag.baseLeft - drag.width;
    const maxY = Math.max(minY, viewRect.bottom - drag.baseTop - drag.height);
    drag.surface.style.setProperty("--rs-pane-x", `${Math.round(clamp(proposedX, minX, Math.max(minX, maxX)))}px`);
    drag.surface.style.setProperty("--rs-pane-y", `${Math.round(clamp(proposedY, minY, maxY))}px`);
  }

  function endMainWorkbenchPaneDrag() {
    if (!activeSurfaceDrag) {
      return;
    }
    activeSurfaceDrag.surface.classList.remove("is-shell-panel-dragging");
    activeSurfaceDrag = null;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function currentControlState() {
    const workerProvider = selectedGroupedValue("provider", "openai");
    return {
      executionMode: String(elements.runtimeMode.value || "live"),
      engineVersion: selectedGroupedValue("engine", "v1"),
      provider: workerProvider,
      model: String(elements.workerModel.value || ""),
      summarizerProvider: String(elements.summarizerProvider.value || workerProvider),
      summarizerModel: String(elements.summarizerModel.value || ""),
      contextMode: String(elements.contextMode.value || "weighted"),
      directBaselineMode: String(elements.directBaselineMode.value || "off"),
      vettingEnabled: String(elements.vettingEnabled.value || "1"),
      researchEnabled: String(elements.researchMode.value || "0"),
      objective: String(elements.objective.value || "").trim(),
      sessionContext: String(elements.sessionContext.value || "").trim(),
      constraints: splitLines(elements.constraints.value),
      loopRounds: Math.max(1, parseInt(elements.loopRounds.value || "3", 10) || 3),
      maxCostUsd: Math.max(0, Number(elements.maxCostUsd.value || 0) || 0),
    };
  }

  function updateNarrative() {
    const control = currentControlState();
    const workerModelLabel = modelLabel(control.provider, control.model);
    const summarizerModelLabel = modelLabel(control.summarizerProvider, control.summarizerModel);
    const baselineLabel = control.directBaselineMode === "both"
      ? "compare against a single-thread baseline on the same provider and model"
      : control.directBaselineMode === "single"
        ? "also prepare a separate single-thread baseline run on the same provider and model"
        : "skip the single-thread baseline";
    const researchLabel = control.researchEnabled === "1" ? "on" : "off";
    const vettingLabel = control.vettingEnabled === "1" ? "summarizer vetting on" : "summarizer vetting off";
    const contextLabel = control.contextMode === "full" ? "full worker packets" : "weighted worker packets";

    if (elements.contractNarrative) {
      elements.contractNarrative.textContent =
        `Run the ${control.engineVersion.toUpperCase()} engine in ${control.executionMode} mode with ${providerLabel(control.provider)} / ${workerModelLabel} for the worker path, keep ${providerLabel(control.summarizerProvider)} / ${summarizerModelLabel} on the final answer lane, ${baselineLabel}, use ${contextLabel}, keep research ${researchLabel}, and leave ${vettingLabel}.`;
    }

    elements.summaryPath.textContent =
      control.directBaselineMode === "both"
        ? "Para + Direct compare"
        : control.directBaselineMode === "single"
          ? "Para + staged direct baseline"
          : "Para only";
    elements.summaryLimits.textContent = `${control.loopRounds} rounds, $${control.maxCostUsd.toFixed(1)} spend wall`;
    elements.summaryResearch.textContent = control.researchEnabled === "1" ? "On" : "Off";

    elements.headerRuntime.textContent = control.executionMode === "mock" ? "Mock" : "Live";
    elements.headerBaseline.textContent =
      control.directBaselineMode === "both"
        ? "Both compare"
        : control.directBaselineMode === "single"
          ? "Single only"
          : "Off";
    elements.headerProvider.textContent = `${providerLabel(control.provider)} / ${workerModelLabel}`;
    elements.headerVetting.textContent = control.vettingEnabled === "1" ? "On" : "Off";
    elements.objectiveMirror.textContent = control.objective || "No staged objective yet.";
  }

  function syncHeaderFromBackend(state) {
    const loop = state?.loop || {};
    const activeTask = state?.activeTask || null;
    elements.headerTask.textContent = activeTask?.taskId || "staged draft";
    if (typeof loop.completedRounds === "number" && typeof loop.totalRounds === "number") {
      elements.headerProgress.textContent = `${Number(loop.completedRounds || 0)} / ${Number(loop.totalRounds || 0)}`;
    }
    elements.headerElapsed.textContent = String(loop?.status || "idle") === "idle" ? "n/a" : String(loop?.status || "running");
  }

  function draftPayloadForSave() {
    const control = currentControlState();
    const existing = runtimeState.draft ? clone(runtimeState.draft) : {};
    const summarizerHarness = existing.summarizerHarness || { concision: "balanced", instruction: "" };
    const directHarness = existing.directHarness || {
      concision: "none",
      instruction: "Prefer the most detailed factual response the evidence supports. Be concrete, complete, and explicit about uncertainty.",
    };
    const providerRouting = existing.providerRouting || { ollama: { selectionMode: "single", judgeMode: "prefer_distinct" } };

    return {
      objective: control.objective,
      constraints: control.constraints,
      sessionContext: control.sessionContext,
      executionMode: control.executionMode,
      frontMode: "full",
      engineVersion: control.engineVersion,
      engineGraph: existing.engineGraph || null,
      providerRouting: providerRouting,
      contextMode: control.contextMode,
      directBaselineMode: control.directBaselineMode,
      provider: control.provider,
      model: control.model,
      summarizerProvider: control.summarizerProvider,
      summarizerModel: control.summarizerModel,
      directProvider: control.provider,
      directModel: control.model,
      directHarness: directHarness,
      summarizerHarness: summarizerHarness,
      ollamaBaseUrl: existing.ollamaBaseUrl || "http://127.0.0.1:11434",
      timeoutMode: existing.timeoutMode || "default",
      ollamaTimeoutProfile: existing.ollamaTimeoutProfile || null,
      targetTimeouts: existing.targetTimeouts || null,
      reasoningEffort: existing.reasoningEffort || "low",
      maxCostUsd: control.maxCostUsd,
      maxTotalTokens: Number(existing.maxTotalTokens || 0),
      maxOutputTokens: Number(existing.maxOutputTokens || 0),
      budgetTargets: existing.budgetTargets || null,
      researchEnabled: control.researchEnabled === "1",
      researchExternalWebAccess: existing.researchExternalWebAccess !== false,
      researchDomains: Array.isArray(existing.researchDomains) ? existing.researchDomains : [],
      localFilesEnabled: existing.localFilesEnabled !== false,
      localFileRoots: Array.isArray(existing.localFileRoots) ? existing.localFileRoots : ["."],
      githubToolsEnabled: existing.githubToolsEnabled === true,
      githubAllowedRepos: Array.isArray(existing.githubAllowedRepos) ? existing.githubAllowedRepos : [],
      dynamicSpinupEnabled: existing.dynamicSpinupEnabled === true,
      vettingEnabled: control.vettingEnabled === "1",
      loopRounds: control.loopRounds,
      loopDelayMs: Number(existing.loopDelayMs || 1000),
      workers: Array.isArray(existing.workers) ? existing.workers.map((worker) => Object.assign({}, worker, { model: control.model })) : [],
    };
  }

  function liveRunPayload() {
    const draftPayload = draftPayloadForSave();
    return Object.assign({}, draftPayload, {
      sessionContext: draftPayload.sessionContext,
      workers: Array.isArray(draftPayload.workers) ? draftPayload.workers : [],
    });
  }

  async function saveDraft() {
    const payload = draftPayloadForSave();
    elements.draftState.textContent = "Saving staged draft...";
    const response = await fetchJson(API.draft, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    runtimeState.draft = response?.draft ? clone(response.draft) : payload;
    elements.draftState.textContent = "Staged draft synced to /v1/draft.";
  }

  function queueDraftSave() {
    if (!runtimeState.controlsLoaded) return;
    clearTimeout(runtimeState.saveTimer);
    elements.draftState.textContent = "Draft changed. Waiting to sync...";
    runtimeState.saveTimer = setTimeout(function () {
      saveDraft().catch(function (error) {
        elements.draftState.textContent = "Draft sync failed: " + String(error.message || error);
      });
    }, 450);
  }

  function fillModelsForCurrentProviders() {
    const workerProvider = selectedGroupedValue("provider", "openai");
    populateSelect(elements.workerModel, modelOptions(workerProvider), elements.workerModel.value || runtimeState.draft?.model || "");
    populateSelect(elements.summarizerModel, modelOptions(elements.summarizerProvider.value || workerProvider), elements.summarizerModel.value || runtimeState.draft?.summarizerModel || "");
  }

  function hydrateControls(draft, state) {
    runtimeState.controlsLoaded = false;
    runtimeState.backendState = state;
    runtimeState.draft = clone(draft);

    elements.runtimeMode.value = String(draft.executionMode || "live");
    setGroupedButton("engine", String(draft.engineVersion || "v1"));
    setGroupedButton("provider", String(draft.provider || "openai"));
    elements.summarizerProvider.value = String(draft.summarizerProvider || draft.provider || "openai");
    fillModelsForCurrentProviders();
    elements.workerModel.value = String(draft.model || elements.workerModel.value || "");
    populateSelect(elements.summarizerModel, modelOptions(elements.summarizerProvider.value), String(draft.summarizerModel || ""));
    elements.contextMode.value = String(draft.contextMode || "weighted");
    elements.directBaselineMode.value = String(draft.directBaselineMode || "off");
    elements.vettingEnabled.value = toBoolString(draft.vettingEnabled);
    elements.researchMode.value = draft.researchEnabled ? "1" : "0";
    elements.objective.value = String(draft.objective || "");
    elements.sessionContext.value = String(draft.sessionContext || "");
    elements.constraints.value = Array.isArray(draft.constraints) ? draft.constraints.join("\n") : "";
    elements.loopRounds.value = String(draft.loopRounds || 3);
    elements.maxCostUsd.value = String(Number(draft.maxCostUsd || 0));

    syncHeaderFromBackend(state);
    updateNarrative();
    runtimeState.controlsLoaded = true;
    elements.draftState.textContent = "Loaded staged draft from /v1/state.";
  }

  async function loadState(options) {
    const settings = Object.assign({ hydrate: true }, options || {});
    const state = await fetchJson(API.state);
    const draft = state?.draft || {};
    if (settings.hydrate) {
      hydrateControls(draft, state);
    } else {
      runtimeState.backendState = state;
      syncHeaderFromBackend(state);
    }
  }

  async function sendPrompt() {
    const payload = liveRunPayload();
    if (!payload.objective) {
      elements.draftState.textContent = "Objective is required before Send.";
      return;
    }
    elements.draftState.textContent = "Queueing live run...";
    const response = await fetchJson(API.frontLiveRuns, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    elements.draftState.textContent = `Front live queued: ${String(response?.runId || "run created")}`;
    await loadState({ hydrate: false });
  }

  navButtons.forEach((button) => {
    button.addEventListener("click", function () {
      const target = button.getAttribute("data-view-target");
      navButtons.forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        if (active) {
          item.setAttribute("aria-current", "page");
        } else {
          item.removeAttribute("aria-current");
        }
      });
      viewPanels.forEach((panel) => {
        const active = panel.getAttribute("data-view-panel") === target;
        panel.classList.toggle("is-active", active);
        panel.hidden = !active;
      });
      if (target === "repo") {
        window.setTimeout(refreshActiveInspector, 40);
      }
    });
  });

  inspectorModeButtons.forEach((button) => {
    button.addEventListener("click", function () {
      setInspectorMode(button.getAttribute("data-inspector-mode"));
    });
  });

  if (elements.sidebarToggle) {
    elements.sidebarToggle.addEventListener("click", function () {
      applySidebarState(!shellState.sidebarCollapsed);
      try {
        window.localStorage.setItem("replacementShell.sidebarCollapsed", shellState.sidebarCollapsed ? "1" : "0");
      } catch (_) {}
      window.setTimeout(refreshActiveInspector, 60);
    });
  }

  themeButtons.forEach((button) => {
    button.addEventListener("click", function () {
      const theme = button.getAttribute("data-theme-option");
      document.documentElement.setAttribute("data-bs-theme", theme);
      themeButtons.forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", active ? "true" : "false");
      });
    });
  });

  groupedButtons.forEach((button) => {
    button.addEventListener("click", function () {
      const group = button.getAttribute("data-group");
      const value = button.getAttribute("data-value");
      setGroupedButton(group, value);
      if (group === "provider") {
        const previousSummarizerProvider = elements.summarizerProvider.value;
        const previousSummarizerModel = elements.summarizerModel.value;
        fillModelsForCurrentProviders();
        if (!elements.summarizerProvider.value) {
          elements.summarizerProvider.value = value;
        }
        if (previousSummarizerProvider === runtimeState.draft?.provider || previousSummarizerProvider === value) {
          elements.summarizerProvider.value = value;
          populateSelect(elements.summarizerModel, modelOptions(value), previousSummarizerModel || elements.workerModel.value);
          if (previousSummarizerModel === runtimeState.draft?.model || !previousSummarizerModel) {
            elements.summarizerModel.value = elements.workerModel.value;
          }
        }
      }
      updateNarrative();
      queueDraftSave();
    });
  });

  [
    elements.runtimeMode,
    elements.workerModel,
    elements.summarizerProvider,
    elements.summarizerModel,
    elements.contextMode,
    elements.directBaselineMode,
    elements.vettingEnabled,
    elements.researchMode,
    elements.objective,
    elements.sessionContext,
    elements.constraints,
    elements.loopRounds,
    elements.maxCostUsd,
  ].forEach((element) => {
    if (!element) return;
    element.addEventListener("input", function () {
      if (element === elements.objective) {
        elements.objectiveMirror.textContent = String(elements.objective.value || "").trim() || "No staged objective yet.";
      }
      if (element === elements.summarizerProvider) {
        populateSelect(elements.summarizerModel, modelOptions(elements.summarizerProvider.value), elements.summarizerModel.value || runtimeState.draft?.summarizerModel || "");
      }
      updateNarrative();
      queueDraftSave();
    });
    element.addEventListener("change", function () {
      if (element === elements.summarizerProvider) {
        populateSelect(elements.summarizerModel, modelOptions(elements.summarizerProvider.value), elements.summarizerModel.value || runtimeState.draft?.summarizerModel || "");
      }
      updateNarrative();
      queueDraftSave();
    });
  });

  elements.sendPrompt.addEventListener("click", function () {
    sendPrompt().catch(function (error) {
      elements.draftState.textContent = "Send failed: " + String(error.message || error);
    });
  });

  installMainWorkbenchPanes();
  window.addEventListener("pointermove", onMainWorkbenchPaneMove);
  window.addEventListener("pointerup", endMainWorkbenchPaneDrag);

  fillModelsForCurrentProviders();
  try {
    applySidebarState(window.localStorage.getItem("replacementShell.sidebarCollapsed") === "1");
  } catch (_) {
    applySidebarState(false);
  }
  try {
    setInspectorMode(window.localStorage.getItem("replacementShell.inspectorMode") || "repo");
  } catch (_) {
    setInspectorMode("repo");
  }
  loadState({ hydrate: true }).catch(function (error) {
    elements.draftState.textContent = "Load failed: " + String(error.message || error);
  });
  window.setInterval(function () {
    loadState({ hydrate: false }).catch(function () {});
  }, 5000);
})();
