(function () {
  const API = {
    state: "/v1/state",
    draft: "/v1/draft",
    frontEvalRuns: "/v1/front/eval/runs",
    frontLiveRuns: "/v1/front/live/runs",
    frontJudgeRuns: "/v1/front/judge/runs",
    targetsBackground: "/v1/targets/background",
    rounds: "/v1/rounds",
    loops: "/v1/loops",
    loopsCancel: "/v1/loops/cancel",
    jobsManage: "/v1/jobs/manage",
    stateReset: "/v1/state/reset",
    sessionReset: "/v1/session/reset",
    sessionArchivesClear: "/v1/session/archives/clear",
    sessionReplay: "/v1/session/replay",
    sessionExport: "/v1/session/export",
    events: "/v1/events",
    steps: "/v1/steps",
    evalHistory: "/v1/evals/history",
    evalArtifact: "/v1/evals/artifact",
    history: "/v1/history",
    artifact: "/v1/artifact",
    handoffs: "/v1/handoffs",
    authStatus: "/v1/auth/status",
    authKeys: "/v1/auth/keys",
    authRequirements: "/v1/auth/requirements",
    codexLimits: "/v1/codex/limits",
    codexLimitsManual: "/v1/codex/limits/manual",
    codexAuth: "/v1/codex/auth",
    codexLaneRun: "/v1/codex/lanes/run",
  };

  const OPENAI_API_MODEL_SOURCE = "openai_api";
  const OPENAI_CODEX_MODEL_SOURCE = "codex_auth";
  const OPENAI_API_MODEL_TRANSPORT = "openai_responses";
  const OPENAI_CODEX_MODEL_TRANSPORT = "codex_cli";

  const OPENAI_BASE_MODELS = [
    { value: "openai:gpt-5-mini", model: "gpt-5-mini", label: "GPT-5 Mini", shortLabel: "GPT-5 Mini", source: "openai_api", sourceLabel: "API key", transport: "openai_responses" },
    { value: "openai:gpt-5.4", model: "gpt-5.4", label: "GPT-5.4", shortLabel: "GPT-5.4", source: "openai_api", sourceLabel: "API key", transport: "openai_responses" },
    { value: "openai:gpt-5.4-mini", model: "gpt-5.4-mini", label: "GPT-5.4 Mini", shortLabel: "GPT-5.4 Mini", source: "openai_api", sourceLabel: "API key", transport: "openai_responses" },
  ];

  const OPENAI_CODEX_FALLBACK_MODELS = [
    { value: "codex:gpt-5.5", model: "gpt-5.5", label: "GPT-5.5", shortLabel: "GPT-5.5", source: "codex_auth", sourceLabel: "Codex", transport: "codex_cli" },
    { value: "codex:gpt-5.4", model: "gpt-5.4", label: "GPT-5.4", shortLabel: "GPT-5.4", source: "codex_auth", sourceLabel: "Codex", transport: "codex_cli" },
    { value: "codex:gpt-5.4-mini", model: "gpt-5.4-mini", label: "GPT-5.4 Mini", shortLabel: "GPT-5.4 Mini", source: "codex_auth", sourceLabel: "Codex", transport: "codex_cli" },
    { value: "codex:gpt-5.3-codex", model: "gpt-5.3-codex", label: "GPT-5.3 Codex", shortLabel: "5.3 Codex", source: "codex_auth", sourceLabel: "Codex", transport: "codex_cli" },
    { value: "codex:gpt-5.3-codex-spark", model: "gpt-5.3-codex-spark", label: "GPT-5.3 Codex Spark", shortLabel: "5.3 Spark", source: "codex_auth", sourceLabel: "Codex", transport: "codex_cli" },
    { value: "codex:gpt-5.2", model: "gpt-5.2", label: "GPT-5.2", shortLabel: "GPT-5.2", source: "codex_auth", sourceLabel: "Codex", transport: "codex_cli" },
  ];

  const providerCatalog = {
    openai: {
      label: "OpenAI",
      models: mergeModelOptions(OPENAI_BASE_MODELS, OPENAI_CODEX_FALLBACK_MODELS),
    },
    deepseek: {
      label: "DeepSeek",
      models: [
        { value: "deepseek-v4-flash", label: "DeepSeek V4 Flash", shortLabel: "V4 Flash" },
        { value: "deepseek-v4-pro", label: "DeepSeek V4 Pro", shortLabel: "V4 Pro" },
        { value: "deepseek-chat", label: "DeepSeek Chat (Legacy)", shortLabel: "Chat Legacy" },
      ],
    },
    anthropic: {
      label: "Anthropic",
      models: [
        { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", shortLabel: "Sonnet 4.6" },
        { value: "claude-opus-4-7", label: "Claude Opus 4.7", shortLabel: "Opus 4.7" },
      ],
    },
    xai: {
      label: "xAI",
      models: [
        { value: "grok-4.20-reasoning", label: "Grok 4.20 Reasoning", shortLabel: "Grok 4.20" },
        { value: "grok-4-1-fast-reasoning", label: "Grok 4.1 Fast Reasoning", shortLabel: "Grok 4.1 Fast" },
      ],
    },
  };

  const COMPOSER_ATTACHMENT_LIMIT = 4;
  const COMPOSER_ATTACHMENT_MAX_BYTES = 180000;
  const COMPOSER_ATTACHMENT_MAX_CHARS = 6000;
  const TEXTAREA_MIN_HEIGHT_PX = 48;
  const TEXTAREA_MAX_VISIBLE_ROWS = 7;
  const SCROLLBAR_PROXIMITY_PX = 30;
  const COMPOSER_SUPPORTED_EXTENSIONS = [
    ".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".log", ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".xml", ".yaml", ".yml", ".sql", ".sh", ".bat", ".ps1"
  ];

  const runtimeState = {
    backendState: null,
    draft: null,
    saveTimer: null,
    codexLimits: null,
    codexLimitsTimer: null,
    authRequirements: null,
    controlsLoaded: false,
    providerPaneRole: "worker",
  };

  const shellState = {
    sidebarCollapsed: false,
    inspectorMode: "repo",
    homeCollapsedPanels: new Set(),
    composerToolMenuOpen: false,
    stagedAttachments: [],
  };
  const scoreState = {
    selectedRunId: "",
    selectedSessionId: "",
    payload: null,
    sessions: [],
    loaded: false,
    emptyRunSkips: new Set(),
    autoComparableFallback: true,
  };
  const sessionBrowserState = {
    loaded: false,
    selectedKey: "current",
    entries: [],
    exportPayload: null,
  };
  const failedCallState = {
    loaded: false,
    selectedName: "",
    failures: [],
  };
  const handoffState = {
    loaded: false,
    selectedName: "",
    handoffs: [],
  };
  const nodeTransferState = {
    loaded: false,
    selectedName: "",
    transfers: [],
  };
  let activeSurfaceDrag = null;
  let scrollbarHotRaf = 0;
  const scrollbarHotElements = new Set();

  const navButtons = Array.from(document.querySelectorAll("[data-view-target]"));
  const viewPanels = Array.from(document.querySelectorAll("[data-view-panel]"));
  const themeButtons = Array.from(document.querySelectorAll("[data-theme-option]"));
  const groupedButtons = Array.from(document.querySelectorAll("[data-group]"));
  const summarizerProviderButtons = Array.from(document.querySelectorAll("[data-summarizer-provider-option]"));
  const providerRoleButtons = Array.from(document.querySelectorAll("[data-provider-role-option]"));
  const sharedProviderButtons = Array.from(document.querySelectorAll("[data-provider-option]"));
  const selectorActuators = Array.from(document.querySelectorAll(".igs-selector-actuator, .igs-provider-actuator"));
  const selectToggleButtons = Array.from(document.querySelectorAll("[data-select-toggle]"));
  const selectCycleButtons = Array.from(document.querySelectorAll("[data-select-cycle]"));
  const inspectorModeButtons = Array.from(document.querySelectorAll("[data-inspector-mode]"));
  const inspectorPanels = Array.from(document.querySelectorAll("[data-inspector-panel]"));
  const homePanels = Array.from(document.querySelectorAll("[data-home-panel]"));
  const homeCollapseButtons = Array.from(document.querySelectorAll("[data-home-collapse-toggle]"));
  const composerToolActions = Array.from(document.querySelectorAll("[data-composer-tool-action]"));
  const composerReasoningOptions = Array.from(document.querySelectorAll("[data-composer-reasoning-option]"));
  const contractNativeSelects = Array.from(document.querySelectorAll("[data-contract-pill-select]"));
  const HOME_COLLAPSE_STORAGE_KEY = "igsShell.homeCollapsedPanels";
  const HOME_COLLAPSE_DEFAULT_VERSION_KEY = "igsShell.homeCollapsedPanelsDefaultVersion";
  const HOME_COLLAPSE_DEFAULT_VERSION = "20260504-fields-collapsed-v1";
  const HOME_COLLAPSIBLE_PANELS = [
    { id: "contract", label: "Run contract", shortLabel: "Contract", side: "left" },
    { id: "lanes", label: "Lane status", shortLabel: "Lanes", side: "right" },
    { id: "trace", label: "Trace output", shortLabel: "Trace", side: "right" },
    { id: "supporting", label: "Supporting controls", shortLabel: "Supporting", side: "left" },
    { id: "math2code", label: "Math2Code", shortLabel: "Math2Code", side: "left" },
  ];

  const elements = {
    shellApp: document.querySelector(".igs-shell-app"),
    sidebarToggle: document.getElementById("replacementSidebarToggle"),
    draftState: document.getElementById("previewDraftState"),
    runtimeMode: document.getElementById("previewRuntimeMode"),
    engineVersion: document.getElementById("previewEngineVersion"),
    workerProvider: document.getElementById("previewWorkerProvider"),
    workerModel: document.getElementById("previewWorkerModel"),
    summarizerProvider: document.getElementById("previewSummarizerProvider"),
    summarizerModel: document.getElementById("previewSummarizerModel"),
    contextMode: document.getElementById("previewContextMode"),
    reasoningEffort: document.getElementById("previewReasoningEffort"),
    directBaselineMode: document.getElementById("previewDirectBaselineMode"),
    vettingEnabled: document.getElementById("previewVettingEnabled"),
    researchMode: document.getElementById("previewResearchMode"),
    memoryMode: document.getElementById("previewMemoryMode"),
    objective: document.getElementById("previewObjective"),
    composerRow: document.querySelector(".igs-chat-composer .igs-composer-row"),
    sessionContext: document.getElementById("previewSessionContext"),
    constraints: document.getElementById("previewConstraints"),
    loopRounds: document.getElementById("previewLoopRounds"),
    maxCostUsd: document.getElementById("previewMaxCostUsd"),
    sendPrompt: document.getElementById("previewSendPrompt"),
    sendIcon: document.querySelector("#previewSendPrompt .igs-send-icon"),
    sendText: document.querySelector("#previewSendPrompt .igs-send-text"),
    composerToolMenuToggle: document.getElementById("previewComposerToolMenuToggle"),
    composerToolMenu: document.getElementById("previewComposerToolMenu"),
    composerFileInput: document.getElementById("previewComposerFileInput"),
    composerAttachmentList: document.getElementById("previewComposerAttachmentList"),
    contractNarrative: document.getElementById("previewContractNarrative"),
    runActivity: document.getElementById("previewRunActivity"),
    runThread: document.getElementById("previewRunThread"),
    laneGrid: document.getElementById("previewLaneGrid"),
    homeLayout: document.querySelector(".igs-home-workspace"),
    homeDrawer: document.getElementById("previewHomeDrawer"),
    homeSidecar: document.querySelector(".igs-home-sidecar"),
    homeCollapsedPills: document.getElementById("previewHomeCollapsedPills"),
    traceSummary: document.getElementById("previewTraceSummary"),
    stepLog: document.getElementById("previewStepLog"),
    eventLog: document.getElementById("previewEventLog"),
    summaryPath: document.getElementById("previewSummaryPath"),
    summaryLimits: document.getElementById("previewSummaryLimits"),
    summaryReasoning: document.getElementById("previewSummaryReasoning"),
    summaryContext: document.getElementById("previewSummaryContext"),
    summaryResearch: document.getElementById("previewSummaryResearch"),
    summaryMemory: document.getElementById("previewSummaryMemory"),
    headerTask: document.getElementById("previewHeaderTask"),
    headerRuntime: document.getElementById("previewHeaderRuntime"),
    headerBaseline: document.getElementById("previewHeaderBaseline"),
    headerProvider: document.getElementById("previewHeaderProvider"),
    headerVetting: document.getElementById("previewHeaderVetting"),
    headerProgress: document.getElementById("previewHeaderProgress"),
    headerElapsed: document.getElementById("previewHeaderElapsed"),
    scoreRunSelect: document.getElementById("scoreRunSelect"),
    scoreSessionSelect: document.getElementById("scoreSessionSelect"),
    scoreRefreshBtn: document.getElementById("scoreRefreshBtn"),
    scoreRunMeta: document.getElementById("scoreRunMeta"),
    scoreStatus: document.getElementById("scoreStatus"),
    scoreCompareDetail: document.getElementById("scoreCompareDetail"),
    sessionSearch: document.getElementById("sessionSearch"),
    sessionRefreshBtn: document.getElementById("sessionRefreshBtn"),
    sessionStatus: document.getElementById("sessionStatus"),
    sessionList: document.getElementById("sessionList"),
    sessionDetailMeta: document.getElementById("sessionDetailMeta"),
    sessionThread: document.getElementById("sessionThread"),
    sessionRawExport: document.getElementById("sessionRawExport"),
    sessionPreviewCurrentBtn: document.getElementById("sessionPreviewCurrentBtn"),
    sessionReplayBtn: document.getElementById("sessionReplayBtn"),
    failedCallSelect: document.getElementById("failedCallSelect"),
    failedCallRefreshBtn: document.getElementById("failedCallRefreshBtn"),
    failedCallStatus: document.getElementById("failedCallStatus"),
    failedCallMeta: document.getElementById("failedCallMeta"),
    failedCallIngestion: document.getElementById("failedCallIngestion"),
    failedCallRaw: document.getElementById("failedCallRaw"),
    failedCallPacket: document.getElementById("failedCallPacket"),
    handoffSelect: document.getElementById("handoffSelect"),
    handoffCreateBtn: document.getElementById("handoffCreateBtn"),
    handoffRefreshBtn: document.getElementById("handoffRefreshBtn"),
    handoffStatus: document.getElementById("handoffStatus"),
    handoffMeta: document.getElementById("handoffMeta"),
    handoffPacket: document.getElementById("handoffPacket"),
    nodeTransferSelect: document.getElementById("nodeTransferSelect"),
    nodeTransferRefreshBtn: document.getElementById("nodeTransferRefreshBtn"),
    nodeTransferStatus: document.getElementById("nodeTransferStatus"),
    nodeTransferMeta: document.getElementById("nodeTransferMeta"),
    nodeTransferPacket: document.getElementById("nodeTransferPacket"),
    debugRefreshState: document.getElementById("debugRefreshState"),
    debugResetSession: document.getElementById("debugResetSession"),
    debugClearSessionArchives: document.getElementById("debugClearSessionArchives"),
    debugRunRound: document.getElementById("debugRunRound"),
    debugRunLoop: document.getElementById("debugRunLoop"),
    debugSummarize: document.getElementById("debugSummarize"),
    debugCancelLoop: document.getElementById("debugCancelLoop"),
    debugResetState: document.getElementById("debugResetState"),
    debugOperationStatus: document.getElementById("debugOperationStatus"),
    debugTargetControls: document.getElementById("debugTargetControls"),
    debugExportCurrentSession: document.getElementById("debugExportCurrentSession"),
    debugHistoryStatus: document.getElementById("debugHistoryStatus"),
    debugJobHistory: document.getElementById("debugJobHistory"),
    debugRoundHistory: document.getElementById("debugRoundHistory"),
    debugSessionArchives: document.getElementById("debugSessionArchives"),
    debugExportPreview: document.getElementById("debugExportPreview"),
    debugSchedulerEvents: document.getElementById("debugSchedulerEvents"),
    debugStepLog: document.getElementById("debugStepLog"),
    debugEventLog: document.getElementById("debugEventLog"),
    authRequirementModal: document.getElementById("authRequirementModal"),
    authRequirementClose: document.getElementById("authRequirementClose"),
    authRequirementBody: document.getElementById("authRequirementBody"),
    authRequirementProvider: document.getElementById("authRequirementProvider"),
    authRequirementKeyInput: document.getElementById("authRequirementKeyInput"),
    authRequirementSaveKey: document.getElementById("authRequirementSaveKey"),
    authRequirementCodexSignIn: document.getElementById("authRequirementCodexSignIn"),
    authRequirementStatus: document.getElementById("authRequirementStatus"),
    settingsCodexAuthMode: document.getElementById("settingsCodexAuthMode"),
    settingsCodexAuthSave: document.getElementById("settingsCodexAuthSave"),
    settingsCodexModel: document.getElementById("settingsCodexModel"),
    settingsCodexArmRun: document.getElementById("settingsCodexArmRun"),
    settingsCodexArmStatus: document.getElementById("settingsCodexArmStatus"),
    settingsCodexRefresh: document.getElementById("settingsCodexRefresh"),
    settingsCodexLimits: document.getElementById("settingsCodexLimits"),
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
      window.localStorage.setItem("igsShell.inspectorMode", nextMode);
    } catch (_) {}
    window.setTimeout(refreshActiveInspector, 40);
  }

  function providerLabel(providerId) {
    return providerCatalog[String(providerId || "").trim()]?.label || String(providerId || "unknown");
  }

  function mergeModelOptions() {
    const merged = [];
    const seen = new Set();
    Array.from(arguments).forEach((list) => {
      (Array.isArray(list) ? list : []).forEach((model) => {
        const value = String(model?.value || "").trim();
        if (!value || seen.has(value)) return;
        seen.add(value);
        merged.push({
          value,
          model: String(model.model || parseModelSelection(value).model || value).trim(),
          label: String(model.label || value).trim(),
          shortLabel: String(model.shortLabel || model.label || value).trim(),
          source: normalizeModelSource(model.source),
          sourceLabel: String(model.sourceLabel || sourceLabelForModelSource(model.source)).trim(),
          transport: String(model.transport || transportForModelSource(model.source)).trim(),
        });
      });
    });
    return merged;
  }

  function normalizeModelSource(source) {
    const normalized = String(source || "").trim().toLowerCase();
    if (normalized === OPENAI_CODEX_MODEL_SOURCE || normalized === "codex" || normalized === "codex_cli") {
      return OPENAI_CODEX_MODEL_SOURCE;
    }
    return OPENAI_API_MODEL_SOURCE;
  }

  function sourceLabelForModelSource(source) {
    return normalizeModelSource(source) === OPENAI_CODEX_MODEL_SOURCE ? "Codex" : "API key";
  }

  function transportForModelSource(source) {
    return normalizeModelSource(source) === OPENAI_CODEX_MODEL_SOURCE ? OPENAI_CODEX_MODEL_TRANSPORT : OPENAI_API_MODEL_TRANSPORT;
  }

  function sourcePrefixForModelSource(source) {
    return normalizeModelSource(source) === OPENAI_CODEX_MODEL_SOURCE ? "codex" : "openai";
  }

  function modelSelectionValue(modelId, source) {
    const model = String(modelId || "").trim();
    if (!model) return "";
    return sourcePrefixForModelSource(source) + ":" + model;
  }

  function parseModelSelection(value) {
    const raw = String(value || "").trim();
    const match = raw.match(/^(openai|codex):(.+)$/i);
    if (!match) {
      return {
        value: raw,
        model: raw,
        source: OPENAI_API_MODEL_SOURCE,
        transport: OPENAI_API_MODEL_TRANSPORT,
      };
    }
    const source = normalizeModelSource(match[1]);
    return {
      value: raw,
      model: String(match[2] || "").trim(),
      source,
      transport: transportForModelSource(source),
    };
  }

  function modelOptionDisplayLabel(optionConfig) {
    const label = String(optionConfig?.label || optionConfig?.model || optionConfig?.value || "").trim();
    const hasSourceLabel = Boolean(optionConfig?.source || optionConfig?.sourceLabel);
    const sourceLabel = hasSourceLabel ? String(optionConfig?.sourceLabel || sourceLabelForModelSource(optionConfig?.source)).trim() : "";
    return sourceLabel ? `${label} · ${sourceLabel}` : label;
  }

  function modelOptionPillLabel(optionConfig) {
    const label = String(optionConfig?.shortLabel || optionConfig?.label || optionConfig?.model || optionConfig?.value || "").trim();
    const hasSourceLabel = Boolean(optionConfig?.source || optionConfig?.sourceLabel);
    const sourceLabel = hasSourceLabel ? String(optionConfig?.sourceLabel || sourceLabelForModelSource(optionConfig?.source)).trim() : "";
    return sourceLabel ? `${label} · ${sourceLabel}` : label;
  }

  function modelOptionMatches(optionConfig, selectedValue, selectedSource) {
    const raw = String(selectedValue || "").trim();
    if (!optionConfig || !raw) return false;
    if (String(optionConfig.value || "") === raw) return true;
    const parsed = parseModelSelection(raw);
    const desiredSource = normalizeModelSource(selectedSource || parsed.source);
    return String(optionConfig.model || optionConfig.value || "").trim() === parsed.model
      && normalizeModelSource(optionConfig.source) === desiredSource;
  }

  function resolveModelOptionValue(options, selectedValue, selectedSource) {
    const models = Array.isArray(options) ? options : [];
    const match = models.find((option) => modelOptionMatches(option, selectedValue, selectedSource));
    return match ? match.value : (models[0]?.value || "");
  }

  function selectedModelOption(select) {
    return select?.selectedOptions?.[0] || null;
  }

  function selectedModelId(select) {
    const option = selectedModelOption(select);
    return String(option?.dataset?.modelId || parseModelSelection(select?.value).model || "").trim();
  }

  function selectedModelSource(select) {
    const option = selectedModelOption(select);
    return normalizeModelSource(option?.dataset?.modelSource || parseModelSelection(select?.value).source);
  }

  function displayLabelForCodexModel(modelId, displayName) {
    const raw = String(displayName || modelId || "").trim();
    if (!raw) return "";
    return raw
      .replace(/^gpt-/i, "GPT-")
      .replace(/-codex-spark$/i, " Codex Spark")
      .replace(/-codex$/i, " Codex")
      .replace(/-mini$/i, " Mini");
  }

  function shortLabelForCodexModel(modelId, displayName) {
    const label = displayLabelForCodexModel(modelId, displayName);
    return label.replace(/^GPT-/, "GPT-");
  }

  function isVisibleCodexCatalogModel(entry) {
    const model = String(entry?.model || "").trim().toLowerCase();
    if (!model) return false;
    if (String(entry?.visibility || "").trim().toLowerCase() === "hide") return false;
    return model.startsWith("gpt-5") || model.includes("codex");
  }

  function codexCatalogModelOption(entry) {
    const model = String(entry?.model || "").trim();
    const label = displayLabelForCodexModel(model, entry?.displayName);
    return {
      value: modelSelectionValue(model, OPENAI_CODEX_MODEL_SOURCE),
      model,
      label,
      shortLabel: shortLabelForCodexModel(model, label),
      source: OPENAI_CODEX_MODEL_SOURCE,
      sourceLabel: "Codex",
      transport: OPENAI_CODEX_MODEL_TRANSPORT,
    };
  }

  function refreshOpenAIModelSelects(previousWorker, previousSummarizer) {
    const workerProvider = selectedGroupedValue("provider", "openai");
    if (workerProvider === "openai" && elements.workerModel) {
      populateSelect(
        elements.workerModel,
        modelOptions("openai"),
        previousWorker || elements.workerModel.value || runtimeState.draft?.model || "",
        runtimeState.draft?.modelSource
      );
    }
    if (elements.summarizerProvider && elements.summarizerProvider.value === "openai" && elements.summarizerModel) {
      populateSelect(
        elements.summarizerModel,
        modelOptions("openai"),
        previousSummarizer || elements.summarizerModel.value || runtimeState.draft?.summarizerModel || "",
        runtimeState.draft?.summarizerModelSource
      );
    }
  }

  function mergeCodexCatalogIntoOpenAIModels(status) {
    const catalogModels = status?.catalog && Array.isArray(status.catalog.models) ? status.catalog.models : [];
    const codexOptions = catalogModels.filter(isVisibleCodexCatalogModel).map(codexCatalogModelOption);
    const nextModels = mergeModelOptions(OPENAI_BASE_MODELS, OPENAI_CODEX_FALLBACK_MODELS, codexOptions);
    const currentModels = providerCatalog.openai.models || [];
    const currentKey = currentModels.map((model) => model.value).join("|");
    const nextKey = nextModels.map((model) => model.value).join("|");
    if (currentKey === nextKey) return;
    const previousWorker = elements.workerModel?.value || "";
    const previousSummarizer = elements.summarizerModel?.value || "";
    providerCatalog.openai.models = nextModels;
    refreshOpenAIModelSelects(previousWorker, previousSummarizer);
    syncContractPillSelects();
    updateNarrative();
  }

  function seedSelectorActuatorOrbits() {
    selectorActuators.forEach((actuator, actuatorIndex) => {
      const orbit = actuator.querySelector(".actuator-orbit");
      if (!orbit || orbit.children.length) return;
      const isProviderActuator = actuator.classList.contains("igs-provider-actuator");
      const particleCount = isProviderActuator ? 20 : 26;
      for (let index = 0; index < particleCount; index += 1) {
        const star = document.createElement("i");
        const seed = (actuatorIndex + 1) * (index + 3);
        const size = isProviderActuator
          ? 0.72 + ((seed * 17) % 13) / 10
          : 1 + ((seed * 17) % 24) / 10;
        const distance = isProviderActuator
          ? 5 + ((seed * 29) % 15)
          : 18 + ((seed * 29) % 82);
        const duration = 7 + ((seed * 31) % 110) / 10;
        const delay = ((seed * 13) % 100) / 10;
        star.style.setProperty("--size", size.toFixed(2) + "px");
        star.style.setProperty("--distance", distance.toFixed(1) + "px");
        star.style.setProperty("--duration", duration.toFixed(2) + "s");
        star.style.setProperty("--delay", delay.toFixed(2));
        orbit.appendChild(star);
      }
    });
  }

  function modelOptions(providerId) {
    return providerCatalog[String(providerId || "").trim()]?.models || [];
  }

  function modelLabel(providerId, modelId, modelSource) {
    const options = modelOptions(providerId);
    const match = options.find((model) => modelOptionMatches(model, modelId, modelSource));
    if (match) return modelOptionDisplayLabel(match);
    const parsed = parseModelSelection(modelId);
    return String(parsed.model || modelId || "");
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

  async function fetchText(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(response.status + " " + response.statusText);
    }
    return response.text();
  }

  function jsonPostOptions(payload) {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    };
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function truncateText(value, maxLength) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    const limit = Math.max(20, Number(maxLength || 160));
    return text.length <= limit ? text : text.slice(0, limit - 3).trimEnd() + "...";
  }

  function boolValue(value, fallback) {
    if (value === undefined || value === null || value === "") return Boolean(fallback);
    return value === true || value === "1" || value === 1;
  }

  function fileExtension(name) {
    const match = String(name || "").toLowerCase().match(/\.[^.\\/]+$/);
    return match ? match[0] : "";
  }

  function supportedComposerFile(file) {
    return COMPOSER_SUPPORTED_EXTENSIONS.includes(fileExtension(file?.name));
  }

  function formatFileSize(bytes) {
    const value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) return "0 B";
    if (value < 1024) return Math.round(value) + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(value < 10 * 1024 ? 1 : 0) + " KB";
    return (value / (1024 * 1024)).toFixed(1) + " MB";
  }

  function closeAuthRequirementModal() {
    if (elements.authRequirementModal) {
      elements.authRequirementModal.hidden = true;
    }
  }

  function authConsumerLabel(consumer) {
    return [
      String(consumer?.label || consumer?.role || "Model arm").trim(),
      String(consumer?.provider || "").trim(),
      String(consumer?.model || "").trim(),
      String(consumer?.modelSource || "").trim() === OPENAI_CODEX_MODEL_SOURCE ? "Codex" : "",
    ].filter(Boolean).join(" · ");
  }

  function renderAuthRequirementModal(status) {
    runtimeState.authRequirements = status || {};
    if (!elements.authRequirementModal || !elements.authRequirementBody) return;
    const missing = Array.isArray(status?.missing) ? status.missing : [];
    const apiMissing = missing.filter((item) => String(item?.kind || "") === "api_key");
    elements.authRequirementBody.innerHTML = missing.length
      ? missing.map((item) => `
        <section class="igs-auth-missing-card">
          <strong>${escapeHtml(item.label || item.domain || "Provider access")}</strong>
          <p>${escapeHtml(item.message || "This selected model source needs credentials before Para can run it.")}</p>
          <div class="igs-auth-consumer-list">
            ${(Array.isArray(item.consumers) ? item.consumers : []).map((consumer) => `<span>${escapeHtml(authConsumerLabel(consumer))}</span>`).join("")}
          </div>
        </section>
      `).join("")
      : `<section class="igs-auth-missing-card"><strong>Provider access ready</strong><p>All selected model arms have usable authentication.</p></section>`;

    if (elements.authRequirementProvider) {
      elements.authRequirementProvider.innerHTML = apiMissing.map((item) => (
        `<option value="${escapeHtml(item.provider || "")}">${escapeHtml(item.label || item.provider || "")}</option>`
      )).join("");
      elements.authRequirementProvider.disabled = apiMissing.length === 0;
    }
    const hasApiMissing = apiMissing.length > 0;
    const hasCodexMissing = missing.some((item) => String(item?.kind || "") === "chatgpt_auth");
    if (elements.authRequirementKeyInput) {
      elements.authRequirementKeyInput.disabled = !hasApiMissing;
      elements.authRequirementKeyInput.value = "";
      elements.authRequirementKeyInput.placeholder = hasApiMissing ? "Paste provider key" : "No API key needed for this missing item";
    }
    if (elements.authRequirementSaveKey) {
      elements.authRequirementSaveKey.disabled = !hasApiMissing;
    }
    if (elements.authRequirementCodexSignIn) {
      elements.authRequirementCodexSignIn.disabled = !hasCodexMissing;
    }
    if (elements.authRequirementStatus) {
      elements.authRequirementStatus.textContent = missing.length
        ? "Run paused until provider access is ready."
        : "Provider access is ready.";
    }
    elements.authRequirementModal.hidden = false;
  }

  async function saveMissingAuthKey() {
    if (!elements.authRequirementProvider || !elements.authRequirementKeyInput) return;
    const provider = String(elements.authRequirementProvider.value || "").trim();
    const key = String(elements.authRequirementKeyInput.value || "").trim();
    if (!provider || !key) {
      if (elements.authRequirementStatus) elements.authRequirementStatus.textContent = "Pick a provider and paste a key first.";
      return;
    }
    if (elements.authRequirementSaveKey) elements.authRequirementSaveKey.disabled = true;
    if (elements.authRequirementStatus) elements.authRequirementStatus.textContent = "Saving provider key...";
    try {
      await fetchJson(API.authKeys, jsonPostOptions({ provider, appendKey: key }));
      elements.authRequirementKeyInput.value = "";
      if (elements.authRequirementStatus) elements.authRequirementStatus.textContent = "Key saved. Rechecking provider access...";
      if (runtimeState.authRequirementPayload) {
        await ensureAuthRequirementsReady(runtimeState.authRequirementPayload, { silentWhenReady: true });
      }
    } catch (error) {
      if (elements.authRequirementStatus) elements.authRequirementStatus.textContent = "Key save failed: " + String(error.message || error);
    } finally {
      if (elements.authRequirementSaveKey) elements.authRequirementSaveKey.disabled = false;
    }
  }

  function openCodexAuthHelp() {
    if (elements.authRequirementStatus) {
      elements.authRequirementStatus.textContent = "Use Settings > Codex agent arm to inherit your existing ChatGPT auth or choose a Para-managed ChatGPT sign-in. API key mode is separate platform billing.";
    }
    if (elements.settingsCodexAuthMode) {
      elements.settingsCodexAuthMode.focus();
    }
  }

  async function ensureAuthRequirementsReady(payload, options) {
    const settings = Object.assign({ silentWhenReady: false }, options || {});
    runtimeState.authRequirementPayload = clone(payload || {});
    const status = await fetchJson(API.authRequirements, jsonPostOptions(payload || {}));
    runtimeState.authRequirements = status;
    if (status?.ready) {
      if (!settings.silentWhenReady) closeAuthRequirementModal();
      else closeAuthRequirementModal();
      return true;
    }
    renderAuthRequirementModal(status);
    return false;
  }

  function buildAttachmentId(prefix) {
    return String(prefix || "file") + "-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }

  function stageComposerAttachment(attachment) {
    const deduped = shellState.stagedAttachments.filter((entry) => !(entry.name === attachment.name && entry.text === attachment.text));
    shellState.stagedAttachments = deduped.concat([attachment]).slice(-COMPOSER_ATTACHMENT_LIMIT);
    renderComposerTools();
  }

  function removeComposerAttachment(attachmentId) {
    shellState.stagedAttachments = shellState.stagedAttachments.filter((attachment) => attachment.id !== attachmentId);
    renderComposerTools();
  }

  function buildAttachmentContextBlock() {
    if (!shellState.stagedAttachments.length) return "";
    const blocks = ["Attached source files for this request. Treat them as user-provided context:"];
    shellState.stagedAttachments.forEach((attachment) => {
      blocks.push(
        "File: " + attachment.name + " (" + formatFileSize(attachment.size) + (attachment.truncated ? ", truncated" : "") + ")",
        attachment.text
      );
    });
    return blocks.join("\n\n");
  }

  function buildSendSessionContext(baseSessionContext) {
    const sections = [String(baseSessionContext || "").trim()].filter(Boolean);
    const attachmentBlock = buildAttachmentContextBlock();
    if (attachmentBlock) {
      sections.push(attachmentBlock);
    }
    return sections.join("\n\n---\n\n");
  }

  function homePanelConfig(panelId) {
    return HOME_COLLAPSIBLE_PANELS.find((panel) => panel.id === panelId) || null;
  }

  function elementHasScrollableAxis(element) {
    if (!element || element === document.documentElement || element === document.body) return false;
    const style = window.getComputedStyle(element);
    const yScrollable = /(auto|scroll|overlay)/.test(style.overflowY) && element.scrollHeight > element.clientHeight + 2;
    const xScrollable = /(auto|scroll|overlay)/.test(style.overflowX) && element.scrollWidth > element.clientWidth + 2;
    return yScrollable || xScrollable;
  }

  function pointerNearElementScrollChannel(element, x, y) {
    const rect = element.getBoundingClientRect();
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return false;
    const verticalHot = element.scrollHeight > element.clientHeight + 2 && rect.right - x <= SCROLLBAR_PROXIMITY_PX;
    const horizontalHot = element.scrollWidth > element.clientWidth + 2 && rect.bottom - y <= SCROLLBAR_PROXIMITY_PX;
    return verticalHot || horizontalHot;
  }

  function setScrollbarHotElements(nextHotElements) {
    scrollbarHotElements.forEach((element) => {
      if (!nextHotElements.has(element)) {
        element.classList.remove("igs-scrollbar-hot");
        scrollbarHotElements.delete(element);
      }
    });
    nextHotElements.forEach((element) => {
      if (!scrollbarHotElements.has(element)) {
        element.classList.add("igs-scrollbar-hot");
        scrollbarHotElements.add(element);
      }
    });
  }

  function clearScrollbarHotState() {
    document.documentElement.classList.remove("igs-scrollbar-viewport-hot");
    setScrollbarHotElements(new Set());
  }

  function updateScrollbarProximity(x, y) {
    const root = document.documentElement;
    const pageCanScrollY = root.scrollHeight > window.innerHeight + 2;
    const pageCanScrollX = root.scrollWidth > window.innerWidth + 2;
    const viewportHot = (pageCanScrollY && window.innerWidth - x <= SCROLLBAR_PROXIMITY_PX)
      || (pageCanScrollX && window.innerHeight - y <= SCROLLBAR_PROXIMITY_PX);
    root.classList.toggle("igs-scrollbar-viewport-hot", viewportHot);

    const nextHotElements = new Set();
    let element = document.elementFromPoint(x, y);
    while (element && element.nodeType === Node.ELEMENT_NODE) {
      if (elementHasScrollableAxis(element) && pointerNearElementScrollChannel(element, x, y)) {
        nextHotElements.add(element);
      }
      element = element.parentElement;
    }
    setScrollbarHotElements(nextHotElements);
  }

  function scheduleScrollbarProximity(event) {
    const x = Number(event.clientX || 0);
    const y = Number(event.clientY || 0);
    if (scrollbarHotRaf) {
      window.cancelAnimationFrame(scrollbarHotRaf);
    }
    scrollbarHotRaf = window.requestAnimationFrame(function () {
      scrollbarHotRaf = 0;
      updateScrollbarProximity(x, y);
    });
  }

  function defaultHomeCollapsedPanelIds() {
    return HOME_COLLAPSIBLE_PANELS.map((panel) => panel.id);
  }

  function readHomeCollapsedPanels() {
    try {
      const defaultVersion = window.localStorage.getItem(HOME_COLLAPSE_DEFAULT_VERSION_KEY);
      const stored = window.localStorage.getItem(HOME_COLLAPSE_STORAGE_KEY);
      if (defaultVersion !== HOME_COLLAPSE_DEFAULT_VERSION || stored === null) {
        const defaults = defaultHomeCollapsedPanelIds();
        window.localStorage.setItem(HOME_COLLAPSE_STORAGE_KEY, JSON.stringify(defaults));
        window.localStorage.setItem(HOME_COLLAPSE_DEFAULT_VERSION_KEY, HOME_COLLAPSE_DEFAULT_VERSION);
        return defaults;
      }
      const parsed = JSON.parse(stored);
      if (!Array.isArray(parsed)) return defaultHomeCollapsedPanelIds();
      return parsed
        .map((panelId) => String(panelId || "").trim())
        .filter((panelId) => Boolean(homePanelConfig(panelId)));
    } catch (_) {
      return defaultHomeCollapsedPanelIds();
    }
  }

  function persistHomeCollapsedPanels() {
    try {
      window.localStorage.setItem(HOME_COLLAPSE_STORAGE_KEY, JSON.stringify(Array.from(shellState.homeCollapsedPanels)));
      window.localStorage.setItem(HOME_COLLAPSE_DEFAULT_VERSION_KEY, HOME_COLLAPSE_DEFAULT_VERSION);
    } catch (_) {}
  }

  function homeSideEmpty(side) {
    return HOME_COLLAPSIBLE_PANELS
      .filter((panel) => panel.side === side)
      .every((panel) => shellState.homeCollapsedPanels.has(panel.id));
  }

  function homeDrawerEmpty() {
    return HOME_COLLAPSIBLE_PANELS.every((panel) => shellState.homeCollapsedPanels.has(panel.id));
  }

  function renderHomeCollapsedPills() {
    if (!elements.homeCollapsedPills) return;
    const panelStates = HOME_COLLAPSIBLE_PANELS.map((panel) => ({
      panel,
      visible: !shellState.homeCollapsedPanels.has(panel.id),
    }));
    elements.homeCollapsedPills.hidden = panelStates.length === 0;
    elements.homeCollapsedPills.innerHTML = panelStates.map((item, index) => {
      const previousVisible = Boolean(panelStates[index - 1]?.visible);
      const nextVisible = Boolean(panelStates[index + 1]?.visible);
      const classes = [
        "igs-pill",
        "igs-home-panel-pill",
        item.visible ? "is-active" : "is-hidden",
        item.visible && previousVisible ? "is-joined-left" : "",
        item.visible && nextVisible ? "is-joined-right" : "",
      ].filter(Boolean).join(" ");
      const label = item.panel.shortLabel || item.panel.label;
      const action = item.visible ? "Hide" : "Show";
      return `
      <button type="button" class="${classes}" data-home-panel-toggle="${escapeHtml(item.panel.id)}" aria-pressed="${item.visible ? "true" : "false"}" aria-expanded="${item.visible ? "true" : "false"}" aria-label="${action} ${escapeHtml(item.panel.label)}" title="${action} ${escapeHtml(item.panel.label)}">
        ${escapeHtml(label)}
      </button>
    `;
    }).join("");
    elements.homeCollapsedPills.querySelectorAll("[data-home-panel-toggle]").forEach((button) => {
      button.addEventListener("click", function () {
        const panelId = button.getAttribute("data-home-panel-toggle");
        setHomePanelCollapsed(panelId, !shellState.homeCollapsedPanels.has(panelId));
      });
    });
  }

  function applyHomePanelCollapseState() {
    homePanels.forEach((panel) => {
      const panelId = String(panel.getAttribute("data-home-panel") || "").trim();
      const collapsed = panelId !== "chat" && shellState.homeCollapsedPanels.has(panelId);
      panel.hidden = collapsed;
      panel.classList.toggle("is-home-panel-collapsed", collapsed);
    });
    homeCollapseButtons.forEach((button) => {
      const panelId = String(button.getAttribute("data-home-collapse-toggle") || "").trim();
      const config = homePanelConfig(panelId);
      const collapsed = shellState.homeCollapsedPanels.has(panelId);
      button.setAttribute("aria-expanded", collapsed ? "false" : "true");
      button.setAttribute("title", config ? `Hide ${config.label}` : "Hide panel");
    });
    if (elements.homeSidecar) {
      elements.homeSidecar.hidden = homeSideEmpty("right");
    }
    if (elements.homeDrawer) {
      elements.homeDrawer.hidden = homeDrawerEmpty();
    }
    if (elements.homeLayout) {
      const visibleHomePanelIds = HOME_COLLAPSIBLE_PANELS
        .filter((panel) => !shellState.homeCollapsedPanels.has(panel.id))
        .map((panel) => panel.id);
      elements.homeLayout.classList.toggle("is-drawer-empty", homeDrawerEmpty());
      elements.homeLayout.classList.toggle("is-drawer-left-empty", homeSideEmpty("left"));
      elements.homeLayout.classList.toggle("is-drawer-right-empty", homeSideEmpty("right"));
      elements.homeLayout.classList.toggle(
        "is-contract-drawer-only",
        visibleHomePanelIds.length === 1 && visibleHomePanelIds[0] === "contract"
      );
    }
    renderHomeCollapsedPills();
  }

  function setHomePanelCollapsed(panelId, collapsed) {
    const normalized = String(panelId || "").trim();
    if (!homePanelConfig(normalized)) return;
    if (collapsed) {
      shellState.homeCollapsedPanels.add(normalized);
    } else {
      shellState.homeCollapsedPanels.delete(normalized);
    }
    persistHomeCollapsedPanels();
    applyHomePanelCollapseState();
    if (!collapsed && normalized === "contract") {
      window.requestAnimationFrame(syncProviderButtonMetrics);
    }
  }

  function prettyJson(value) {
    try {
      return JSON.stringify(value, null, 2);
    } catch (_) {
      return String(value ?? "");
    }
  }

  function firstText() {
    for (let index = 0; index < arguments.length; index += 1) {
      const value = arguments[index];
      if (typeof value === "string") {
        const text = value.trim();
        if (text) return text;
      } else if (Array.isArray(value)) {
        const text = value.map((item) => firstText(item)).filter(Boolean).join("\n");
        if (text.trim()) return text.trim();
      } else if (value && typeof value === "object") {
        const text = firstText(
          value.answer,
          value.publicAnswer,
          value.output,
          value.text,
          value.answerDraft,
          value.observation,
          value.stance,
          value.because,
          value.confidenceNote
        );
        if (text) return text;
      }
    }
    return "";
  }

  function shortStatus(value, fallback) {
    const text = String(value || fallback || "").trim();
    return text || "idle";
  }

  function tailLines(text, maxLines) {
    const lines = String(text || "").split(/\r?\n/).filter((line) => line.trim());
    const count = Math.max(12, Number(maxLines || 60));
    return lines.slice(-count).join("\n") || "No data.";
  }

  function formatTimestamp(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return text;
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatKnownNumber(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) return "unknown";
    return Math.round(number).toLocaleString();
  }

  function formatObservedNumber(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return "0";
    return Math.round(number).toLocaleString();
  }

  function formatShortNumber(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) return "0";
    if (number >= 1_000_000_000) return (number / 1_000_000_000).toFixed(number >= 10_000_000_000 ? 0 : 1).replace(/\.0$/, "") + "b";
    if (number >= 1_000_000) return (number / 1_000_000).toFixed(number >= 10_000_000 ? 0 : 1).replace(/\.0$/, "") + "m";
    if (number >= 1_000) return (number / 1_000).toFixed(number >= 10_000 ? 0 : 1).replace(/\.0$/, "") + "k";
    return Math.round(number).toLocaleString();
  }

  function formatUsd(value, decimals) {
    const number = Number(value || 0);
    const places = Number.isFinite(Number(decimals)) ? Number(decimals) : 4;
    if (!Number.isFinite(number)) return "$0";
    return "$" + number.toFixed(places).replace(/\.?0+$/, "");
  }

  function codexSourceLink(url, label) {
    const href = String(url || "").trim();
    const text = String(label || "source").trim();
    if (!href) return escapeHtml(text);
    return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(text)}</a>`;
  }

  function codexManualChips(record) {
    if (!record) return "";
    if (typeof record === "string" || typeof record === "number" || typeof record === "boolean") {
      const text = String(record).trim();
      return text ? `<span>${escapeHtml(text)}</span>` : "";
    }
    if (!record || typeof record !== "object" || Array.isArray(record)) return "";
    return Object.entries(record)
      .filter(([, value]) => value !== null && value !== undefined && typeof value !== "object" && String(value).trim())
      .slice(0, 8)
      .map(([key, value]) => `<span><em>${escapeHtml(key)}</em> ${escapeHtml(String(value))}</span>`)
      .join("");
  }

  function hasCodexManualDetails(record) {
    if (!record) return false;
    if (typeof record === "string" || typeof record === "number" || typeof record === "boolean") {
      return Boolean(String(record).trim());
    }
    if (typeof record !== "object" || Array.isArray(record)) return false;
    return Object.entries(record).some(([key, value]) => {
      if (String(key).toLowerCase() === "label") return false;
      return value !== null && value !== undefined && typeof value !== "object" && Boolean(String(value).trim());
    });
  }

  function renderCodexMetric(label, value, note, tone) {
    return `
      <div class="igs-codex-limit-metric ${tone ? "is-" + escapeHtml(tone) : ""}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
        ${note ? `<small>${escapeHtml(note)}</small>` : ""}
      </div>
    `;
  }

  function codexManualEditorTemplate(status) {
    const selectedModel = String(status?.selectedModel || elements.settingsCodexModel?.value || "gpt-5.5");
    const manual = status?.manualAccountLimits || {};
    const general = manual.general && typeof manual.general === "object"
      ? manual.general
      : { label: "Codex account", limit: "", resetWindow: "", notes: "" };
    const currentModel = manual.models && typeof manual.models === "object" && manual.models[selectedModel]
      ? manual.models[selectedModel]
      : { limit: "", resetWindow: "", notes: "" };
    return JSON.stringify({
      general: {
        label: String(general.label || "Codex account"),
        limit: String(general.limit || ""),
        resetWindow: String(general.resetWindow || ""),
        notes: String(general.notes || ""),
      },
      models: {
        [selectedModel]: {
          limit: String(currentModel.limit || ""),
          resetWindow: String(currentModel.resetWindow || ""),
          notes: String(currentModel.notes || ""),
        },
      },
    }, null, 2);
  }

  function bindCodexManualEditor(status) {
    if (!elements.settingsCodexLimits) return;
    const textarea = elements.settingsCodexLimits.querySelector("#settingsCodexManualJson");
    const button = elements.settingsCodexLimits.querySelector("#settingsCodexManualSave");
    const message = elements.settingsCodexLimits.querySelector("#settingsCodexManualStatus");
    if (!textarea || !button) return;
    textarea.value = codexManualEditorTemplate(status);
    button.addEventListener("click", function () {
      let payload;
      try {
        payload = JSON.parse(textarea.value || "{}");
      } catch (error) {
        if (message) message.textContent = "Manual snapshot is not valid JSON.";
        return;
      }
      button.disabled = true;
      if (message) message.textContent = "Saving...";
      fetchJson(API.codexLimitsManual, jsonPostOptions(payload))
        .then(() => loadCodexLimits())
        .catch((error) => {
          if (message) message.textContent = "Save failed: " + String(error.message || error);
        })
        .finally(() => {
          button.disabled = false;
        });
    });
  }

  function renderCodexLimitsStatus(payload) {
    if (!elements.settingsCodexLimits) return;
    const status = payload && typeof payload === "object" ? payload : {};
    const selectedModel = String(status.selectedModel || elements.settingsCodexModel?.value || "gpt-5.5");
    const auth = status.auth || {};
    const catalog = status.catalog || {};
    const catalogModel = catalog.selectedModel || {};
    const pricing = status.pricing || {};
    const publicLimits = status.publicModelLimits || {};
    const tiers = Array.isArray(publicLimits.tiers) ? publicLimits.tiers : [];
    const projectRateLimits = status.projectRateLimits || {};
    const manual = status.manualAccountLimits || {};
    const manualGeneral = manual.general || manual.codex || manual.account || null;
    const manualModel = manual.models && typeof manual.models === "object" ? manual.models[selectedModel] : null;
    const measured = status.measured || {};
    const smoke = measured.lastSmoke || {};
    const catalogReasoning = Array.isArray(catalogModel.supportedReasoningLevels)
      ? catalogModel.supportedReasoningLevels.join(", ")
      : "";
    const manualGeneralChips = hasCodexManualDetails(manualGeneral) ? codexManualChips(manualGeneral) : "";
    const manualModelChips = hasCodexManualDetails(manualModel) ? codexManualChips(manualModel) : "";
    const authPolicyMode = String(auth?.policy?.mode || "inherit_chatgpt");
    if (elements.settingsCodexAuthMode && elements.settingsCodexAuthMode.value !== authPolicyMode) {
      elements.settingsCodexAuthMode.value = authPolicyMode;
    }

    elements.settingsCodexLimits.innerHTML = `
      <div class="igs-codex-limit-badges" aria-label="Codex evidence sources">
        <span class="is-info">OpenAI agent arm</span>
        <span class="${auth.known ? "is-live" : "is-muted"}">${auth.known ? "Codex auth ready" : "Codex auth missing"}</span>
        <span class="is-info">${escapeHtml(authPolicyMode.replace(/_/g, " "))}</span>
        <span class="${catalog.exists ? "is-live" : "is-muted"}">${catalog.exists ? "Local catalog loaded" : "No local model catalog"}</span>
        <span class="is-info">Docs snapshot</span>
        <span class="${manualGeneralChips || manualModelChips ? "is-live" : "is-muted"}">${manualGeneralChips || manualModelChips ? "Manual account snapshot" : "Manual snapshot empty"}</span>
        <span class="is-info">Measured smoke</span>
      </div>

      <div class="igs-codex-limit-grid">
        <section class="igs-codex-limit-card">
          <div class="igs-codex-card-head">
            <span>Arm model</span>
            <strong>${escapeHtml(catalogModel.displayName || selectedModel)}</strong>
          </div>
          <div class="igs-codex-metric-grid">
            ${renderCodexMetric("Catalog context", formatKnownNumber(catalogModel.contextWindow), "tokens")}
            ${renderCodexMetric("Max context", formatKnownNumber(catalogModel.maxContextWindow), "tokens")}
            ${renderCodexMetric("Default reasoning", catalogModel.defaultReasoningLevel || "unknown", catalogReasoning ? catalogReasoning : "")}
            ${renderCodexMetric("API flag", catalogModel.supportedInApi ? "supported" : "unknown", catalogModel.visibility || "")}
          </div>
          <div class="igs-codex-auth-line">
            <span>Auth</span>
            <strong>${escapeHtml(auth.known ? (auth.mode || "available") : "unknown")}</strong>
            <small>${escapeHtml(auth.known ? (auth.source || "auth.json present") : "No Codex auth file visible to this backend process.")}</small>
          </div>
          <p>${escapeHtml(catalogModel.description || "Codex arm uses local Codex CLI automation with user Codex config enabled by default.")}</p>
          <p>${escapeHtml(auth.note || "Presence-only auth check.")}</p>
        </section>

        <section class="igs-codex-limit-card">
          <div class="igs-codex-card-head">
            <span>Public model caps</span>
            <strong>${escapeHtml(publicLimits.rateLimitClass || "unknown class")}</strong>
          </div>
          <div class="igs-codex-metric-grid">
            ${renderCodexMetric("Context window", formatKnownNumber(publicLimits.contextWindow), "tokens", "accent")}
            ${renderCodexMetric("Max output", formatKnownNumber(publicLimits.maxOutputTokens), "tokens", "accent")}
            ${renderCodexMetric("Pricing input", pricing.known ? formatUsd(pricing.inputPer1M, 3) : "unknown", "per 1M")}
            ${renderCodexMetric("Pricing output", pricing.known ? formatUsd(pricing.outputPer1M, 3) : "unknown", "per 1M")}
          </div>
          <div class="igs-codex-tier-strip" aria-label="Public tier limits">
            ${tiers.length ? tiers.map((tier) => `
              <span><strong>${escapeHtml(String(tier.tier || "").replace("Tier ", "T"))}</strong> ${escapeHtml(formatShortNumber(tier.rpm))} rpm / ${escapeHtml(formatShortNumber(tier.tpm))} tpm</span>
            `).join("") : "<span>No tier rows in local snapshot.</span>"}
          </div>
          <p>${codexSourceLink(publicLimits.sourceUrl, publicLimits.source || "OpenAI model docs")}.</p>
        </section>

        <section class="igs-codex-limit-card">
          <div class="igs-codex-card-head">
            <span>Account quota</span>
            <strong>${manualGeneralChips || manualModelChips ? "manual snapshot" : "not captured"}</strong>
          </div>
          ${manualGeneralChips ? `
            <div class="igs-codex-chip-block">
              <span class="igs-codex-chip-label">General</span>
              ${manualGeneralChips}
            </div>
          ` : ""}
          ${manualModelChips ? `
            <div class="igs-codex-chip-block">
              <span class="igs-codex-chip-label">${escapeHtml(selectedModel)}</span>
              ${manualModelChips}
            </div>
          ` : ""}
          ${manualGeneralChips || manualModelChips ? "" : `
            <p>No account-level Codex quota has been saved yet. The UI can show a manual snapshot here because the Codex CLI does not expose those settings in JSONL.</p>
          `}
          <p>${escapeHtml(projectRateLimits.note || "Project rate limits require organization/project API credentials.")}</p>
          <p>${codexSourceLink(projectRateLimits.sourceUrl, projectRateLimits.source || "Admin rate-limit API")}.</p>
          <details class="igs-codex-manual-editor">
            <summary>Update manual snapshot</summary>
            <textarea id="settingsCodexManualJson" spellcheck="false" aria-label="Manual Codex account limit snapshot"></textarea>
            <div class="igs-codex-editor-actions">
              <button type="button" class="igs-pill igs-codex-refresh" id="settingsCodexManualSave">Save snapshot</button>
              <span id="settingsCodexManualStatus" aria-live="polite"></span>
            </div>
          </details>
        </section>

        <section class="igs-codex-limit-card">
          <div class="igs-codex-card-head">
            <span>Last local smoke</span>
            <strong>${escapeHtml(smoke.model || "not run")}</strong>
          </div>
          <div class="igs-codex-metric-grid">
            ${renderCodexMetric("Input", formatObservedNumber(smoke.inputTokens), "tokens")}
            ${renderCodexMetric("Cached", formatObservedNumber(smoke.cachedInputTokens), "tokens")}
            ${renderCodexMetric("Output", formatObservedNumber(smoke.outputTokens), "tokens")}
            ${renderCodexMetric("Est. cost", formatUsd(smoke.estimatedCostUsd, 6), "USD", "accent")}
          </div>
          <p>${escapeHtml(measured.note || "Measured usage is local telemetry, not an account quota.")}</p>
          <small>${escapeHtml(smoke.measuredAt ? "Measured " + formatTimestamp(smoke.measuredAt) : "")}</small>
        </section>
      </div>
    `;
    bindCodexManualEditor(status);
  }

  async function loadCodexLimits() {
    if (!elements.settingsCodexLimits) return;
    const model = String(elements.settingsCodexModel?.value || "gpt-5.5").trim();
    elements.settingsCodexLimits.innerHTML = `<div class="igs-inline-note">Refreshing Codex limits for ${escapeHtml(model)}...</div>`;
    const payload = await fetchJson(API.codexLimits + "?model=" + encodeURIComponent(model));
    runtimeState.codexLimits = payload;
    mergeCodexCatalogIntoOpenAIModels(payload);
    renderCodexLimitsStatus(payload);
  }

  async function saveCodexAuthMode() {
    if (!elements.settingsCodexAuthMode) return;
    const mode = String(elements.settingsCodexAuthMode.value || "inherit_chatgpt").trim();
    if (elements.settingsCodexAuthSave) elements.settingsCodexAuthSave.disabled = true;
    if (elements.settingsCodexArmStatus) {
      elements.settingsCodexArmStatus.textContent = "Saving Codex auth mode...";
    }
    try {
      await fetchJson(API.codexAuth, jsonPostOptions({ mode }));
      if (elements.settingsCodexArmStatus) {
        elements.settingsCodexArmStatus.textContent = "Codex auth mode saved.";
      }
      queueCodexLimitsLoad();
    } catch (error) {
      if (elements.settingsCodexArmStatus) {
        elements.settingsCodexArmStatus.textContent = "Codex auth save failed: " + String(error.message || error);
      }
    } finally {
      if (elements.settingsCodexAuthSave) elements.settingsCodexAuthSave.disabled = false;
    }
  }

  async function runCodexArmSmoke() {
    if (!elements.settingsCodexArmRun) return;
    const model = String(elements.settingsCodexModel?.value || "gpt-5.5").trim();
    const authMode = String(elements.settingsCodexAuthMode?.value || "inherit_chatgpt").trim();
    const activeProvider = selectedGroupedValue("provider", "openai");
    if (activeProvider !== "openai") {
      if (elements.settingsCodexArmStatus) {
        elements.settingsCodexArmStatus.textContent = "Select OpenAI in the Run contract before launching the Codex agent arm.";
      }
      return;
    }
    if (authMode === "disabled") {
      renderAuthRequirementModal({
        ready: false,
        missing: [{
          domain: "codex_chatgpt",
          kind: "chatgpt_auth",
          provider: "openai",
          label: "Codex arm disabled",
          message: "Codex launches are disabled in Settings.",
          consumers: [{ role: "codex_arm", label: "Codex agent arm", provider: "openai", model, modelSource: OPENAI_CODEX_MODEL_SOURCE }],
        }],
      });
      return;
    }
    const preflightPayload = {
      provider: "openai",
      model,
      modelSource: authMode === "api_key" ? OPENAI_API_MODEL_SOURCE : OPENAI_CODEX_MODEL_SOURCE,
      summarizerProvider: "openai",
      summarizerModel: model,
      summarizerModelSource: authMode === "api_key" ? OPENAI_API_MODEL_SOURCE : OPENAI_CODEX_MODEL_SOURCE,
    };
    if (!(await ensureAuthRequirementsReady(preflightPayload))) return;
    const confirmed = window.confirm("Launch one read-only Codex arm smoke? This may spend Codex/OpenAI tokens.");
    if (!confirmed) return;
    elements.settingsCodexArmRun.disabled = true;
    if (elements.settingsCodexArmStatus) {
      elements.settingsCodexArmStatus.textContent = "Launching Codex arm through local Codex automation...";
    }
    const payload = {
      laneId: "codex_adversarial",
      providerFamily: "openai",
      model,
      authMode,
      objective: "Run a read-only Para Codex arm smoke. Inspect the current staged state and return a compact pressure packet; do not edit files.",
      sandbox: "read-only",
      disablePlugins: true,
      timeoutSeconds: 900,
      maxCostUsd: 0.25,
    };
    try {
      const result = await fetchJson(API.codexLaneRun, jsonPostOptions(payload));
      if (elements.settingsCodexArmStatus) {
        const artifact = result?.artifactFile ? " Artifact: " + result.artifactFile : "";
        elements.settingsCodexArmStatus.textContent = result?.ok
          ? "Codex arm completed with status " + String(result.status || "unknown") + "." + artifact
          : "Codex arm did not launch: " + String(result?.message || "rejected");
      }
      queueCodexLimitsLoad();
    } catch (error) {
      if (elements.settingsCodexArmStatus) {
        elements.settingsCodexArmStatus.textContent = "Codex arm failed: " + String(error.message || error);
      }
    } finally {
      elements.settingsCodexArmRun.disabled = false;
    }
  }

  function queueCodexLimitsLoad() {
    if (!elements.settingsCodexLimits) return;
    clearTimeout(runtimeState.codexLimitsTimer);
    runtimeState.codexLimitsTimer = setTimeout(function () {
      loadCodexLimits().catch(function (error) {
        if (elements.settingsCodexLimits) {
          elements.settingsCodexLimits.innerHTML = `<div class="igs-inline-note">Codex limits failed to load: ${escapeHtml(error.message || error)}</div>`;
        }
      });
    }, 150);
  }

  function populateSelect(select, options, selectedValue, selectedSource) {
    const previousValue = String(selectedValue || "").trim();
    const resolvedValue = resolveModelOptionValue(options, previousValue, selectedSource);
    select.innerHTML = "";
    options.forEach((optionConfig, index) => {
      const option = document.createElement("option");
      option.value = optionConfig.value;
      option.textContent = modelOptionDisplayLabel(optionConfig);
      option.dataset.modelId = String(optionConfig.model || parseModelSelection(optionConfig.value).model || optionConfig.value || "").trim();
      option.dataset.modelSource = normalizeModelSource(optionConfig.source);
      option.dataset.transport = String(optionConfig.transport || transportForModelSource(optionConfig.source)).trim();
      option.dataset.sourceLabel = String(optionConfig.sourceLabel || sourceLabelForModelSource(optionConfig.source)).trim();
      option.dataset.pillDisplay = modelOptionPillLabel(optionConfig);
      select.appendChild(option);
      if (!resolvedValue && !previousValue && index === 0) {
        select.value = optionConfig.value;
      }
    });
    if (resolvedValue) {
      select.value = resolvedValue;
    } else if (options[0]) {
      select.value = options[0].value;
    }
    syncContractPillSelect(select);
  }

  function setGroupedButton(group, value) {
    if (group === "provider" && elements.workerProvider) {
      elements.workerProvider.value = String(value || "openai").trim();
    }
    groupedButtons
      .filter((button) => button.getAttribute("data-group") === group)
      .forEach((button) => {
        const active = button.getAttribute("data-value") === value;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
    if (group === "provider") {
      syncProviderPaneButtons();
    }
  }

  function setStateTileDisplayLabel(button, label) {
    const displayLabel = String(label || "").trim();
    button.dataset.stateLabel = displayLabel;
    const text = button.querySelector(".igs-state-text");
    if (text) {
      text.dataset.stateLabel = displayLabel;
    }
  }

  function syncSummarizerProviderButtons(value) {
    const selectedValue = String(value || "").trim();
    summarizerProviderButtons.forEach((button) => {
      const active = String(button.getAttribute("data-summarizer-provider-option") || "").trim() === selectedValue;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    syncProviderPaneButtons();
  }

  function setSummarizerProviderValue(value, options) {
    if (!elements.summarizerProvider) return;
    const nextValue = String(value || selectedGroupedValue("provider", "openai") || "openai").trim();
    elements.summarizerProvider.value = nextValue;
    syncSummarizerProviderButtons(nextValue);
    if (options?.dispatch) {
      elements.summarizerProvider.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function selectedGroupedValue(group, fallback) {
    if (group === "provider" && elements.workerProvider) {
      return String(elements.workerProvider.value || fallback || "").trim();
    }
    const active = groupedButtons.find(
      (button) => button.getAttribute("data-group") === group && button.classList.contains("is-active")
    );
    return active ? active.getAttribute("data-value") : fallback;
  }

  function activeProviderPaneRole() {
    return runtimeState.providerPaneRole === "summarizer" ? "summarizer" : "worker";
  }

  function providerValueForRole(role) {
    const normalizedRole = role === "summarizer" ? "summarizer" : "worker";
    const workerProvider = selectedGroupedValue("provider", "openai");
    return normalizedRole === "summarizer"
      ? String(elements.summarizerProvider?.value || workerProvider || "openai").trim()
      : workerProvider;
  }

  function syncProviderPaneButtons() {
    const role = activeProviderPaneRole();
    const activeValue = providerValueForRole(role);
    providerRoleButtons.forEach((button) => {
      const active = String(button.getAttribute("data-provider-role-option") || "").trim() === role;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    sharedProviderButtons.forEach((button) => {
      const active = String(button.getAttribute("data-provider-option") || "").trim() === activeValue;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function syncProviderButtonMetrics() {
    const segment = sharedProviderButtons[0]?.closest(".igs-provider-segment");
    if (!segment || !sharedProviderButtons.length) return;
    const previousWidth = segment.style.getPropertyValue("--provider-button-width");
    segment.style.removeProperty("--provider-button-width");
    let maxWidth = 0;
    sharedProviderButtons.forEach((button) => {
      const originalWidth = button.style.width;
      const originalFlexBasis = button.style.flexBasis;
      button.style.width = "max-content";
      button.style.flexBasis = "auto";
      maxWidth = Math.max(maxWidth, Math.ceil(button.getBoundingClientRect().width));
      button.style.width = originalWidth;
      button.style.flexBasis = originalFlexBasis;
    });
    if (maxWidth > 0) {
      const resolvedWidth = Math.max(86, maxWidth);
      const segmentStyle = window.getComputedStyle(segment);
      const gap = Number.parseFloat(segmentStyle.columnGap || segmentStyle.gap || "7") || 7;
      const segmentWidth = (resolvedWidth * sharedProviderButtons.length) + (gap * Math.max(0, sharedProviderButtons.length - 1));
      segment.style.setProperty("--provider-button-width", resolvedWidth + "px");
      segment.style.setProperty("--provider-segment-width", Math.ceil(segmentWidth) + "px");
    } else if (previousWidth) {
      segment.style.setProperty("--provider-button-width", previousWidth);
    }
  }

  function setProviderPaneRole(role) {
    runtimeState.providerPaneRole = role === "summarizer" ? "summarizer" : "worker";
    syncProviderPaneButtons();
  }

  function setWorkerProviderValue(value) {
    const nextValue = String(value || "openai").trim();
    const previousSummarizerProvider = elements.summarizerProvider?.value || "";
    const previousSummarizerModel = elements.summarizerModel?.value || "";
    setGroupedButton("provider", nextValue);
    fillModelsForCurrentProviders();
    if (!elements.summarizerProvider.value) {
      setSummarizerProviderValue(nextValue);
    }
    if (previousSummarizerProvider === runtimeState.draft?.provider || previousSummarizerProvider === nextValue) {
      setSummarizerProviderValue(nextValue);
      populateSelect(elements.summarizerModel, modelOptions(nextValue), previousSummarizerModel || elements.workerModel.value, runtimeState.draft?.summarizerModelSource);
      if (previousSummarizerModel === runtimeState.draft?.model || !previousSummarizerModel) {
        elements.summarizerModel.value = elements.workerModel.value;
      }
    }
    syncProviderPaneButtons();
  }

  function syncSelectToggleButtons(selectId) {
    selectToggleButtons.forEach((button) => {
      const targetId = String(button.getAttribute("data-select-toggle") || "").trim();
      if (selectId && targetId !== selectId) return;
      const select = targetId ? document.getElementById(targetId) : null;
      if (!select) return;
      const onValue = button.getAttribute("data-toggle-on");
      const offValue = button.getAttribute("data-toggle-off");
      const isBinaryToggle = onValue !== null && offValue !== null;
      const active = isBinaryToggle
        ? String(select.value) === String(onValue)
        : String(select.value) === String(button.getAttribute("data-value") || "");
      const pressLevel = active ? "full" : "none";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.dataset.toggleState = active ? "on" : "off";
      button.dataset.pressLevel = pressLevel;
      button.dataset.stateTone = active ? "on" : "off";
      const stateLabel = active ? "On" : "Off";
      setStateTileDisplayLabel(button, stateLabel);
      button.setAttribute("aria-label", `${contractControlName(button)}: ${stateLabel}`);
      if (isBinaryToggle) {
        setStateTileDisplayLabel(button, stateLabel);
      }
    });
  }

  function cycleValuesForButton(button) {
    return String(button?.getAttribute("data-cycle-values") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }

  function optionLabelForValue(select, value) {
    const match = Array.from(select?.options || []).find((option) => String(option.value) === String(value));
    return String(match?.textContent || value || "Off").trim();
  }

  function pressLevelForCycleButton(button, value) {
    const values = cycleValuesForButton(button);
    const levels = String(button?.getAttribute("data-cycle-press-levels") || "")
      .split(",")
      .map((level) => level.trim().toLowerCase())
      .filter(Boolean);
    const index = values.findIndex((item) => String(item) === String(value));
    if (index < 0) return "none";
    if (levels[index]) return levels[index];
    if (values.length >= 3) return index === 0 ? "none" : index === 1 ? "half" : "full";
    if (values.length === 2) return index === 0 ? "none" : "full";
    return index === 0 ? "none" : "full";
  }

  function stateToneFor(targetId, value) {
    const normalized = String(value || "").toLowerCase();
    if (targetId === "previewRuntimeMode") return normalized || "live";
    if (targetId === "previewEngineVersion") return normalized || "v2";
    if (targetId === "previewContextMode") return normalized === "weighted" ? "light" : normalized;
    if (targetId === "previewReasoningEffort") return normalized || "low";
    if (targetId === "previewDirectBaselineMode") return normalized || "off";
    return normalized === "1" || normalized === "on" ? "on" : "off";
  }

  function isVisuallyActiveState(targetId, value) {
    const normalized = String(value || "").toLowerCase();
    if (targetId === "previewDirectBaselineMode") return normalized !== "off";
    if (targetId === "previewReasoningEffort") return normalized !== "low";
    if (targetId === "previewVettingEnabled" || targetId === "previewResearchMode" || targetId === "previewMemoryMode") {
      return normalized === "1" || normalized === "on";
    }
    return Boolean(normalized);
  }

  function contractControlName(button) {
    const tileName = button?.closest("[data-contract-control-tile]")?.getAttribute("data-contract-control-tile");
    const textName = String(button?.querySelector(".igs-state-text")?.textContent || "").trim();
    return tileName || textName || "Control";
  }

  function syncSelectCycleButtons(selectId) {
    selectCycleButtons.forEach((button) => {
      const targetId = String(button.getAttribute("data-select-cycle") || "").trim();
      if (selectId && targetId !== selectId) return;
      const select = targetId ? document.getElementById(targetId) : null;
      if (!select) return;
      const stateLabel = optionLabelForValue(select, select.value);
      const stateTone = stateToneFor(targetId, select.value);
      const pressLevel = pressLevelForCycleButton(button, select.value);
      const active = pressLevel !== "none" && isVisuallyActiveState(targetId, select.value);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", pressLevel === "half" ? "mixed" : active ? "true" : "false");
      setStateTileDisplayLabel(button, stateLabel);
      button.dataset.stateTone = stateTone;
      button.dataset.pressLevel = pressLevel;
      button.setAttribute("aria-label", `${contractControlName(button)}: ${stateLabel}`);
    });
  }

  function setSelectFromToggleButton(button) {
    const targetId = String(button?.getAttribute("data-select-toggle") || "").trim();
    const select = targetId ? document.getElementById(targetId) : null;
    if (!select) return;
    const onValue = button.getAttribute("data-toggle-on");
    const offValue = button.getAttribute("data-toggle-off");
    const nextValue = onValue !== null && offValue !== null
      ? (String(select.value) === String(onValue) ? String(offValue) : String(onValue))
      : String(button.getAttribute("data-value") || "");
    if (!nextValue && nextValue !== "0") return;
    select.value = nextValue;
    syncSelectToggleButtons(targetId);
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setSelectFromCycleButton(button) {
    const targetId = String(button?.getAttribute("data-select-cycle") || "").trim();
    const select = targetId ? document.getElementById(targetId) : null;
    if (!select) return;
    const values = cycleValuesForButton(button);
    if (!values.length) return;
    const currentIndex = values.findIndex((value) => String(value) === String(select.value));
    const nextValue = values[(currentIndex + 1 + values.length) % values.length];
    select.value = nextValue;
    syncSelectCycleButtons(targetId);
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function contractSelectOptionLabel(select) {
    const option = select?.selectedOptions?.[0] || null;
    return String(option?.textContent || select?.value || "Select").trim() || "Select";
  }

  function contractSelectDisplayLabel(select) {
    const option = select?.selectedOptions?.[0] || null;
    return String(option?.dataset?.pillDisplay || option?.textContent || select?.value || "Select").trim() || "Select";
  }

  function contractSelectOptionMeasureLabel(select) {
    return Array.from(select?.options || []).reduce((longest, option) => {
      const label = String(option?.dataset?.pillDisplay || option?.textContent || option?.value || "").trim();
      return label.length > longest.length ? label : longest;
    }, contractSelectDisplayLabel(select));
  }

  function syncContractPillIntrinsicWidth(select) {
    const wrapper = contractPillSelectFor(select);
    if (!select || !wrapper) return;
    const label = contractSelectOptionMeasureLabel(select);
    const width = Math.min(30, Math.max(8, Array.from(label).length + 4));
    const cssWidth = width + "ch";
    wrapper.style.setProperty("--pill-control-width", cssWidth);
    wrapper.closest(".igs-control-tile")?.style.setProperty("--pill-control-width", cssWidth);
  }

  function contractPillSelectFor(select) {
    return select?.nextElementSibling?.classList?.contains("igs-pill-select")
      ? select.nextElementSibling
      : null;
  }

  function closeContractPillSelects(exceptWrapper) {
    contractNativeSelects.forEach((select) => {
      const wrapper = contractPillSelectFor(select);
      if (!wrapper || wrapper === exceptWrapper) return;
      wrapper.classList.remove("is-open");
      const trigger = wrapper.querySelector(".igs-pill-select-trigger");
      const menu = wrapper.querySelector(".igs-pill-select-menu");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
      if (menu) menu.hidden = true;
    });
  }

  function syncContractPillSelect(select) {
    const wrapper = contractPillSelectFor(select);
    if (!select || !wrapper) return;
    const trigger = wrapper.querySelector(".igs-pill-select-trigger");
    const value = wrapper.querySelector(".igs-pill-select-value");
    const tile = wrapper.closest(".igs-control-tile");
    const label = String(select.getAttribute("data-contract-pill-select") || select.id || "Control");
    syncContractPillIntrinsicWidth(select);
    if (trigger) {
      trigger.setAttribute("aria-label", label + ": " + contractSelectOptionLabel(select));
    }
    if (tile) {
      tile.classList.add("igs-select-tile");
      tile.setAttribute("role", "button");
      tile.setAttribute("tabindex", select.disabled ? "-1" : "0");
      tile.setAttribute("aria-haspopup", "listbox");
      tile.setAttribute("aria-label", label + ": " + contractSelectOptionLabel(select));
    }
    if (value) {
      value.textContent = contractSelectDisplayLabel(select);
    }
    wrapper.classList.toggle("is-disabled", select.disabled);
    tile?.classList.toggle("is-disabled", select.disabled);
  }

  function renderContractPillMenu(select) {
    const wrapper = contractPillSelectFor(select);
    if (!select || !wrapper) return;
    const menu = wrapper.querySelector(".igs-pill-select-menu");
    if (!menu) return;
    const selectedValue = String(select.value || "");
    menu.innerHTML = Array.from(select.options || []).map((option) => {
      const value = String(option.value || "");
      const label = String(option.textContent || value || "Option").trim();
      const active = value === selectedValue;
      return `
        <button type="button" class="igs-pill-select-option${active ? " is-active" : ""}" role="option" aria-selected="${active ? "true" : "false"}" data-pill-select-value="${escapeHtml(value)}">
          ${escapeHtml(label)}
        </button>
      `;
    }).join("");
  }

  function setContractPillSelectOpen(select, open) {
    const wrapper = contractPillSelectFor(select);
    if (!wrapper || select.disabled) return;
    const shouldOpen = Boolean(open);
    closeContractPillSelects(shouldOpen ? wrapper : null);
    renderContractPillMenu(select);
    wrapper.classList.toggle("is-open", shouldOpen);
    const trigger = wrapper.querySelector(".igs-pill-select-trigger");
    const menu = wrapper.querySelector(".igs-pill-select-menu");
    if (trigger) trigger.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
    wrapper.closest(".igs-control-tile")?.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
    if (menu) menu.hidden = !shouldOpen;
  }

  function installContractPillSelects() {
    contractNativeSelects.forEach((select) => {
      if (contractPillSelectFor(select)) {
        syncContractPillSelect(select);
        return;
      }
      const label = String(select.getAttribute("data-contract-pill-select") || select.id || "Control");
      const wrapper = document.createElement("div");
      wrapper.className = "igs-pill-select";
      wrapper.setAttribute("data-pill-select-control", select.id || "");
      wrapper.innerHTML = `
        <div class="igs-pill-select-trigger" aria-haspopup="listbox" aria-expanded="false">
          <strong class="igs-pill-select-value">${escapeHtml(contractSelectDisplayLabel(select))}</strong>
        </div>
        <div class="igs-pill-select-menu" role="listbox" hidden></div>
      `;
      select.insertAdjacentElement("afterend", wrapper);
      const tile = wrapper.closest(".igs-control-tile");
      if (tile) {
        tile.classList.add("igs-select-tile");
        tile.addEventListener("click", function (event) {
          if (event.target.closest(".igs-pill-select-menu")) return;
          event.preventDefault();
          setContractPillSelectOpen(select, !wrapper.classList.contains("is-open"));
        });
        tile.addEventListener("keydown", function (event) {
          if (event.key !== "Enter" && event.key !== " ") return;
          if (event.target.closest(".igs-pill-select-menu")) return;
          event.preventDefault();
          setContractPillSelectOpen(select, !wrapper.classList.contains("is-open"));
        });
      }
      wrapper.querySelector(".igs-pill-select-trigger")?.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setContractPillSelectOpen(select, !wrapper.classList.contains("is-open"));
      });
      wrapper.querySelector(".igs-pill-select-menu")?.addEventListener("click", function (event) {
        const button = event.target.closest("[data-pill-select-value]");
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        select.value = String(button.getAttribute("data-pill-select-value") || "");
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncContractPillSelect(select);
        setContractPillSelectOpen(select, false);
      });
      select.addEventListener("change", function () {
        syncContractPillSelect(select);
      });
      syncContractPillSelect(select);
    });
  }

  function syncContractPillSelects() {
    contractNativeSelects.forEach(syncContractPillSelect);
  }

  function installMainWorkbenchPanes() {
    document.querySelectorAll(".igs-surface").forEach((surface) => {
      if (surface.dataset.shellWorkbenchPane === "1") {
        return;
      }
      const handle = surface.querySelector(":scope > .igs-surface-head");
      if (!handle) {
        return;
      }
      surface.dataset.shellWorkbenchPane = "1";
      surface.classList.add("igs-workbench-pane");
      handle.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || event.target.closest("button,a,input,select,textarea,label")) {
          return;
        }
        const view = surface.closest(".igs-view");
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
      engineVersion: String(elements.engineVersion?.value || selectedGroupedValue("engine", "v1")),
      provider: workerProvider,
      model: selectedModelId(elements.workerModel),
      modelSource: selectedModelSource(elements.workerModel),
      summarizerProvider: String(elements.summarizerProvider.value || workerProvider),
      summarizerModel: selectedModelId(elements.summarizerModel),
      summarizerModelSource: selectedModelSource(elements.summarizerModel),
      contextMode: String(elements.contextMode.value || "weighted"),
      reasoningEffort: String(elements.reasoningEffort?.value || "low"),
      directBaselineMode: String(elements.directBaselineMode.value || "off"),
      vettingEnabled: String(elements.vettingEnabled.value || "1"),
      researchEnabled: String(elements.researchMode.value || "0"),
      knowledgebaseEnabled: String(elements.memoryMode?.value || "0"),
      objective: String(elements.objective.value || "").trim(),
      sessionContext: String(elements.sessionContext.value || "").trim(),
      constraints: splitLines(elements.constraints.value),
      loopRounds: Math.max(1, parseInt(elements.loopRounds.value || "3", 10) || 3),
      maxCostUsd: Math.max(0, Number(elements.maxCostUsd.value || 0) || 0),
    };
  }

  function updateNarrative() {
    const control = currentControlState();
    const workerModelLabel = modelLabel(control.provider, control.model, control.modelSource);
    const summarizerModelLabel = modelLabel(control.summarizerProvider, control.summarizerModel, control.summarizerModelSource);
    const baselineLabel = control.directBaselineMode === "both"
      ? "compare against a single-thread baseline on the same provider and model"
      : control.directBaselineMode === "single"
        ? "also prepare a separate single-thread baseline run on the same provider and model"
        : "skip the single-thread baseline";
    const researchLabel = control.researchEnabled === "1" ? "on" : "off";
    const memoryLabel = control.knowledgebaseEnabled === "1" ? "on" : "off";
    const vettingLabel = control.vettingEnabled === "1" ? "summarizer vetting on" : "summarizer vetting off";
    const contextLabel = control.contextMode === "full" ? "full worker packets" : "weighted worker packets";
    const reasoningLabel = optionLabelForValue(elements.reasoningEffort, control.reasoningEffort);

    if (elements.contractNarrative) {
      elements.contractNarrative.textContent =
        `Run the ${control.engineVersion.toUpperCase()} engine in ${control.executionMode} mode with ${providerLabel(control.provider)} / ${workerModelLabel} for the worker path, keep ${providerLabel(control.summarizerProvider)} / ${summarizerModelLabel} on the final answer lane, ${baselineLabel}, use ${contextLabel}, use ${reasoningLabel.toLowerCase()} reasoning, keep research ${researchLabel}, keep fractal memory ${memoryLabel}, and leave ${vettingLabel}.`;
    }

    elements.summaryPath.textContent =
      control.directBaselineMode === "both"
        ? "Para + Direct compare"
        : control.directBaselineMode === "single"
          ? "Para + staged direct baseline"
          : "Para only";
    elements.summaryLimits.textContent = `${control.loopRounds} rounds, $${control.maxCostUsd.toFixed(1)} spend wall`;
    if (elements.summaryReasoning) {
      elements.summaryReasoning.textContent = reasoningLabel;
    }
    if (elements.summaryContext) {
      elements.summaryContext.textContent = control.contextMode === "full" ? "Full" : "Light";
    }
    elements.summaryResearch.textContent = control.researchEnabled === "1" ? "On" : "Off";
    if (elements.summaryMemory) {
      elements.summaryMemory.textContent = control.knowledgebaseEnabled === "1" ? "On" : "Off";
    }

    elements.headerRuntime.textContent =
      control.executionMode === "judge" ? "Judge" : (control.executionMode === "eval" ? "Eval" : "Para");
    elements.headerBaseline.textContent =
      control.directBaselineMode === "both"
        ? "Both compare"
        : control.directBaselineMode === "single"
          ? "Single only"
          : "Off";
    elements.headerProvider.textContent = `${providerLabel(control.provider)} / ${workerModelLabel}`;
    elements.headerVetting.textContent = control.vettingEnabled === "1" ? "On" : "Off";
    renderComposerTools();
    renderLiveViewport(runtimeState.backendState || { draft: runtimeState.draft || {} });
  }

  function resizeObjectiveTextarea() {
    const textarea = elements.objective;
    if (!textarea) return;
    textarea.style.height = "auto";
    const maxHeight = objectiveTextareaMaxHeight(textarea);
    const nextHeight = Math.max(TEXTAREA_MIN_HEIGHT_PX, Math.min(textarea.scrollHeight || TEXTAREA_MIN_HEIGHT_PX, maxHeight));
    textarea.style.setProperty("--composer-textarea-height", `${nextHeight}px`);
    textarea.style.height = `${nextHeight}px`;
    textarea.scrollTop = textarea.scrollHeight;
    if (elements.composerRow) {
      elements.composerRow.classList.toggle("is-expanded", nextHeight > TEXTAREA_MIN_HEIGHT_PX + 4);
    }
  }

  function objectiveTextareaMaxHeight(textarea) {
    const style = window.getComputedStyle ? window.getComputedStyle(textarea) : null;
    const lineHeight = Number.parseFloat(style?.lineHeight || "") || 22;
    const paddingTop = Number.parseFloat(style?.paddingTop || "") || 0;
    const paddingBottom = Number.parseFloat(style?.paddingBottom || "") || 0;
    return Math.ceil((lineHeight * TEXTAREA_MAX_VISIBLE_ROWS) + paddingTop + paddingBottom);
  }

  function draftFlag(name, fallback) {
    return boolValue(runtimeState.draft?.[name], fallback);
  }

  function setDraftFlag(name, enabled) {
    runtimeState.draft = Object.assign({}, runtimeState.draft || {});
    runtimeState.draft[name] = Boolean(enabled);
  }

  function setComposerMenuOpen(open) {
    shellState.composerToolMenuOpen = Boolean(open);
    renderComposerTools();
  }

  function composerToolState(action) {
    if (action === "context") return elements.contextMode?.value === "full";
    if (action === "reasoning") return String(elements.reasoningEffort?.value || "low") !== "low";
    if (action === "web-search") return elements.researchMode.value === "1";
    if (action === "memory") return elements.memoryMode?.value === "1";
    if (action === "local-files") return draftFlag("localFilesEnabled", true);
    if (action === "github-tools") return draftFlag("githubToolsEnabled", false);
    if (action === "vetting") return elements.vettingEnabled.value !== "0";
    if (action === "upload") return shellState.stagedAttachments.length > 0;
    return false;
  }

  function composerToolLabel(action, active) {
    if (action === "upload") {
      return shellState.stagedAttachments.length
        ? `Upload files (${shellState.stagedAttachments.length} staged)`
        : "Upload files";
    }
    if (action === "context") return active ? "Context full" : "Context light";
    if (action === "reasoning") {
      return "Reasoning " + optionLabelForValue(elements.reasoningEffort, elements.reasoningEffort?.value || "low").toLowerCase();
    }
    if (action === "web-search") return active ? "Web search on" : "Web search off";
    if (action === "memory") return active ? "Fractal memory on" : "Fractal memory off";
    if (action === "local-files") return active ? "Local files on" : "Local files off";
    if (action === "github-tools") return active ? "GitHub tools on" : "GitHub tools off";
    if (action === "vetting") return active ? "Vetting on" : "Vetting off";
    return action;
  }

  function renderComposerAttachments() {
    if (!elements.composerAttachmentList) return;
    elements.composerAttachmentList.hidden = shellState.stagedAttachments.length === 0;
    elements.composerAttachmentList.innerHTML = shellState.stagedAttachments.map((attachment) => `
      <span class="igs-composer-attachment-chip">
        ${escapeHtml(attachment.name)} · ${escapeHtml(formatFileSize(attachment.size))}
        <button type="button" class="igs-composer-attachment-remove" data-attachment-id="${escapeHtml(attachment.id)}" aria-label="Remove ${escapeHtml(attachment.name)}">x</button>
      </span>
    `).join("");
  }

  function syncComposerReasoningOptions() {
    const selected = String(elements.reasoningEffort?.value || "low");
    composerReasoningOptions.forEach((button) => {
      const active = String(button.getAttribute("data-composer-reasoning-option") || "") === selected;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function renderComposerTools() {
    if (elements.composerToolMenu) {
      elements.composerToolMenu.hidden = !shellState.composerToolMenuOpen;
    }
    if (elements.composerToolMenuToggle) {
      elements.composerToolMenuToggle.classList.toggle("is-active", shellState.composerToolMenuOpen || shellState.stagedAttachments.length > 0);
      elements.composerToolMenuToggle.setAttribute("aria-expanded", shellState.composerToolMenuOpen ? "true" : "false");
      elements.composerToolMenuToggle.setAttribute(
        "title",
        shellState.stagedAttachments.length ? `${shellState.stagedAttachments.length} file(s) staged` : "Open tools"
      );
    }
    composerToolActions.forEach((button) => {
      const action = String(button.getAttribute("data-composer-tool-action") || "");
      const active = composerToolState(action);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.textContent = composerToolLabel(action, active);
    });
    syncComposerReasoningOptions();
    renderComposerAttachments();
  }

  function toggleComposerTool(action) {
    if (action === "upload") {
      setComposerMenuOpen(false);
      elements.composerFileInput?.click();
      return;
    }
    if (action === "web-search") {
      elements.researchMode.value = elements.researchMode.value === "1" ? "0" : "1";
      syncSelectToggleButtons("previewResearchMode");
    } else if (action === "context" && elements.contextMode) {
      elements.contextMode.value = elements.contextMode.value === "full" ? "weighted" : "full";
      syncSelectCycleButtons("previewContextMode");
    } else if (action === "memory" && elements.memoryMode) {
      elements.memoryMode.value = elements.memoryMode.value === "1" ? "0" : "1";
      syncSelectToggleButtons("previewMemoryMode");
    } else if (action === "local-files") {
      setDraftFlag("localFilesEnabled", !draftFlag("localFilesEnabled", true));
    } else if (action === "github-tools") {
      setDraftFlag("githubToolsEnabled", !draftFlag("githubToolsEnabled", false));
    } else if (action === "vetting") {
      elements.vettingEnabled.value = elements.vettingEnabled.value === "1" ? "0" : "1";
      syncSelectToggleButtons("previewVettingEnabled");
    }
    setComposerMenuOpen(false);
    updateNarrative();
    queueDraftSave();
  }

  function setComposerReasoning(value) {
    if (!elements.reasoningEffort) return;
    const nextValue = String(value || "low").trim();
    if (!nextValue) return;
    elements.reasoningEffort.value = nextValue;
    syncSelectCycleButtons("previewReasoningEffort");
    syncComposerReasoningOptions();
    updateNarrative();
    queueDraftSave();
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

  function runMessageHtml(kind, role, text, meta) {
    const normalized = String(text || "").trim();
    if (!normalized) return "";
    return `
      <article class="igs-message igs-message-${escapeHtml(kind || "system")} igs-run-message igs-run-message-${escapeHtml(kind || "system")}" aria-label="${escapeHtml(role || "Message")}${meta ? " - " + escapeHtml(meta) : ""}">
        <p>${escapeHtml(normalized)}</p>
      </article>
    `;
  }

  function runLaneCardHtml(label, status, text, tone) {
    return `
      <article class="igs-lane-card igs-lane-card-${escapeHtml(tone || "idle")}">
        <div class="igs-lane-card-head">
          <strong>${escapeHtml(label || "Lane")}</strong>
          <span>${escapeHtml(shortStatus(status, "idle"))}</span>
        </div>
        <p>${escapeHtml(truncateText(text || "No output captured yet.", 300))}</p>
      </article>
    `;
  }

  function activeTargetLabels(loop) {
    const targets = Array.isArray(loop?.activeTargets) ? loop.activeTargets : [];
    return targets.map((target) => {
      if (typeof target === "string") return target;
      return String(target?.targetLabel || target?.target || target?.id || "").trim();
    }).filter(Boolean);
  }

  function activeDispatchTargets(dispatch) {
    const jobs = Array.isArray(dispatch?.activeJobs) ? dispatch.activeJobs : [];
    const legacyTargets = Array.isArray(dispatch?.activeTargets) ? dispatch.activeTargets : [];
    return jobs.concat(legacyTargets).map((target) => {
      if (typeof target === "string") {
        return { id: target, label: target, status: "" };
      }
      return {
        id: String(target?.target || target?.id || target?.targetLabel || "").trim(),
        label: String(target?.targetLabel || target?.target || target?.id || "").trim(),
        status: String(target?.status || target?.schedulerState || "").trim(),
      };
    }).filter((target) => target.id || target.label);
  }

  function isRunBusy(loop) {
    const status = String(loop?.status || "").toLowerCase();
    return status === "running" || status === "queued" || activeTargetLabels(loop).length > 0;
  }

  function hasActiveDispatchTarget(state, target) {
    const normalized = String(target || "").toLowerCase();
    return activeTargetLabels(state?.loop || {}).some((activeTarget) => String(activeTarget || "").toLowerCase() === normalized)
      || activeDispatchTargets(state?.dispatch || {}).some((activeTarget) => (
        String(activeTarget.id || "").toLowerCase() === normalized
        || String(activeTarget.label || "").toLowerCase() === normalized
      ));
  }

  function answerNowReady(state) {
    const loop = state?.loop || {};
    if (hasFinalChatAnswer(state)) return false;
    if (!isRunBusy(loop)) return false;
    const task = state?.activeTask || null;
    const commander = state?.commander || task?.stateCommander || null;
    return !!task && Number(commander?.round || 0) > 0;
  }

  function updateComposerActionButton(state) {
    if (!elements.sendPrompt || !elements.sendIcon || !elements.sendText) return;
    const partialAnswerActive = !hasFinalChatAnswer(state) && hasActiveDispatchTarget(state, "answer_now");
    const ready = answerNowReady(state);
    const mode = partialAnswerActive ? "answering" : (ready ? "answer-now" : "send");
    elements.sendPrompt.dataset.composerActionMode = mode;
    elements.sendPrompt.disabled = partialAnswerActive;
    elements.sendPrompt.classList.toggle("is-answer-now", mode !== "send");
    if (mode === "answering") {
      elements.sendIcon.textContent = "";
      elements.sendText.textContent = "Answering";
      elements.sendPrompt.setAttribute("aria-label", "Answer now is running");
      elements.sendPrompt.setAttribute("title", "Answer now is running");
    } else if (mode === "answer-now") {
      elements.sendIcon.textContent = "";
      elements.sendText.textContent = "Answer now";
      elements.sendPrompt.setAttribute("aria-label", "Answer now");
      elements.sendPrompt.setAttribute("title", "Queue a partial answer from the current live run");
    } else {
      elements.sendIcon.textContent = "↑";
      elements.sendText.textContent = "Send prompt";
      elements.sendPrompt.setAttribute("aria-label", "Send prompt");
      elements.sendPrompt.setAttribute("title", "Send prompt");
    }
  }

  function summaryAnswerText(summary) {
    return firstText(summary?.frontAnswer?.answer, summary?.frontAnswer, summary?.answer, summary?.publicAnswer, summary?.output);
  }

  function directAnswerText(directBaseline) {
    return firstText(directBaseline?.answer?.answer, directBaseline?.answer, directBaseline?.output);
  }

  function activeSummaryState(state, task) {
    const summary = state?.summary && typeof state.summary === "object" ? state.summary : null;
    if (summary) return summary;
    const activeTask = task || state?.activeTask || null;
    return activeTask?.summary && typeof activeTask.summary === "object" ? activeTask.summary : null;
  }

  function activeDirectBaselineState(state, task) {
    const directBaseline = state?.directBaseline && typeof state.directBaseline === "object" ? state.directBaseline : null;
    if (directBaseline) return directBaseline;
    const activeTask = task || state?.activeTask || null;
    return activeTask?.directBaseline && typeof activeTask.directBaseline === "object" ? activeTask.directBaseline : null;
  }

  function hasFinalChatAnswer(state) {
    const task = state?.activeTask || null;
    return Boolean(summaryAnswerText(activeSummaryState(state, task)) || directAnswerText(activeDirectBaselineState(state, task)));
  }

  function buildActiveSessionMessages(state, busy, loopStatus) {
    const task = state?.activeTask || null;
    const messages = [];
    const activeObjective = firstText(task?.objective, task?.prompt, task?.input);
    if (activeObjective) {
      messages.push(runMessageHtml("user", "User", activeObjective, task?.runtime?.executionMode || "session"));
    }

    const finalAnswer = summaryAnswerText(activeSummaryState(state, task));
    const baselineAnswer = directAnswerText(activeDirectBaselineState(state, task));
    if (finalAnswer) {
      messages.push(runMessageHtml("assistant", "Assistant", finalAnswer, "summarizer output"));
    } else if (baselineAnswer) {
      messages.push(runMessageHtml("assistant", "Assistant", baselineAnswer, "single-thread baseline"));
    } else if (task) {
      messages.push(runMessageHtml(
        "system",
        "Runtime",
        busy ? "The live lanes are running. Background lane output is visible on the right as it lands." : "No final answer artifact is captured for this task yet.",
        busy ? "working" : loopStatus
      ));
    } else {
      messages.push(runMessageHtml("system", "Runtime", "Stage an objective and press Send to start the live lane stack.", "idle"));
    }
    return messages;
  }

  function renderLiveViewport(state) {
    if (!elements.runThread || !elements.laneGrid) return;
    const task = state?.activeTask || null;
    const draft = state?.draft || {};
    const loop = state?.loop || {};
    const workers = Array.isArray(task?.workers) && task.workers.length
      ? task.workers
      : (Array.isArray(draft?.workers) ? draft.workers : []);
    const workerState = state?.workers && typeof state.workers === "object" ? state.workers : {};
    const loopStatus = shortStatus(loop?.status, "idle");
    const lastMessage = firstText(loop?.lastMessage, state?.dispatch?.lastMessage);
    const activeTargets = activeTargetLabels(loop);
    const busy = isRunBusy(loop);

    if (elements.runActivity) {
      elements.runActivity.textContent = task
        ? [
            `Task ${task.taskId || "active"}`,
            `loop ${loopStatus}`,
            activeTargets.length ? `active ${activeTargets.join(", ")}` : "",
            lastMessage
          ].filter(Boolean).join(" | ")
        : "No live run is active.";
      elements.runActivity.classList.toggle("is-active", busy);
    }
    if (elements.traceSummary) {
      elements.traceSummary.textContent = [
        `Loop: ${loopStatus}`,
        loop?.jobId ? `Job: ${loop.jobId}` : "",
        lastMessage
      ].filter(Boolean).join(" | ") || "Waiting for scheduler activity.";
    }

    const finalAnswer = summaryAnswerText(state?.summary);
    const baselineAnswer = directAnswerText(state?.directBaseline);
    const messages = buildActiveSessionMessages(state, busy, loopStatus);
    elements.runThread.innerHTML = messages.join("");
    elements.runThread.scrollTop = elements.runThread.scrollHeight;

    const laneCards = [];
    laneCards.push(runLaneCardHtml(
      "Commander",
      state?.commander ? "completed" : (activeTargets.some((target) => /commander/i.test(target)) ? "running" : "waiting"),
      firstText(state?.commander?.answerDraft, state?.commander),
      state?.commander ? "done" : "idle"
    ));
    workers.forEach((worker) => {
      const checkpoint = workerState?.[worker.id];
      laneCards.push(runLaneCardHtml(
        worker.label || worker.id || "Worker",
        checkpoint ? "completed" : (activeTargets.some((target) => target === worker.id || target.includes(worker.id)) ? "running" : "waiting"),
        firstText(
          checkpoint?.observation,
          checkpoint?.detriments,
          checkpoint?.benefits,
          checkpoint?.uncertainty,
          checkpoint
        ),
        checkpoint ? "done" : "idle"
      ));
    });
    laneCards.push(runLaneCardHtml(
      "Commander review",
      state?.commanderReview ? "completed" : (activeTargets.some((target) => /review/i.test(target)) ? "running" : "waiting"),
      firstText(
        state?.commanderReview?.answerDraft,
        state?.commanderReview?.requiredDecisionGates,
        state?.commanderReview?.evidenceOrCommsRisks,
        state?.commanderReview
      ),
      state?.commanderReview ? "done" : "idle"
    ));
    laneCards.push(runLaneCardHtml(
      "Summarizer",
      state?.summary ? "completed" : (activeTargets.some((target) => /summarizer|final/i.test(target)) ? "running" : "waiting"),
      finalAnswer || firstText(state?.summary?.summarizerOpinion, state?.summary),
      state?.summary ? "done" : "idle"
    ));
    if (state?.directBaseline) {
      laneCards.push(runLaneCardHtml("Direct baseline", "completed", baselineAnswer, "done"));
    }
    elements.laneGrid.innerHTML = laneCards.join("");
    updateComposerActionButton(state);
  }

  async function loadRunLogs() {
    const [steps, events] = await Promise.all([
      fetchText(API.steps),
      fetchText(API.events),
    ]);
    const stepText = tailLines(steps, 80);
    const eventText = tailLines(events, 80);
    if (elements.stepLog) {
      elements.stepLog.textContent = stepText;
    }
    if (elements.eventLog) {
      elements.eventLog.textContent = eventText;
    }
    if (elements.debugStepLog) {
      elements.debugStepLog.textContent = stepText;
    }
    if (elements.debugEventLog) {
      elements.debugEventLog.textContent = eventText;
    }
  }

  function activeTaskForDebug(state) {
    const task = state?.activeTask || null;
    if (!task) return null;
    return Object.assign({}, task, {
      workers: Array.isArray(task.workers) ? task.workers : (Array.isArray(state?.draft?.workers) ? state.draft.workers : []),
      stateWorkers: state?.workers || {},
      stateCommander: state?.commander || null,
      stateCommanderReview: state?.commanderReview || null,
      directBaseline: state?.directBaseline || null,
      summary: state?.summary || null,
    });
  }

  function debugWorkspaceBusy(state) {
    const loopStatus = String(state?.loop?.status || "").toLowerCase();
    const dispatchStatus = String(state?.dispatch?.status || "").toLowerCase();
    return ["queued", "running"].includes(loopStatus)
      || ["queued", "running"].includes(dispatchStatus)
      || activeTargetLabels(state?.loop || {}).length > 0;
  }

  function debugTargetButtonHtml(target, label, disabled) {
    return `<button type="button" class="btn btn-outline-light btn-sm" data-debug-target="${escapeHtml(target)}"${disabled ? " disabled" : ""}>${escapeHtml(label)}</button>`;
  }

  function renderDebugTargetControls(state) {
    if (!elements.debugTargetControls) return;
    const task = activeTaskForDebug(state);
    if (!task?.taskId) {
      elements.debugTargetControls.innerHTML = `<div class="igs-debug-card">No active task.</div>`;
      return;
    }

    const busy = debugWorkspaceBusy(state);
    const commanderRound = Number(state?.commander?.round || task?.stateCommander?.round || 0);
    const reviewReady = !!state?.commanderReview;
    const summaryReady = reviewReady || !!state?.summary;
    const workers = Array.isArray(task.workers) ? task.workers : [];
    const directMode = String(task?.runtime?.directBaselineMode || state?.draft?.directBaselineMode || "off").toLowerCase();
    const activeAnswerNow = hasActiveDispatchTarget(state, "answer_now");
    const cards = [];

    if (directMode !== "off") {
      cards.push(`
        <article class="igs-debug-card">
          <div class="igs-debug-card-title">Single-thread baseline</div>
          <div class="igs-debug-card-meta">${escapeHtml(state?.directBaseline ? "Baseline captured." : "Manual baseline target.")}</div>
          <div class="igs-debug-card-actions">
            ${debugTargetButtonHtml("direct_baseline", "Run baseline", busy || !!state?.directBaseline)}
          </div>
        </article>
      `);
    }

    cards.push(`
      <article class="igs-debug-card">
        <div class="igs-debug-card-title">Commander</div>
        <div class="igs-debug-card-meta">${escapeHtml(commanderRound > 0 ? "Round " + commanderRound : "Ready for round 1")}</div>
        <div class="igs-debug-card-actions">
          ${debugTargetButtonHtml("commander", "Run commander", busy)}
        </div>
      </article>
    `);

    workers.forEach((worker) => {
      const workerId = String(worker?.id || "").trim();
      if (!workerId) return;
      const checkpoint = state?.workers?.[workerId] || null;
      const label = worker.label || worker.type || worker.role || workerId;
      cards.push(`
        <article class="igs-debug-card">
          <div class="igs-debug-card-title">${escapeHtml(workerId + " | " + label)}</div>
          <div class="igs-debug-card-meta">${escapeHtml(checkpoint ? "Checkpoint step " + String(checkpoint.step || 0) : "No checkpoint yet.")}</div>
          <div class="igs-debug-card-actions">
            ${debugTargetButtonHtml(workerId, "Run " + workerId, busy || commanderRound <= 0)}
          </div>
        </article>
      `);
    });

    cards.push(`
      <article class="igs-debug-card">
        <div class="igs-debug-card-title">Commander Review</div>
        <div class="igs-debug-card-meta">${escapeHtml(reviewReady ? "Review checkpoint captured." : "Waiting on commander-aligned workers.")}</div>
        <div class="igs-debug-card-actions">
          ${debugTargetButtonHtml("commander_review", "Run review", busy || commanderRound <= 0)}
        </div>
      </article>
    `);

    cards.push(`
      <article class="igs-debug-card">
        <div class="igs-debug-card-title">Summarizer</div>
        <div class="igs-debug-card-meta">${escapeHtml(summaryReady ? "Ready to produce final or partial answer." : "Waiting on review/checkpoints.")}</div>
        <div class="igs-debug-card-actions">
          ${debugTargetButtonHtml("summarizer", "Summarize", busy || !summaryReady)}
          ${debugTargetButtonHtml("answer_now", "Answer Now", !answerNowReady(state) || activeAnswerNow)}
        </div>
      </article>
    `);

    elements.debugTargetControls.innerHTML = cards.join("");
  }

  function renderDebugSchedulerEvents(state) {
    if (!elements.debugSchedulerEvents) return;
    const task = activeTaskForDebug(state);
    const loop = state?.loop || {};
    const dispatch = state?.dispatch || {};
    if (!task?.taskId) {
      elements.debugSchedulerEvents.innerHTML = `<div class="igs-debug-card">No active task.</div>`;
      return;
    }
    const activeTargets = activeTargetLabels(loop);
    const dispatchTargets = activeDispatchTargets(dispatch);
    const cards = [
      `
        <article class="igs-debug-card">
          <div class="igs-debug-card-title">${escapeHtml(task.taskId)}</div>
          <div class="igs-debug-card-meta">${escapeHtml("Loop " + String(loop.status || "idle") + " | " + Number(loop.completedRounds || 0) + "/" + Number(loop.totalRounds || 0) + " rounds")}</div>
        </article>
      `,
    ];
    activeTargets.forEach((target) => {
      cards.push(`
        <article class="igs-debug-card is-active">
          <div class="igs-debug-card-title">${escapeHtml(target)}</div>
          <div class="igs-debug-card-meta">Active loop target.</div>
        </article>
      `);
    });
    dispatchTargets.forEach((target) => {
      const label = target.label || target.id || "dispatch";
      cards.push(`
        <article class="igs-debug-card is-active">
          <div class="igs-debug-card-title">${escapeHtml(label)}</div>
          <div class="igs-debug-card-meta">${escapeHtml(String(target.status || dispatch.status || "dispatch"))}</div>
        </article>
      `);
    });
    elements.debugSchedulerEvents.innerHTML = cards.join("");
  }

  function renderDebugState(state) {
    renderDebugTargetControls(state);
    renderDebugSchedulerEvents(state);
  }

  function debugHistoryCard(title, meta, actionsHtml) {
    return `
      <article class="igs-debug-card">
        <div class="igs-debug-card-title">${escapeHtml(title || "Entry")}</div>
        <div class="igs-debug-card-meta">${escapeHtml(meta || "No metadata.")}</div>
        ${actionsHtml ? `<div class="igs-debug-card-actions">${actionsHtml}</div>` : ""}
      </article>
    `;
  }

  function renderDebugJobHistory(payload) {
    if (!elements.debugJobHistory) return;
    const warnings = Array.isArray(payload?.contractWarnings) ? payload.contractWarnings.filter(Boolean) : [];
    const cards = [];
    warnings.forEach((warning) => {
      cards.push(debugHistoryCard("Telemetry note", warning, ""));
    });
    if (payload?.recoveryWarning) {
      cards.push(debugHistoryCard("Recovery note", payload.recoveryWarning, ""));
    }
    const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
    if (!jobs.length) {
      cards.push(debugHistoryCard("Queue policy", "No recent jobs yet. Background loops and target dispatches will appear here.", ""));
      elements.debugJobHistory.innerHTML = cards.join("");
      return;
    }
    jobs.forEach((job) => {
      const isTarget = String(job?.jobType || "loop") === "target";
      const title = isTarget
        ? ((job?.target === "answer_now" ? "Answer Now" : "Dispatch " + String(job?.target || "target")) + " | " + String(job?.taskId || job?.jobId || "job"))
        : (String(job?.objective || job?.taskId || job?.jobId || "Loop job"));
      const meta = [
        "Status " + String(job?.status || "unknown"),
        isTarget ? "target " + String(job?.target || "target") : "rounds " + Number(job?.completedRounds || 0) + "/" + Number(job?.rounds || 0),
        "attempt " + Number(job?.attempt || 1),
        job?.lastMessage ? "note " + job.lastMessage : "",
        job?.error ? "error " + job.error : "",
      ].filter(Boolean).join(" | ");
      const actions = [];
      if (job?.canResume) actions.push(`<button type="button" class="btn btn-outline-info btn-sm" data-debug-job-action="resume" data-job-id="${escapeHtml(job.jobId || "")}">Resume</button>`);
      if (job?.canRetry) actions.push(`<button type="button" class="btn btn-outline-light btn-sm" data-debug-job-action="retry" data-job-id="${escapeHtml(job.jobId || "")}">Retry</button>`);
      if (job?.canCancel) actions.push(`<button type="button" class="btn btn-outline-danger btn-sm" data-debug-job-action="cancel" data-job-id="${escapeHtml(job.jobId || "")}">Cancel</button>`);
      cards.push(debugHistoryCard(title, meta, actions.join("")));
    });
    elements.debugJobHistory.innerHTML = cards.join("");
  }

  function renderDebugRoundHistory(rounds) {
    if (!elements.debugRoundHistory) return;
    const entries = Array.isArray(rounds) ? rounds : [];
    if (!entries.length) {
      elements.debugRoundHistory.innerHTML = debugHistoryCard("No round history yet", "Round artifacts will appear after commander, worker, review, or summary output is captured.", "");
      return;
    }
    elements.debugRoundHistory.innerHTML = entries.map((roundEntry) => {
      const artifacts = [
        roundEntry?.commanderArtifact?.name ? "commander " + roundEntry.commanderArtifact.name : "",
        roundEntry?.commanderReviewArtifact?.name ? "review " + roundEntry.commanderReviewArtifact.name : "",
        roundEntry?.summaryArtifact?.name ? "summary " + roundEntry.summaryArtifact.name : "",
        Array.isArray(roundEntry?.workerArtifacts) && roundEntry.workerArtifacts.length ? String(roundEntry.workerArtifacts.length) + " worker artifacts" : "",
      ].filter(Boolean).join(" | ");
      return debugHistoryCard(
        "Round " + String(roundEntry?.round || 0) + " | " + String(roundEntry?.taskId || "task"),
        [truncateText(roundEntry?.objective || "No objective recorded.", 120), "captured " + String(roundEntry?.capturedAt || "n/a"), artifacts].filter(Boolean).join(" | "),
        ""
      );
    }).join("");
  }

  function renderDebugSessionArchives(sessions) {
    if (!elements.debugSessionArchives) return;
    const entries = Array.isArray(sessions) ? sessions : [];
    if (!entries.length) {
      elements.debugSessionArchives.innerHTML = debugHistoryCard("No session archives yet", "Reset Session will archive the current workspace before clearing it.", "");
      return;
    }
    elements.debugSessionArchives.innerHTML = entries.map((session) => {
      const file = String(session?.file || "");
      const actions = `
        <button type="button" class="btn btn-outline-info btn-sm" data-debug-export-archive="${escapeHtml(file)}">Preview export</button>
        <button type="button" class="btn btn-outline-warning btn-sm" data-debug-replay-archive="${escapeHtml(file)}">Replay</button>
      `;
      return debugHistoryCard(
        file || "archive",
        ["task " + String(session?.taskId || "none"), "archived " + String(session?.archivedAt || "n/a"), "reason " + String(session?.reason || "unspecified")].join(" | "),
        actions
      );
    }).join("");
  }

  function syncDebugArchiveClearButton(history) {
    if (!elements.debugClearSessionArchives) return;
    const count = Number(history?.sessionArchiveCount || 0);
    elements.debugClearSessionArchives.disabled = count <= 0;
    elements.debugClearSessionArchives.textContent = count > 0 ? "Clear Session Archives (" + count + ")" : "Clear Session Archives";
  }

  async function loadDebugHistory() {
    if (!elements.debugJobHistory) return;
    if (elements.debugHistoryStatus) {
      elements.debugHistoryStatus.textContent = "Loading jobs, rounds, and archived sessions...";
    }
    const payload = await fetchJson(API.history);
    renderDebugJobHistory(payload);
    renderDebugRoundHistory(payload?.rounds);
    renderDebugSessionArchives(payload?.sessions);
    syncDebugArchiveClearButton(payload);
    if (elements.debugHistoryStatus) {
      const jobCount = Array.isArray(payload?.jobs) ? payload.jobs.length : 0;
      const roundCount = Array.isArray(payload?.rounds) ? payload.rounds.length : 0;
      const sessionCount = Number(payload?.sessionArchiveCount || 0);
      elements.debugHistoryStatus.textContent = "Loaded " + jobCount + " jobs, " + roundCount + " rounds, " + sessionCount + " archived sessions.";
    }
  }

  async function loadDebugExportPreview(archiveFile) {
    if (!elements.debugExportPreview) return;
    const file = String(archiveFile || "").trim();
    elements.debugExportPreview.textContent = file ? "Loading " + file + "..." : "Loading current session export...";
    const query = file ? "?archiveFile=" + encodeURIComponent(file) : "";
    const payload = await fetchJson(API.sessionExport + query);
    elements.debugExportPreview.textContent = prettyJson(payload);
    if (elements.debugHistoryStatus) {
      elements.debugHistoryStatus.textContent = file ? "Previewing archived session " + file + "." : "Previewing current session export.";
    }
  }

  function sessionStateFromExport(payload) {
    const archive = payload?.archive && typeof payload.archive === "object" ? payload.archive : null;
    const sourceState = archive?.state && typeof archive.state === "object"
      ? archive.state
      : (payload?.state && typeof payload.state === "object" ? payload.state : {});
    const state = Object.assign({}, sourceState);
    if (!state.activeTask && archive) {
      state.activeTask = {
        taskId: archive.taskId || "",
        objective: archive.objective || "",
        runtime: { executionMode: "archive" },
      };
    }
    return state;
  }

  function renderSessionExportThread(payload) {
    const state = sessionStateFromExport(payload);
    const loopStatus = shortStatus(state?.loop?.status, payload?.source === "archive" ? "archived" : "current");
    const messages = buildActiveSessionMessages(state, false, loopStatus);
    return messages.join("") || runMessageHtml("system", "Runtime", "No thread content was found in this session export.", loopStatus);
  }

  function currentSessionEntry(state) {
    const activeTask = state?.activeTask && typeof state.activeTask === "object" ? state.activeTask : null;
    const draft = state?.draft && typeof state.draft === "object" ? state.draft : {};
    const objective = firstText(activeTask?.objective, draft?.objective, "Current workspace");
    const answer = firstText(summaryAnswerText(state?.summary), directAnswerText(state?.directBaseline), state?.loop?.lastMessage);
    return {
      key: "current",
      kind: "current",
      file: "",
      label: "Current session",
      taskId: activeTask?.taskId || "active",
      objective,
      archivedAt: state?.lastUpdated || "",
      reason: "live workspace",
      preview: answer,
      searchText: ["current", activeTask?.taskId, objective, answer].filter(Boolean).join(" ").toLowerCase(),
    };
  }

  function buildSessionBrowserEntries(history, state) {
    const entries = [currentSessionEntry(state || {})];
    (Array.isArray(history?.sessions) ? history.sessions : []).forEach((session) => {
      const file = String(session?.file || "").trim();
      if (!file) return;
      const objective = String(session?.objective || "").trim() || "Archived session";
      const preview = String(session?.carryContextPreview || "").trim();
      entries.push({
        key: file,
        kind: "archive",
        file,
        label: file,
        taskId: String(session?.taskId || "none"),
        objective,
        archivedAt: String(session?.archivedAt || session?.createdAt || ""),
        reason: String(session?.reason || "unspecified"),
        preview,
        searchText: [file, session?.taskId, objective, session?.reason, preview].filter(Boolean).join(" ").toLowerCase(),
      });
    });
    return entries;
  }

  function filteredSessionEntries() {
    const query = String(elements.sessionSearch?.value || "").trim().toLowerCase();
    if (!query) return sessionBrowserState.entries;
    return sessionBrowserState.entries.filter((entry) => String(entry.searchText || "").includes(query));
  }

  function sessionCardHtml(entry) {
    const active = String(entry?.key || "") === sessionBrowserState.selectedKey;
    const badge = entry?.kind === "current" ? "Current" : "Archive";
    const actions = entry?.kind === "archive"
      ? `<button type="button" class="btn btn-outline-warning btn-sm" data-session-continue="${escapeHtml(entry.key)}">Continue</button>`
      : "";
    return `
      <article class="igs-session-card${active ? " is-active" : ""}" data-session-key="${escapeHtml(entry.key || "")}">
        <button type="button" class="igs-session-card-main" data-session-select="${escapeHtml(entry.key || "")}">
          <span class="igs-session-card-badge">${escapeHtml(badge)}</span>
          <strong>${escapeHtml(entry.objective || entry.label || "Session")}</strong>
          <small>${escapeHtml(["task " + String(entry.taskId || "none"), entry.archivedAt || "", entry.reason || ""].filter(Boolean).join(" | "))}</small>
          ${entry.preview ? `<p>${escapeHtml(truncateText(entry.preview, 180))}</p>` : ""}
        </button>
        <div class="igs-session-card-actions">
          <button type="button" class="btn btn-outline-info btn-sm" data-session-preview="${escapeHtml(entry.key || "")}">View</button>
          ${actions}
        </div>
      </article>
    `;
  }

  function renderSessionBrowserList() {
    if (!elements.sessionList) return;
    const entries = filteredSessionEntries();
    if (!entries.length) {
      elements.sessionList.innerHTML = `<div class="igs-inline-note">No sessions match that search.</div>`;
      return;
    }
    elements.sessionList.innerHTML = entries.map(sessionCardHtml).join("");
  }

  function selectedSessionEntry() {
    return sessionBrowserState.entries.find((entry) => entry.key === sessionBrowserState.selectedKey)
      || sessionBrowserState.entries[0]
      || null;
  }

  function renderSessionExport(payload, entry) {
    if (elements.sessionThread) {
      elements.sessionThread.innerHTML = renderSessionExportThread(payload);
    }
    if (elements.sessionRawExport) {
      elements.sessionRawExport.textContent = prettyJson(payload || {});
    }
    if (elements.sessionDetailMeta) {
      const source = entry?.kind === "archive" ? "Archived session" : "Current session";
      elements.sessionDetailMeta.textContent = [
        source,
        entry?.taskId ? "task " + entry.taskId : "",
        entry?.archivedAt || "",
        entry?.reason ? "reason " + entry.reason : "",
      ].filter(Boolean).join(" | ") || "Session selected.";
    }
    if (elements.sessionReplayBtn) {
      const replayable = entry?.kind === "archive";
      elements.sessionReplayBtn.disabled = !replayable;
      elements.sessionReplayBtn.dataset.sessionReplay = replayable ? String(entry.key || "") : "";
    }
  }

  async function loadSessionExport(archiveFile) {
    const file = String(archiveFile || "").trim();
    if (elements.sessionStatus) {
      elements.sessionStatus.textContent = file ? "Loading archived session " + file + "..." : "Loading current session export...";
    }
    const query = file ? "?archiveFile=" + encodeURIComponent(file) : "";
    const payload = await fetchJson(API.sessionExport + query);
    sessionBrowserState.exportPayload = payload;
    renderSessionExport(payload, selectedSessionEntry());
    if (elements.sessionStatus) {
      elements.sessionStatus.textContent = file ? "Previewing archived session " + file + "." : "Previewing current session.";
    }
    return payload;
  }

  async function selectSessionForPreview(key) {
    const nextKey = String(key || "current").trim() || "current";
    sessionBrowserState.selectedKey = nextKey;
    renderSessionBrowserList();
    const entry = selectedSessionEntry();
    await loadSessionExport(entry?.file || "");
  }

  async function previewCurrentSession() {
    sessionBrowserState.selectedKey = "current";
    renderSessionBrowserList();
    await loadSessionExport("");
  }

  async function loadSessionBrowser() {
    if (!elements.sessionList) return;
    if (elements.sessionStatus) {
      elements.sessionStatus.textContent = "Loading current and archived sessions...";
    }
    const [history, state] = await Promise.all([
      fetchJson(API.history),
      fetchJson(API.state),
    ]);
    runtimeState.backendState = state || runtimeState.backendState;
    sessionBrowserState.entries = buildSessionBrowserEntries(history || {}, state || {});
    sessionBrowserState.loaded = true;
    if (!sessionBrowserState.entries.some((entry) => entry.key === sessionBrowserState.selectedKey)) {
      sessionBrowserState.selectedKey = "current";
    }
    renderSessionBrowserList();
    await loadSessionExport(selectedSessionEntry()?.file || "");
  }

  async function continueSelectedSession(archiveFile) {
    const file = String(archiveFile || selectedSessionEntry()?.file || "").trim();
    if (!file) return;
    if (!window.confirm("Continue from " + file + " in Home?")) return;
    if (elements.sessionStatus) {
      elements.sessionStatus.textContent = "Continuing archived session " + file + "...";
    }
    await fetchJson(API.sessionReplay, jsonPostOptions({ archiveFile: file }));
    await loadState({ hydrate: true });
    sessionBrowserState.selectedKey = "current";
    await loadSessionBrowser();
    setActiveView("home");
  }

  async function refreshDebugSurface() {
    if (elements.debugOperationStatus) {
      elements.debugOperationStatus.textContent = "Refreshing Debug...";
    }
    await Promise.all([
      loadState({ hydrate: false }),
      loadDebugHistory(),
      loadRunLogs(),
    ]);
    if (elements.debugOperationStatus) {
      elements.debugOperationStatus.textContent = "Debug refreshed.";
    }
  }

  async function runDebugOperation(url, payload, successText, options) {
    const settings = Object.assign({ hydrate: false }, options || {});
    if (elements.debugOperationStatus) {
      elements.debugOperationStatus.textContent = "Sending " + successText.toLowerCase() + "...";
    }
    const response = await fetchJson(url, jsonPostOptions(payload));
    if (elements.debugOperationStatus) {
      elements.debugOperationStatus.textContent = successText + ".";
    }
    await loadState({ hydrate: settings.hydrate });
    await loadDebugHistory();
    return response;
  }

  function draftPayloadForSave(options) {
    const settings = Object.assign({ includeAttachments: false }, options || {});
    const control = currentControlState();
    const existing = runtimeState.draft ? clone(runtimeState.draft) : {};
    const summarizerHarness = existing.summarizerHarness || { concision: "balanced", instruction: "" };
    const directHarness = existing.directHarness || {
      concision: "none",
      instruction: "Prefer the most detailed factual response the evidence supports. Be concrete, complete, and explicit about uncertainty.",
    };
    const providerRouting = existing.providerRouting || { ollama: { selectionMode: "single", judgeMode: "prefer_distinct" } };
    const existingKnowledgebase = existing.knowledgebase && typeof existing.knowledgebase === "object" ? existing.knowledgebase : {};
    const knowledgebaseEnabled = control.knowledgebaseEnabled === "1";

    return {
      objective: control.objective,
      constraints: control.constraints,
      sessionContext: settings.includeAttachments ? buildSendSessionContext(control.sessionContext) : control.sessionContext,
      executionMode: control.executionMode,
      frontMode: "full",
      engineVersion: control.engineVersion,
      engineGraph: existing.engineGraph || null,
      providerRouting: providerRouting,
      contextMode: control.contextMode,
      directBaselineMode: control.directBaselineMode,
      provider: control.provider,
      model: control.model,
      modelSource: control.modelSource,
      summarizerProvider: control.summarizerProvider,
      summarizerModel: control.summarizerModel,
      summarizerModelSource: control.summarizerModelSource,
      directProvider: control.provider,
      directModel: control.model,
      directModelSource: control.modelSource,
      directHarness: directHarness,
      summarizerHarness: summarizerHarness,
      ollamaBaseUrl: existing.ollamaBaseUrl || "http://127.0.0.1:11434",
      timeoutMode: existing.timeoutMode || "default",
      ollamaTimeoutProfile: existing.ollamaTimeoutProfile || null,
      targetTimeouts: existing.targetTimeouts || null,
      reasoningEffort: control.reasoningEffort,
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
      knowledgebaseEnabled: knowledgebaseEnabled,
      knowledgebase: Object.assign({}, existingKnowledgebase, { enabled: knowledgebaseEnabled }),
      dynamicSpinupEnabled: existing.dynamicSpinupEnabled === true,
      vettingEnabled: control.vettingEnabled === "1",
      loopRounds: control.loopRounds,
      loopDelayMs: Number(existing.loopDelayMs || 1000),
      workers: Array.isArray(existing.workers) ? existing.workers.map((worker) => Object.assign({}, worker, { model: control.model, modelSource: control.modelSource })) : [],
    };
  }

  function liveRunPayload() {
    const draftPayload = draftPayloadForSave({ includeAttachments: true });
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

  function clearComposerAfterSend() {
    clearTimeout(runtimeState.saveTimer);
    runtimeState.saveTimer = null;
    if (elements.objective) {
      elements.objective.value = "";
    }
    if (runtimeState.draft && typeof runtimeState.draft === "object") {
      runtimeState.draft.objective = "";
    }
    shellState.stagedAttachments = [];
    resizeObjectiveTextarea();
    renderComposerTools();
  }

  function fillModelsForCurrentProviders() {
    const workerProvider = selectedGroupedValue("provider", "openai");
    syncSummarizerProviderButtons(elements.summarizerProvider?.value || workerProvider);
    populateSelect(
      elements.workerModel,
      modelOptions(workerProvider),
      elements.workerModel.value || runtimeState.draft?.model || "",
      runtimeState.draft?.modelSource
    );
    populateSelect(
      elements.summarizerModel,
      modelOptions(elements.summarizerProvider.value || workerProvider),
      elements.summarizerModel.value || runtimeState.draft?.summarizerModel || "",
      runtimeState.draft?.summarizerModelSource
    );
    syncContractPillSelects();
  }

  function hydrateControls(draft, state) {
    runtimeState.controlsLoaded = false;
    runtimeState.backendState = state;
    runtimeState.draft = clone(draft);

    elements.runtimeMode.value = String(draft.executionMode || "live");
    if (elements.engineVersion) {
      elements.engineVersion.value = String(draft.engineVersion || "v1");
    } else {
      setGroupedButton("engine", String(draft.engineVersion || "v1"));
    }
    setGroupedButton("provider", String(draft.provider || "openai"));
    setSummarizerProviderValue(String(draft.summarizerProvider || draft.provider || "openai"));
    fillModelsForCurrentProviders();
    populateSelect(elements.workerModel, modelOptions(draft.provider || "openai"), String(draft.model || elements.workerModel.value || ""), draft.modelSource);
    populateSelect(elements.summarizerModel, modelOptions(elements.summarizerProvider.value), String(draft.summarizerModel || ""), draft.summarizerModelSource);
    elements.contextMode.value = String(draft.contextMode || "weighted");
    if (elements.reasoningEffort) {
      elements.reasoningEffort.value = String(draft.reasoningEffort || "low");
    }
    elements.directBaselineMode.value = String(draft.directBaselineMode || "off");
    elements.vettingEnabled.value = toBoolString(draft.vettingEnabled);
    elements.researchMode.value = draft.researchEnabled ? "1" : "0";
    if (elements.memoryMode) {
      elements.memoryMode.value = draft.knowledgebaseEnabled ? "1" : "0";
    }
    syncSelectToggleButtons();
    syncSelectCycleButtons();
    elements.objective.value = String(draft.objective || "");
    resizeObjectiveTextarea();
    elements.sessionContext.value = String(draft.sessionContext || "");
    elements.constraints.value = Array.isArray(draft.constraints) ? draft.constraints.join("\n") : "";
    elements.loopRounds.value = String(draft.loopRounds || 3);
    elements.maxCostUsd.value = String(Number(draft.maxCostUsd || 0));

    syncHeaderFromBackend(state);
    syncContractPillSelects();
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
      queueCodexLimitsLoad();
    } else {
      runtimeState.backendState = state;
      syncHeaderFromBackend(state);
    }
    renderLiveViewport(state);
    renderDebugState(state);
    loadRunLogs().catch(function (error) {
      if (elements.traceSummary) {
        elements.traceSummary.textContent = "Trace load failed: " + String(error.message || error);
      }
      if (elements.debugOperationStatus) {
        elements.debugOperationStatus.textContent = "Trace load failed: " + String(error.message || error);
      }
    });
  }

  async function sendPrompt() {
    const payload = liveRunPayload();
    if (!payload.objective) {
      elements.draftState.textContent = "Objective is required before Send.";
      return;
    }
    if (!(await ensureAuthRequirementsReady(payload))) {
      elements.draftState.textContent = "Run paused: provider authentication is required.";
      return;
    }
    const executionMode = String(payload.executionMode || "live").toLowerCase();
    const runEndpoint = executionMode === "eval"
      ? API.frontEvalRuns
      : (executionMode === "judge" ? API.frontJudgeRuns : API.frontLiveRuns);
    const runLabel = executionMode === "eval" ? "eval" : (executionMode === "judge" ? "judge" : "live");
    elements.draftState.textContent = "Queueing " + runLabel + " run...";
    if (elements.runActivity) {
      elements.runActivity.textContent = "Queueing " + runLabel + " run...";
      elements.runActivity.classList.add("is-active");
    }
    const response = await fetchJson(runEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    elements.draftState.textContent = `Front ${runLabel} queued: ${String(response?.runId || "run created")}`;
    clearComposerAfterSend();
    await loadState({ hydrate: false });
  }

  async function queueAnswerNow() {
    const state = runtimeState.backendState || {};
    if (!answerNowReady(state) || hasActiveDispatchTarget(state, "answer_now")) {
      return;
    }
    updateComposerActionButton(Object.assign({}, state, { loop: Object.assign({}, state.loop || {}, { activeTargets: ["answer_now"] }) }));
    await fetchJson(API.targetsBackground, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "answer_now" }),
    });
    elements.draftState.textContent = "Answer now queued.";
    await loadState({ hydrate: false });
  }

  function submitComposerAction() {
    if (!elements.sendPrompt || elements.sendPrompt.disabled) return;
    const mode = elements.sendPrompt.dataset.composerActionMode || "send";
    const action = mode === "answer-now" ? queueAnswerNow() : sendPrompt();
    action.catch(function (error) {
      elements.draftState.textContent = (mode === "answer-now" ? "Answer now failed: " : "Send failed: ") + String(error.message || error);
      updateComposerActionButton(runtimeState.backendState || {});
    });
  }

  function scoreBlockScores(block) {
    if (!block || typeof block !== "object") return {};
    return block.scores && typeof block.scores === "object" ? block.scores : block;
  }

  function scoreValue(block, key) {
    const scores = scoreBlockScores(block);
    const value = Number(scores?.[key] || 0);
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  function formatScore(value) {
    return value == null ? "n/a" : Number(value).toFixed(1);
  }

  function replicateNumber(replicate, fallbackIndex) {
    const value = Number(replicate?.replicate || fallbackIndex || 1);
    return Number.isFinite(value) && value > 0 ? value : 1;
  }

  function variantType(variant) {
    const type = String(variant?.type || "").trim().toLowerCase();
    if (type) return type;
    const id = String(variant?.variantId || "");
    if (id.startsWith("direct-")) return "direct";
    if (id.startsWith("para-")) return "steered";
    return "";
  }

  function variantProvider(variant) {
    return String(variant?.provider || variant?.directProvider || variant?.summarizerProvider || "").trim();
  }

  function variantModel(variant) {
    return String(variant?.model || variant?.directModel || variant?.summarizerModel || "").trim();
  }

  function runVariantCounts(run) {
    const counts = { steered: 0, direct: 0 };
    (Array.isArray(run?.cases) ? run.cases : []).forEach((caseEntry) => {
      (Array.isArray(caseEntry?.variants) ? caseEntry.variants : []).forEach((variant) => {
        const type = variantType(variant);
        if (type === "steered") counts.steered += 1;
        if (type === "direct") counts.direct += 1;
      });
    });
    return counts;
  }

  function findCompanionDirectRunId(runs, selectedRun) {
    const currentRunId = String(selectedRun?.runId || "").trim();
    const selectedSuite = String(selectedRun?.suiteId || "").toLowerCase();
    const selectedCases = new Set((Array.isArray(selectedRun?.cases) ? selectedRun.cases : [])
      .map((caseEntry) => String(caseEntry?.caseId || "").trim())
      .filter(Boolean));
    return (Array.isArray(runs) ? runs : [])
      .filter((run) => {
        const runId = String(run?.runId || "").trim();
        if (!runId || runId === currentRunId) return false;
        const suite = String(run?.suiteId || "").toLowerCase();
        if (!suite.includes("direct")) return false;
        if (selectedSuite.includes("five") && !suite.includes("five")) return false;
        return true;
      })
      .map((run) => {
        const suite = String(run?.suiteId || "").toLowerCase();
        let score = Number(run?.summary?.variantCount || 0);
        if (suite.includes("direct")) score += 100;
        if (selectedSuite.includes("msp") && suite.includes("msp")) score += 20;
        if (selectedCases.size && Number(run?.summary?.variantCount || 0) >= selectedCases.size) score += 10;
        return { run, score };
      })
      .sort((a, b) => b.score - a.score)
      .map((entry) => String(entry.run?.runId || "").trim())
      .find(Boolean) || "";
  }

  function mergeDirectRunIntoSelectedRun(selectedRun, directRun) {
    if (!selectedRun || !directRun) return selectedRun;
    const directCases = new Map();
    (Array.isArray(directRun.cases) ? directRun.cases : []).forEach((caseEntry) => {
      const caseId = String(caseEntry?.caseId || "").trim();
      if (caseId) directCases.set(caseId, caseEntry);
    });
    const merged = Object.assign({}, selectedRun, {
      cases: (Array.isArray(selectedRun.cases) ? selectedRun.cases : []).map((caseEntry) => {
        const caseId = String(caseEntry?.caseId || "").trim();
        const directCase = directCases.get(caseId);
        if (!directCase) return caseEntry;
        const existingVariants = Array.isArray(caseEntry?.variants) ? caseEntry.variants : [];
        const existingIds = new Set(existingVariants.map((variant) => String(variant?.variantId || "").trim()).filter(Boolean));
        const directVariants = (Array.isArray(directCase?.variants) ? directCase.variants : [])
          .filter((variant) => variantType(variant) === "direct")
          .filter((variant) => {
            const variantId = String(variant?.variantId || "").trim();
            return !variantId || !existingIds.has(variantId);
          });
        return Object.assign({}, caseEntry, {
          objective: caseEntry?.objective || directCase?.objective || "",
          constraints: Array.isArray(caseEntry?.constraints) && caseEntry.constraints.length ? caseEntry.constraints : directCase?.constraints,
          variants: existingVariants.concat(directVariants),
        });
      }),
      directCompanionRunId: String(directRun.runId || ""),
      directCompanionSuiteId: String(directRun.suiteId || ""),
    });
    return merged;
  }

  async function hydrateCompanionDirectRun(payload) {
    const selectedRun = payload?.selectedRun && typeof payload.selectedRun === "object" ? payload.selectedRun : null;
    const counts = runVariantCounts(selectedRun);
    if (!selectedRun || !counts.steered || counts.direct) return payload;
    const companionRunId = findCompanionDirectRunId(payload?.runs, selectedRun);
    if (!companionRunId) return payload;
    const query = `?runId=${encodeURIComponent(companionRunId)}`;
    const companionPayload = await fetchJson(API.evalHistory + query);
    const companionRun = companionPayload?.selectedRun && typeof companionPayload.selectedRun === "object"
      ? companionPayload.selectedRun
      : null;
    if (!companionRun) return payload;
    return Object.assign({}, payload, {
      selectedRun: mergeDirectRunIntoSelectedRun(selectedRun, companionRun),
      directCompanionRunId: companionRunId,
    });
  }

  function answerTextFromEntry(entry) {
    if (!entry || typeof entry !== "object") return "";
    if (typeof entry.publicAnswer === "string") return entry.publicAnswer;
    const answer = entry.answer;
    if (typeof answer === "string") return answer;
    if (answer && typeof answer === "object") {
      return String(answer.answer || answer.publicAnswer || answer.output || "").trim();
    }
    return "";
  }

  function buildScoreLane(kind, variant, replicate, overrides = {}) {
    const isPara = kind === "para";
    const provider = overrides.provider || (isPara ? variant?.summarizerProvider : variant?.provider) || variantProvider(variant);
    const model = overrides.model || (isPara ? variant?.summarizerModel : variant?.model) || variantModel(variant);
    const hasOverride = (key) => Object.prototype.hasOwnProperty.call(overrides, key);
    return {
      kind,
      label: overrides.label || (isPara ? "Para output" : "Direct output"),
      source: overrides.source || String(variant?.variantId || "baseline"),
      provider,
      model,
      status: String(overrides.status || replicate?.status || "unknown"),
      answer: String(hasOverride("answer") ? overrides.answer : answerTextFromEntry(replicate)).trim(),
      quality: hasOverride("quality") ? overrides.quality : replicate?.quality || null,
      health: hasOverride("health") ? overrides.health : replicate?.answerHealth || null,
      control: hasOverride("control") ? overrides.control : replicate?.control || null,
      deterministic: hasOverride("deterministic") ? overrides.deterministic : replicate?.deterministic || null,
      usage: hasOverride("usage") ? overrides.usage : replicate?.usage || null,
      updatedAt: overrides.updatedAt || replicate?.updatedAt || "",
    };
  }

  function baselineLaneFromSteered(variant, replicate) {
    const comparison = replicate?.comparison && typeof replicate.comparison === "object" ? replicate.comparison : {};
    const baselineAnswer = String(comparison.baselineAnswer || "").trim();
    const hasBaselineScores = !!(replicate?.baselineQuality || replicate?.baselineAnswerHealth);
    if (!baselineAnswer && !hasBaselineScores) return null;
    return buildScoreLane("direct", variant, replicate, {
      label: "Direct output",
      source: "embedded baseline",
      provider: variant?.directProvider || variantProvider(variant),
      model: variant?.directModel || variantModel(variant),
      answer: baselineAnswer,
      quality: replicate?.baselineQuality || comparison?.baselineQuality || null,
      health: replicate?.baselineAnswerHealth || comparison?.baselineAnswerHealth || null,
      control: null,
    });
  }

  function directMatchScore(directVariant, steeredVariant) {
    const targetProvider = String(steeredVariant?.directProvider || steeredVariant?.provider || steeredVariant?.summarizerProvider || "").trim();
    const targetModel = String(steeredVariant?.directModel || steeredVariant?.model || steeredVariant?.summarizerModel || "").trim();
    const provider = variantProvider(directVariant);
    const model = variantModel(directVariant);
    let score = 0;
    if (targetProvider && provider === targetProvider) score += 50;
    if (targetModel && model === targetModel) score += 45;
    if (targetProvider && String(directVariant?.directProvider || "") === targetProvider) score += 10;
    if (targetModel && String(directVariant?.directModel || "") === targetModel) score += 10;
    if (provider && String(steeredVariant?.summarizerProvider || "") === provider) score += 5;
    return score;
  }

  function directLaneForSteered(caseEntry, steeredVariant, steeredReplicate, fallbackIndex) {
    const baselineLane = baselineLaneFromSteered(steeredVariant, steeredReplicate);
    if (baselineLane) return baselineLane;
    const variants = Array.isArray(caseEntry?.variants) ? caseEntry.variants : [];
    const directVariants = variants.filter((variant) => variantType(variant) === "direct");
    if (!directVariants.length) return null;
    const ranked = directVariants
      .map((variant) => ({ variant, score: directMatchScore(variant, steeredVariant) }))
      .sort((a, b) => b.score - a.score);
    const match = ranked[0]?.variant || directVariants[0];
    const targetReplicate = replicateNumber(steeredReplicate, fallbackIndex);
    const replicate = (Array.isArray(match.replicates) ? match.replicates : []).find((entry, index) => {
      return replicateNumber(entry, index + 1) === targetReplicate;
    }) || (Array.isArray(match.replicates) ? match.replicates[0] : null);
    return replicate ? buildScoreLane("direct", match, replicate) : null;
  }

  function buildScoreSessions(run) {
    const cases = Array.isArray(run?.cases) ? run.cases : [];
    const sessions = [];
    cases.forEach((caseEntry) => {
      const variants = Array.isArray(caseEntry?.variants) ? caseEntry.variants : [];
      const steeredVariants = variants.filter((variant) => variantType(variant) === "steered");
      steeredVariants.forEach((variant) => {
        const replicates = Array.isArray(variant?.replicates) ? variant.replicates : [];
        replicates.forEach((replicate, index) => {
          const repNo = replicateNumber(replicate, index + 1);
          const directLane = directLaneForSteered(caseEntry, variant, replicate, index + 1);
          const paraLane = buildScoreLane("para", variant, replicate);
          const sessionId = [
            String(caseEntry?.caseId || "case"),
            String(variant?.variantId || "para"),
            "r" + repNo,
            directLane?.source || "direct",
          ].join("::");
          sessions.push({
            sessionId,
            label: [
              String(caseEntry?.title || caseEntry?.caseId || "Case"),
              String(variant?.title || variant?.variantId || "Para"),
              "r" + repNo,
            ].filter(Boolean).join(" | "),
            caseId: String(caseEntry?.caseId || ""),
            caseTitle: String(caseEntry?.title || caseEntry?.caseId || "Case"),
            objective: String(caseEntry?.objective || ""),
            constraints: Array.isArray(caseEntry?.constraints) ? caseEntry.constraints.map((item) => String(item || "").trim()).filter(Boolean) : [],
            variantId: String(variant?.variantId || ""),
            replicate: repNo,
            para: paraLane,
            direct: directLane,
            judge: {
              provider: String(run?.judgeProvider || ""),
              model: String(run?.judgeModel || ""),
              status: String(run?.status || ""),
              runId: String(run?.runId || ""),
            },
          });
        });
      });
    });
    return sessions;
  }

  function renderScoreMetricStrip(lane) {
    const quality = scoreValue(lane?.quality, "overallQuality");
    const health = scoreValue(lane?.health, "overallHealth");
    const control = scoreValue(lane?.control, "overallControl");
    const metrics = [
      { label: "Quality", value: quality },
      { label: "Health", value: health },
      { label: "Control", value: control },
    ];
    return `
      <div class="igs-score-metrics">
        ${metrics.map((metric) => `
          <div class="igs-score-metric">
            <span>${escapeHtml(metric.label)}</span>
            <strong>${escapeHtml(formatScore(metric.value))}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function renderJudgeReadout(lane) {
    const rows = [];
    const quality = lane?.quality || {};
    const health = lane?.health || {};
    const control = lane?.control || {};
    [
      ["Quality verdict", quality.verdict || quality.rationale || ""],
      ["Quality weakness", quality.strongestWeakness || ""],
      ["Health verdict", health.verdict || health.rationale || ""],
      ["Control verdict", control.verdict || control.strongestControlWeakness || control.rationale || ""],
    ].forEach(([label, value]) => {
      const text = truncateText(value, 320);
      if (text) {
        rows.push(`
          <div class="igs-score-note">
            <span>${escapeHtml(label)}</span>
            <p>${escapeHtml(text)}</p>
          </div>
        `);
      }
    });
    return rows.length ? `<div class="igs-score-notes">${rows.join("")}</div>` : "";
  }

  function renderScoreLaneCard(lane, tone) {
    if (!lane) {
      return `
        <section class="igs-surface igs-score-card ${escapeHtml(tone || "")}">
          <div class="igs-surface-head"><h4>Direct output</h4></div>
          <div class="igs-inline-note">No comparable direct answer was found for this session.</div>
        </section>
      `;
    }
    const metaBits = [
      providerLabel(lane.provider),
      modelLabel(lane.provider, lane.model),
      lane.source,
      lane.status,
    ].filter(Boolean);
    return `
      <section class="igs-surface igs-score-card ${escapeHtml(tone || "")}">
        <div class="igs-surface-head">
          <div>
            <div class="igs-surface-kicker">${escapeHtml(lane.kind === "para" ? "Para output" : "Direct output")}</div>
            <h4>${escapeHtml(lane.label)}</h4>
          </div>
          <span class="igs-pill ${lane.kind === "para" ? "igs-pill-success" : "igs-pill-warn"}">To judge</span>
        </div>
        <div class="igs-score-meta">${escapeHtml(metaBits.join(" | ") || "No metadata")}</div>
        ${renderScoreMetricStrip(lane)}
        ${renderJudgeReadout(lane)}
        <div class="igs-score-answer">
          <div class="igs-score-answer-label">Answer text sent to judge</div>
          <pre>${escapeHtml(lane.answer || "No answer captured.")}</pre>
        </div>
      </section>
    `;
  }

  function renderScoreQuestionBubble(session) {
    const question = String(session?.objective || "").trim();
    const constraints = Array.isArray(session?.constraints)
      ? session.constraints.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    return `
      <section class="igs-score-question-bubble" aria-label="User question">
        <div class="igs-message-role">User question</div>
        <p>${escapeHtml(question || "No user question recorded for this judged session.")}</p>
        ${constraints.length ? `
          <div class="igs-score-question-constraints">
            ${constraints.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
          </div>
        ` : ""}
      </section>
    `;
  }

  function renderScoreJudgePanel(session) {
    const paraQuality = scoreValue(session?.para?.quality, "overallQuality");
    const directQuality = scoreValue(session?.direct?.quality, "overallQuality");
    const paraHealth = scoreValue(session?.para?.health, "overallHealth");
    const directHealth = scoreValue(session?.direct?.health, "overallHealth");
    const deltaQuality = paraQuality != null && directQuality != null ? paraQuality - directQuality : null;
    const deltaHealth = paraHealth != null && directHealth != null ? paraHealth - directHealth : null;
    const packet = {
      runId: session?.judge?.runId || "",
      caseId: session?.caseId || "",
      variantId: session?.variantId || "",
      replicate: session?.replicate || 1,
      judge: session?.judge || {},
      scores: {
        summarizer: {
          quality: paraQuality,
          health: paraHealth,
          control: scoreValue(session?.para?.control, "overallControl"),
        },
        direct: {
          quality: directQuality,
          health: directHealth,
        },
        delta: {
          quality: deltaQuality,
          health: deltaHealth,
        },
      },
    };
    const metaBits = [
      providerLabel(session?.judge?.provider || ""),
      modelLabel(session?.judge?.provider || "", session?.judge?.model || ""),
      session?.judge?.status ? ("run " + session.judge.status) : "",
    ].filter(Boolean);
    const judgeNotes = [
      ["Para quality", session?.para?.quality?.verdict || session?.para?.quality?.rationale || ""],
      ["Direct quality", session?.direct?.quality?.verdict || session?.direct?.quality?.rationale || ""],
      ["Para control", session?.para?.control?.verdict || session?.para?.control?.rationale || ""],
      ["Para memory", session?.para?.quality?.memoryCompliance || session?.para?.health?.memoryCompliance || session?.para?.control?.memoryCompliance || ""],
      ["Direct memory", session?.direct?.quality?.memoryCompliance || session?.direct?.health?.memoryCompliance || ""],
    ].map(([label, value]) => {
      const text = truncateText(value, 320);
      return text ? `
        <div class="igs-score-note">
          <span>${escapeHtml(label)}</span>
          <p>${escapeHtml(text)}</p>
        </div>
      ` : "";
    }).filter(Boolean).join("");
    return `
      <section class="igs-surface igs-score-card accent igs-score-judge">
        <div class="igs-surface-head">
          <div>
            <div class="igs-surface-kicker">Judge comparison</div>
            <h4>Judge</h4>
          </div>
          <span class="igs-pill igs-pill-muted">${escapeHtml(metaBits.join(" | ") || "Judge")}</span>
        </div>
        <div class="igs-score-delta-grid">
          <div class="igs-score-delta">
            <span>Quality delta</span>
            <strong>${escapeHtml(deltaQuality == null ? "n/a" : (deltaQuality >= 0 ? "+" : "") + deltaQuality.toFixed(1))}</strong>
          </div>
          <div class="igs-score-delta">
            <span>Health delta</span>
            <strong>${escapeHtml(deltaHealth == null ? "n/a" : (deltaHealth >= 0 ? "+" : "") + deltaHealth.toFixed(1))}</strong>
          </div>
          <div class="igs-score-delta">
            <span>Session</span>
            <strong>${escapeHtml("r" + String(session?.replicate || 1))}</strong>
          </div>
        </div>
        ${judgeNotes ? `<div class="igs-score-notes">${judgeNotes}</div>` : ""}
        <details class="igs-score-packet">
          <summary>AI score packet</summary>
          <pre>${escapeHtml(JSON.stringify(packet, null, 2))}</pre>
        </details>
      </section>
    `;
  }

  function renderScoreSession(session) {
    if (!session) {
      return `<div class="igs-inline-note">No comparable judged sessions found in this run.</div>`;
    }
    return `
      <section class="igs-score-session-head">
        <div>
          <div class="igs-kicker">${escapeHtml(session.caseId || "case")}</div>
          <h4>${escapeHtml(session.caseTitle || "Judged session")}</h4>
        </div>
      </section>
      <div class="igs-score-lane-grid">
        ${renderScoreQuestionBubble(session)}
        ${renderScoreLaneCard(session.para, "primary")}
        ${renderScoreLaneCard(session.direct, "secondary")}
        ${renderScoreJudgePanel(session)}
      </div>
    `;
  }

  function handoffLabel(entry) {
    const bits = [
      String(entry?.packetId || entry?.name || "handoff"),
      String(entry?.loopStatus || "").trim(),
      String(entry?.taskId || "").trim(),
      entry?.modifiedAt ? formatTimestamp(entry.modifiedAt) : "",
    ].filter(Boolean);
    return bits.join(" | ");
  }

  function renderHandoffMeta(payload) {
    const content = payload?.content && typeof payload.content === "object" ? payload.content : payload;
    const task = content?.activeTask && typeof content.activeTask === "object" ? content.activeTask : {};
    const loop = content?.loop && typeof content.loop === "object" ? content.loop : {};
    const integrity = content?.integrity && typeof content.integrity === "object" ? content.integrity : {};
    const rows = [
      ["Packet", content?.packetId || payload?.name || ""],
      ["Created", content?.createdAt || payload?.modifiedAt || ""],
      ["Reason", content?.reason || ""],
      ["Task", task.taskId || ""],
      ["Loop", loop.status || ""],
      ["Current round", [loop.completedRounds, loop.totalRounds].filter((value) => value !== undefined && value !== null).join(" / ")],
      ["Failed calls", String(Array.isArray(content?.failedCalls) ? content.failedCalls.length : 0)],
      ["Blockers", String(Array.isArray(content?.knownBlockers) ? content.knownBlockers.length : 0)],
      ["Evidence digest", integrity.evidenceDigest || ""],
      ["Packet hash", content?.packetHash || ""],
    ].filter((row) => String(row[1] || "").trim());
    const objective = String(task.objective || "").trim();
    const objectiveRow = objective
      ? `<div class="igs-fail-meta-row igs-fail-meta-row-wide"><span>Objective</span><strong>${escapeHtml(truncateText(objective, 420))}</strong></div>`
      : "";
    const rowsHtml = rows.map(([label, value]) => `
      <div class="igs-fail-meta-row">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `).join("");
    return rowsHtml + objectiveRow || "No handoff metadata captured.";
  }

  function setHandoffDetail(payload) {
    if (elements.handoffMeta) {
      elements.handoffMeta.innerHTML = renderHandoffMeta(payload);
    }
    if (elements.handoffPacket) {
      const content = payload?.content && typeof payload.content === "object" ? payload.content : payload;
      elements.handoffPacket.textContent = prettyJson(content || {});
    }
  }

  function clearHandoffDetail(message) {
    const text = message || "No handoff selected.";
    if (elements.handoffMeta) elements.handoffMeta.textContent = text;
    if (elements.handoffPacket) elements.handoffPacket.textContent = "{}";
  }

  async function loadHandoffDetail(name) {
    const selectedName = String(name || "").trim();
    if (!selectedName) {
      clearHandoffDetail("No handoff selected.");
      return;
    }
    if (elements.handoffStatus) {
      elements.handoffStatus.textContent = "Loading " + selectedName + "...";
    }
    const payload = await fetchJson(API.artifact + "?name=" + encodeURIComponent(selectedName));
    setHandoffDetail(payload);
    if (elements.handoffStatus) {
      const packetId = payload?.content?.packetId || payload?.summary?.packetId || selectedName;
      elements.handoffStatus.textContent = "Viewing handoff packet " + packetId + ".";
    }
  }

  function syncHandoffSelector(handoffs) {
    if (!elements.handoffSelect) return;
    handoffState.handoffs = Array.isArray(handoffs) ? handoffs : [];
    if (!handoffState.handoffs.length) {
      elements.handoffSelect.innerHTML = `<option value="">No handoffs captured</option>`;
      handoffState.selectedName = "";
      clearHandoffDetail("No durable handoff packet has been captured yet.");
      if (elements.handoffStatus) {
        elements.handoffStatus.textContent = "No handoff packets captured.";
      }
      return;
    }
    if (!handoffState.selectedName || !handoffState.handoffs.some((entry) => String(entry.name || "") === handoffState.selectedName)) {
      handoffState.selectedName = String(handoffState.handoffs[0]?.name || "");
    }
    elements.handoffSelect.innerHTML = handoffState.handoffs.map((entry) => {
      const name = String(entry.name || "");
      return `<option value="${escapeHtml(name)}">${escapeHtml(handoffLabel(entry))}</option>`;
    }).join("");
    elements.handoffSelect.value = handoffState.selectedName;
    loadHandoffDetail(handoffState.selectedName).catch(function (error) {
      if (elements.handoffStatus) {
        elements.handoffStatus.textContent = "Handoff load failed: " + String(error.message || error);
      }
    });
  }

  async function loadHandoffs() {
    if (!elements.handoffSelect) return;
    if (elements.handoffStatus) {
      elements.handoffStatus.textContent = "Loading handoff ledger...";
    }
    const payload = await fetchJson(API.history);
    handoffState.loaded = true;
    syncHandoffSelector(Array.isArray(payload?.handoffs) ? payload.handoffs : []);
  }

  async function createHandoffPacket() {
    if (elements.handoffStatus) {
      elements.handoffStatus.textContent = "Creating durable handoff packet...";
    }
    const payload = await fetchJson(API.handoffs, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        actor: "operator",
        reason: "manual-review-handoff",
        nextAction: "Resume from this packet, inspect linked artifacts, then continue the active job or eval.",
      }),
    });
    handoffState.selectedName = String(payload?.artifact?.name || "");
    handoffState.loaded = false;
    await loadHandoffs();
  }

  function nodeTransferLabel(entry) {
    const bits = [
      String(entry?.storage || "") === "eval" ? "eval " + String(entry?.runId || "").trim() : "live",
      String(entry?.status || "transfer"),
      String(entry?.validationStatus || ""),
      String(entry?.sourceNode || ""),
      Array.isArray(entry?.targetNodes) ? "to " + entry.targetNodes.join(",") : "",
      entry?.crc32 ? "crc " + entry.crc32 : "",
      entry?.modifiedAt ? formatTimestamp(entry.modifiedAt) : "",
    ].filter(Boolean);
    return bits.join(" | ");
  }

  function nodeTransferKey(entry) {
    if (String(entry?.storage || "") === "eval") {
      return ["eval", entry?.runId || "", entry?.artifactId || ""].map((part) => encodeURIComponent(String(part))).join("|");
    }
    return ["live", entry?.name || ""].map((part) => encodeURIComponent(String(part))).join("|");
  }

  function nodeTransferEntryForKey(key) {
    const selected = String(key || "");
    return nodeTransferState.transfers.find((entry) => nodeTransferKey(entry) === selected)
      || nodeTransferState.transfers.find((entry) => String(entry?.name || "") === selected)
      || null;
  }

  function renderNodeTransferMeta(payload) {
    const content = payload?.content && typeof payload.content === "object" ? payload.content : payload;
    const integrity = content?.integrity && typeof content.integrity === "object" ? content.integrity : {};
    const check = content?.integrityCheck && typeof content.integrityCheck === "object" ? content.integrityCheck : {};
    const artifacts = content?.artifacts && typeof content.artifacts === "object" ? content.artifacts : {};
    const rows = [
      ["Transfer", content?.transferId || payload?.name || ""],
      ["Status", content?.status || ""],
      ["Validation", content?.validationStatus || ""],
      ["Passed", content?.passedToNextNode === true ? "yes" : "no"],
      ["Integrity", check.ok === true ? "ok" : "failed"],
      ["Source", content?.sourceNode || ""],
      ["Targets", Array.isArray(content?.targetNodes) ? content.targetNodes.join(", ") : ""],
      ["CRC32", integrity.crc32 || ""],
      ["SHA-256", integrity.sha256 || ""],
      ["Bytes", String(integrity.canonicalJsonBytes || "")],
      ["Checkpoint", artifacts.checkpoint || ""],
      ["Output", artifacts.output || ""],
      ["Failed call", artifacts.failedCall || ""],
      ["Oversight", content?.oversightAction || ""],
      ["Error", content?.error || ""],
    ].filter((row) => String(row[1] || "").trim());
    return rows.map(([label, value]) => `
      <div class="igs-fail-meta-row">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `).join("") || "No transfer metadata captured.";
  }

  function setNodeTransferDetail(payload) {
    if (elements.nodeTransferMeta) {
      elements.nodeTransferMeta.innerHTML = renderNodeTransferMeta(payload);
    }
    if (elements.nodeTransferPacket) {
      const content = payload?.content && typeof payload.content === "object" ? payload.content : payload;
      elements.nodeTransferPacket.textContent = prettyJson(content || {});
    }
  }

  function clearNodeTransferDetail(message) {
    const text = message || "No transfer selected.";
    if (elements.nodeTransferMeta) elements.nodeTransferMeta.textContent = text;
    if (elements.nodeTransferPacket) elements.nodeTransferPacket.textContent = "{}";
  }

  async function loadNodeTransferDetail(key) {
    const selectedKey = String(key || "").trim();
    if (!selectedKey) {
      clearNodeTransferDetail("No transfer selected.");
      return;
    }
    const entry = nodeTransferEntryForKey(selectedKey);
    if (elements.nodeTransferStatus) {
      elements.nodeTransferStatus.textContent = "Loading transfer " + (entry?.name || selectedKey) + "...";
    }
    const payload = String(entry?.storage || "") === "eval"
      ? await fetchJson(API.evalArtifact + "?runId=" + encodeURIComponent(entry.runId || "") + "&artifactId=" + encodeURIComponent(entry.artifactId || ""))
      : await fetchJson(API.artifact + "?name=" + encodeURIComponent(entry?.name || selectedKey));
    setNodeTransferDetail(payload);
    if (elements.nodeTransferStatus) {
      const status = payload?.content?.status || "transfer";
      const ok = payload?.content?.integrityCheck?.ok === true ? "checksum ok" : "checksum failed";
      elements.nodeTransferStatus.textContent = "Viewing " + status + " node transfer, " + ok + ".";
    }
  }

  function syncNodeTransferSelector(transfers) {
    if (!elements.nodeTransferSelect) return;
    nodeTransferState.transfers = Array.isArray(transfers) ? transfers : [];
    if (!nodeTransferState.transfers.length) {
      elements.nodeTransferSelect.innerHTML = `<option value="">No transfers captured</option>`;
      nodeTransferState.selectedName = "";
      clearNodeTransferDetail("No node transfers have been captured yet.");
      if (elements.nodeTransferStatus) {
        elements.nodeTransferStatus.textContent = "No node transfers captured.";
      }
      return;
    }
    if (!nodeTransferState.selectedName || !nodeTransferState.transfers.some((entry) => nodeTransferKey(entry) === nodeTransferState.selectedName)) {
      nodeTransferState.selectedName = nodeTransferKey(nodeTransferState.transfers[0]);
    }
    elements.nodeTransferSelect.innerHTML = nodeTransferState.transfers.map((entry) => {
      const key = nodeTransferKey(entry);
      return `<option value="${escapeHtml(key)}">${escapeHtml(nodeTransferLabel(entry))}</option>`;
    }).join("");
    elements.nodeTransferSelect.value = nodeTransferState.selectedName;
    loadNodeTransferDetail(nodeTransferState.selectedName).catch(function (error) {
      if (elements.nodeTransferStatus) {
        elements.nodeTransferStatus.textContent = "Transfer load failed: " + String(error.message || error);
      }
    });
  }

  async function loadNodeTransfers() {
    if (!elements.nodeTransferSelect) return;
    if (elements.nodeTransferStatus) {
      elements.nodeTransferStatus.textContent = "Loading node transfer ledger...";
    }
    const payload = await fetchJson(API.history);
    nodeTransferState.loaded = true;
    syncNodeTransferSelector(Array.isArray(payload?.nodeTransfers) ? payload.nodeTransfers : []);
  }

  function failedCallLabel(entry) {
    const bits = [
      String(entry?.storage || "") === "eval" ? "eval " + String(entry?.runId || "").trim() : "live",
      String(entry?.failureKind || "failed"),
      providerLabel(entry?.provider || ""),
      modelLabel(entry?.provider || "", entry?.model || ""),
      String(entry?.worker || entry?.target || "").trim(),
      entry?.modifiedAt ? formatTimestamp(entry.modifiedAt) : "",
    ].filter(Boolean);
    return bits.join(" | ") || String(entry?.name || "failed call");
  }

  function failedCallKey(entry) {
    if (String(entry?.storage || "") === "eval") {
      return ["eval", entry?.runId || "", entry?.artifactId || ""].map((part) => encodeURIComponent(String(part))).join("|");
    }
    return ["live", entry?.name || ""].map((part) => encodeURIComponent(String(part))).join("|");
  }

  function failedCallEntryForKey(key) {
    const selected = String(key || "");
    return failedCallState.failures.find((entry) => failedCallKey(entry) === selected)
      || failedCallState.failures.find((entry) => String(entry?.name || "") === selected)
      || null;
  }

  function renderFailedCallMeta(payload) {
    const summary = payload?.summary || {};
    const content = payload?.content || {};
    const rows = [
      ["Artifact", payload?.name || ""],
      ["Storage", payload?.storage || ""],
      ["Run", payload?.content?.runId || payload?.summary?.runId || payload?.runId || ""],
      ["Artifact ID", payload?.artifactId || ""],
      ["Kind", summary.failureKind || content.failureKind || ""],
      ["Pass status", summary.passStatus || content.passStatus || ""],
      ["Passed to next", (summary.passedToNextNode ?? content.passedToNextNode) === true ? "yes" : "no"],
      ["Handoff note", summary.handoffNote || content.handoffNote || ""],
      ["Target", summary.target || content.target || ""],
      ["Provider", providerLabel(summary.provider || content.provider || "")],
      ["Model", modelLabel(summary.provider || content.provider || "", summary.model || content.model || "") || summary.model || content.model || ""],
      ["Schema", content.schemaName || ""],
      ["Response", summary.responseId || content.responseId || ""],
      ["Captured", content.capturedAt || payload?.modifiedAt || ""],
      ["Raw bytes", String((content.rawOutputText || "").length)],
      ["Error", summary.error || content.error || ""],
    ].filter((row) => String(row[1] || "").trim());
    const successor = summary.acceptedSuccessor || content.acceptedSuccessor || null;
    if (successor && typeof successor === "object") {
      rows.splice(3, 0, ["Accepted successor", [successor.kind, successor.name || successor.artifactId].filter(Boolean).join(" | ")]);
    }
    return rows.map(([label, value]) => `
      <div class="igs-fail-meta-row">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `).join("") || "No failure metadata captured.";
  }

  function renderFailedCallIngestion(payload) {
    const content = payload?.content || {};
    const ingestion = content.ingestion && typeof content.ingestion === "object" ? content.ingestion : {};
    const packet = {
      failureKind: content.failureKind || payload?.summary?.failureKind || "",
      parseError: ingestion.parseError || content.error || "",
      rawLength: ingestion.rawLength ?? (content.rawOutputText || "").length,
      candidateKind: ingestion.candidateKind || "",
      candidateParseError: ingestion.candidateParseError || "",
      candidateParsedType: ingestion.candidateParsedType || "",
      candidateKeys: ingestion.candidateKeys || [],
      candidateJsonText: ingestion.candidateJsonText || "",
    };
    return prettyJson(packet);
  }

  function renderFailedCallPacket(payload) {
    const content = payload?.content || {};
    return prettyJson({
      artifact: {
        name: payload?.name || "",
        storage: payload?.storage || "",
        modifiedAt: payload?.modifiedAt || "",
        size: payload?.size || 0,
      },
      summary: payload?.summary || {},
      passStatus: content.passStatus || payload?.summary?.passStatus || "",
      passedToNextNode: content.passedToNextNode ?? payload?.summary?.passedToNextNode ?? false,
      acceptedSuccessor: payload?.summary?.acceptedSuccessor || content.acceptedSuccessor || null,
      nodeTransferArtifact: content.nodeTransferArtifact || payload?.summary?.nodeTransferArtifact || null,
      ingestion: content.ingestion || {},
      responseMeta: content.responseMeta || {},
      rawProviderResponse: content.rawProviderResponse || null,
    });
  }

  function setFailedCallDetail(payload) {
    if (elements.failedCallMeta) {
      elements.failedCallMeta.innerHTML = renderFailedCallMeta(payload);
    }
    if (elements.failedCallIngestion) {
      elements.failedCallIngestion.textContent = renderFailedCallIngestion(payload);
    }
    if (elements.failedCallRaw) {
      elements.failedCallRaw.textContent = String(payload?.content?.rawOutputText || "No raw provider text was captured for this failure.");
    }
    if (elements.failedCallPacket) {
      elements.failedCallPacket.textContent = renderFailedCallPacket(payload);
    }
  }

  function clearFailedCallDetail(message) {
    const text = message || "No failed call selected.";
    if (elements.failedCallMeta) elements.failedCallMeta.textContent = text;
    if (elements.failedCallIngestion) elements.failedCallIngestion.textContent = text;
    if (elements.failedCallRaw) elements.failedCallRaw.textContent = text;
    if (elements.failedCallPacket) elements.failedCallPacket.textContent = "{}";
  }

  async function loadFailedCallDetail(key) {
    const selectedKey = String(key || "").trim();
    if (!selectedKey) {
      clearFailedCallDetail("No failed call selected.");
      return;
    }
    const entry = failedCallEntryForKey(selectedKey);
    if (elements.failedCallStatus) {
      elements.failedCallStatus.textContent = "Loading " + (entry?.name || selectedKey) + "...";
    }
    const payload = String(entry?.storage || "") === "eval"
      ? await fetchJson(API.evalArtifact + "?runId=" + encodeURIComponent(entry.runId || "") + "&artifactId=" + encodeURIComponent(entry.artifactId || ""))
      : await fetchJson(API.artifact + "?name=" + encodeURIComponent(entry?.name || selectedKey));
    setFailedCallDetail(payload);
    if (elements.failedCallStatus) {
      const kind = payload?.summary?.failureKind || payload?.content?.failureKind || "failed";
      const source = String(entry?.storage || payload?.storage || "") === "eval" ? "eval run " + String(entry?.runId || "") : "live ledger";
      elements.failedCallStatus.textContent = "Viewing " + kind + " artifact from " + source + ".";
    }
  }

  function syncFailedCallSelector(failures) {
    if (!elements.failedCallSelect) return;
    failedCallState.failures = Array.isArray(failures) ? failures : [];
    if (!failedCallState.failures.length) {
      elements.failedCallSelect.innerHTML = `<option value="">No failed calls captured</option>`;
      failedCallState.selectedName = "";
      clearFailedCallDetail("No failed provider calls have been captured yet.");
      if (elements.failedCallStatus) {
        elements.failedCallStatus.textContent = "No failed calls captured.";
      }
      return;
    }
    if (!failedCallState.selectedName || !failedCallState.failures.some((entry) => failedCallKey(entry) === failedCallState.selectedName)) {
      failedCallState.selectedName = failedCallKey(failedCallState.failures[0]);
    }
    elements.failedCallSelect.innerHTML = failedCallState.failures.map((entry) => {
      const key = failedCallKey(entry);
      return `<option value="${escapeHtml(key)}">${escapeHtml(failedCallLabel(entry))}</option>`;
    }).join("");
    elements.failedCallSelect.value = failedCallState.selectedName;
    loadFailedCallDetail(failedCallState.selectedName).catch(function (error) {
      if (elements.failedCallStatus) {
        elements.failedCallStatus.textContent = "Failed call load failed: " + String(error.message || error);
      }
    });
  }

  async function loadFailedCalls() {
    if (!elements.failedCallSelect) return;
    if (elements.failedCallStatus) {
      elements.failedCallStatus.textContent = "Loading failed call ledger...";
    }
    const payload = await fetchJson(API.history);
    const failures = Array.isArray(payload?.failedCalls)
      ? payload.failedCalls
      : (Array.isArray(payload?.artifacts) ? payload.artifacts.filter((entry) => entry?.kind === "failed_call") : []);
    failedCallState.loaded = true;
    syncFailedCallSelector(failures);
  }

  function renderScoreRunMeta(run, sessions) {
    if (!run) return "No judged runs available.";
    const summary = run.summary || {};
    const learning = run.judgeLearning && typeof run.judgeLearning === "object" ? run.judgeLearning : null;
    const learningResult = learning && learning.lastResult && typeof learning.lastResult === "object" ? learning.lastResult : null;
    const learningLabel = learning
      ? (
        learning.enabled
          ? `learning ${learning.status || "on"}${learningResult ? `, ${Number(learningResult.learnedRecordCount || 0)} memories` : ""}`
          : "learning off"
      )
      : "";
    const bits = [
      String(run.suiteId || "").trim(),
      String(run.status || "").trim(),
      run.judgeProvider ? providerLabel(run.judgeProvider) : "",
      run.judgeModel ? modelLabel(run.judgeProvider || "", run.judgeModel) : "",
      Number(summary.variantCount || 0) ? `${Number(summary.variantCount || 0)} variants` : "",
      Number(summary.errorCount || 0) ? `${Number(summary.errorCount || 0)} errors` : "0 errors",
      Number(summary.totalTokens || 0) ? `${Number(summary.totalTokens || 0).toLocaleString()} tokens` : "",
      sessions.length ? `${sessions.length} comparable sessions` : "",
      run.directCompanionSuiteId ? `direct baseline ${run.directCompanionSuiteId}` : "",
      learningLabel,
    ].filter(Boolean);
    return bits.join(" | ");
  }

  function scoreRunComparableHint(run) {
    const suite = String(run?.suiteId || run?.suite || run?.title || "").toLowerCase();
    const variants = Number(run?.summary?.variantCount || 0);
    let score = variants;
    if (suite.includes("memory") || suite.includes("para") || suite.includes("steered")) score += 100;
    if (suite.includes("direct")) score -= 20;
    return score;
  }

  function fallbackScoreRunId(runs, currentRunId) {
    const current = String(currentRunId || "").trim();
    return runs
      .filter((run) => {
        const runId = String(run?.runId || "").trim();
        return runId && runId !== current && !scoreState.emptyRunSkips.has(runId);
      })
      .sort((a, b) => scoreRunComparableHint(b) - scoreRunComparableHint(a))
      .map((run) => String(run.runId || "").trim())
      .find(Boolean) || "";
  }

  function syncScoreSelectors(payload) {
    if (!elements.scoreRunSelect || !elements.scoreSessionSelect || !elements.scoreCompareDetail) return;
    const runs = Array.isArray(payload?.runs) ? payload.runs : [];
    const selectedRun = payload?.selectedRun && typeof payload.selectedRun === "object" ? payload.selectedRun : null;
    if (!scoreState.selectedRunId && payload?.selectedRunId) {
      scoreState.selectedRunId = String(payload.selectedRunId || "");
    }
    const runOptions = runs.map((run) => {
      const label = [
        String(run.suiteId || run.runId || "Run"),
        String(run.status || ""),
        run.judgeProvider ? providerLabel(run.judgeProvider) : "",
        run.updatedAt ? formatTimestamp(run.updatedAt) : "",
      ].filter(Boolean).join(" | ");
      return `<option value="${escapeHtml(String(run.runId || ""))}">${escapeHtml(label)}</option>`;
    }).join("");
    elements.scoreRunSelect.innerHTML = runOptions || `<option value="">No eval runs</option>`;
    if (scoreState.selectedRunId) {
      elements.scoreRunSelect.value = scoreState.selectedRunId;
    }
    if (!selectedRun && runs.length) {
      scoreState.selectedRunId = String(runs[0]?.runId || "");
      persistScoreSelection();
      loadScoreRuns(scoreState.selectedRunId);
      return;
    }
    const sessions = buildScoreSessions(selectedRun);
    if (!sessions.length && selectedRun && runs.length && scoreState.autoComparableFallback) {
      const currentRunId = String(selectedRun.runId || scoreState.selectedRunId || "").trim();
      if (currentRunId) {
        scoreState.emptyRunSkips.add(currentRunId);
      }
      const fallbackRun = fallbackScoreRunId(runs, currentRunId);
      if (fallbackRun) {
        scoreState.selectedRunId = fallbackRun;
        scoreState.selectedSessionId = "";
        persistScoreSelection();
        loadScoreRuns(fallbackRun);
        return;
      }
      scoreState.autoComparableFallback = false;
    }
    if (sessions.length) {
      scoreState.emptyRunSkips.clear();
      scoreState.autoComparableFallback = false;
    }
    scoreState.sessions = sessions;
    if (!scoreState.selectedSessionId || !sessions.some((session) => session.sessionId === scoreState.selectedSessionId)) {
      scoreState.selectedSessionId = sessions[0]?.sessionId || "";
      persistScoreSelection();
    }
    elements.scoreSessionSelect.innerHTML = sessions.map((session) => {
      return `<option value="${escapeHtml(session.sessionId)}">${escapeHtml(session.label)}</option>`;
    }).join("") || `<option value="">No comparable sessions</option>`;
    if (scoreState.selectedSessionId) {
      elements.scoreSessionSelect.value = scoreState.selectedSessionId;
    }
    elements.scoreRunMeta.textContent = renderScoreRunMeta(selectedRun, sessions);
    renderCurrentScoreSession();
    installMainWorkbenchPanes();
  }

  function renderCurrentScoreSession() {
    if (!elements.scoreStatus || !elements.scoreCompareDetail) return;
    const selectedSession = scoreState.sessions.find((session) => session.sessionId === scoreState.selectedSessionId) || scoreState.sessions[0] || null;
    elements.scoreStatus.textContent = selectedSession
      ? `Viewing ${selectedSession.caseId || "case"} / ${selectedSession.variantId || "variant"} / replicate ${selectedSession.replicate}.`
      : "No Direct vs Para judged pair was found in this run.";
    elements.scoreCompareDetail.innerHTML = renderScoreSession(selectedSession);
    installMainWorkbenchPanes();
  }

  function persistScoreSelection() {
    try {
      window.localStorage.setItem("igsShell.scoreRunId", scoreState.selectedRunId || "");
      window.localStorage.setItem("igsShell.scoreSessionId", scoreState.selectedSessionId || "");
    } catch (_) {}
  }

  async function loadScoreRuns(runId) {
    if (!elements.scoreRunSelect) return;
    const requestedRunId = String(runId || scoreState.selectedRunId || "").trim();
    if (elements.scoreStatus) {
      elements.scoreStatus.textContent = "Loading judged sessions...";
    }
    const query = requestedRunId ? `?runId=${encodeURIComponent(requestedRunId)}` : "";
    let payload = await fetchJson(API.evalHistory + query);
    payload = await hydrateCompanionDirectRun(payload || {});
    scoreState.payload = payload || {};
    scoreState.loaded = true;
    scoreState.selectedRunId = String(payload?.selectedRunId || requestedRunId || "");
    persistScoreSelection();
    syncScoreSelectors(payload || {});
  }

  function setActiveView(target) {
    const nextTarget = String(target || "home").trim() || "home";
    navButtons.forEach((item) => {
      const active = item.getAttribute("data-view-target") === nextTarget;
      item.classList.toggle("is-active", active);
      if (active) {
        item.setAttribute("aria-current", "page");
      } else {
        item.removeAttribute("aria-current");
      }
    });
    viewPanels.forEach((panel) => {
      const active = panel.getAttribute("data-view-panel") === nextTarget;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
    if (nextTarget === "repo") {
      window.setTimeout(refreshActiveInspector, 40);
    }
    if (nextTarget === "review" && !failedCallState.loaded) {
      loadFailedCalls().catch(function (error) {
        if (elements.failedCallStatus) {
          elements.failedCallStatus.textContent = "Failed call ledger failed to load: " + String(error.message || error);
        }
      });
    }
    if (nextTarget === "review" && !handoffState.loaded) {
      loadHandoffs().catch(function (error) {
        if (elements.handoffStatus) {
          elements.handoffStatus.textContent = "Handoff ledger failed to load: " + String(error.message || error);
        }
      });
    }
    if (nextTarget === "review" && !nodeTransferState.loaded) {
      loadNodeTransfers().catch(function (error) {
        if (elements.nodeTransferStatus) {
          elements.nodeTransferStatus.textContent = "Node transfer ledger failed to load: " + String(error.message || error);
        }
      });
    }
    if (nextTarget === "scores" && !scoreState.loaded) {
      loadScoreRuns(scoreState.selectedRunId).catch(function (error) {
        if (elements.scoreStatus) {
          elements.scoreStatus.textContent = "Eval sessions failed to load: " + String(error.message || error);
        }
      });
    }
    if (nextTarget === "sessions" && !sessionBrowserState.loaded) {
      loadSessionBrowser().catch(function (error) {
        if (elements.sessionStatus) {
          elements.sessionStatus.textContent = "Session browser failed to load: " + String(error.message || error);
        }
      });
    }
    if (nextTarget === "debug") {
      refreshDebugSurface().catch(function (error) {
        if (elements.debugOperationStatus) {
          elements.debugOperationStatus.textContent = "Debug refresh failed: " + String(error.message || error);
        }
      });
    }
  }

  navButtons.forEach((button) => {
    button.addEventListener("click", function () {
      setActiveView(button.getAttribute("data-view-target"));
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
        window.localStorage.setItem("igsShell.sidebarCollapsed", shellState.sidebarCollapsed ? "1" : "0");
      } catch (_) {}
      window.setTimeout(refreshActiveInspector, 60);
    });
  }

  homeCollapseButtons.forEach((button) => {
    button.addEventListener("click", function () {
      const panelId = button.getAttribute("data-home-collapse-toggle");
      setHomePanelCollapsed(panelId, true);
    });
  });

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
          setSummarizerProviderValue(value);
        }
        if (previousSummarizerProvider === runtimeState.draft?.provider || previousSummarizerProvider === value) {
          setSummarizerProviderValue(value);
          populateSelect(elements.summarizerModel, modelOptions(value), previousSummarizerModel || elements.workerModel.value, runtimeState.draft?.summarizerModelSource);
          if (previousSummarizerModel === runtimeState.draft?.model || !previousSummarizerModel) {
            elements.summarizerModel.value = elements.workerModel.value;
          }
        }
      }
      updateNarrative();
      queueDraftSave();
    });
  });

  summarizerProviderButtons.forEach((button) => {
    button.addEventListener("click", function () {
      const value = button.getAttribute("data-summarizer-provider-option");
      setSummarizerProviderValue(value, { dispatch: true });
    });
  });

  providerRoleButtons.forEach((button) => {
    button.addEventListener("click", function () {
      setProviderPaneRole(button.getAttribute("data-provider-role-option"));
    });
  });

  sharedProviderButtons.forEach((button) => {
    button.addEventListener("click", function () {
      const value = String(button.getAttribute("data-provider-option") || "").trim();
      if (!value) return;
      if (activeProviderPaneRole() === "summarizer") {
        setSummarizerProviderValue(value, { dispatch: true });
        return;
      }
      setWorkerProviderValue(value);
      updateNarrative();
      queueDraftSave();
    });
  });

  selectToggleButtons.forEach((button) => {
    button.addEventListener("click", function () {
      setSelectFromToggleButton(button);
    });
  });

  selectCycleButtons.forEach((button) => {
    button.addEventListener("click", function () {
      setSelectFromCycleButton(button);
    });
  });

  [
    elements.runtimeMode,
    elements.engineVersion,
    elements.workerModel,
    elements.summarizerProvider,
    elements.summarizerModel,
    elements.contextMode,
    elements.reasoningEffort,
    elements.directBaselineMode,
    elements.vettingEnabled,
    elements.researchMode,
    elements.memoryMode,
    elements.objective,
    elements.sessionContext,
    elements.constraints,
    elements.loopRounds,
    elements.maxCostUsd,
  ].forEach((element) => {
    if (!element) return;
    element.addEventListener("input", function () {
      if (element === elements.objective) {
        resizeObjectiveTextarea();
      }
      if (element === elements.summarizerProvider) {
        syncSummarizerProviderButtons(elements.summarizerProvider.value);
        populateSelect(
          elements.summarizerModel,
          modelOptions(elements.summarizerProvider.value),
          elements.summarizerModel.value || runtimeState.draft?.summarizerModel || "",
          runtimeState.draft?.summarizerModelSource
        );
      }
      if (element.matches?.("[data-contract-pill-select]")) {
        syncContractPillSelect(element);
      }
      if (element.id) {
        syncSelectToggleButtons(element.id);
        syncSelectCycleButtons(element.id);
      }
      updateNarrative();
      queueDraftSave();
    });
    element.addEventListener("change", function () {
      if (element === elements.summarizerProvider) {
        syncSummarizerProviderButtons(elements.summarizerProvider.value);
        populateSelect(
          elements.summarizerModel,
          modelOptions(elements.summarizerProvider.value),
          elements.summarizerModel.value || runtimeState.draft?.summarizerModel || "",
          runtimeState.draft?.summarizerModelSource
        );
      }
      if (element.matches?.("[data-contract-pill-select]")) {
        syncContractPillSelect(element);
      }
      if (element.id) {
        syncSelectToggleButtons(element.id);
        syncSelectCycleButtons(element.id);
      }
      updateNarrative();
      if (element === elements.objective) {
        resizeObjectiveTextarea();
      }
      queueDraftSave();
    });
  });

  if (elements.objective) {
    elements.objective.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) {
        return;
      }
      event.preventDefault();
      submitComposerAction();
    });
  }

  if (elements.composerToolMenuToggle) {
    elements.composerToolMenuToggle.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      setComposerMenuOpen(!shellState.composerToolMenuOpen);
    });
  }

  composerToolActions.forEach((button) => {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      toggleComposerTool(button.getAttribute("data-composer-tool-action"));
    });
  });

  composerReasoningOptions.forEach((button) => {
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      setComposerReasoning(button.getAttribute("data-composer-reasoning-option"));
    });
  });

  if (elements.composerFileInput) {
    elements.composerFileInput.setAttribute("accept", COMPOSER_SUPPORTED_EXTENSIONS.join(","));
    elements.composerFileInput.addEventListener("change", async function () {
      const files = Array.from(elements.composerFileInput.files || []);
      elements.composerFileInput.value = "";
      if (!files.length) return;
      const remainingSlots = Math.max(0, COMPOSER_ATTACHMENT_LIMIT - shellState.stagedAttachments.length);
      const selectedFiles = files.slice(0, remainingSlots);
      const rejected = [];
      for (const file of selectedFiles) {
        if (!supportedComposerFile(file)) {
          rejected.push(file.name + " unsupported");
          continue;
        }
        if (Number(file.size || 0) > COMPOSER_ATTACHMENT_MAX_BYTES) {
          rejected.push(file.name + " over " + formatFileSize(COMPOSER_ATTACHMENT_MAX_BYTES));
          continue;
        }
        try {
          const rawText = await file.text();
          stageComposerAttachment({
            id: buildAttachmentId("file"),
            name: file.name,
            size: Number(file.size || rawText.length || 0),
            type: file.type || "text/plain",
            text: rawText.slice(0, COMPOSER_ATTACHMENT_MAX_CHARS),
            truncated: rawText.length > COMPOSER_ATTACHMENT_MAX_CHARS,
            addedAt: new Date().toISOString(),
          });
        } catch (_) {
          rejected.push(file.name + " unreadable");
        }
      }
      if (files.length > selectedFiles.length) {
        rejected.push("Only " + COMPOSER_ATTACHMENT_LIMIT + " files can be staged");
      }
      if (rejected.length) {
        elements.draftState.textContent = "File staging skipped: " + rejected.join(", ");
      } else {
        elements.draftState.textContent = "File context staged for next send.";
      }
    });
  }

  if (elements.settingsCodexModel) {
    elements.settingsCodexModel.addEventListener("change", queueCodexLimitsLoad);
  }

  if (elements.settingsCodexAuthSave) {
    elements.settingsCodexAuthSave.addEventListener("click", function () {
      saveCodexAuthMode();
    });
  }

  if (elements.settingsCodexArmRun) {
    elements.settingsCodexArmRun.addEventListener("click", function () {
      runCodexArmSmoke();
    });
  }

  if (elements.settingsCodexRefresh) {
    elements.settingsCodexRefresh.addEventListener("click", function () {
      queueCodexLimitsLoad();
    });
  }

  if (elements.authRequirementClose) {
    elements.authRequirementClose.addEventListener("click", closeAuthRequirementModal);
  }

  if (elements.authRequirementModal) {
    elements.authRequirementModal.addEventListener("click", function (event) {
      if (event.target === elements.authRequirementModal) {
        closeAuthRequirementModal();
      }
    });
  }

  if (elements.authRequirementSaveKey) {
    elements.authRequirementSaveKey.addEventListener("click", function () {
      saveMissingAuthKey();
    });
  }

  if (elements.authRequirementCodexSignIn) {
    elements.authRequirementCodexSignIn.addEventListener("click", openCodexAuthHelp);
  }

  if (elements.composerAttachmentList) {
    elements.composerAttachmentList.addEventListener("click", function (event) {
      const button = event.target.closest("[data-attachment-id]");
      if (!button) return;
      removeComposerAttachment(button.getAttribute("data-attachment-id"));
    });
  }

  document.addEventListener("click", function (event) {
    if (!shellState.composerToolMenuOpen) return;
    if (event.target.closest(".igs-composer-tool-launcher")) return;
    setComposerMenuOpen(false);
  });

  document.addEventListener("click", function (event) {
    if (event.target.closest(".igs-pill-select, .igs-select-tile")) return;
    closeContractPillSelects();
  });

  elements.sendPrompt.addEventListener("click", function () {
    submitComposerAction();
  });

  if (elements.debugRefreshState) {
    elements.debugRefreshState.addEventListener("click", function () {
      refreshDebugSurface().catch(function (error) {
        if (elements.debugOperationStatus) {
          elements.debugOperationStatus.textContent = "Debug refresh failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.debugRunRound) {
    elements.debugRunRound.addEventListener("click", function () {
      runDebugOperation(API.rounds, {}, "Round dispatch queued").catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Run round failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugRunLoop) {
    elements.debugRunLoop.addEventListener("click", function () {
      const control = currentControlState();
      const delayMs = Number(runtimeState.draft?.loopDelayMs || 1000) || 1000;
      runDebugOperation(API.loops, { rounds: control.loopRounds, delayMs }, "Auto loop queued").catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Run auto loop failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugSummarize) {
    elements.debugSummarize.addEventListener("click", function () {
      runDebugOperation(API.targetsBackground, { target: "summarizer" }, "Summarizer queued").catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Summarizer failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugCancelLoop) {
    elements.debugCancelLoop.addEventListener("click", function () {
      runDebugOperation(API.loopsCancel, {}, "Cancel sent").catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Cancel loop failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugResetSession) {
    elements.debugResetSession.addEventListener("click", function () {
      if (!window.confirm("Reset active session and archive the current workspace?")) return;
      runDebugOperation(API.sessionReset, {}, "Session reset", { hydrate: true }).catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Session reset failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugClearSessionArchives) {
    elements.debugClearSessionArchives.addEventListener("click", function () {
      if (!window.confirm("Delete saved session archives? This cannot be undone.")) return;
      runDebugOperation(API.sessionArchivesClear, {}, "Session archives cleared").catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Session archive clear failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugResetState) {
    elements.debugResetState.addEventListener("click", function () {
      if (!window.confirm("Reset state and clear the active task?")) return;
      runDebugOperation(API.stateReset, {}, "State reset", { hydrate: true }).catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "State reset failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugTargetControls) {
    elements.debugTargetControls.addEventListener("click", function (event) {
      const button = event.target.closest("[data-debug-target]");
      if (!button || button.disabled) return;
      const target = String(button.getAttribute("data-debug-target") || "").trim();
      if (!target) return;
      runDebugOperation(
        API.targetsBackground,
        { target },
        target === "answer_now" ? "Partial answer queued" : "Target queued"
      ).catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Target dispatch failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugExportCurrentSession) {
    elements.debugExportCurrentSession.addEventListener("click", function () {
      loadDebugExportPreview("").catch(function (error) {
        if (elements.debugHistoryStatus) elements.debugHistoryStatus.textContent = "Session export failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugSessionArchives) {
    elements.debugSessionArchives.addEventListener("click", function (event) {
      const exportButton = event.target.closest("[data-debug-export-archive]");
      if (exportButton) {
        loadDebugExportPreview(exportButton.getAttribute("data-debug-export-archive")).catch(function (error) {
          if (elements.debugHistoryStatus) elements.debugHistoryStatus.textContent = "Archived session export failed: " + String(error.message || error);
        });
        return;
      }
      const replayButton = event.target.closest("[data-debug-replay-archive]");
      if (!replayButton) return;
      const archiveFile = String(replayButton.getAttribute("data-debug-replay-archive") || "").trim();
      if (!archiveFile || !window.confirm("Replay " + archiveFile + " into the active workspace?")) return;
      runDebugOperation(API.sessionReplay, { archiveFile }, "Archived session replayed", { hydrate: true }).catch(function (error) {
        if (elements.debugHistoryStatus) elements.debugHistoryStatus.textContent = "Archived session replay failed: " + String(error.message || error);
      });
    });
  }

  if (elements.debugJobHistory) {
    elements.debugJobHistory.addEventListener("click", function (event) {
      const button = event.target.closest("[data-debug-job-action]");
      if (!button) return;
      const action = String(button.getAttribute("data-debug-job-action") || "").trim();
      const jobId = String(button.getAttribute("data-job-id") || "").trim();
      if (!action || !jobId) return;
      const successText = action === "resume"
        ? "Interrupted loop resumed"
        : (action === "retry" ? "Loop queued for retry" : "Job cancelled");
      runDebugOperation(API.jobsManage, { action, jobId }, successText).catch(function (error) {
        if (elements.debugOperationStatus) elements.debugOperationStatus.textContent = "Job action failed: " + String(error.message || error);
      });
    });
  }

  if (elements.scoreRefreshBtn) {
    elements.scoreRefreshBtn.addEventListener("click", function () {
      scoreState.loaded = false;
      scoreState.emptyRunSkips.clear();
      loadScoreRuns(scoreState.selectedRunId).catch(function (error) {
        if (elements.scoreStatus) {
          elements.scoreStatus.textContent = "Eval sessions failed to refresh: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.sessionRefreshBtn) {
    elements.sessionRefreshBtn.addEventListener("click", function () {
      sessionBrowserState.loaded = false;
      loadSessionBrowser().catch(function (error) {
        if (elements.sessionStatus) {
          elements.sessionStatus.textContent = "Session browser refresh failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.sessionPreviewCurrentBtn) {
    elements.sessionPreviewCurrentBtn.addEventListener("click", function () {
      previewCurrentSession().catch(function (error) {
        if (elements.sessionStatus) {
          elements.sessionStatus.textContent = "Current session preview failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.sessionSearch) {
    elements.sessionSearch.addEventListener("input", function () {
      renderSessionBrowserList();
    });
  }

  if (elements.sessionList) {
    elements.sessionList.addEventListener("click", function (event) {
      const continueButton = event.target.closest("[data-session-continue]");
      if (continueButton) {
        continueSelectedSession(continueButton.getAttribute("data-session-continue")).catch(function (error) {
          if (elements.sessionStatus) {
            elements.sessionStatus.textContent = "Archived session continue failed: " + String(error.message || error);
          }
        });
        return;
      }
      const button = event.target.closest("[data-session-select], [data-session-preview]");
      if (!button) return;
      selectSessionForPreview(button.getAttribute("data-session-select") || button.getAttribute("data-session-preview")).catch(function (error) {
        if (elements.sessionStatus) {
          elements.sessionStatus.textContent = "Session preview failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.sessionReplayBtn) {
    elements.sessionReplayBtn.addEventListener("click", function () {
      continueSelectedSession(elements.sessionReplayBtn.dataset.sessionReplay).catch(function (error) {
        if (elements.sessionStatus) {
          elements.sessionStatus.textContent = "Archived session continue failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.failedCallRefreshBtn) {
    elements.failedCallRefreshBtn.addEventListener("click", function () {
      failedCallState.loaded = false;
      loadFailedCalls().catch(function (error) {
        if (elements.failedCallStatus) {
          elements.failedCallStatus.textContent = "Failed call ledger refresh failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.handoffRefreshBtn) {
    elements.handoffRefreshBtn.addEventListener("click", function () {
      handoffState.loaded = false;
      loadHandoffs().catch(function (error) {
        if (elements.handoffStatus) {
          elements.handoffStatus.textContent = "Handoff ledger refresh failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.handoffCreateBtn) {
    elements.handoffCreateBtn.addEventListener("click", function () {
      createHandoffPacket().catch(function (error) {
        if (elements.handoffStatus) {
          elements.handoffStatus.textContent = "Handoff creation failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.handoffSelect) {
    elements.handoffSelect.addEventListener("change", function () {
      handoffState.selectedName = String(elements.handoffSelect.value || "");
      loadHandoffDetail(handoffState.selectedName).catch(function (error) {
        if (elements.handoffStatus) {
          elements.handoffStatus.textContent = "Handoff load failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.nodeTransferRefreshBtn) {
    elements.nodeTransferRefreshBtn.addEventListener("click", function () {
      nodeTransferState.loaded = false;
      loadNodeTransfers().catch(function (error) {
        if (elements.nodeTransferStatus) {
          elements.nodeTransferStatus.textContent = "Node transfer ledger refresh failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.nodeTransferSelect) {
    elements.nodeTransferSelect.addEventListener("change", function () {
      nodeTransferState.selectedName = String(elements.nodeTransferSelect.value || "");
      loadNodeTransferDetail(nodeTransferState.selectedName).catch(function (error) {
        if (elements.nodeTransferStatus) {
          elements.nodeTransferStatus.textContent = "Transfer load failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.failedCallSelect) {
    elements.failedCallSelect.addEventListener("change", function () {
      failedCallState.selectedName = String(elements.failedCallSelect.value || "");
      loadFailedCallDetail(failedCallState.selectedName).catch(function (error) {
        if (elements.failedCallStatus) {
          elements.failedCallStatus.textContent = "Failed call load failed: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.scoreRunSelect) {
    elements.scoreRunSelect.addEventListener("change", function () {
      scoreState.selectedRunId = String(elements.scoreRunSelect.value || "");
      scoreState.selectedSessionId = "";
      scoreState.loaded = false;
      scoreState.autoComparableFallback = false;
      scoreState.emptyRunSkips.clear();
      persistScoreSelection();
      loadScoreRuns(scoreState.selectedRunId).catch(function (error) {
        if (elements.scoreStatus) {
          elements.scoreStatus.textContent = "Eval run failed to load: " + String(error.message || error);
        }
      });
    });
  }

  if (elements.scoreSessionSelect) {
    elements.scoreSessionSelect.addEventListener("change", function () {
      scoreState.selectedSessionId = String(elements.scoreSessionSelect.value || "");
      persistScoreSelection();
      renderCurrentScoreSession();
    });
  }

  installMainWorkbenchPanes();
  window.addEventListener("pointermove", onMainWorkbenchPaneMove);
  window.addEventListener("pointerup", endMainWorkbenchPaneDrag);
  window.addEventListener("pointermove", scheduleScrollbarProximity, { passive: true });
  window.addEventListener("mousemove", scheduleScrollbarProximity, { passive: true });
  window.addEventListener("pointerleave", clearScrollbarHotState);
  window.addEventListener("blur", clearScrollbarHotState);

  seedSelectorActuatorOrbits();
  syncProviderButtonMetrics();
  if (document.fonts?.ready) {
    document.fonts.ready.then(syncProviderButtonMetrics).catch(function () {});
  }
  installContractPillSelects();
  fillModelsForCurrentProviders();
  syncSelectToggleButtons();
  syncSelectCycleButtons();
  resizeObjectiveTextarea();
  window.addEventListener("resize", resizeObjectiveTextarea);
  window.addEventListener("resize", syncProviderButtonMetrics);
  try {
    applySidebarState(window.localStorage.getItem("igsShell.sidebarCollapsed") === "1");
  } catch (_) {
    applySidebarState(false);
  }
  try {
    setInspectorMode(window.localStorage.getItem("igsShell.inspectorMode") || "repo");
  } catch (_) {
    setInspectorMode("repo");
  }
  shellState.homeCollapsedPanels = new Set(readHomeCollapsedPanels());
  applyHomePanelCollapseState();
  window.requestAnimationFrame(syncProviderButtonMetrics);
  try {
    scoreState.selectedRunId = window.localStorage.getItem("igsShell.scoreRunId") || "";
    scoreState.selectedSessionId = window.localStorage.getItem("igsShell.scoreSessionId") || "";
  } catch (_) {}
  loadState({ hydrate: true }).catch(function (error) {
    elements.draftState.textContent = "Load failed: " + String(error.message || error);
  });
  window.setInterval(function () {
    loadState({ hydrate: false }).catch(function () {});
  }, 5000);
})();
