const MODEL_CATALOG = {
  "gpt-5.4": { label: "GPT-5.4" },
  "gpt-5.4-mini": { label: "GPT-5.4 mini" },
  "gpt-5.4-nano": { label: "GPT-5.4 nano" },
  "gpt-5.2": { label: "GPT-5.2" },
  "gpt-5.1": { label: "GPT-5.1" },
  "gpt-5": { label: "GPT-5" },
  "gpt-5-mini": { label: "GPT-5 mini" },
  "gpt-5-nano": { label: "GPT-5 nano" },
  "gpt-4.1": { label: "GPT-4.1" },
  "gpt-4.1-mini": { label: "GPT-4.1 mini" },
  "gpt-4.1-nano": { label: "GPT-4.1 nano" },
  "gpt-4o": { label: "GPT-4o" },
  "gpt-4o-mini": { label: "GPT-4o mini" }
};

const ANTHROPIC_MODEL_CATALOG = {
  "claude-opus-4-1-20250805": { label: "Claude Opus 4.1" },
  "claude-opus-4-20250514": { label: "Claude Opus 4" },
  "claude-sonnet-4-20250514": { label: "Claude Sonnet 4" },
  "claude-3-7-sonnet-20250219": { label: "Claude Sonnet 3.7" },
  "claude-3-5-haiku-latest": { label: "Claude Haiku 3.5" }
};

const XAI_MODEL_CATALOG = {
  "grok-4.20-reasoning": { label: "Grok 4.20 Reasoning" },
  "grok-4-1-fast-reasoning": { label: "Grok 4.1 Fast Reasoning" },
  "grok-4.20-multi-agent": { label: "Grok 4.20 Multi-Agent" },
  "grok-4.20": { label: "Grok 4.20" }
};

const MINIMAX_MODEL_CATALOG = {
  "MiniMax-M2.7": { label: "MiniMax M2.7" },
  "MiniMax-M2.7-highspeed": { label: "MiniMax M2.7 Highspeed" },
  "MiniMax-M2.5": { label: "MiniMax M2.5" },
  "MiniMax-M2.5-highspeed": { label: "MiniMax M2.5 Highspeed" },
  "MiniMax-M2.1": { label: "MiniMax M2.1" },
  "MiniMax-M2.1-highspeed": { label: "MiniMax M2.1 Highspeed" },
  "MiniMax-M2": { label: "MiniMax M2" }
};

const PROVIDER_CATALOG = {
  openai: { label: "OpenAI" },
  anthropic: { label: "Anthropic" },
  xai: { label: "xAI" },
  minimax: { label: "MiniMax" },
  ollama: { label: "Ollama" }
};
const PROVIDER_ORDER = Object.keys(PROVIDER_CATALOG);
const PROVIDER_CAPABILITY_CATALOG = {
  openai: {
    toolLoop: true,
    webSearch: true,
    localFiles: true,
    githubTools: true,
    costTracking: true,
    notes: [
      "Responses API path with built-in web search and audited tool loop.",
      "Estimated spend tracking is available."
    ]
  },
  anthropic: {
    toolLoop: true,
    webSearch: true,
    localFiles: true,
    githubTools: true,
    costTracking: false,
    notes: [
      "Messages API path with tool_use/tool_result turns.",
      "Server web search plus client tool loops are enabled."
    ]
  },
  xai: {
    toolLoop: true,
    webSearch: true,
    localFiles: true,
    githubTools: true,
    costTracking: false,
    notes: [
      "xAI Responses path with Grok-compatible function tools.",
      "Built-in web search is enabled in this runtime."
    ]
  },
  minimax: {
    toolLoop: true,
    webSearch: false,
    localFiles: true,
    githubTools: true,
    costTracking: false,
    notes: [
      "Anthropic-compatible MiniMax path for messages and client tools.",
      "Built-in live web search is not wired here yet."
    ]
  },
  ollama: {
    toolLoop: true,
    webSearch: false,
    localFiles: true,
    githubTools: true,
    costTracking: false,
    notes: [
      "Native local structured generation with client-side function tools.",
      "Live web search is still disabled for Ollama in this runtime."
    ]
  }
};
const OLLAMA_MODEL_CATALOG = {
  qwen3: { label: "Qwen3" },
  "qwen3-coder": { label: "Qwen3 Coder" },
  gemma3: { label: "Gemma 3" },
  "llama3.2": { label: "Llama 3.2" }
};
const PROVIDER_MODEL_CATALOG = {
  openai: MODEL_CATALOG,
  anthropic: ANTHROPIC_MODEL_CATALOG,
  xai: XAI_MODEL_CATALOG,
  minimax: MINIMAX_MODEL_CATALOG,
  ollama: OLLAMA_MODEL_CATALOG
};
const PROVIDER_DEFAULT_MODELS = {
  openai: "gpt-5-mini",
  anthropic: "claude-sonnet-4-20250514",
  xai: "grok-4.20-reasoning",
  minimax: "MiniMax-M2.7",
  ollama: "qwen3"
};

const DEFAULT_TARGET_TIMEOUTS = {
  directBaseline: 150,
  commander: 180,
  workerDefault: 180,
  workers: {},
  commanderReview: 240,
  summarizer: 240,
  answerNow: 180,
  arbiter: 180
};
const MODEL_ORDER = Object.keys(MODEL_CATALOG);
const WORKER_SLOT_IDS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const WORKER_TYPE_CATALOG = {
  proponent: { label: "Proponent", role: "utility", focus: "benefits, feasibility, leverage, momentum, practical execution", temperature: "balanced" },
  sceptic: { label: "Sceptic", role: "adversarial", focus: "failure modes, downside, hidden coupling, consequences, externalities", temperature: "cool" },
  economist: { label: "Economist", role: "adversarial", focus: "cost ceilings, burn rate, return on effort, economic drag", temperature: "cool" },
  security: { label: "Security", role: "adversarial", focus: "security abuse, privilege escalation, hostile actors", temperature: "hot" },
  reliability: { label: "Reliability", role: "adversarial", focus: "reliability collapse, uptime loss, brittle dependencies", temperature: "cool" },
  concurrency: { label: "Concurrency", role: "adversarial", focus: "concurrency races, lock contention, timing faults", temperature: "hot" },
  data: { label: "Data Integrity", role: "adversarial", focus: "data integrity, corruption, replay hazards", temperature: "cool" },
  compliance: { label: "Compliance", role: "adversarial", focus: "compliance, policy drift, governance gaps", temperature: "balanced" },
  user: { label: "User Advocate", role: "adversarial", focus: "user confusion, adoption friction, trust loss", temperature: "balanced" },
  performance: { label: "Performance", role: "adversarial", focus: "performance cliffs, hot paths, slow feedback", temperature: "hot" },
  observability: { label: "Observability", role: "adversarial", focus: "observability blind spots, missing traces, opaque failures", temperature: "cool" },
  scalability: { label: "Scalability", role: "adversarial", focus: "scalability failure, fan-out load, resource exhaustion", temperature: "hot" },
  recovery: { label: "Recovery", role: "adversarial", focus: "recovery posture, rollback gaps, broken resumes", temperature: "cool" },
  integration: { label: "Integrations", role: "adversarial", focus: "integration mismatch, boundary contracts, interoperability", temperature: "balanced" },
  abuse: { label: "Abuse Cases", role: "adversarial", focus: "abuse cases, spam, malicious automation", temperature: "hot" },
  latency: { label: "Latency", role: "adversarial", focus: "latency budgets, throughput realism, field conditions", temperature: "balanced" },
  incentives: { label: "Incentives", role: "adversarial", focus: "incentive mismatch, local maxima, misuse of metrics", temperature: "balanced" },
  scope: { label: "Scope Control", role: "adversarial", focus: "scope creep, hidden complexity, disguised expansions", temperature: "cool" },
  maintainability: { label: "Maintainability", role: "adversarial", focus: "maintainability drag, operator toil, handoff risk", temperature: "cool" },
  edge: { label: "Edge Cases", role: "adversarial", focus: "edge cases, chaos inputs, pathological sequences", temperature: "hot" },
  human: { label: "Human Factors", role: "adversarial", focus: "human factors, fatigue, procedural mistakes", temperature: "balanced" },
  portability: { label: "Portability", role: "adversarial", focus: "vendor lock-in, portability loss, external dependence", temperature: "cool" },
  privacy: { label: "Privacy", role: "adversarial", focus: "privacy leakage, retention risk, oversharing", temperature: "cool" },
  product: { label: "Product Strategy", role: "adversarial", focus: "product mismatch, weak demand signal, false confidence", temperature: "balanced" },
  governance: { label: "Governance", role: "adversarial", focus: "decision paralysis, review bottlenecks, process drag", temperature: "cool" },
  wildcard: { label: "Wildcard", role: "adversarial", focus: "wildcard attack surfaces, overlooked weirdness, novel failure", temperature: "hot" }
};
const WORKER_TYPE_ORDER = [
  "proponent", "sceptic", "economist", "security", "reliability", "concurrency", "data", "compliance", "user",
  "performance", "observability", "scalability", "recovery", "integration", "abuse", "latency", "incentives",
  "scope", "maintainability", "edge", "human", "portability", "privacy", "product", "governance", "wildcard"
];
const WORKER_TEMPERATURE_CATALOG = {
  cool: { label: "Cool" },
  balanced: { label: "Balanced" },
  hot: { label: "Hot" }
};
const WORKER_TEMPERATURE_ORDER = Object.keys(WORKER_TEMPERATURE_CATALOG);
const HARNESS_CONCISION_CATALOG = {
  none: { label: "No harness" },
  tight: { label: "Tight" },
  balanced: { label: "Balanced" },
  expansive: { label: "Expansive" }
};
const HARNESS_CONCISION_ORDER = Object.keys(HARNESS_CONCISION_CATALOG);
const DEFAULT_RUNTIME_BUDGET = {
  maxCostUsd: 5,
  maxTotalTokens: 100000,
  maxOutputTokens: 1200
};
const QUALITY_PROFILE_CATALOG = {
  low: {
    label: "Low",
    eyebrow: "Lean spend",
    description: "Keeps every lane on a cheap capable model for everyday work without burning budget.",
    workerModel: "gpt-5-mini",
    summarizerModel: "gpt-5-mini",
    reasoningEffort: "low",
    maxCostUsd: DEFAULT_RUNTIME_BUDGET.maxCostUsd,
    maxTotalTokens: 100000,
    maxOutputTokens: DEFAULT_RUNTIME_BUDGET.maxOutputTokens,
    loopRounds: 3,
    loopDelayMs: 1000
  },
  mid: {
    label: "Mid",
    eyebrow: "Best bang",
    description: "Lets cheap worker lanes explore while a stronger summarizer shapes the final answer.",
    workerModel: "gpt-5-mini",
    summarizerModel: "gpt-5.4-mini",
    reasoningEffort: "medium",
    maxCostUsd: 12,
    maxTotalTokens: 500000,
    maxOutputTokens: 1800,
    loopRounds: 4,
    loopDelayMs: 1000
  },
  high: {
    label: "High",
    eyebrow: "Sharper debate",
    description: "Upgrades the adversarial lanes and the final judge for harder prompts and denser steering.",
    workerModel: "gpt-5.4-mini",
    summarizerModel: "gpt-5.4",
    reasoningEffort: "high",
    maxCostUsd: 30,
    maxTotalTokens: 1000000,
    maxOutputTokens: 2800,
    loopRounds: 6,
    loopDelayMs: 1000
  },
  ultra: {
    label: "Ultra",
    eyebrow: "Long haul",
    description: "Keeps the spend wall while letting long pressure runs breathe with a very high token ceiling.",
    workerModel: "gpt-5.4",
    summarizerModel: "gpt-5.4",
    reasoningEffort: "xhigh",
    maxCostUsd: 75,
    maxTotalTokens: 2000000,
    maxOutputTokens: 4000,
    loopRounds: 8,
    loopDelayMs: 1000
  }
};
const QUALITY_PROFILE_ORDER = ["low", "mid", "high", "ultra"];
const COMPOSER_ATTACHMENT_LIMIT = 4;
const COMPOSER_ATTACHMENT_MAX_BYTES = 180000;
const COMPOSER_ATTACHMENT_MAX_CHARS = 6000;
const COMPOSER_RECENT_FILES_KEY = "loopComposerRecentFiles";
const OPERATOR_NOTICE_ACK_KEY = "loopOperatorNoticeAckV1";
const COMPOSER_SUPPORTED_EXTENSIONS = [
  ".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".log", ".py", ".js", ".jsx", ".ts", ".tsx",
  ".html", ".css", ".xml", ".yaml", ".yml", ".sql", ".sh", ".bat", ".ps1"
];
let latestAuthStatus = {
  hasKey: false,
  keyCount: 0,
  backend: "env",
  writable: false,
  preferred: true,
  deprecated: false,
  preferredBackends: ["env", "external"],
  recommendedBackend: "env",
  defaultMode: "safe",
  statusNote: "",
  rotationPolicy: null,
  providerOrder: ["openai", "anthropic", "xai", "minimax"],
  providerGroups: {},
  isolationNote: "",
  termsWarning: ""
};
let authDynamicRowsByProvider = {};
let authRowSequence = 0;
let authSaveTimers = {};
let authRowSaveState = {};
let latestLoopActive = false;
let latestManualDispatchCount = 0;
let latestManualDispatchEntries = [];
let manualDispatchSequence = 0;
let artifactSelections = { left: "", right: "" };
let formDirty = false;
let lastSyncedFormSourceKey = "";
let activeView = localStorage.getItem("loopActiveView") || "home";
let sidebarCollapsed = localStorage.getItem("loopSidebarCollapsed") === "1";
let activeTheme = localStorage.getItem("loopTheme") || "dark";
let mobileSidebarOpen = false;
let latestState = null;
let latestHistoryState = null;
let latestEvalHistory = null;
let sidebarCopyCollapseTargets = [];
let selectedEvalRunId = localStorage.getItem("loopSelectedEvalRunId") || "";
let evalArtifactSelections = { left: "", right: "" };
let evalArtifactContentCache = {};
let evalArtifactRequestState = {};
let composerToolMenuOpen = false;
let composerSourceDrawerOpen = false;
let composerRecentDrawerOpen = false;
let stagedComposerAttachments = [];
let recentComposerAttachments = [];
let draftSaveTimer = null;
let workerControlsSignature = "";
let workerControlExpanded = safeJsonParse(localStorage.getItem("loopWorkerControlExpanded") || "{}", {});
let workerEditorOverrides = { workers: {}, summarizer: null };
let workerEditorModalState = { kind: "", key: "" };
let debugControlsSignature = "";
let threadRenderSignature = "";
let threadRenderTaskId = "";
let threadInspectorOpen = false;
let frontEvalTechnicalOpen = false;
let frontEvalArbiterRequestKey = "";
let exportPreviewKey = "";
let operatorNoticeAcceptedThisSession = false;
const API = {
  artifact: "/v1/artifact",
  draft: "/v1/draft",
  authStatus: "/v1/auth/status",
  authKeys: "/v1/auth/keys",
  authMode: "/v1/auth/mode",
  evalArtifact: "/v1/evals/artifact",
  evalHistory: "/v1/evals/history",
  exportSession: "/v1/session/export",
  state: "/v1/state",
  events: "/v1/events",
  steps: "/v1/steps",
  history: "/v1/history",
  runtimeApply: "/v1/runtime/apply",
  tasks: "/v1/tasks",
  loops: "/v1/loops",
  targetsBackground: "/v1/targets/background",
  rounds: "/v1/rounds",
  workersAdd: "/v1/workers/add",
  workersRemove: "/v1/workers/remove",
  loopsCancel: "/v1/loops/cancel",
  evalRuns: "/v1/evals/runs",
  sessionReset: "/v1/session/reset",
  stateReset: "/v1/state/reset",
  positionModel: "/v1/positions/model",
  sessionReplay: "/v1/session/replay",
  jobsManage: "/v1/jobs/manage",
  workersUpdate: "/v1/workers/update"
};

function apiBase() {
  const params = new URLSearchParams(window.location.search);
  return String(
    params.get("apiBase")
    || window.LOOP_API_BASE
    || ""
  ).trim();
}

function apiRoute(path) {
  const base = apiBase();
  if (!base) return String(path || "");
  return base.replace(/\/+$/, "") + "/" + String(path || "").replace(/^\/+/, "");
}

function apiModeDisplay() {
  return "Python";
}

function shouldShowOperatorNotice() {
  return !operatorNoticeAcceptedThisSession && localStorage.getItem(OPERATOR_NOTICE_ACK_KEY) !== "1";
}

function syncOperatorNoticeVisibility() {
  const visible = shouldShowOperatorNotice();
  $("#operatorNoticeModal").prop("hidden", !visible).attr("aria-hidden", visible ? "false" : "true");
  $("body").toggleClass("operator-notice-open", visible);
}

function acceptOperatorNotice() {
  operatorNoticeAcceptedThisSession = true;
  if ($("#operatorNoticeDontShow").is(":checked")) {
    localStorage.setItem(OPERATOR_NOTICE_ACK_KEY, "1");
  } else {
    localStorage.removeItem(OPERATOR_NOTICE_ACK_KEY);
  }
  syncOperatorNoticeVisibility();
}

function apiModeDetails() {
  const base = apiBase();
  return base
    ? ("Python control plane via " + base)
    : "Python-served shell with same-origin /v1 routes";
}

function renderApiModeStatus() {
  const $pill = $("#headerApiMode");
  if (!$pill.length) return;
  const $card = $pill.closest(".workspace-pill");
  $pill.text(apiModeDisplay());
  $card
    .addClass("api-mode-pill")
    .addClass("is-python")
    .attr("title", apiModeDetails());
}

function showMessage(text, isError = false) {
  $("#message").text(text || "").css({
    color: isError ? "#fecaca" : "#8ce7ff",
    borderColor: isError ? "rgba(248, 113, 113, 0.28)" : "rgba(76, 201, 240, 0.22)",
    background: isError ? "rgba(61, 25, 25, 0.76)" : "rgba(14, 33, 50, 0.76)"
  });
}

function clearMessageIfMatching(prefixes) {
  const message = String($("#message").text() || "");
  const patterns = Array.isArray(prefixes) ? prefixes : [prefixes];
  if (!patterns.some(function (prefix) { return message.startsWith(String(prefix || "")); })) {
    return;
  }
  $("#message").text("").css({
    color: "",
    borderColor: "",
    background: ""
  });
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function formatUsd(value) {
  const amount = Number(value || 0);
  return "$" + amount.toFixed(4);
}

function formatUsdBudget(value) {
  const amount = Number(value || 0);
  return "$" + amount.toFixed(2);
}

function formatElapsedDuration(startedAt) {
  const started = Number(startedAt || 0);
  if (!started) return "0s";
  const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes <= 0) return remainder + "s";
  return minutes + "m " + String(remainder).padStart(2, "0") + "s";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function truncateText(value, maxLength = 220) {
  const text = String(value || "").trim().replace(/\s+/g, " ");
  if (!text) return "";
  return text.length > maxLength ? text.slice(0, Math.max(0, maxLength - 3)).trim() + "..." : text;
}

function safeJsonParse(raw, fallback) {
  try {
    const parsed = JSON.parse(raw);
    return parsed == null ? fallback : parsed;
  } catch (_) {
    return fallback;
  }
}

function normalizeWorkerControlKey(key) {
  return String(key || "").trim().toLowerCase();
}

function setWorkerControlExpandedState(key, open) {
  const normalizedKey = normalizeWorkerControlKey(key);
  if (!normalizedKey) return;
  workerControlExpanded[normalizedKey] = !!open;
  localStorage.setItem("loopWorkerControlExpanded", JSON.stringify(workerControlExpanded));
}

function mergeHarnessOverride(baseHarness, overrideHarness, fallback = "tight") {
  return normalizeHarnessConfig(Object.assign({}, baseHarness || {}, overrideHarness || {}), fallback);
}

function editableWorkerSnapshot(worker, provider) {
  const base = worker && typeof worker === "object" ? worker : {};
  const typeId = String(base.type || "sceptic").trim().toLowerCase() || "sceptic";
  const template = WORKER_TYPE_CATALOG[typeId] || WORKER_TYPE_CATALOG.sceptic;
  return Object.assign({}, base, {
    id: String(base.id || "").trim(),
    type: typeId,
    temperature: String(base.temperature || template.temperature || "balanced").trim().toLowerCase() || "balanced",
    model: normalizeSelectedModelForProvider(String(base.model || defaultModelForProvider(provider)), provider),
    label: template.label,
    role: template.role,
    focus: template.focus,
    harness: normalizeHarnessConfig(base.harness, "tight")
  });
}

function editableSummarizerSnapshot(summarizer, provider) {
  const base = summarizer && typeof summarizer === "object" ? summarizer : {};
  return Object.assign({}, base, {
    id: "summarizer",
    label: "Main thread",
    provider,
    model: normalizeSelectedModelForProvider(String(base.model || defaultModelForProvider(provider)), provider),
    harness: normalizeHarnessConfig(base.harness, "expansive")
  });
}

function mergeWorkerEditorWorker(worker, override, provider) {
  const base = worker && typeof worker === "object" ? worker : {};
  const extra = override && typeof override === "object" ? override : {};
  const merged = Object.assign({}, base, extra);
  merged.harness = mergeHarnessOverride(base.harness, extra.harness, "tight");
  return editableWorkerSnapshot(merged, provider);
}

function mergeWorkerEditorSummarizer(summarizer, override, provider) {
  const base = summarizer && typeof summarizer === "object" ? summarizer : {};
  const extra = override && typeof override === "object" ? override : {};
  const merged = Object.assign({}, base, extra);
  merged.harness = mergeHarnessOverride(base.harness, extra.harness, "expansive");
  return editableSummarizerSnapshot(merged, provider);
}

function workerEditableSignature(worker) {
  return JSON.stringify({
    id: String(worker?.id || "").trim(),
    type: String(worker?.type || "sceptic"),
    temperature: String(worker?.temperature || "balanced"),
    model: String(worker?.model || ""),
    harness: normalizeHarnessConfig(worker?.harness, "tight")
  });
}

function summarizerEditableSignature(summarizer) {
  return JSON.stringify({
    provider: String(summarizer?.provider || "openai"),
    model: String(summarizer?.model || ""),
    harness: normalizeHarnessConfig(summarizer?.harness, "expansive")
  });
}

function setWorkerEditorWorkerOverride(workerId, patch) {
  const key = normalizeWorkerControlKey(workerId);
  if (!key) return;
  const current = workerEditorOverrides.workers[key] && typeof workerEditorOverrides.workers[key] === "object"
    ? workerEditorOverrides.workers[key]
    : {};
  const next = Object.assign({}, current, patch || {});
  if (patch && Object.prototype.hasOwnProperty.call(patch, "harness")) {
    next.harness = Object.assign({}, current.harness || {}, patch.harness || {});
  }
  workerEditorOverrides.workers[key] = next;
}

function setWorkerEditorSummarizerOverride(patch) {
  const current = workerEditorOverrides.summarizer && typeof workerEditorOverrides.summarizer === "object"
    ? workerEditorOverrides.summarizer
    : {};
  const next = Object.assign({}, current, patch || {});
  if (patch && Object.prototype.hasOwnProperty.call(patch, "harness")) {
    next.harness = Object.assign({}, current.harness || {}, patch.harness || {});
  }
  workerEditorOverrides.summarizer = next;
}

function visibleWorkerRosterSource(draft = latestState?.draft || null, task = latestState?.activeTask || null) {
  const provider = runtimeProviderSource(task, draft);
  return stagedWorkerSource(draft, task).map(function (worker) {
    return mergeWorkerEditorWorker(worker, workerEditorOverrides.workers[normalizeWorkerControlKey(worker?.id)], provider);
  });
}

function visibleSummarizerSource(draft = latestState?.draft || null, task = latestState?.activeTask || null) {
  const provider = normalizeProviderId($("#summarizerProvider").val() || summarizerProviderSource(task, draft));
  return mergeWorkerEditorSummarizer(stagedSummarizerSource(draft, task), workerEditorOverrides.summarizer, provider);
}

function reconcileWorkerEditorOverrides(draft = latestState?.draft || null, task = latestState?.activeTask || null) {
  const provider = runtimeProviderSource(task, draft);
  const nextWorkerOverrides = {};
  const baseWorkers = stagedWorkerSource(draft, task);
  const byKey = {};
  baseWorkers.forEach(function (worker) {
    byKey[normalizeWorkerControlKey(worker?.id)] = worker;
  });
  Object.keys(workerEditorOverrides.workers || {}).forEach(function (key) {
    const base = byKey[key];
    const override = workerEditorOverrides.workers[key];
    if (!base || !override || typeof override !== "object") return;
    const baseSignature = workerEditableSignature(mergeWorkerEditorWorker(base, null, provider));
    const overrideSignature = workerEditableSignature(mergeWorkerEditorWorker(base, override, provider));
    if (baseSignature !== overrideSignature) {
      nextWorkerOverrides[key] = override;
    }
  });
  workerEditorOverrides.workers = nextWorkerOverrides;

  const summarizerProvider = normalizeProviderId($("#summarizerProvider").val() || summarizerProviderSource(task, draft));
  const baseSummarizer = mergeWorkerEditorSummarizer(stagedSummarizerSource(draft, task), null, summarizerProvider);
  const overrideSummarizer = mergeWorkerEditorSummarizer(stagedSummarizerSource(draft, task), workerEditorOverrides.summarizer, summarizerProvider);
  if (workerEditorOverrides.summarizer && summarizerEditableSignature(baseSummarizer) === summarizerEditableSignature(overrideSummarizer)) {
    workerEditorOverrides.summarizer = null;
  }
}

function appendCompactHoverPopup($root, lines) {
  const detailLines = (lines || []).filter(Boolean);
  if (!detailLines.length) return;
  const $popup = $("<div>").addClass("compact-card-tooltip");
  detailLines.forEach(function (line) {
    $popup.append($("<div>").addClass("compact-card-tooltip-line").text(line));
  });
  $root.append($popup);
}

function loadRecentComposerAttachments() {
  const stored = safeJsonParse(localStorage.getItem(COMPOSER_RECENT_FILES_KEY) || "[]", []);
  if (!Array.isArray(stored)) return [];
  return stored
    .map(function (entry) {
      if (!entry || typeof entry !== "object") return null;
      const name = String(entry.name || "").trim();
      const text = String(entry.text || "");
      if (!name || !text) return null;
      return {
        id: String(entry.id || (name + "-" + Date.now())),
        name: name,
        size: Number(entry.size || text.length || 0),
        type: String(entry.type || "text/plain"),
        text: text,
        truncated: !!entry.truncated,
        addedAt: String(entry.addedAt || "")
      };
    })
    .filter(Boolean)
    .slice(0, 6);
}

function saveRecentComposerAttachments() {
  localStorage.setItem(COMPOSER_RECENT_FILES_KEY, JSON.stringify(recentComposerAttachments.slice(0, 6)));
}

function buildAttachmentId(prefix = "attachment") {
  return prefix + "-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
}

function formatFileSize(bytes) {
  const size = Number(bytes || 0);
  if (size >= 1024 * 1024) return (size / (1024 * 1024)).toFixed(1) + " MB";
  if (size >= 1024) return Math.round(size / 1024) + " KB";
  return size + " B";
}

function supportedComposerFile(file) {
  const name = String(file?.name || "").toLowerCase();
  const type = String(file?.type || "").toLowerCase();
  const extension = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  return COMPOSER_SUPPORTED_EXTENSIONS.includes(extension)
    || type.startsWith("text/")
    || type.includes("json")
    || type.includes("xml")
    || type.includes("javascript");
}

function markComposerConfigDirty() {
  formDirty = true;
  renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
  renderQualityProfileCards();
  renderComposerTools();
  renderAuthStatus(latestAuthStatus);
  queueDraftSave();
}

function clearComposerAttachments() {
  stagedComposerAttachments = [];
  composerRecentDrawerOpen = false;
  renderComposerTools();
}

function resetComposerSurface(clearAttachments = true) {
  if (clearAttachments) {
    stagedComposerAttachments = [];
  }
  composerToolMenuOpen = false;
  composerSourceDrawerOpen = false;
  composerRecentDrawerOpen = false;
  renderComposerTools();
}

function removeComposerAttachment(attachmentId) {
  stagedComposerAttachments = stagedComposerAttachments.filter(function (attachment) {
    return attachment.id !== attachmentId;
  });
  renderComposerTools();
}

function storeRecentComposerAttachment(attachment) {
  const deduped = recentComposerAttachments.filter(function (entry) {
    return !(entry.name === attachment.name && entry.text === attachment.text);
  });
  deduped.unshift({
    id: buildAttachmentId("recent"),
    name: attachment.name,
    size: attachment.size,
    type: attachment.type,
    text: attachment.text,
    truncated: !!attachment.truncated,
    addedAt: new Date().toISOString()
  });
  recentComposerAttachments = deduped.slice(0, 6);
  saveRecentComposerAttachments();
}

function stageComposerAttachment(attachment) {
  const deduped = stagedComposerAttachments.filter(function (entry) {
    return !(entry.name === attachment.name && entry.text === attachment.text);
  });
  stagedComposerAttachments = deduped.concat([attachment]).slice(-COMPOSER_ATTACHMENT_LIMIT);
  renderComposerTools();
}

function attachmentPreviewText(attachment) {
  return truncateText(String(attachment?.text || "").replace(/\s+/g, " "), 150);
}

function buildAttachmentContextBlock() {
  if (!stagedComposerAttachments.length) return "";
  const blocks = ["Attached source files for this request. Treat them as user-provided context:"];
  stagedComposerAttachments.forEach(function (attachment) {
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

function lineAnchorId(ref) {
  return "line-ref-" + String(ref || "").replace(/[^a-zA-Z0-9_-]+/g, "-");
}

function defaultDraftState() {
  return {
    objective: "",
    constraints: [],
    sessionContext: "",
    executionMode: "live",
    frontMode: "full",
    contextMode: "weighted",
    directBaselineMode: "off",
    provider: "openai",
    model: "gpt-5-mini",
    summarizerProvider: "openai",
    summarizerModel: "gpt-5-mini",
    directProvider: "openai",
    directModel: "gpt-5-mini",
    ollamaBaseUrl: "http://127.0.0.1:11434",
    reasoningEffort: "low",
    targetTimeouts: Object.assign({}, DEFAULT_TARGET_TIMEOUTS, { workers: {} }),
    maxCostUsd: DEFAULT_RUNTIME_BUDGET.maxCostUsd,
    maxTotalTokens: DEFAULT_RUNTIME_BUDGET.maxTotalTokens,
    maxOutputTokens: DEFAULT_RUNTIME_BUDGET.maxOutputTokens,
    researchEnabled: false,
    researchExternalWebAccess: true,
    researchDomains: [],
    localFilesEnabled: false,
    localFileRoots: ["."],
    githubToolsEnabled: false,
    githubAllowedRepos: [],
    dynamicSpinupEnabled: false,
    vettingEnabled: true,
    summarizerHarness: { concision: "expansive", instruction: "" },
    loopRounds: 3,
    loopDelayMs: 1000,
    workers: [
      { id: "A", type: "proponent", label: "Proponent", role: "utility", focus: "benefits, feasibility, leverage, momentum, practical execution", temperature: "balanced", model: "gpt-5-mini", harness: { concision: "tight", instruction: "" } },
      { id: "B", type: "sceptic", label: "Sceptic", role: "adversarial", focus: "failure modes, downside, hidden coupling, consequences, externalities", temperature: "cool", model: "gpt-5-mini", harness: { concision: "tight", instruction: "" } }
    ],
    updatedAt: ""
  };
}

function normalizeOllamaBaseUrl(value) {
  const raw = String(value || "").trim();
  return (raw || "http://127.0.0.1:11434").replace(/\/+$/, "");
}

function shouldShowOllamaBaseUrl(workerProvider, summarizerProvider) {
  return normalizeProviderId(workerProvider) === "ollama" || normalizeProviderId(summarizerProvider) === "ollama";
}

function normalizeContextMode(value) {
  const raw = String(value || "").trim().toLowerCase();
  return raw === "full" ? "full" : "weighted";
}

function clampTimeoutSeconds(value, fallback) {
  const parsed = parseInt(value, 10);
  const candidate = Number.isFinite(parsed) ? parsed : parseInt(fallback, 10);
  return Math.max(15, Math.min(3600, Number.isFinite(candidate) ? candidate : 180));
}

function normalizeTargetTimeouts(value) {
  let config = value;
  if (typeof config === "string") {
    const trimmed = config.trim();
    if (trimmed.startsWith("{")) {
      try {
        config = JSON.parse(trimmed);
      } catch (_) {
        config = {};
      }
    } else {
      config = {};
    }
  }
  const source = (config && typeof config === "object") ? config : {};
  const workers = {};
  const rawWorkers = source.workers && typeof source.workers === "object" ? source.workers : {};
  Object.keys(rawWorkers).forEach(function (workerId) {
    const key = String(workerId || "").trim().toUpperCase();
    if (!/^[A-Z]$/.test(key)) return;
    workers[key] = clampTimeoutSeconds(rawWorkers[workerId], DEFAULT_TARGET_TIMEOUTS.workerDefault);
  });
  return {
    directBaseline: clampTimeoutSeconds(source.directBaseline, DEFAULT_TARGET_TIMEOUTS.directBaseline),
    commander: clampTimeoutSeconds(source.commander, DEFAULT_TARGET_TIMEOUTS.commander),
    workerDefault: clampTimeoutSeconds(source.workerDefault, DEFAULT_TARGET_TIMEOUTS.workerDefault),
    workers: workers,
    commanderReview: clampTimeoutSeconds(source.commanderReview, DEFAULT_TARGET_TIMEOUTS.commanderReview),
    summarizer: clampTimeoutSeconds(source.summarizer, DEFAULT_TARGET_TIMEOUTS.summarizer),
    answerNow: clampTimeoutSeconds(source.answerNow, DEFAULT_TARGET_TIMEOUTS.answerNow),
    arbiter: clampTimeoutSeconds(source.arbiter, DEFAULT_TARGET_TIMEOUTS.arbiter)
  };
}

function currentTargetTimeoutsSource(task, draft) {
  return normalizeTargetTimeouts(
    draft?.targetTimeouts
    || task?.runtime?.targetTimeouts
    || DEFAULT_TARGET_TIMEOUTS
  );
}

function targetTimeoutSeconds(config, target) {
  const normalized = normalizeTargetTimeouts(config);
  const key = String(target || "").trim();
  if (/^[A-Za-z]$/.test(key)) {
    const workerId = key.toUpperCase();
    return normalized.workers[workerId] || normalized.workerDefault;
  }
  const lowered = key.toLowerCase();
  if (lowered === "direct_baseline") return normalized.directBaseline;
  if (lowered === "commander") return normalized.commander;
  if (lowered === "commander_review") return normalized.commanderReview;
  if (lowered === "summarizer") return normalized.summarizer;
  if (lowered === "answer_now") return normalized.answerNow;
  if (lowered === "arbiter") return normalized.arbiter;
  return normalized.workerDefault;
}

function normalizeFrontMode(value) {
  const raw = String(value || "").trim().toLowerCase();
  return raw === "eval" ? "eval" : "full";
}

function frontModeLabel(value) {
  return normalizeFrontMode(value) === "eval" ? "Eval" : "Full";
}

function contextModeLabel(value) {
  return normalizeContextMode(value) === "full" ? "Full workers" : "Light workers";
}

function normalizeDirectBaselineMode(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (raw === "single" || raw === "both") return raw;
  return "off";
}

function directBaselineModeLabel(value) {
  const normalized = normalizeDirectBaselineMode(value);
  if (normalized === "single") return "Single only";
  if (normalized === "both") return "Both compare";
  return "Off";
}

function shouldShowDirectBaselineFields(mode) {
  return normalizeDirectBaselineMode(mode) !== "off";
}

function syncFrontModeFields() {
  const frontMode = normalizeFrontMode($("#frontMode").val());
  const $directBaseline = $("#directBaselineMode");
  if (!$directBaseline.length) return;
  if (frontMode === "eval") {
    $directBaseline.val("both");
    $directBaseline.prop("disabled", true);
  } else {
    $directBaseline.prop("disabled", false);
  }
}

function syncDirectBaselineFields() {
  syncFrontModeFields();
  const mode = normalizeDirectBaselineMode($("#directBaselineMode").val());
  const visible = shouldShowDirectBaselineFields(mode);
  const workerProvider = normalizeProviderId($("#provider").val());
  const $providerField = $("#directProviderField");
  const $modelField = $("#directModelField");
  const $provider = $("#directProvider");
  const $model = $("#directModel");
  const $hint = $("#directBaselineHint");
  if (!$providerField.length || !$modelField.length || !$provider.length || !$model.length || !$hint.length) return;
  $providerField.prop("hidden", !visible);
  $modelField.prop("hidden", !visible);
  $provider.prop("disabled", !visible);
  $model.prop("disabled", !visible);
  const providerValue = normalizeProviderId($provider.val() || workerProvider);
  const modelValue = normalizeSelectedModelForProvider($model.val() || $("#model").val(), providerValue);
  populateStaticModelSelect("#directModel", modelValue, providerValue);
  $provider.val(providerValue);
  $model.val(modelValue);
  $hint.text(
    visible
      ? (
        mode === "both"
          ? "Runs once in parallel with the pressurized loop and saves a compare-ready artifact in Review."
          : "Runs one direct single-thread answer instead of the pressurized multi-lane loop."
      )
      : "Only used when the single-thread baseline is enabled."
  );
}

function syncOllamaBaseUrlField() {
  const workerProvider = normalizeProviderId($("#provider").val());
  const summarizerProvider = normalizeProviderId($("#summarizerProvider").val() || workerProvider);
  const directMode = normalizeDirectBaselineMode($("#directBaselineMode").val());
  const directProvider = normalizeProviderId($("#directProvider").val() || workerProvider);
  const visible = shouldShowOllamaBaseUrl(workerProvider, summarizerProvider) || (directMode !== "off" && directProvider === "ollama");
  const $field = $("#ollamaBaseUrlField");
  const $input = $("#ollamaBaseUrl");
  const $hint = $("#ollamaBaseUrlHint");
  if (!$field.length || !$input.length || !$hint.length) return;
  $field.prop("hidden", !visible);
  $input.prop("disabled", !visible);
  if (!$input.val().trim()) {
    $input.val(normalizeOllamaBaseUrl(""));
  }
  const roles = [];
  if (workerProvider === "ollama") roles.push("workers");
  if (summarizerProvider === "ollama") roles.push("summarizer");
  if (directMode !== "off" && directProvider === "ollama") roles.push("single-thread baseline");
  $hint.text(
    visible
      ? ("Used by " + roles.join(" and ") + ". Accepts either a host like http://192.168.0.26:11434 or an /api base URL.")
      : "Only used when an Ollama provider is active."
  );
}

function buildWorkerTypeOptions(selectedValue) {
  return WORKER_TYPE_ORDER.map(function (id) {
    const selected = id === selectedValue ? " selected" : "";
    return `<option value="${id}"${selected}>${WORKER_TYPE_CATALOG[id].label}</option>`;
  }).join("");
}

function buildWorkerTemperatureOptions(selectedValue) {
  return WORKER_TEMPERATURE_ORDER.map(function (id) {
    const selected = id === selectedValue ? " selected" : "";
    return `<option value="${id}"${selected}>${WORKER_TEMPERATURE_CATALOG[id].label}</option>`;
  }).join("");
}

function buildHarnessConcisionOptions(selectedValue) {
  return HARNESS_CONCISION_ORDER.map(function (id) {
    const selected = id === selectedValue ? " selected" : "";
    return `<option value="${id}"${selected}>${HARNESS_CONCISION_CATALOG[id].label}</option>`;
  }).join("");
}

function normalizeHarnessConfig(config, fallback = "tight") {
  const source = config && typeof config === "object" ? config : {};
  const concision = HARNESS_CONCISION_CATALOG[source.concision] ? source.concision : fallback;
  return {
    concision,
    instruction: String(source.instruction || "").trim()
  };
}

function harnessConcisionLabel(config, fallback = "tight") {
  const normalized = normalizeHarnessConfig(config, fallback);
  return HARNESS_CONCISION_CATALOG[normalized.concision]?.label || normalized.concision;
}

function normalizeProviderId(provider) {
  const candidate = String(provider || "").trim().toLowerCase();
  return PROVIDER_CATALOG[candidate] ? candidate : "openai";
}

function providerSupportsCustomModel(provider) {
  return normalizeProviderId(provider) !== "openai";
}

function defaultModelForProvider(provider) {
  const normalized = normalizeProviderId(provider);
  return PROVIDER_DEFAULT_MODELS[normalized] || PROVIDER_DEFAULT_MODELS.openai;
}

function providerModelCatalog(provider) {
  const normalized = normalizeProviderId(provider);
  return PROVIDER_MODEL_CATALOG[normalized] || MODEL_CATALOG;
}

function providerModelOrder(provider) {
  return Object.keys(providerModelCatalog(provider));
}

function providerCapabilities(provider) {
  const normalized = normalizeProviderId(provider);
  const raw = PROVIDER_CAPABILITY_CATALOG[normalized] || {};
  return {
    provider: normalized,
    toolLoop: !!raw.toolLoop,
    webSearch: !!raw.webSearch,
    localFiles: !!raw.localFiles,
    githubTools: !!raw.githubTools,
    costTracking: !!raw.costTracking,
    notes: Array.isArray(raw.notes) ? raw.notes.filter(Boolean) : []
  };
}

function providerNoteSummary(provider) {
  const notes = providerCapabilities(provider).notes || [];
  return notes.length ? notes.join(" ") : "No provider note reported.";
}

function normalizeSelectedModelForProvider(modelId, provider) {
  const normalizedProvider = normalizeProviderId(provider);
  const candidate = String(modelId || "").trim();
  const catalog = providerModelCatalog(normalizedProvider);
  if (candidate && catalog[candidate]) {
    return candidate;
  }
  if (candidate && providerSupportsCustomModel(normalizedProvider)) {
    return candidate;
  }
  return defaultModelForProvider(normalizedProvider);
}

function qualityProfileModelConfig(profileId, provider) {
  const normalizedProvider = normalizeProviderId(provider);
  const defaults = {
    low: { workerModel: defaultModelForProvider(normalizedProvider), summarizerModel: defaultModelForProvider(normalizedProvider) },
    mid: { workerModel: defaultModelForProvider(normalizedProvider), summarizerModel: defaultModelForProvider(normalizedProvider) },
    high: { workerModel: defaultModelForProvider(normalizedProvider), summarizerModel: defaultModelForProvider(normalizedProvider) },
    ultra: { workerModel: defaultModelForProvider(normalizedProvider), summarizerModel: defaultModelForProvider(normalizedProvider) }
  };
  const providerModels = {
    openai: {
      low: { workerModel: "gpt-5-mini", summarizerModel: "gpt-5-mini" },
      mid: { workerModel: "gpt-5-mini", summarizerModel: "gpt-5.4-mini" },
      high: { workerModel: "gpt-5.4-mini", summarizerModel: "gpt-5.4" },
      ultra: { workerModel: "gpt-5.4", summarizerModel: "gpt-5.4" }
    },
    anthropic: {
      low: { workerModel: "claude-3-5-haiku-latest", summarizerModel: "claude-3-5-haiku-latest" },
      mid: { workerModel: "claude-3-5-haiku-latest", summarizerModel: "claude-sonnet-4-20250514" },
      high: { workerModel: "claude-sonnet-4-20250514", summarizerModel: "claude-opus-4-20250514" },
      ultra: { workerModel: "claude-sonnet-4-20250514", summarizerModel: "claude-opus-4-1-20250805" }
    },
    xai: {
      low: { workerModel: "grok-4-1-fast-reasoning", summarizerModel: "grok-4-1-fast-reasoning" },
      mid: { workerModel: "grok-4-1-fast-reasoning", summarizerModel: "grok-4.20-reasoning" },
      high: { workerModel: "grok-4.20-reasoning", summarizerModel: "grok-4.20-reasoning" },
      ultra: { workerModel: "grok-4.20-reasoning", summarizerModel: "grok-4.20-multi-agent" }
    },
    minimax: {
      low: { workerModel: "MiniMax-M2.1-highspeed", summarizerModel: "MiniMax-M2.1-highspeed" },
      mid: { workerModel: "MiniMax-M2.1-highspeed", summarizerModel: "MiniMax-M2.5" },
      high: { workerModel: "MiniMax-M2.5", summarizerModel: "MiniMax-M2.7" },
      ultra: { workerModel: "MiniMax-M2.7", summarizerModel: "MiniMax-M2.7" }
    },
    ollama: {
      low: { workerModel: "qwen3", summarizerModel: "qwen3" },
      mid: { workerModel: "qwen3", summarizerModel: "qwen3-coder" },
      high: { workerModel: "qwen3-coder", summarizerModel: "qwen3-coder" },
      ultra: { workerModel: "qwen3-coder", summarizerModel: "qwen3-coder" }
    }
  };
  return (providerModels[normalizedProvider] && providerModels[normalizedProvider][profileId]) || defaults[profileId] || defaults.low;
}

function buildProviderOptions(selectedValue) {
  const selectedProvider = normalizeProviderId(selectedValue);
  return PROVIDER_ORDER.map(function (id) {
    const selected = id === selectedProvider ? " selected" : "";
    return `<option value="${id}"${selected}>${PROVIDER_CATALOG[id].label}</option>`;
  }).join("");
}

function buildModelOptions(selectedValue, provider) {
  const catalog = providerModelCatalog(provider);
  const order = providerModelOrder(provider);
  const options = order.map(function (id) {
    const selected = id === selectedValue ? " selected" : "";
    return `<option value="${id}"${selected}>${catalog[id].label}</option>`;
  });
  if (selectedValue && !catalog[selectedValue]) {
    options.push(`<option value="${selectedValue}" selected>${String(selectedValue)} (custom)</option>`);
  }
  return options.join("");
}

function modelLabel(modelId, provider) {
  const catalog = providerModelCatalog(provider);
  if (catalog[modelId]?.label) return catalog[modelId].label;
  const match = Object.keys(PROVIDER_MODEL_CATALOG).find(function (providerId) {
    return !!PROVIDER_MODEL_CATALOG[providerId]?.[modelId]?.label;
  });
  if (match) return PROVIDER_MODEL_CATALOG[match][modelId].label;
  return String(modelId || "Model");
}

function providerLabel(provider) {
  const normalized = normalizeProviderId(provider);
  return PROVIDER_CATALOG[normalized]?.label || String(provider || "Provider");
}

function providerCapabilitySummary(capabilities) {
  if (!capabilities || typeof capabilities !== "object") {
    return "Capabilities not reported.";
  }
  const bits = [];
  bits.push(capabilities.toolLoop ? "tools on" : "tools off");
  bits.push(capabilities.webSearch ? "web search on" : "web search off");
  bits.push(capabilities.localFiles ? "local files on" : "local files off");
  bits.push(capabilities.githubTools ? "GitHub tools on" : "GitHub tools off");
  bits.push(capabilities.costTracking ? "cost tracked" : "cost local/untracked");
  return bits.join(" | ");
}

function enforceProviderCapabilitySelections(notifyUser = false) {
  const workerProvider = normalizeProviderId($("#provider").val());
  const capabilities = providerCapabilities(workerProvider);
  const disabled = [];

  if (!capabilities.webSearch && $("#researchEnabled").val() === "1") {
    $("#researchEnabled").val("0");
    disabled.push("web search");
  }
  if (!capabilities.localFiles && $("#localFilesEnabled").val() === "1") {
    $("#localFilesEnabled").val("0");
    disabled.push("local files");
  }
  if (!capabilities.githubTools && $("#githubToolsEnabled").val() === "1") {
    $("#githubToolsEnabled").val("0");
    disabled.push("GitHub tools");
  }

  if (!capabilities.webSearch && composerSourceDrawerOpen) {
    composerSourceDrawerOpen = false;
  }

  if (notifyUser && disabled.length) {
    showMessage(
      providerLabel(workerProvider) + " disables " + disabled.join(", ") + " in this runtime. " + providerNoteSummary(workerProvider),
      false
    );
  }

  return {
    provider: workerProvider,
    capabilities,
    disabled
  };
}

function buildArtifactOptions(artifacts, selectedValue) {
  const options = [`<option value="">Select artifact</option>`];
  (artifacts || []).forEach(function (artifact) {
    const selected = artifact.name === selectedValue ? " selected" : "";
    const kind = artifact.kind || "artifact";
    options.push(`<option value="${artifact.name}"${selected}>${artifact.name} [${kind}]</option>`);
  });
  return options.join("");
}

function pickArtifact(artifacts, preferredKinds, excludeName) {
  const list = artifacts || [];
  const preferred = list.find(function (artifact) {
    return (!excludeName || artifact.name !== excludeName) && preferredKinds.includes(artifact.kind);
  });
  if (preferred) return preferred;
  return list.find(function (artifact) {
    return !excludeName || artifact.name !== excludeName;
  }) || null;
}

function formatInteger(value) {
  return Number(value || 0).toLocaleString();
}

function nextAvailableWorkerType(task, draft) {
  const workers = stagedWorkerSource(draft, task);
  const usedIds = new Set((workers || []).map(function (worker) {
    return String(worker?.id || "").trim().toUpperCase();
  }));
  const slotIndex = WORKER_SLOT_IDS.findIndex(function (workerId) {
    return !usedIds.has(workerId);
  });
  if (slotIndex >= 0 && WORKER_TYPE_ORDER[slotIndex]) {
    return WORKER_TYPE_ORDER[slotIndex];
  }
  return WORKER_TYPE_ORDER[WORKER_TYPE_ORDER.length - 1] || "wildcard";
}

function renderAddWorkerTypeControl(task, draft, loop) {
  const $select = $("#addWorkerType");
  const $remove = $("#removeAdversarial");
  if (!$select.length) return;

  const workers = stagedWorkerSource(draft, task);
  const isActive = isWorkspaceBusy(loop, latestState);
  const suggestedType = nextAvailableWorkerType(task, draft);
  const preferredSelection = String($select.data("selectedType") || $select.val() || "").trim();
  const selectedValue = WORKER_TYPE_CATALOG[preferredSelection] ? preferredSelection : suggestedType;

  $select.html(WORKER_TYPE_ORDER.map(function (typeId) {
    const selected = typeId === selectedValue ? " selected" : "";
    const suffix = typeId === suggestedType ? " (Suggested)" : "";
    return `<option value="${typeId}"${selected}>${WORKER_TYPE_CATALOG[typeId].label}${suffix}</option>`;
  }).join(""));
  $select.val(selectedValue);
  $select.data("selectedType", selectedValue);
  $select.prop("disabled", isActive || workers.length >= WORKER_SLOT_IDS.length);
  if ($remove.length) {
    const canRemove = workers.length > 2;
    $remove.prop("hidden", !canRemove);
    $remove.prop("disabled", isActive || !canRemove);
  }
}

function artifactOutputCapParts(artifact) {
  const requested = Number(artifact?.requestedMaxOutputTokens || 0);
  const effective = Number(artifact?.effectiveMaxOutputTokens || 0);
  const attempts = Array.isArray(artifact?.maxOutputTokenAttempts)
    ? artifact.maxOutputTokenAttempts.map(function (value) { return Number(value || 0); }).filter(Boolean)
    : [];
  const parts = [];

  if (requested > 0 || effective > 0) {
    parts.push("cap " + (requested > 0 ? formatInteger(requested) : "n/a") + " -> " + (effective > 0 ? formatInteger(effective) : "n/a"));
  }
  if (attempts.length) {
    parts.push("attempts " + attempts.map(formatInteger).join(" -> "));
  }
  if (artifact?.recoveredFromIncomplete) {
    parts.push("recovered after max_output_tokens");
  }
  if (artifact?.rawOutputAvailable) {
    parts.push("raw text saved for review");
  }

  return parts;
}

function artifactOutputCapSummary(artifact) {
  const parts = artifactOutputCapParts(artifact);
  return parts.length ? parts.join(" | ") : "cap not recorded";
}

function executionHealthTone(health) {
  if (!health || !health.degraded) return "clean";
  if (Number(health.fallbackCount || 0) > 0) return "warning";
  if (Number(health.recoveredCount || 0) > 0) return "recovered";
  return "warning";
}

function renderExecutionHealthBadge(health, fallbackText = "Clean") {
  const tone = executionHealthTone(health);
  const text = !health || !health.degraded
    ? fallbackText
    : (Number(health.fallbackCount || 0) > 0
      ? "Fallback"
      : (Number(health.recoveredCount || 0) > 0 ? "Recovered" : "Warning"));
  return `<span class="execution-health-badge ${escapeHtml(tone)}">${escapeHtml(text)}</span>`;
}

function formatExecutionHealthSummary(health) {
  if (!health || typeof health !== "object") {
    return "Execution status unavailable.";
  }
  if (!health.degraded) {
    return "All captured stages completed without recorded degradation.";
  }
  const bits = [];
  if (Number(health.fallbackCount || 0) > 0) {
    bits.push(formatInteger(health.fallbackCount || 0) + " mock fallback" + (Number(health.fallbackCount || 0) === 1 ? "" : "s"));
  }
  if (Number(health.recoveredCount || 0) > 0) {
    bits.push(formatInteger(health.recoveredCount || 0) + " recovered live stage" + (Number(health.recoveredCount || 0) === 1 ? "" : "s"));
  }
  if (!bits.length && health.degraded) {
    bits.push("Contract warning or malformed runtime metadata detected.");
  }
  const latestIssue = health.latestIssue || null;
  if (latestIssue?.label) {
    bits.push("latest issue: " + latestIssue.label);
  }
  return bits.length ? bits.join(" | ") : "Degraded execution was recorded for this round.";
}

function artifactExecutionHealth(artifact) {
  const mode = String(artifact?.mode || "").trim();
  const recovered = !!artifact?.recoveredFromIncomplete;
  const contractWarnings = Array.isArray(artifact?.contractWarnings) ? artifact.contractWarnings.filter(Boolean) : [];
  const degraded = mode === "mock" || recovered || contractWarnings.length > 0;
  return {
    degraded,
    mode,
    fallbackCount: mode === "mock" ? 1 : 0,
    recoveredCount: recovered ? 1 : 0,
    contractWarningCount: contractWarnings.length
  };
}

function renderArtifactExecutionBadge(artifact) {
  const health = artifactExecutionHealth(artifact);
  if (!health.degraded) {
    return renderExecutionHealthBadge(null, "Live");
  }
  return renderExecutionHealthBadge(health, "Live");
}

function jobExecutionHealthTone(health) {
  const tone = String(health?.tone || "").trim().toLowerCase();
  if (["active", "error", "warning", "recovered", "clean"].includes(tone)) {
    return tone;
  }
  return "clean";
}

function renderJobExecutionBadge(health) {
  const tone = jobExecutionHealthTone(health);
  const label = String(health?.label || (tone === "active" ? "Running" : "Clean")).trim() || "Clean";
  return `<span class="execution-health-badge ${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
}

function formatJobExecutionSummary(health) {
  const summary = String(health?.summary || "").trim();
  if (summary) return summary;
  const tone = jobExecutionHealthTone(health);
  if (tone === "active") return "Background work is currently in flight.";
  if (tone === "error") return "This job ended in an explicit failure state.";
  if (tone === "warning") return "This job completed with a warning condition.";
  if (tone === "recovered") return "This job completed through a partial or recovered path.";
  return "Completed without recorded degradation.";
}

function renderArtifactMeta(data) {
  const summary = data?.summary || {};
  const localToolCalls = Array.isArray(summary.localToolCalls) ? summary.localToolCalls : [];
  const localFileSources = Array.isArray(summary.localFileSources) ? summary.localFileSources : [];
  const githubToolCalls = Array.isArray(summary.githubToolCalls) ? summary.githubToolCalls : [];
  const githubSources = Array.isArray(summary.githubSources) ? summary.githubSources : [];
  const activeSkills = Array.isArray(summary.skills) ? summary.skills.filter(Boolean) : [];
  const contractWarnings = Array.isArray(summary.contractWarnings) ? summary.contractWarnings.filter(Boolean) : [];
  const providerTraceLines = providerTraceSummaryLines(summary.providerTrace);
  const provider = summary.provider || "openai";
  const capabilitySummary = providerCapabilitySummary(summary.providerCapabilities);
  const bits = [
    data?.name || "artifact",
    "kind: " + (data?.kind || "artifact") + " | storage: " + (data?.storage || "unknown"),
    "modified: " + (data?.modifiedAt || "n/a") + " | bytes: " + (data?.size ?? 0),
    "task: " + (summary.taskId || "n/a") + " | target: " + (summary.target || "n/a"),
    "mode: " + (summary.mode || "n/a") + " | provider: " + providerLabel(provider) + " | model: " + modelLabel(summary.model || "n/a", provider),
    "provider capabilities: " + capabilitySummary,
    "skills: " + (activeSkills.length ? activeSkills.join(", ") : "none"),
    "step: " + (summary.step ?? "-") + " | round: " + (summary.round ?? "-"),
    "responseId: " + (summary.responseId || "none"),
    "output cap: " + artifactOutputCapSummary(summary),
    "local tools: " + (localToolCalls.length ? localToolCalls.length + " call" + (localToolCalls.length === 1 ? "" : "s") : "none")
      + " | local sources: " + (localFileSources.length ? localFileSources.length : 0),
    "GitHub tools: " + (githubToolCalls.length ? githubToolCalls.length + " call" + (githubToolCalls.length === 1 ? "" : "s") : "none")
      + " | GitHub sources: " + (githubSources.length ? githubSources.length : 0),
    "provider trace: " + (providerTraceLines.length ? providerTraceLines[0] : "none"),
    providerTraceLines.length > 1 ? "provider trace detail: " + providerTraceLines.slice(1).join(" | ") : "",
    "contract warnings: " + (contractWarnings.length ? contractWarnings.length + " | " + contractWarnings.join(" | ") : "none"),
    "raw output policy: " + (data?.policy?.reviewSurface || "review_only") + " | public thread: " + (data?.policy?.publicThread || "structured_only")
  ].filter(Boolean);
  return bits.join("\n");
}

function renderArtifactContent(data) {
  const content = data?.content || {};
  const summary = data?.summary || {};
  const sections = [];

  if (Object.prototype.hasOwnProperty.call(content, "output")) {
    sections.push("Canonical Structured Output\n" + pretty(content.output));
  } else {
    sections.push("Artifact Content\n" + pretty(content));
  }

  const providerTraceLines = providerTraceSummaryLines(summary.providerTrace);
  if (providerTraceLines.length) {
    sections.push("Provider Trace\n" + providerTraceLines.join("\n"));
  }

  if (content.rawOutputText) {
    sections.push("Review-Only Raw Output\nThis raw text is kept for auditability and replay. The structured output above remains the canonical source of truth.\n\n" + content.rawOutputText);
  }

  return sections.join("\n\n");
}

function evalArtifactCacheKey(runId, artifactId) {
  return String(runId || "").trim() + "::" + String(artifactId || "").trim();
}

function getCachedEvalArtifact(runId, artifactId) {
  return evalArtifactContentCache[evalArtifactCacheKey(runId, artifactId)] || null;
}

function rerenderSelectedEvalRunDetail() {
  if (latestEvalHistory?.selectedRun) {
    $("#evalRunDetail").html(renderEvalRunDetail(latestEvalHistory.selectedRun));
  }
}

function queueEvalArtifactFetch(runId, artifactId) {
  const normalizedRunId = String(runId || "").trim();
  const normalizedArtifactId = String(artifactId || "").trim();
  if (!normalizedRunId || !normalizedArtifactId) return;
  const cacheKey = evalArtifactCacheKey(normalizedRunId, normalizedArtifactId);
  if (evalArtifactContentCache[cacheKey] || evalArtifactRequestState[cacheKey]) return;
  evalArtifactRequestState[cacheKey] = true;
  $.getJSON(apiRoute(API.evalArtifact), { runId: normalizedRunId, artifactId: normalizedArtifactId })
    .done(function (data) {
      evalArtifactContentCache[cacheKey] = data || null;
      if (selectedEvalRunId === normalizedRunId) {
        rerenderSelectedEvalRunDetail();
      }
    })
    .always(function () {
      delete evalArtifactRequestState[cacheKey];
    });
}

function evalUsageForTarget(usage, targetId) {
  const byTarget = usage?.byTarget;
  if (!byTarget || typeof byTarget !== "object") return null;
  return byTarget[targetId] && typeof byTarget[targetId] === "object" ? byTarget[targetId] : null;
}

function normalizeEvalAnswerEntry(payload, fallbackLabel, provider, model, mode, usage) {
  if (!payload || typeof payload !== "object") return null;
  const answer = String(payload.answer || "").trim();
  if (!answer) return null;
  return {
    label: String(fallbackLabel || "Answer").trim() || "Answer",
    answer,
    stance: String(payload.stance || "").trim(),
    confidenceNote: String(payload.confidenceNote || "").trim(),
    provider: provider || "",
    model: model || "",
    mode: mode || "",
    usage: usage || null
  };
}

function extractEvalPrimaryAnswer(data) {
  const content = data?.content || {};
  const output = content?.output || {};
  const frontAnswer = output?.frontAnswer || content?.frontAnswer || {};
  const answer = output?.answer || content?.answer || {};
  const provider = String(content?.provider || content?.primaryTelemetry?.provider || data?.summary?.provider || "").trim();
  const model = String(content?.model || content?.primaryTelemetry?.model || data?.summary?.model || "").trim();
  const mode = String(content?.mode || data?.summary?.mode || "").trim();
  return (
    normalizeEvalAnswerEntry(frontAnswer, "Pressurized answer", provider, model, mode, output?.responseMeta?.usageDelta || content?.usage || null)
    || normalizeEvalAnswerEntry(answer, "Single-thread baseline", provider, model, mode, output?.responseMeta?.usageDelta || content?.usage || null)
    || (typeof content?.primaryAnswer === "string"
      ? normalizeEvalAnswerEntry(
        {
          answer: content.primaryAnswer,
          stance: content?.primaryQuality?.verdict || "",
          confidenceNote: content?.primaryAnswerHealth?.verdict || ""
        },
        "Pressurized answer",
        provider,
        model,
        mode,
        null
      )
      : null)
    || normalizeEvalAnswerEntry(
      {
        answer: content?.publicAnswer || "",
        stance: content?.summary?.frontAnswer?.stance || "",
        confidenceNote: content?.summary?.frontAnswer?.confidenceNote || content?.quality?.rationale || ""
      },
      "Result answer",
      provider,
      model,
      mode,
      content?.usage || null
    )
  );
}

function extractEvalBaselineAnswer(data) {
  const content = data?.content || {};
  const directBaseline = content?.directBaseline || {};
  const baselineAnswer = directBaseline?.answer || content?.baselineAnswer || content?.directAnswer || {};
  const provider = String(directBaseline?.provider || content?.baselineTelemetry?.provider || content?.provider || data?.summary?.provider || "").trim();
  const model = String(directBaseline?.model || content?.baselineTelemetry?.model || content?.model || data?.summary?.model || "").trim();
  const mode = String(directBaseline?.mode || content?.mode || data?.summary?.mode || "").trim();
  if (typeof baselineAnswer === "string") {
    return normalizeEvalAnswerEntry(
      {
        answer: baselineAnswer,
        stance: content?.baselineQuality?.verdict || "",
        confidenceNote: content?.baselineAnswerHealth?.verdict || ""
      },
      "Single-thread baseline",
      provider,
      model,
      mode,
      directBaseline?.usage || null
    );
  }
  return normalizeEvalAnswerEntry(
    baselineAnswer,
    "Single-thread baseline",
    provider,
    model,
    mode,
    directBaseline?.usage || null
  );
}

function renderEvalMetricStrip(metrics) {
  const items = (metrics || []).filter(function (entry) {
    return String(entry?.value || "").trim();
  });
  if (!items.length) return "";
  return `
    <div class="eval-metric-strip">
      ${items.map(function (entry) {
        return `
          <div class="eval-metric-chip">
            <span class="eval-metric-chip-label">${escapeHtml(entry.label || "Metric")}</span>
            <strong>${escapeHtml(String(entry.value || ""))}</strong>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderEvalAnswerCard(entry, tone) {
  const normalized = entry || { label: "Answer", answer: "" };
  if (!String(normalized.answer || "").trim()) {
    return `
      <article class="eval-answer-card${tone ? " " + tone : ""}">
        <div class="eval-answer-card-kicker">${escapeHtml(normalized.label || "Answer")}</div>
        <div class="review-empty small">${escapeHtml(normalized.emptyMessage || "No answer captured yet.")}</div>
      </article>
    `;
  }
  const metaBits = [
    normalized.stance ? "Stance " + normalized.stance : "",
    normalized.provider ? providerLabel(normalized.provider) : "",
    normalized.model ? modelLabel(normalized.model, normalized.provider || "openai") : "",
    normalized.mode ? "Mode " + normalized.mode : "",
    normalized.usage?.totalTokens ? "Tokens " + formatInteger(normalized.usage.totalTokens) : "",
    normalized.usage?.estimatedCostUsd != null ? "Spend " + formatUsd(normalized.usage.estimatedCostUsd || 0) : ""
  ].filter(Boolean);
  return `
    <article class="eval-answer-card${tone ? " " + tone : ""}">
      <div class="eval-answer-card-kicker">${escapeHtml(normalized.label || "Answer")}</div>
      <div class="eval-answer-card-body">${escapeHtml(String(normalized.answer || "").trim())}</div>
      ${normalized.confidenceNote ? `<div class="eval-answer-card-note">${escapeHtml(normalized.confidenceNote)}</div>` : ""}
      ${metaBits.length ? `<div class="eval-answer-card-meta">${escapeHtml(metaBits.join(" | "))}</div>` : ""}
    </article>
  `;
}

function renderEvalAnswerCompare(pressurizedEntry, baselineEntry, comparison) {
  const verdictBits = [];
  if (comparison?.verdict) verdictBits.push("Verdict " + String(comparison.verdict || ""));
  if (comparison?.scoreDelta?.overallQuality != null) verdictBits.push("Delta " + Number(comparison.scoreDelta.overallQuality || 0).toFixed(1));
  if (comparison?.baselineQuality?.scores?.overallQuality != null) verdictBits.push("Baseline quality " + Number(comparison.baselineQuality.scores.overallQuality || 0).toFixed(1));
  if (comparison?.scores?.overallDifferentiation != null) verdictBits.push("Diff " + Number(comparison.scores.overallDifferentiation || 0).toFixed(1));
  if (comparison?.similarity?.sequenceSimilarity != null) verdictBits.push("Seq " + Number(comparison.similarity.sequenceSimilarity || 0).toFixed(2));
  if (comparison?.materialDifference === false) verdictBits.push("Near duplicate");
  return `
    <section class="eval-visual-section">
      <div class="eval-section-head">
        <div class="eval-section-title">Final answer compare</div>
        ${verdictBits.length ? `<div class="eval-section-meta">${escapeHtml(verdictBits.join(" | "))}</div>` : ""}
      </div>
      <div class="eval-answer-compare-grid">
        ${renderEvalAnswerCard(pressurizedEntry || { label: "Pressurized answer", answer: "" }, "primary")}
        ${renderEvalAnswerCard(baselineEntry || { label: "Single-thread baseline", answer: "" }, "secondary")}
      </div>
    </section>
  `;
}

function evalAnswerMetaBits(entry) {
  if (!entry || typeof entry !== "object") return [];
  return [
    entry.stance ? "Stance " + entry.stance : "",
    entry.provider ? providerLabel(entry.provider) : "",
    entry.model ? modelLabel(entry.model, entry.provider || "openai") : "",
    entry.mode ? "Mode " + entry.mode : "",
    entry.usage?.totalTokens ? "Tokens " + formatInteger(entry.usage.totalTokens) : "",
    entry.usage?.estimatedCostUsd != null ? "Spend " + formatUsd(entry.usage.estimatedCostUsd || 0) : ""
  ].filter(Boolean);
}

function renderEvalCompareToggle(pressurizedEntry, baselineEntry, comparison) {
  const summaryBits = [];
  if (comparison?.verdict) summaryBits.push(String(comparison.verdict || ""));
  if (comparison?.scoreDelta?.overallQuality != null) summaryBits.push("delta " + Number(comparison.scoreDelta.overallQuality || 0).toFixed(1));
  if (comparison?.scores?.overallDifferentiation != null) summaryBits.push("diff " + Number(comparison.scores.overallDifferentiation || 0).toFixed(1));
  if (comparison?.materialDifference === false) summaryBits.push("near duplicate");
  return `
    <details class="eval-compare-toggle">
      <summary class="eval-compare-toggle-summary">
        <div>
          <div class="eval-section-title">Technical compare</div>
          ${summaryBits.length ? `<div class="eval-section-meta">${escapeHtml(summaryBits.join(" | "))}</div>` : ""}
        </div>
        <span class="eval-compare-toggle-caret" aria-hidden="true">v</span>
      </summary>
      <div class="eval-compare-toggle-body">
        ${renderEvalAnswerCompare(pressurizedEntry, baselineEntry, comparison)}
      </div>
    </details>
  `;
}

function renderEvalChatColumn(label, answerEntry, objective, tone) {
  const metaBits = evalAnswerMetaBits(answerEntry);
  const answerText = String(answerEntry?.answer || "").trim();
  return `
    <article class="eval-chat-column${tone ? " " + tone : ""}">
      <div class="eval-chat-column-head">
        <div class="eval-chat-column-title">${escapeHtml(label)}</div>
        ${metaBits.length ? `<div class="eval-chat-column-meta">${escapeHtml(metaBits.join(" | "))}</div>` : ""}
      </div>
      <div class="eval-chat-turn user">
        <div class="eval-chat-turn-kicker">User</div>
        <div class="eval-chat-turn-body">${escapeHtml(String(objective || "").trim() || "Waiting for case objective...")}</div>
      </div>
      <div class="eval-chat-turn assistant">
        <div class="eval-chat-turn-kicker">Assistant</div>
        <div class="eval-chat-turn-body">${escapeHtml(answerText || String(answerEntry?.emptyMessage || "Waiting for answer output..."))}</div>
      </div>
      ${answerEntry?.confidenceNote ? `<div class="eval-chat-turn-note">${escapeHtml(answerEntry.confidenceNote)}</div>` : ""}
    </article>
  `;
}

function renderEvalChatCompare(pressurizedEntry, baselineEntry, objective, comparison) {
  const headerBits = [];
  if (comparison?.verdict) headerBits.push("Judge " + String(comparison.verdict || ""));
  if (comparison?.decisionRelation) headerBits.push("Relation " + String(comparison.decisionRelation || ""));
  if (comparison?.scores?.overallDifferentiation != null) headerBits.push("Diff " + Number(comparison.scores.overallDifferentiation || 0).toFixed(1));
  return `
    <section class="eval-visual-section">
      <div class="eval-section-head">
        <div class="eval-section-title">User view compare</div>
        ${headerBits.length ? `<div class="eval-section-meta">${escapeHtml(headerBits.join(" | "))}</div>` : ""}
      </div>
      <div class="eval-chat-compare-grid">
        ${renderEvalChatColumn("Pressurized path", pressurizedEntry, objective, "primary")}
        ${renderEvalChatColumn("Single-thread path", baselineEntry, objective, "secondary")}
      </div>
    </section>
  `;
}

function renderEvalArtifactTrail(replicate) {
  const artifacts = Array.isArray(replicate?.artifacts) ? replicate.artifacts : [];
  if (!artifacts.length) return "";
  const items = artifacts
    .slice()
    .sort(function (left, right) {
      return String(left?.kind || "").localeCompare(String(right?.kind || "")) || String(left?.name || "").localeCompare(String(right?.name || ""));
    })
    .map(function (artifact) {
      const summary = artifact?.summary || {};
      const parts = [
        summary?.target ? String(summary.target).replace(/_/g, " ") : "",
        artifact?.kind ? String(artifact.kind).replace(/_/g, " ") : "",
        summary?.round ? "round " + Number(summary.round || 0) : "",
        summary?.step ? "step " + Number(summary.step || 0) : "",
        summary?.model ? modelLabel(summary.model, summary.provider || "openai") : "",
        artifact?.name ? String(artifact.name) : ""
      ].filter(Boolean);
      return parts.join(" | ");
    });
  return renderListSection("Checkpoint trail", items);
}

function renderEvalHistoricalSummary(replicate, comparison, pressurizedEntry, baselineEntry) {
  const lines = [
    "Pressurized quality " + Number(replicate?.quality?.scores?.overallQuality || 0).toFixed(1)
      + " | health " + Number(replicate?.answerHealth?.scores?.overallHealth || 0).toFixed(1)
      + (replicate?.control?.scores?.overallControl != null ? " | control " + Number(replicate.control.scores.overallControl || 0).toFixed(1) : ""),
    baselineEntry?.answer
      ? (
        "Single-thread quality " + Number(replicate?.baselineQuality?.scores?.overallQuality || 0).toFixed(1)
        + " | health " + Number(replicate?.baselineAnswerHealth?.scores?.overallHealth || 0).toFixed(1)
      )
      : "",
    comparison
      ? (
        "Difference " + String(comparison.verdict || "mixed")
        + " | delta " + Number(comparison?.scoreDelta?.overallQuality || 0).toFixed(1)
        + " | relation " + String(comparison?.decisionRelation || "n/a")
        + " | similarity " + Number(comparison?.similarity?.sequenceSimilarity || 0).toFixed(2)
      )
      : "",
    "Deterministic " + Number(replicate?.deterministic?.passedCount || 0) + "/" + Number(replicate?.deterministic?.totalCount || 0)
      + " | Tokens " + formatInteger(replicate?.usage?.totalTokens || 0)
      + " | Spend " + formatUsd(replicate?.usage?.estimatedCostUsd || 0)
  ].filter(Boolean);
  const sections = [
    renderListSection("Historical summary", lines),
    renderTextSection("Judge rationale", comparison?.rationale || ""),
    renderTextSection("Pressurized edge", comparison?.primaryEdge || ""),
    renderTextSection("Single-thread edge", comparison?.baselineEdge || ""),
    renderEvalArtifactTrail(replicate)
  ].filter(Boolean);
  if (!sections.length) return "";
  return `
    <section class="eval-visual-section">
      <div class="eval-section-head">
        <div class="eval-section-title">Verification history</div>
      </div>
      <div class="eval-history-stack">
        ${sections.map(function (section) {
          return `<div class="eval-history-item">${section}</div>`;
        }).join("")}
      </div>
    </section>
  `;
}

function renderEvalCheckpointVisual(checkpoint, label) {
  if (!checkpoint || typeof checkpoint !== "object") return "";
  const sections = [
    renderTextSection(label || "Checkpoint", checkpoint.observation || checkpoint.requestToPeer || checkpoint.answerDraft || ""),
    renderListSection("Benefits", (checkpoint.benefits || []).slice(0, 4)),
    renderListSection("Detriments", (checkpoint.detriments || []).slice(0, 4)),
    renderListSection("Required circumstances", (checkpoint.requiredCircumstances || []).slice(0, 4)),
    renderListSection("Invalidating circumstances", (checkpoint.invalidatingCircumstances || []).slice(0, 4)),
    renderTextSection("Request to peers", checkpoint.requestToPeer || ""),
    renderTextSection("Lead direction", checkpoint.leadDirection || checkpoint.stance || ""),
    renderTextSection("Why this direction", checkpoint.whyThisDirection || checkpoint.courseDecisionReason || "")
  ].filter(Boolean);
  if (!sections.length) return "";
  return `
    <section class="eval-visual-section">
      <div class="eval-section-head">
        <div class="eval-section-title">${escapeHtml(label || "Checkpoint")}</div>
      </div>
      ${sections.join("")}
    </section>
  `;
}

function renderEvalScoreVisual(content) {
  const quality = content?.quality?.scores || {};
  const health = content?.answerHealth?.scores || {};
  const control = content?.control?.scores || {};
  const deterministicChecks = content?.deterministic?.checks || {};
  const failedChecks = Object.keys(deterministicChecks).filter(function (key) {
    return deterministicChecks[key] && deterministicChecks[key].passed === false;
  }).map(function (key) {
    const detail = String(deterministicChecks[key]?.detail || "").trim();
    return key + (detail ? ": " + detail : "");
  });
  const metrics = [
    { label: "Quality", value: Object.keys(quality).length ? Number(quality.overallQuality || 0).toFixed(1) : "" },
    { label: "Health", value: Object.keys(health).length ? Number(health.overallHealth || 0).toFixed(1) : "" },
    { label: "Control", value: Object.keys(control).length ? Number(control.overallControl || 0).toFixed(1) : "" },
    { label: "Checks", value: String((content?.deterministic?.passedCount || 0)) + "/" + String(content?.deterministic?.totalCount || 0) },
    { label: "Tokens", value: formatInteger(content?.usage?.totalTokens || 0) },
    { label: "Spend", value: formatUsd(content?.usage?.estimatedCostUsd || 0) }
  ];
  const sections = [
    renderEvalMetricStrip(metrics),
    renderTextSection("Quality verdict", content?.quality?.verdict || ""),
    renderTextSection("Quality rationale", content?.quality?.rationale || ""),
    renderTextSection("Answer health verdict", content?.answerHealth?.verdict || ""),
    renderTextSection("Answer health rationale", content?.answerHealth?.rationale || ""),
    renderTextSection("Control verdict", content?.control?.verdict || ""),
    renderTextSection("Control rationale", content?.control?.rationale || ""),
    renderListSection("Failed deterministic checks", failedChecks)
  ].filter(Boolean);
  if (!sections.length) return "";
  return `
    <section class="eval-visual-section">
      <div class="eval-section-head">
        <div class="eval-section-title">Score overview</div>
      </div>
      ${sections.join("")}
    </section>
  `;
}

function renderEvalComparisonVisual(content) {
  const scores = content?.scores || content?.comparison?.scores || {};
  const similarity = content?.similarity || content?.comparison?.similarity || {};
  const metrics = [
    { label: "Diff", value: Object.keys(scores).length ? Number(scores.overallDifferentiation || 0).toFixed(1) : "" },
    { label: "Decision", value: Object.keys(scores).length ? Number(scores.decisionShift || 0).toFixed(1) : "" },
    { label: "Validate", value: Object.keys(scores).length ? Number(scores.validationStrength || 0).toFixed(1) : "" },
    { label: "Separation", value: Object.keys(scores).length ? Number(scores.operationalSeparation || 0).toFixed(1) : "" }
  ];
  const similarityBits = [
    similarity.sequenceSimilarity != null ? "Sequence " + Number(similarity.sequenceSimilarity || 0).toFixed(2) : "",
    similarity.tokenOverlap != null ? "Token overlap " + Number(similarity.tokenOverlap || 0).toFixed(2) : "",
    similarity.sharedOpening != null ? "Shared opening " + (similarity.sharedOpening ? "yes" : "no") : ""
  ].filter(Boolean);
  const sections = [
    renderEvalMetricStrip(metrics),
    renderTextSection("Decision relation", content?.decisionRelation || content?.comparison?.decisionRelation || ""),
    renderTextSection("Pressurized edge", content?.primaryEdge || content?.comparison?.primaryEdge || ""),
    renderTextSection("Baseline edge", content?.baselineEdge || content?.comparison?.baselineEdge || ""),
    renderTextSection("Similarity snapshot", similarityBits.join(" | ")),
    renderTextSection("Comparison rationale", content?.rationale || content?.comparison?.rationale || "")
  ].filter(Boolean);
  if (!sections.length) return "";
  return `
    <section class="eval-visual-section">
      <div class="eval-section-head">
        <div class="eval-section-title">Difference validation</div>
        ${(content?.verdict || content?.comparison?.verdict) ? `<div class="eval-section-meta">${escapeHtml(String(content?.verdict || content?.comparison?.verdict || ""))}</div>` : ""}
      </div>
      ${sections.join("")}
    </section>
  `;
}

function renderEvalArtifactVisual(data) {
  const content = data?.content || {};
  const output = content?.output || {};
  const kind = String(data?.kind || content?.artifactType || "").trim().toLowerCase();
  const primaryAnswer = extractEvalPrimaryAnswer(data);
  const baselineAnswer = extractEvalBaselineAnswer(data);
  const blocks = [];

  if (primaryAnswer && baselineAnswer) {
    blocks.push(renderEvalAnswerCompare(primaryAnswer, baselineAnswer, content?.comparison || null));
  } else if (primaryAnswer) {
    blocks.push(`
      <section class="eval-visual-section">
        <div class="eval-section-head">
          <div class="eval-section-title">${escapeHtml(primaryAnswer.label || "Answer")}</div>
        </div>
        ${renderEvalAnswerCard(primaryAnswer, "primary")}
      </section>
    `);
  }

  if (kind === "score" || content?.quality || content?.control || content?.deterministic) {
    blocks.push(renderEvalScoreVisual(content));
  }

  if (kind === "comparison" || content?.comparison || content?.scores?.overallDifferentiation != null) {
    blocks.push(renderEvalComparisonVisual(content));
  }

  if (kind === "worker_output" || kind === "worker_step" || output?.workerId || content?.workerId) {
    blocks.push(renderEvalCheckpointVisual(output?.workerId ? output : content?.output || content, "Worker checkpoint"));
  } else if (kind === "summary_output" || output?.frontAnswer) {
    blocks.push(renderEvalCheckpointVisual(output, "Pressurized summary"));
  } else if (kind === "summary_round" || kind === "commander_review_output" || kind === "commander_output") {
    blocks.push(renderEvalCheckpointVisual(output || content, "Checkpoint digest"));
  }

  if (!blocks.length) {
    const fallbackSections = [
      renderTextSection("Artifact kind", kind || "artifact"),
      renderTextSection("Quick summary", truncateText(pretty(content), 900))
    ].filter(Boolean);
    if (fallbackSections.length) {
      blocks.push(`<section class="eval-visual-section">${fallbackSections.join("")}</section>`);
    }
  }

  return blocks.length
    ? `<div class="eval-artifact-visual-stack">${blocks.join("")}</div>`
    : `<div class="review-empty">No visual summary available for this artifact yet.</div>`;
}

function setArtifactPane(side, metaText, contentText) {
  $("#artifact" + side + "Meta").text(metaText);
  $("#artifact" + side + "Content").text(contentText);
}

function loadArtifactPane(side, artifactName) {
  if (!artifactName) {
    setArtifactPane(side, "No artifact selected.", "No artifact selected.");
    return;
  }

  $.getJSON(apiRoute(API.artifact), { name: artifactName })
    .done(function (data) {
      if (artifactSelections[side.toLowerCase()] !== artifactName) return;
      setArtifactPane(side, renderArtifactMeta(data), renderArtifactContent(data));
    })
    .fail(function (xhr) {
      setArtifactPane(side, "Artifact load failed.", xhr.responseText || "Artifact load failed.");
    });
}

function syncArtifactReview(artifacts) {
  const list = artifacts || [];
  const names = new Set(list.map(function (artifact) { return artifact.name; }));

  if (!artifactSelections.left || !names.has(artifactSelections.left)) {
    const leftDefault = pickArtifact(list, ["summary_output", "direct_baseline_output", "commander_review_output", "commander_output", "summary_round", "commander_review_round", "commander_round", "worker_output", "worker_step"], "");
    artifactSelections.left = leftDefault ? leftDefault.name : "";
  }

  if (!artifactSelections.right || !names.has(artifactSelections.right) || artifactSelections.right === artifactSelections.left) {
    const rightDefault = pickArtifact(list, ["direct_baseline_output", "commander_review_output", "commander_output", "worker_output", "worker_step", "summary_output", "commander_review_round", "commander_round", "summary_round"], artifactSelections.left);
    artifactSelections.right = rightDefault ? rightDefault.name : "";
  }

  $("#artifactLeftSelect").html(buildArtifactOptions(list, artifactSelections.left));
  $("#artifactRightSelect").html(buildArtifactOptions(list, artifactSelections.right));

  loadArtifactPane("Left", artifactSelections.left);
  loadArtifactPane("Right", artifactSelections.right);
}

function populateStaticProviderSelect(selector, selectedValue) {
  $(selector).html(buildProviderOptions(selectedValue));
}

function populateStaticModelSelect(selector, selectedValue, provider) {
  $(selector).html(buildModelOptions(selectedValue, provider));
}

function refreshProviderModelSelects() {
  const workerProvider = normalizeProviderId($("#provider").val());
  const summarizerProvider = normalizeProviderId($("#summarizerProvider").val() || workerProvider);
  const directProvider = normalizeProviderId($("#directProvider").val() || workerProvider);
  const workerModel = normalizeSelectedModelForProvider($("#model").val(), workerProvider);
  const summarizerModel = normalizeSelectedModelForProvider($("#summarizerModel").val(), summarizerProvider);
  const directModel = normalizeSelectedModelForProvider($("#directModel").val() || $("#model").val(), directProvider);
  populateStaticModelSelect("#model", workerModel, workerProvider);
  populateStaticModelSelect("#summarizerModel", summarizerModel, summarizerProvider);
  populateStaticModelSelect("#directModel", directModel, directProvider);
  $("#model").val(workerModel);
  $("#summarizerModel").val(summarizerModel);
  $("#directModel").val(directModel);

  $(".worker-model").each(function () {
    const nextValue = normalizeSelectedModelForProvider($(this).val(), workerProvider);
    $(this).html(buildModelOptions(nextValue, workerProvider)).val(nextValue);
  });
  $(".summarizer-model-draft").each(function () {
    const nextValue = normalizeSelectedModelForProvider($(this).val(), summarizerProvider);
    $(this).html(buildModelOptions(nextValue, summarizerProvider)).val(nextValue);
  });

  visibleWorkerRosterSource(latestState?.draft || null, latestState?.activeTask || null).forEach(function (worker) {
    setWorkerEditorWorkerOverride(worker.id, {
      model: normalizeSelectedModelForProvider(worker.model, workerProvider)
    });
  });
  setWorkerEditorSummarizerOverride({
    model: normalizeSelectedModelForProvider(visibleSummarizerSource(latestState?.draft || null, latestState?.activeTask || null).model, summarizerProvider)
  });
}

function buildCommanderFormSource(task, draft) {
  if (draft && typeof draft === "object") {
    const safeDraft = Object.assign({}, defaultDraftState(), draft || {});
    return {
      sourceKey: [
        "draft",
        safeDraft.updatedAt || "",
        safeDraft.objective || "",
        safeDraft.sessionContext || "",
        JSON.stringify(safeDraft.constraints || []),
        safeDraft.executionMode || "live",
        safeDraft.frontMode || "full",
        safeDraft.contextMode || "weighted",
        safeDraft.directBaselineMode || "off",
        safeDraft.provider || "openai",
        safeDraft.model || "gpt-5-mini",
        safeDraft.summarizerProvider || safeDraft.provider || "openai",
        safeDraft.summarizerModel || "gpt-5-mini",
        safeDraft.directProvider || safeDraft.provider || "openai",
        safeDraft.directModel || safeDraft.model || "gpt-5-mini",
        safeDraft.ollamaBaseUrl || "http://127.0.0.1:11434",
        JSON.stringify(normalizeTargetTimeouts(safeDraft.targetTimeouts || DEFAULT_TARGET_TIMEOUTS)),
        safeDraft.reasoningEffort || "low",
        safeDraft.maxCostUsd ?? DEFAULT_RUNTIME_BUDGET.maxCostUsd,
        safeDraft.maxTotalTokens ?? DEFAULT_RUNTIME_BUDGET.maxTotalTokens,
        safeDraft.maxOutputTokens ?? DEFAULT_RUNTIME_BUDGET.maxOutputTokens,
        safeDraft.researchEnabled ? 1 : 0,
        safeDraft.researchExternalWebAccess === false ? 0 : 1,
        JSON.stringify(safeDraft.researchDomains || []),
        safeDraft.localFilesEnabled ? 1 : 0,
        JSON.stringify(safeDraft.localFileRoots || []),
        safeDraft.githubToolsEnabled ? 1 : 0,
        JSON.stringify(safeDraft.githubAllowedRepos || []),
        safeDraft.dynamicSpinupEnabled ? 1 : 0,
        safeDraft.vettingEnabled === false ? 0 : 1,
        JSON.stringify(safeDraft.summarizerHarness || {}),
        safeDraft.loopRounds ?? 3,
        safeDraft.loopDelayMs ?? 1000,
        JSON.stringify(safeDraft.workers || [])
      ].join("|"),
      values: safeDraft
    };
  }

  if (task) {
    return {
      sourceKey: [
        "task",
        task.taskId || "none",
        task.objective || "",
        task.sessionContext || "",
        JSON.stringify(task.constraints || []),
        task.runtime?.executionMode || "live",
        task.runtime?.frontMode || "full",
        task.runtime?.contextMode || "weighted",
        task.runtime?.directBaselineMode || "off",
        task.runtime?.provider || "openai",
        task.runtime?.model || "gpt-5-mini",
        task.summarizer?.provider || task.runtime?.provider || "openai",
        task.summarizer?.model || task.runtime?.model || "gpt-5-mini",
        task.runtime?.directProvider || task.runtime?.provider || "openai",
        task.runtime?.directModel || task.runtime?.model || "gpt-5-mini",
        task.runtime?.ollamaBaseUrl || "http://127.0.0.1:11434",
        JSON.stringify(normalizeTargetTimeouts(task.runtime?.targetTimeouts || DEFAULT_TARGET_TIMEOUTS)),
        task.runtime?.reasoningEffort || "low",
        task.runtime?.budget?.maxCostUsd ?? DEFAULT_RUNTIME_BUDGET.maxCostUsd,
        task.runtime?.budget?.maxTotalTokens ?? DEFAULT_RUNTIME_BUDGET.maxTotalTokens,
        task.runtime?.budget?.maxOutputTokens ?? DEFAULT_RUNTIME_BUDGET.maxOutputTokens,
        task.runtime?.research?.enabled ? 1 : 0,
        task.runtime?.research?.externalWebAccess === false ? 0 : 1,
        JSON.stringify(task.runtime?.research?.domains || []),
        task.runtime?.localFiles?.enabled ? 1 : 0,
        JSON.stringify(task.runtime?.localFiles?.roots || []),
        task.runtime?.githubTools?.enabled ? 1 : 0,
        JSON.stringify(task.runtime?.githubTools?.repos || []),
        task.runtime?.dynamicSpinup?.enabled ? 1 : 0,
        task.runtime?.vetting?.enabled === false ? 0 : 1,
        JSON.stringify(task.summarizer?.harness || {}),
        task.preferredLoop?.rounds ?? 3,
        task.preferredLoop?.delayMs ?? 1000,
        JSON.stringify(task.workers || [])
      ].join("|"),
      values: {
        objective: task.objective || "",
        constraints: task.constraints || [],
        sessionContext: task.sessionContext || "",
        executionMode: task.runtime?.executionMode || "live",
        frontMode: task.runtime?.frontMode || "full",
        contextMode: task.runtime?.contextMode || "weighted",
        directBaselineMode: task.runtime?.directBaselineMode || "off",
        provider: task.runtime?.provider || "openai",
        model: task.runtime?.model || "gpt-5-mini",
        summarizerProvider: task.summarizer?.provider || task.runtime?.provider || "openai",
        summarizerModel: task.summarizer?.model || task.runtime?.model || "gpt-5-mini",
        directProvider: task.runtime?.directProvider || task.runtime?.provider || "openai",
        directModel: task.runtime?.directModel || task.runtime?.model || "gpt-5-mini",
        ollamaBaseUrl: task.runtime?.ollamaBaseUrl || "http://127.0.0.1:11434",
        targetTimeouts: normalizeTargetTimeouts(task.runtime?.targetTimeouts || DEFAULT_TARGET_TIMEOUTS),
        reasoningEffort: task.runtime?.reasoningEffort || "low",
        maxCostUsd: task.runtime?.budget?.maxCostUsd ?? DEFAULT_RUNTIME_BUDGET.maxCostUsd,
        maxTotalTokens: task.runtime?.budget?.maxTotalTokens ?? DEFAULT_RUNTIME_BUDGET.maxTotalTokens,
        maxOutputTokens: task.runtime?.budget?.maxOutputTokens ?? DEFAULT_RUNTIME_BUDGET.maxOutputTokens,
        researchEnabled: task.runtime?.research?.enabled ? true : false,
        researchExternalWebAccess: task.runtime?.research?.externalWebAccess === false ? false : true,
        researchDomains: task.runtime?.research?.domains || [],
        localFilesEnabled: task.runtime?.localFiles?.enabled ? true : false,
        localFileRoots: task.runtime?.localFiles?.roots || ["."],
        githubToolsEnabled: task.runtime?.githubTools?.enabled ? true : false,
        githubAllowedRepos: task.runtime?.githubTools?.repos || [],
        dynamicSpinupEnabled: task.runtime?.dynamicSpinup?.enabled ? true : false,
        vettingEnabled: task.runtime?.vetting?.enabled === false ? false : true,
        summarizerHarness: normalizeHarnessConfig(task.summarizer?.harness, "expansive"),
        loopRounds: task.preferredLoop?.rounds ?? 3,
        loopDelayMs: task.preferredLoop?.delayMs ?? 1000,
        workers: task.workers || []
      }
    };
  }
  return buildCommanderFormSource(null, defaultDraftState());
}

function renderComposerContextPreview(sessionContext, constraints) {
  const contextText = truncateText(sessionContext, 220) || "No carry-forward context.";
  const constraintText = constraints && constraints.length
    ? constraints.slice(0, 3).join(" | ")
    : "No constraints configured.";
  $("#sessionContextPreview").text(contextText);
  $("#constraintsPreview").text(truncateText(constraintText, 220));
}

function applyCommanderForm(values) {
  const safe = Object.assign({}, defaultDraftState(), values || {});
  const workerProvider = normalizeProviderId(safe.provider || "openai");
  const summarizerProvider = normalizeProviderId(safe.summarizerProvider || safe.provider || "openai");
  const directProvider = normalizeProviderId(safe.directProvider || safe.provider || "openai");
  const workerModel = normalizeSelectedModelForProvider(safe.model, workerProvider);
  const summarizerModel = normalizeSelectedModelForProvider(safe.summarizerModel || safe.model, summarizerProvider);
  const directModel = normalizeSelectedModelForProvider(safe.directModel || safe.model, directProvider);
  $("#sessionContext").val(safe.sessionContext || "");
  $("#objective").val(safe.objective || "");
  $("#constraints").val((safe.constraints || []).join("\n"));
  $("#executionMode").val(safe.executionMode || "live");
  $("#frontMode").val(normalizeFrontMode(safe.frontMode));
  $("#contextMode").val(normalizeContextMode(safe.contextMode));
  $("#directBaselineMode").val(normalizeDirectBaselineMode(safe.directBaselineMode));
  $("#provider").val(workerProvider);
  $("#summarizerProvider").val(summarizerProvider);
  $("#directProvider").val(directProvider);
  $("#ollamaBaseUrl").val(normalizeOllamaBaseUrl(safe.ollamaBaseUrl));
  populateStaticModelSelect("#model", workerModel, workerProvider);
  populateStaticModelSelect(
    "#summarizerModel",
    summarizerModel,
    summarizerProvider
  );
  populateStaticModelSelect("#directModel", directModel, directProvider);
  $("#model").val(workerModel);
  $("#summarizerModel").val(summarizerModel);
  $("#directModel").val(directModel);
  $("#reasoningEffort").val(safe.reasoningEffort || "low");
  $("#maxCostUsd").val(safe.maxCostUsd ?? DEFAULT_RUNTIME_BUDGET.maxCostUsd);
  $("#maxTotalTokens").val(safe.maxTotalTokens ?? DEFAULT_RUNTIME_BUDGET.maxTotalTokens);
  $("#maxOutputTokens").val(safe.maxOutputTokens ?? DEFAULT_RUNTIME_BUDGET.maxOutputTokens);
  $("#loopRounds").val(safe.loopRounds ?? 3);
  $("#loopDelayMs").val(safe.loopDelayMs ?? 1000);
  $("#researchEnabled").val(safe.researchEnabled ? "1" : "0");
  $("#researchExternalWebAccess").val(safe.researchExternalWebAccess === false ? "0" : "1");
  $("#localFilesEnabled").val(safe.localFilesEnabled ? "1" : "0");
  $("#localFileRoots").val((safe.localFileRoots || ["."]).join(", "));
  $("#githubToolsEnabled").val(safe.githubToolsEnabled ? "1" : "0");
  $("#githubAllowedRepos").val((safe.githubAllowedRepos || []).join(", "));
  $("#dynamicSpinupEnabled").val(safe.dynamicSpinupEnabled ? "1" : "0");
  $("#vettingEnabled").val(safe.vettingEnabled === false ? "0" : "1");
  $("#researchDomains").val((safe.researchDomains || []).join(", "));
  syncDirectBaselineFields();
  syncOllamaBaseUrlField();
  enforceProviderCapabilitySelections(false);
  renderQualityProfileCards();
  renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
  renderComposerTools();
  renderAuthPoolPreview();
}

function syncCommanderForm(task, draft, force = false) {
  const source = buildCommanderFormSource(task, draft);
  if (!force && formDirty) return;
  if (!force && source.sourceKey === lastSyncedFormSourceKey) return;
  applyCommanderForm(source.values);
  lastSyncedFormSourceKey = source.sourceKey;
  formDirty = false;
}

function collectCommanderPayload() {
  return {
    sessionContext: $("#sessionContext").val().trim(),
    objective: $("#objective").val().trim(),
    constraints: $("#constraints").val().split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean),
    executionMode: $("#executionMode").val(),
    frontMode: normalizeFrontMode($("#frontMode").val()),
    contextMode: normalizeContextMode($("#contextMode").val()),
    directBaselineMode: normalizeDirectBaselineMode($("#directBaselineMode").val()),
    provider: $("#provider").val(),
    model: $("#model").val(),
    summarizerProvider: $("#summarizerProvider").val(),
    summarizerModel: $("#summarizerModel").val(),
    directProvider: $("#directProvider").val(),
    directModel: $("#directModel").val(),
    ollamaBaseUrl: normalizeOllamaBaseUrl($("#ollamaBaseUrl").val()),
    reasoningEffort: $("#reasoningEffort").val(),
    maxCostUsd: parseFloat($("#maxCostUsd").val()) || 0,
    maxTotalTokens: parseInt($("#maxTotalTokens").val(), 10) || 0,
    maxOutputTokens: parseInt($("#maxOutputTokens").val(), 10) || 0,
    loopRounds: parseInt($("#loopRounds").val(), 10) || 1,
    loopDelayMs: parseInt($("#loopDelayMs").val(), 10) || 0,
    researchEnabled: $("#researchEnabled").val(),
    researchExternalWebAccess: $("#researchExternalWebAccess").val(),
    localFilesEnabled: $("#localFilesEnabled").val(),
    localFileRoots: $("#localFileRoots").val().trim(),
    githubToolsEnabled: $("#githubToolsEnabled").val(),
    githubAllowedRepos: $("#githubAllowedRepos").val().trim(),
    dynamicSpinupEnabled: $("#dynamicSpinupEnabled").val(),
    vettingEnabled: $("#vettingEnabled").val(),
    researchDomains: $("#researchDomains").val().trim()
  };
}

function activeWorkerSource(task, draft) {
  if (task && Array.isArray(task.workers) && task.workers.length) {
    return task.workers;
  }
  return Array.isArray(draft?.workers) && draft.workers.length ? draft.workers : defaultDraftState().workers;
}

function runtimeProviderSource(task, draft) {
  return normalizeProviderId(draft?.provider || task?.runtime?.provider || "openai");
}

function summarizerProviderSource(task, draft) {
  return normalizeProviderId(draft?.summarizerProvider || task?.summarizer?.provider || task?.runtime?.provider || draft?.provider || "openai");
}

function stagedWorkerSource(draft, task) {
  if (Array.isArray(draft?.workers) && draft.workers.length) {
    return draft.workers;
  }
  if (task && Array.isArray(task.workers) && task.workers.length) {
    return task.workers;
  }
  return defaultDraftState().workers;
}

function stagedSummarizerSource(draft, task) {
  const fallback = defaultDraftState();
  return {
    id: "summarizer",
    label: "Main thread",
    provider: String(draft?.summarizerProvider || task?.summarizer?.provider || task?.runtime?.provider || fallback.summarizerProvider || fallback.provider),
    model: String(draft?.summarizerModel || task?.summarizer?.model || task?.runtime?.model || fallback.summarizerModel || fallback.model),
    harness: normalizeHarnessConfig(draft?.summarizerHarness || task?.summarizer?.harness || fallback.summarizerHarness, "expansive")
  };
}

function collectVisibleSummarizerConfig() {
  return visibleSummarizerSource(latestState?.draft || null, latestState?.activeTask || null);
}

function collectVisibleWorkerRoster() {
  return visibleWorkerRosterSource(latestState?.draft || null, latestState?.activeTask || null);
}

function displayWorkerLabel(worker) {
  const template = WORKER_TYPE_CATALOG[worker?.type];
  const currentLabel = String(worker?.label || "").trim();
  if (template && (!currentLabel || /^Worker [A-Z]$/i.test(currentLabel))) {
    return template.label;
  }
  return currentLabel || template?.label || String(worker?.id || "Worker");
}

function buildDraftSavePayload(options = {}) {
  const payload = collectCommanderPayload();
  const overrideRoster = Array.isArray(options.workerRoster) ? options.workerRoster : null;
  const roster = overrideRoster && overrideRoster.length
    ? overrideRoster
    : collectVisibleWorkerRoster();
  const fallbackSummarizer = stagedSummarizerSource(latestState?.draft || null, latestState?.activeTask || null);
  const visibleSummarizer = collectVisibleSummarizerConfig();
  const summarizerConfig = options.summarizerConfig && typeof options.summarizerConfig === "object"
    ? options.summarizerConfig
    : {
        provider: String(payload.summarizerProvider || fallbackSummarizer.provider || payload.provider || "openai"),
        model: String(payload.summarizerModel || payload.model || fallbackSummarizer.model || ""),
        harness: visibleSummarizer?.harness || fallbackSummarizer.harness
      };
  payload.constraints = JSON.stringify(payload.constraints);
  payload.workers = JSON.stringify(roster.length ? roster : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null));
  payload.summarizerProvider = String(summarizerConfig?.provider || payload.summarizerProvider || payload.provider || "openai");
  payload.summarizerModel = String(summarizerConfig?.model || payload.summarizerModel || payload.model || "");
  payload.summarizerHarness = JSON.stringify(normalizeHarnessConfig(summarizerConfig?.harness, "expansive"));
  payload.targetTimeouts = JSON.stringify(currentTargetTimeoutsSource(latestState?.activeTask || null, latestState?.draft || null));
  return payload;
}

function buildProfileAppliedWorkerRoster(modelId) {
  const visibleWorkers = collectVisibleWorkerRoster();
  const baseWorkers = visibleWorkers.length
    ? visibleWorkers
    : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null);
  return baseWorkers.map(function (worker) {
    return Object.assign({}, worker, {
      model: normalizeSelectedModelForProvider(modelId, runtimeProviderSource(latestState?.activeTask || null, latestState?.draft || null))
    });
  });
}

function setVisibleWorkerModels(modelId) {
  const provider = runtimeProviderSource(latestState?.activeTask || null, latestState?.draft || null);
  visibleWorkerRosterSource(latestState?.draft || null, latestState?.activeTask || null).forEach(function (worker) {
    setWorkerEditorWorkerOverride(worker.id, { model: normalizeSelectedModelForProvider(modelId, provider) });
  });
  $("#workerEditorBody .worker-model").val(normalizeSelectedModelForProvider(modelId, provider));
}

function setVisibleSummarizerModel(modelId) {
  const provider = normalizeProviderId($("#summarizerProvider").val() || summarizerProviderSource(latestState?.activeTask || null, latestState?.draft || null));
  const normalized = normalizeSelectedModelForProvider(modelId, provider);
  setWorkerEditorSummarizerOverride({ model: normalized });
  $("#workerEditorBody .summarizer-model-draft").val(normalized);
}

function buildQualityProfileSnapshot() {
  const payload = collectCommanderPayload();
  const workerSource = collectVisibleWorkerRoster();
  const roster = workerSource.length
    ? workerSource
    : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null);
  const summarizerSource = collectVisibleSummarizerConfig();
  return {
    frontMode: normalizeFrontMode(payload.frontMode),
    contextMode: normalizeContextMode(payload.contextMode),
    directBaselineMode: normalizeDirectBaselineMode(payload.directBaselineMode),
    provider: String(payload.provider || "openai"),
    model: String(payload.model || ""),
    summarizerProvider: String(summarizerSource?.provider || payload.summarizerProvider || payload.provider || "openai"),
    summarizerModel: String(summarizerSource?.model || payload.summarizerModel || payload.model || ""),
    directProvider: String(payload.directProvider || payload.provider || "openai"),
    directModel: String(payload.directModel || payload.model || ""),
    ollamaBaseUrl: normalizeOllamaBaseUrl(payload.ollamaBaseUrl),
    reasoningEffort: String(payload.reasoningEffort || ""),
    maxCostUsd: Number(payload.maxCostUsd || 0),
    maxTotalTokens: Number(payload.maxTotalTokens || 0),
    maxOutputTokens: Number(payload.maxOutputTokens || 0),
    loopRounds: Number(payload.loopRounds || 0),
    loopDelayMs: Number(payload.loopDelayMs || 0),
    workerModels: roster.map(function (worker) {
      return String(worker?.model || payload.model || "");
    })
  };
}

function matchesQualityProfile(profileId, snapshot = null) {
  const profile = QUALITY_PROFILE_CATALOG[profileId];
  if (!profile) return false;
  const comparable = snapshot || buildQualityProfileSnapshot();
  const provider = normalizeProviderId(comparable.provider);
  const summarizerProvider = normalizeProviderId(comparable.summarizerProvider || comparable.provider);
  if (provider !== summarizerProvider) return false;
  const modelConfig = qualityProfileModelConfig(profileId, provider);
  if (comparable.model !== modelConfig.workerModel) return false;
  if (comparable.summarizerModel !== modelConfig.summarizerModel) return false;
  if (comparable.reasoningEffort !== profile.reasoningEffort) return false;
  if (Number(comparable.maxCostUsd) !== Number(profile.maxCostUsd)) return false;
  if (Number(comparable.maxTotalTokens) !== Number(profile.maxTotalTokens)) return false;
  if (Number(comparable.maxOutputTokens) !== Number(profile.maxOutputTokens)) return false;
  if (Number(comparable.loopRounds) !== Number(profile.loopRounds)) return false;
  if (Number(comparable.loopDelayMs) !== Number(profile.loopDelayMs)) return false;
  return (comparable.workerModels.length ? comparable.workerModels : [comparable.model]).every(function (modelId) {
    return modelId === modelConfig.workerModel;
  });
}

function detectQualityProfileId(snapshot = null) {
  const comparable = snapshot || buildQualityProfileSnapshot();
  return QUALITY_PROFILE_ORDER.find(function (profileId) {
    return matchesQualityProfile(profileId, comparable);
  }) || "";
}

function buildTaskQualityProfileSnapshot(task) {
  if (!task) return null;
  const budget = task?.runtime?.budget || {};
  return {
    frontMode: normalizeFrontMode(task?.runtime?.frontMode),
    contextMode: normalizeContextMode(task?.runtime?.contextMode),
    directBaselineMode: normalizeDirectBaselineMode(task?.runtime?.directBaselineMode),
    provider: String(task?.runtime?.provider || "openai"),
    model: String(task?.runtime?.model || "gpt-5-mini"),
    summarizerProvider: String(task?.summarizer?.provider || task?.runtime?.provider || "openai"),
    summarizerModel: String(task?.summarizer?.model || task?.runtime?.model || "gpt-5-mini"),
    directProvider: String(task?.runtime?.directProvider || task?.runtime?.provider || "openai"),
    directModel: String(task?.runtime?.directModel || task?.runtime?.model || "gpt-5-mini"),
    ollamaBaseUrl: normalizeOllamaBaseUrl(task?.runtime?.ollamaBaseUrl),
    reasoningEffort: String(task?.runtime?.reasoningEffort || "low"),
    maxCostUsd: Number(budget.maxCostUsd ?? 0),
    maxTotalTokens: Number(budget.maxTotalTokens ?? 0),
    maxOutputTokens: Number(budget.maxOutputTokens ?? 0),
    loopRounds: Number(task?.preferredLoop?.rounds ?? 0),
    loopDelayMs: Number(task?.preferredLoop?.delayMs ?? 0),
    workerModels: (task?.workers || []).map(function (worker) {
      return String(worker?.model || task?.runtime?.model || "gpt-5-mini");
    })
  };
}

function profileDisplayName(profileId) {
  return QUALITY_PROFILE_CATALOG[profileId]?.label || "Manual";
}

function formatTokenWall(value) {
  const amount = Number(value || 0);
  return amount > 0 ? amount.toLocaleString() + " token wall" : "token wall off";
}

function runtimeSnapshotsMatch(left, right) {
  if (!left || !right) return false;
  if (normalizeFrontMode(left.frontMode) !== normalizeFrontMode(right.frontMode)) return false;
  if (normalizeContextMode(left.contextMode) !== normalizeContextMode(right.contextMode)) return false;
  if (normalizeDirectBaselineMode(left.directBaselineMode) !== normalizeDirectBaselineMode(right.directBaselineMode)) return false;
  if (normalizeProviderId(left.provider) !== normalizeProviderId(right.provider)) return false;
  if (normalizeProviderId(left.summarizerProvider || left.provider) !== normalizeProviderId(right.summarizerProvider || right.provider)) return false;
  if (left.model !== right.model) return false;
  if (left.summarizerModel !== right.summarizerModel) return false;
  if (normalizeDirectBaselineMode(left.directBaselineMode) !== "off" || normalizeDirectBaselineMode(right.directBaselineMode) !== "off") {
    if (normalizeProviderId(left.directProvider || left.provider) !== normalizeProviderId(right.directProvider || right.provider)) return false;
    if (String(left.directModel || "") !== String(right.directModel || "")) return false;
  }
  if (
    (
      shouldShowOllamaBaseUrl(left.provider, left.summarizerProvider)
      || shouldShowOllamaBaseUrl(right.provider, right.summarizerProvider)
      || (normalizeDirectBaselineMode(left.directBaselineMode) !== "off" && normalizeProviderId(left.directProvider || left.provider) === "ollama")
      || (normalizeDirectBaselineMode(right.directBaselineMode) !== "off" && normalizeProviderId(right.directProvider || right.provider) === "ollama")
    )
    && normalizeOllamaBaseUrl(left.ollamaBaseUrl) !== normalizeOllamaBaseUrl(right.ollamaBaseUrl)
  ) return false;
  if (left.reasoningEffort !== right.reasoningEffort) return false;
  if (Number(left.maxCostUsd) !== Number(right.maxCostUsd)) return false;
  if (Number(left.maxTotalTokens) !== Number(right.maxTotalTokens)) return false;
  if (Number(left.maxOutputTokens) !== Number(right.maxOutputTokens)) return false;
  if (Number(left.loopRounds) !== Number(right.loopRounds)) return false;
  if (Number(left.loopDelayMs) !== Number(right.loopDelayMs)) return false;
  const leftModels = (left.workerModels || []).slice().sort();
  const rightModels = (right.workerModels || []).slice().sort();
  return JSON.stringify(leftModels) === JSON.stringify(rightModels);
}

function appendHomeRuntimeBlock($root, label, value, detailLines, warning = false, metaText = "") {
  const $block = $("<div>").addClass("home-runtime-block compact-hover-card");
  if (warning) $block.addClass("warning");
  $block.append($("<div>").addClass("home-runtime-label").text(label));
  $block.append($("<div>").addClass("home-runtime-value").text(value));
  if (String(metaText || "").trim()) {
    $block.append($("<div>").addClass("home-runtime-meta").text(metaText));
  }
  appendCompactHoverPopup($block, detailLines);
  $root.append($block);
}

function renderQualityProfileCards() {
  const $root = $("#qualityProfileCards");
  const $status = $("#qualityProfileStatus");
  if (!$root.length || !$status.length) return;

  const snapshot = buildQualityProfileSnapshot();
  const workerProvider = normalizeProviderId(snapshot.provider || "openai");
  const summarizerProvider = normalizeProviderId(snapshot.summarizerProvider || snapshot.provider || "openai");
  const activeProfileId = detectQualityProfileId(snapshot);
  const distinctWorkerModels = Array.from(new Set((snapshot.workerModels || []).filter(Boolean)));
  const workerModelSummary = distinctWorkerModels.length === 1
    ? modelLabel(distinctWorkerModels[0], workerProvider)
    : (distinctWorkerModels.length > 1 ? "mixed worker models" : modelLabel(snapshot.model, workerProvider));

  $root.empty();
  QUALITY_PROFILE_ORDER.forEach(function (profileId) {
    const profile = QUALITY_PROFILE_CATALOG[profileId];
    const workerModels = qualityProfileModelConfig(profileId, workerProvider);
    const summarizerModels = qualityProfileModelConfig(profileId, summarizerProvider);
    const tokenText = Number(profile.maxTotalTokens) > 0 ? Number(profile.maxTotalTokens).toLocaleString() + " local tokens" : "cost wall only";
    const $button = $("<button>")
      .attr("type", "button")
      .addClass("quality-profile-card compact-hover-card")
      .toggleClass("active", activeProfileId === profileId)
      .attr("data-profile-id", profileId);
    $button.append($("<div>").addClass("quality-profile-eyebrow").text(profile.eyebrow));
    $button.append($("<div>").addClass("quality-profile-title").text(profile.label));
    appendCompactHoverPopup($button, [
      profile.description,
      "Workers: " + providerLabel(workerProvider) + " / " + modelLabel(workerModels.workerModel, workerProvider),
      "Summarizer: " + providerLabel(summarizerProvider) + " / " + modelLabel(summarizerModels.summarizerModel, summarizerProvider),
      "Reasoning: " + profile.reasoningEffort + " | Budget: " + formatUsdBudget(profile.maxCostUsd),
      tokenText + " | Loop: " + Number(profile.loopRounds || 0) + " rounds"
    ]);
    $root.append($button);
  });

  if (activeProfileId) {
    const profile = QUALITY_PROFILE_CATALOG[activeProfileId];
    const workerModels = qualityProfileModelConfig(activeProfileId, workerProvider);
    const summarizerModels = qualityProfileModelConfig(activeProfileId, summarizerProvider);
    $status.text(
      profile.label +
      " matches the current runtime template. " +
      "Workers use " + providerLabel(workerProvider) + " / " + modelLabel(workerModels.workerModel, workerProvider) +
      ", summarizer uses " + providerLabel(summarizerProvider) + " / " + modelLabel(summarizerModels.summarizerModel, summarizerProvider) +
      ", the token wall is " + (profile.maxTotalTokens > 0 ? Number(profile.maxTotalTokens).toLocaleString() : "off") +
      ", and auto loop depth is " + Number(profile.loopRounds || 0) + " rounds."
    );
    return;
  }

  $status.text(
    "Manual mix active. Workers are on " + workerModelSummary +
    ", summarizer is on " + providerLabel(summarizerProvider) + " / " + modelLabel(snapshot.summarizerModel, summarizerProvider) +
    ", reasoning is " + (snapshot.reasoningEffort || "unset") +
    ", and auto loop depth is " + Number(snapshot.loopRounds || 0) + " rounds. Click a profile to snap the whole runtime back into a tested template."
  );
}

function applyQualityProfile(profileId) {
  const profile = QUALITY_PROFILE_CATALOG[profileId];
  if (!profile) return;

  const workerProvider = normalizeProviderId($("#provider").val());
  const summarizerProvider = normalizeProviderId($("#summarizerProvider").val() || workerProvider);
  const workerModels = qualityProfileModelConfig(profileId, workerProvider);
  const summarizerModels = qualityProfileModelConfig(profileId, summarizerProvider);

  $("#provider").val(workerProvider);
  $("#summarizerProvider").val(summarizerProvider);
  populateStaticModelSelect("#model", workerModels.workerModel, workerProvider);
  populateStaticModelSelect("#summarizerModel", summarizerModels.summarizerModel, summarizerProvider);
  $("#model").val(workerModels.workerModel);
  $("#summarizerModel").val(summarizerModels.summarizerModel);
  refreshProviderModelSelects();
  $("#reasoningEffort").val(profile.reasoningEffort);
  $("#maxCostUsd").val(profile.maxCostUsd);
  $("#maxTotalTokens").val(profile.maxTotalTokens);
  $("#maxOutputTokens").val(profile.maxOutputTokens);
  $("#loopRounds").val(profile.loopRounds);
  $("#loopDelayMs").val(profile.loopDelayMs);

  const workerRoster = buildProfileAppliedWorkerRoster(workerModels.workerModel);
  setVisibleWorkerModels(workerModels.workerModel);
  setVisibleSummarizerModel(summarizerModels.summarizerModel);
  enforceProviderCapabilitySelections(true);
  formDirty = true;
  renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
  renderQualityProfileCards();
  renderAuthPoolPreview();

  postForm(API.draft, buildDraftSavePayload({ workerRoster }), profile.label + " profile applied", {
    clearFormDirty: true,
    onSuccess: function () {
      workerControlsSignature = "";
      renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
      renderQualityProfileCards();
    }
  });
}

function queueDraftSave() {
  clearTimeout(draftSaveTimer);
  draftSaveTimer = setTimeout(function () {
    $.post(apiRoute(API.draft), buildDraftSavePayload()).fail(function (xhr) {
      showMessage("Draft save failed: " + extractErrorMessage(xhr), true);
    });
  }, 350);
}

function renderComposerTools() {
  const $menu = $("#composerToolMenu");
  const $status = $("#composerToolStatus");
  const $sourceDrawer = $("#composerSourceDrawer");
  const $recentDrawer = $("#composerRecentDrawer");
  const $attachments = $("#composerAttachmentList");
  const $toggle = $("#composerToolMenuToggle");
  if (!$menu.length || !$status.length || !$sourceDrawer.length || !$recentDrawer.length || !$attachments.length || !$toggle.length) {
    return;
  }

  const capabilityState = enforceProviderCapabilitySelections(false);
  const workerProvider = capabilityState.provider;
  const capabilities = capabilityState.capabilities;
  const researchEnabled = capabilities.webSearch && $("#researchEnabled").val() === "1";
  const externalWeb = $("#researchExternalWebAccess").val() !== "0";
  const localFilesEnabled = capabilities.localFiles && $("#localFilesEnabled").val() === "1";
  const localFileRootsValue = String($("#localFileRoots").val() || "").trim();
  const localRootCount = localFileRootsValue ? localFileRootsValue.split(",").map(function (item) { return item.trim(); }).filter(Boolean).length : 0;
  const githubToolsEnabled = capabilities.githubTools && $("#githubToolsEnabled").val() === "1";
  const githubReposValue = String($("#githubAllowedRepos").val() || "").trim();
  const githubRepoCount = githubReposValue ? githubReposValue.split(",").map(function (item) { return item.trim(); }).filter(Boolean).length : 0;
  const vettingEnabled = $("#vettingEnabled").val() !== "0";
  const domainsValue = String($("#researchDomains").val() || "").trim();
  const sourceCount = domainsValue ? domainsValue.split(",").map(function (item) { return item.trim(); }).filter(Boolean).length : 0;
  const toolChips = [];

  toolChips.push(`<span class="composer-tool-chip${researchEnabled ? " active" : ""}">Provider ${escapeHtml(providerLabel(workerProvider))}</span>`);
  toolChips.push(`<span class="composer-tool-chip${researchEnabled ? " active" : ""}">Search ${capabilities.webSearch ? (researchEnabled ? "on" : "off") : "n/a"}</span>`);
  if (researchEnabled) {
    toolChips.push(`<span class="composer-tool-chip">${externalWeb ? "Live web" : "Cached web"}</span>`);
  }
  if (sourceCount > 0) {
    toolChips.push(`<span class="composer-tool-chip">${sourceCount} source${sourceCount === 1 ? "" : "s"}</span>`);
  }
  if (localFilesEnabled) {
    toolChips.push(`<span class="composer-tool-chip">${localRootCount || 1} local root${(localRootCount || 1) === 1 ? "" : "s"}</span>`);
  }
  if (githubToolsEnabled) {
    toolChips.push(`<span class="composer-tool-chip">${githubRepoCount || 1} GitHub repo${(githubRepoCount || 1) === 1 ? "" : "s"}</span>`);
  }
  if (stagedComposerAttachments.length > 0) {
    toolChips.push(`<span class="composer-tool-chip">${stagedComposerAttachments.length} file${stagedComposerAttachments.length === 1 ? "" : "s"}</span>`);
  }
  if (vettingEnabled) {
    toolChips.push(`<span class="composer-tool-chip">Vetting</span>`);
  }
  toolChips.push(`<span class="composer-tool-chip">${escapeHtml(providerCapabilitySummary(capabilities))}</span>`);
  $status.html(toolChips.join(""));

  const webSearchDisabled = capabilities.webSearch ? "" : " disabled title=\"This provider does not support live web search in the current runtime.\"";
  const localFilesDisabled = capabilities.localFiles ? "" : " disabled title=\"This provider does not support local file tool calls in the current runtime.\"";
  const githubToolsDisabled = capabilities.githubTools ? "" : " disabled title=\"This provider does not support GitHub tool calls in the current runtime.\"";
  $menu.html(`
    <button type="button" class="composer-tool-action" data-tool-action="upload">Upload files</button>
    <button type="button" class="composer-tool-action" data-tool-action="recent">Recent files</button>
    <button type="button" class="composer-tool-action${researchEnabled ? " active" : ""}" data-tool-action="web-search"${webSearchDisabled}>${capabilities.webSearch ? (researchEnabled ? "Web search on" : "Web search off") : "Web search unavailable"}</button>
    <button type="button" class="composer-tool-action${localFilesEnabled ? " active" : ""}" data-tool-action="local-files"${localFilesDisabled}>${capabilities.localFiles ? (localFilesEnabled ? "Local files on" : "Local files off") : "Local files unavailable"}</button>
    <button type="button" class="composer-tool-action${githubToolsEnabled ? " active" : ""}" data-tool-action="github-tools"${githubToolsDisabled}>${capabilities.githubTools ? (githubToolsEnabled ? "GitHub on" : "GitHub off") : "GitHub unavailable"}</button>
    <button type="button" class="composer-tool-action${composerSourceDrawerOpen ? " active" : ""}" data-tool-action="sources"${webSearchDisabled}>${capabilities.webSearch ? "Add sources" : "Sources unavailable"}</button>
    <button type="button" class="composer-tool-action${vettingEnabled ? " active" : ""}" data-tool-action="vetting">${vettingEnabled ? "Vetting on" : "Vetting off"}</button>
  `);
  $menu.prop("hidden", !composerToolMenuOpen);
  $toggle.attr("aria-expanded", composerToolMenuOpen ? "true" : "false");

  if (!hasFocusWithin("#composerSourceDrawer")) {
    $("#composerResearchDomainsInput").val(domainsValue);
    $("#composerResearchModeSelect").val(externalWeb ? "1" : "0");
  }
  $sourceDrawer.prop("hidden", !composerSourceDrawerOpen);

  if (composerRecentDrawerOpen) {
    if (recentComposerAttachments.length) {
      $recentDrawer.html(`
        <div class="composer-recent-stack">
          ${recentComposerAttachments.map(function (attachment) {
            return `
              <button type="button" class="composer-recent-file" data-recent-file-id="${escapeHtml(attachment.id)}">
                <span class="composer-recent-title">${escapeHtml(attachment.name)}</span>
                <span class="composer-recent-meta">${escapeHtml(formatFileSize(attachment.size) + (attachment.truncated ? " | truncated" : ""))}</span>
              </button>
            `;
          }).join("")}
        </div>
      `);
    } else {
      $recentDrawer.html(`<div class="fieldnote">No recent text files staged yet.</div>`);
    }
  } else {
    $recentDrawer.empty();
  }
  $recentDrawer.prop("hidden", !composerRecentDrawerOpen);

  if (!stagedComposerAttachments.length) {
    $attachments.empty();
    return;
  }

  $attachments.html(`
    <div class="composer-attachment-stack">
      ${stagedComposerAttachments.map(function (attachment) {
        return `
          <article class="composer-attachment-card">
            <div class="composer-attachment-head">
              <div>
                <div class="composer-attachment-title">${escapeHtml(attachment.name)}</div>
                <div class="composer-attachment-meta">${escapeHtml(formatFileSize(attachment.size) + (attachment.truncated ? " | truncated for send" : ""))}</div>
              </div>
              <button type="button" class="composer-attachment-remove" data-attachment-id="${escapeHtml(attachment.id)}">Remove</button>
            </div>
            <div class="composer-attachment-preview">${escapeHtml(attachmentPreviewText(attachment))}</div>
          </article>
        `;
      }).join("")}
    </div>
  `);
}

function hasFocusWithin(selector) {
  const active = document.activeElement;
  return !!active && $(active).closest(selector).length > 0;
}

function isMobileShell() {
  return window.matchMedia("(max-width: 1100px)").matches;
}

function setTheme(theme) {
  activeTheme = theme === "light" ? "light" : "dark";
  localStorage.setItem("loopTheme", activeTheme);
  document.documentElement.setAttribute("data-bs-theme", activeTheme);
  $(".theme-toggle-btn")
    .removeClass("active")
    .attr("aria-pressed", "false");
  $('.theme-toggle-btn[data-theme-option="' + activeTheme + '"]')
    .addClass("active")
    .attr("aria-pressed", "true");
}

function initializeSidebarBootstrapCollapse() {
  sidebarCopyCollapseTargets = [];
  if (!(window.bootstrap && window.bootstrap.Collapse)) {
    return;
  }
  document.querySelectorAll("#sidebarPanel .sidebar-copy.collapse").forEach(function (element) {
    sidebarCopyCollapseTargets.push({
      element,
      instance: window.bootstrap.Collapse.getOrCreateInstance(element, { toggle: false })
    });
  });
}

function syncSidebarBootstrapCollapse() {
  if (!sidebarCopyCollapseTargets.length) {
    return;
  }
  const shouldShow = isMobileShell() || !sidebarCollapsed;
  sidebarCopyCollapseTargets.forEach(function (target) {
    const element = target.element;
    const shown = element.classList.contains("show") && !element.classList.contains("collapsing");
    if (shouldShow && !shown) {
      target.instance.show();
    } else if (!shouldShow && shown) {
      target.instance.hide();
    }
  });
}

function syncShellChrome() {
  const mobile = isMobileShell();
  if (!mobile) {
    mobileSidebarOpen = false;
  }
  $(".app-shell")
    .attr("data-sidebartype", mobile ? "overlay" : (sidebarCollapsed ? "mini-sidebar" : "full"))
    .toggleClass("sidebar-collapsed", !mobile && sidebarCollapsed)
    .toggleClass("show-sidebar", mobile && mobileSidebarOpen);
  $("#sidebarBackdrop").prop("hidden", !(mobile && mobileSidebarOpen));
  $("#mobileSidebarToggle")
    .prop("hidden", !mobile)
    .attr("aria-expanded", mobile && mobileSidebarOpen ? "true" : "false")
    .text(mobileSidebarOpen ? "Close menu" : "Menu");
  const sidebarToggleLabel = mobile
    ? "Close sidebar"
    : (sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar");
  const sidebarToggleIcon = mobile
    ? "close"
    : (sidebarCollapsed ? "expand" : "collapse");
  $("#sidebarToggle")
    .attr("data-shell-icon", sidebarToggleIcon)
    .attr("aria-expanded", mobile ? (mobileSidebarOpen ? "true" : "false") : (sidebarCollapsed ? "false" : "true"))
    .attr("aria-label", sidebarToggleLabel)
    .attr("title", sidebarToggleLabel);
  syncSidebarBootstrapCollapse();
}

function setMobileSidebarOpen(open) {
  mobileSidebarOpen = !!open;
  syncShellChrome();
}

function setSidebarCollapsed(collapsed) {
  sidebarCollapsed = !!collapsed;
  localStorage.setItem("loopSidebarCollapsed", sidebarCollapsed ? "1" : "0");
  syncShellChrome();
}

function syncWorkspaceStatus(task, state, workers, loop, usage, budget) {
  const taskId = task?.taskId || "none";
  const memoryVersion = state?.memoryVersion ?? 0;
  const workerCount = workers.length || 0;
  const dispatch = state?.dispatch || {};
  const dispatchEntries = Array.isArray(dispatch.activeJobs) ? dispatch.activeJobs : [];
  const dispatchPrimary = dispatchEntries[0] || null;
  const dispatchActive = dispatchEntries.length > 0 || latestManualDispatchCount > 0;
  const loopJobId = dispatchActive && !loop?.jobId ? (dispatchPrimary?.jobId || "none") : (loop?.jobId || "none");
  const loopStatus = dispatchActive
    ? ("dispatch-" + String(dispatch.status || "running"))
    : (loop?.status || "idle");
  const loopProgress = dispatchActive
    ? (Number(dispatch.runningCount || 0) + " running | " + Number(dispatch.queuedCount || 0) + " queued")
    : ((loop?.completedRounds ?? 0) + " / " + (loop?.totalRounds ?? 0));
  const loopElapsed = formatElapsedCompact(dispatchPrimary?.startedAt || dispatchPrimary?.queuedAt || loop?.startedAt || loop?.queuedAt) || "n/a";
  const usageTokens = (usage.totalTokens ?? 0) + " / " + (budget.maxTotalTokens ?? 0);
  const usageWebSearchCalls = usage.webSearchCalls ?? 0;
  const usageCost = formatUsd(usage.estimatedCostUsd || 0) + " / " + formatUsd(budget.maxCostUsd || 0);

  $("#taskId, #headerTaskId").text(taskId);
  $("#memoryVersion, #headerMemoryVersion").text(memoryVersion);
  $("#workerCount, #headerWorkerCount").text(workerCount);
  $("#loopJobId, #headerLoopJobId").text(loopJobId);
  $("#loopStatus, #headerLoopStatus").text(loopStatus);
  $("#loopProgress, #headerLoopProgress").text(loopProgress);
  $("#headerLoopElapsed").text(loopElapsed);
  $("#usageTokens, #footerUsageTokens").text(usageTokens);
  $("#usageWebSearchCalls, #footerUsageWebSearchCalls").text(usageWebSearchCalls);
  $("#usageCost, #footerUsageCost").text(usageCost);
  renderApiModeStatus();
}

function activeDispatchEntries(state) {
  const stateEntries = Array.isArray(state?.dispatch?.activeJobs) ? state.dispatch.activeJobs : [];
  return stateEntries.length ? stateEntries : latestManualDispatchEntries;
}

function activeDispatchCount(state) {
  return activeDispatchEntries(state).length;
}

function hasActiveDispatchTarget(state, target) {
  return activeDispatchEntries(state).some(function (entry) {
    return String(entry?.target || "") === String(target || "");
  });
}

function inferFrontActiveTarget(loop, state) {
  const dispatchTarget = activeDispatchEntries(state).map(function (entry) {
    return String(entry?.target || "").trim();
  }).find(Boolean);
  if (dispatchTarget) return dispatchTarget;
  const message = String(loop?.lastMessage || state?.dispatch?.lastMessage || "").trim();
  if (!message) return "";
  const workerMatch = message.match(/worker\s+([a-z0-9_-]+)/i);
  if (workerMatch) return String(workerMatch[1] || "").toUpperCase();
  if (/answer now/i.test(message)) return "answer_now";
  if (/direct baseline|single-thread baseline/i.test(message)) return "direct_baseline";
  if (/commander review/i.test(message)) return "commander_review";
  if (/summarizer/i.test(message)) return "summarizer";
  if (/commander/i.test(message)) return "commander";
  return "";
}

function activeFrontTargets(loop, state) {
  const loopTargets = Array.isArray(loop?.activeTargets)
    ? loop.activeTargets.map(function (target) { return String(target || "").trim(); }).filter(Boolean)
    : [];
  const dispatchTargets = activeDispatchEntries(state)
    .map(function (entry) { return String(entry?.target || "").trim(); })
    .filter(Boolean);
  if (loopTargets.length) {
    const combined = loopTargets.slice();
    dispatchTargets.forEach(function (target) {
      if (target && !combined.includes(target)) {
        combined.push(target);
      }
    });
    return combined;
  }
  if (dispatchTargets.length) return dispatchTargets;
  const inferred = inferFrontActiveTarget(loop, state);
  return inferred ? [inferred] : [];
}

function setTopologyNodeState(nodeId, metaId, stateKey, metaText) {
  const $node = $("#" + nodeId);
  if ($node.length) {
    $node.removeClass("is-active is-waiting is-ready");
    $node.addClass("is-" + String(stateKey || "ready"));
  }
  const $meta = $("#" + metaId);
  if ($meta.length) {
    $meta.text(metaText || "");
  }
}

function updateTopologyPanel(task, loop, state) {
  const activeTargets = activeFrontTargets(loop, state);
  const workerRoster = activeWorkerSource(task, state?.draft || null);
  const workerCount = Array.isArray(workerRoster) ? workerRoster.length : 0;
  const summary = state?.summary || task?.summary || null;
  const providerTrace = activeProviderTraceSource(state).trace;
  const toolEnabled = !!(
    task?.runtime?.research?.enabled ||
    task?.runtime?.localFiles?.enabled ||
    task?.runtime?.githubTools?.enabled
  );

  const commanderState = activeTargets.includes("commander") || activeTargets.includes("commander_review")
    ? "active"
    : ((task?.stateCommander?.round || task?.stateCommanderReview?.round) ? "ready" : "waiting");
  const workersActive = activeTargets.some(function (target) { return /^[A-Z]$/.test(String(target || "")); });
  const workersState = workersActive ? "active" : (workerCount ? (isWorkspaceBusy(loop, state) ? "waiting" : "ready") : "ready");
  const summarizerState = activeTargets.includes("summarizer") || activeTargets.includes("answer_now")
    ? "active"
    : (summary ? "ready" : (isWorkspaceBusy(loop, state) ? "waiting" : "ready"));
  const toolsState = providerTrace && (
    Number(providerTrace?.localToolCallCount || 0) > 0
    || Number(providerTrace?.githubToolCallCount || 0) > 0
  )
    ? "active"
    : (toolEnabled ? "ready" : "waiting");

  setTopologyNodeState(
    "topologyNodeCommander",
    "topologyMetaCommander",
    commanderState,
    commanderState === "active"
      ? (providerTraceStatusText(providerTrace) || "Lead draft / review pass")
      : "lead draft / review pass"
  );
  setTopologyNodeState(
    "topologyNodeWorkers",
    "topologyMetaWorkers",
    workersState,
    workersActive
      ? ("active lanes " + activeTargets.filter(function (target) { return /^[A-Z]$/.test(String(target || "")); }).join(", "))
      : (workerCount ? (String(workerCount) + " adversarial lane" + (workerCount === 1 ? "" : "s")) : "no workers configured")
  );
  setTopologyNodeState(
    "topologyNodeSummarizer",
    "topologyMetaSummarizer",
    summarizerState,
    activeTargets.includes("answer_now")
      ? "partial answer updating live"
      : (summary ? "single-voice answer ready" : "single-voice answer")
  );
  setTopologyNodeState(
    "topologyNodeTools",
    "topologyMetaTools",
    toolsState,
    toolEnabled ? "local + GitHub reads" : "tool plane idle"
  );

  $("#topologyNodeCount").text("4");
  $("#topologyEdgeCount").text(toolEnabled ? "3" : "2");
  $("#topologyActiveCount").text(
    [commanderState, workersState, summarizerState, toolsState].filter(function (value) {
      return value === "active";
    }).length || 0
  );
}

function workerFrontStatus(workerId, task, loop, state) {
  const activeTargets = activeFrontTargets(loop, state);
  const checkpoint = task?.stateWorkers?.[workerId] || null;
  if (activeTargets.includes(workerId)) {
    return { key: "running", label: "Working" };
  }
  if (checkpoint) {
    return { key: "completed", label: "Done" };
  }
  if (isWorkspaceBusy(loop, state)) {
    return { key: "waiting", label: "Waiting" };
  }
  return { key: "ready", label: "Ready" };
}

function summarizerFrontStatus(task, loop, state) {
  const activeTargets = activeFrontTargets(loop, state);
  if (activeTargets.includes("commander")) {
    return { key: "running", label: "Drafting" };
  }
  if (activeTargets.includes("commander_review")) {
    return { key: "running", label: "Reviewing" };
  }
  if (activeTargets.includes("summarizer")) {
    return { key: "running", label: "Summarizing" };
  }
  if (activeTargets.includes("answer_now")) {
    return { key: "running", label: "Answering" };
  }
  if (task?.summary) {
    return { key: "completed", label: "Done" };
  }
  if (task?.stateCommanderReview?.round || task?.stateCommander?.round) {
    return { key: isWorkspaceBusy(loop, state) ? "waiting" : "ready", label: isWorkspaceBusy(loop, state) ? "Waiting" : "Ready" };
  }
  if (isWorkspaceBusy(loop, state)) {
    return { key: "waiting", label: "Waiting" };
  }
  return { key: "ready", label: "Ready" };
}

function statusClassName(status) {
  return "is-" + String(status?.key || "ready");
}

function buildStatusBadge(status) {
  return $("<span>")
    .addClass("workercontrol-state " + statusClassName(status))
    .text(status?.label || "Ready");
}

function isWorkspaceBusy(loop, state) {
  return loop?.status === "running" || loop?.status === "queued" || activeDispatchCount(state) > 0;
}

function closeInlineHelpPopovers($except = $()) {
  $(".inline-help.open").not($except).removeClass("open");
  const activeElement = document.activeElement;
  const $activeHelp = $(activeElement).closest(".inline-help");
  if ($activeHelp.length && !$except.is($activeHelp)) {
    activeElement.blur();
  }
}

function updateAuthButtons() {
  const inputsLocked = latestLoopActive || activeDispatchCount(latestState) > 0;
  $(".add-auth-field").each(function () {
    const provider = String($(this).data("provider") || "openai");
    $(this).prop("disabled", inputsLocked || !authProviderGroup(provider).writable);
  });
  $(".clear-auth").each(function () {
    const provider = String($(this).data("provider") || "openai");
    const group = authProviderGroup(provider);
    $(this).prop("disabled", inputsLocked || !group.writable || !group.hasKey);
  });
  $(".auth-key-input, .auth-key-remove, .auth-mode-toggle").each(function () {
    const provider = String($(this).data("provider") || $(this).closest(".auth-key-row").data("provider") || "openai");
    const group = authProviderGroup(provider);
    const keyControl = $(this).hasClass("auth-key-input") || $(this).hasClass("auth-key-remove");
    $(this).prop("disabled", inputsLocked || (keyControl && !group.writable));
  });
}

function formatKeyCountLabel(count) {
  const total = Math.max(0, Number(count || 0));
  if (!total) return "none";
  return total === 1 ? "1 key" : total + " keys";
}

function nextAuthRowId() {
  authRowSequence += 1;
  return "auth-row-" + authRowSequence;
}

function compactMaskedKey(masked) {
  const text = String(masked || "").trim();
  if (!text) return "masked";
  const last4 = text.slice(-4);
  return "\u2022\u2022\u2022\u2022" + last4;
}

function authProviderGroup(provider) {
  const normalized = String(provider || "openai").trim().toLowerCase();
  const group = latestAuthStatus.providerGroups?.[normalized];
  if (group && typeof group === "object") return group;
  return {
    provider: normalized,
    label: normalized,
    hasKey: false,
    keyCount: 0,
    masks: [],
    selectedMode: latestAuthStatus.defaultMode || "safe",
    selectedModeLabel: (latestAuthStatus.defaultMode || "safe") === "local" ? "Local" : "Safe",
    effectiveBackend: latestAuthStatus.recommendedBackend || "env",
    safeBackend: latestAuthStatus.recommendedBackend || "env",
    writable: !!latestAuthStatus.writable,
    failureMode: "",
    failureDetail: ""
  };
}

function ensureAuthDynamicRows(provider) {
  const normalized = String(provider || "openai").trim().toLowerCase();
  if (!authProviderGroup(normalized).writable) return;
  if (!authDynamicRowsByProvider[normalized]) authDynamicRowsByProvider[normalized] = [];
  const group = authProviderGroup(normalized);
  if (group.hasKey || authDynamicRowsByProvider[normalized].length) return;
  authDynamicRowsByProvider[normalized].push({ id: nextAuthRowId(), value: "" });
}

function resetAuthDynamicRows(provider = null) {
  if (provider) {
    const normalized = String(provider || "openai").trim().toLowerCase();
    authDynamicRowsByProvider[normalized] = [];
    ensureAuthDynamicRows(normalized);
    return;
  }
  authDynamicRowsByProvider = {};
  (latestAuthStatus.providerOrder || []).forEach(function (providerId) {
    ensureAuthDynamicRows(providerId);
  });
}

function authDynamicRows(provider) {
  const normalized = String(provider || "openai").trim().toLowerCase();
  ensureAuthDynamicRows(normalized);
  return authDynamicRowsByProvider[normalized] || [];
}

function updateAuthDynamicRow(provider, rowId, value) {
  const normalized = String(provider || "openai").trim().toLowerCase();
  authDynamicRowsByProvider[normalized] = authDynamicRows(normalized).map(function (row) {
    return row.id === rowId ? Object.assign({}, row, { value: value }) : row;
  });
}

function removeAuthDynamicRow(provider, rowId) {
  const normalized = String(provider || "openai").trim().toLowerCase();
  authDynamicRowsByProvider[normalized] = authDynamicRows(normalized).filter(function (row) {
    return row.id !== rowId;
  });
  ensureAuthDynamicRows(normalized);
}

function authPreviewRotationOffset(keyCount) {
  const total = Math.max(0, Number(keyCount || 0));
  if (total <= 1) return 0;
  const taskId = String(latestState?.activeTask?.taskId || "").trim();
  const commanderRound = Number(latestState?.commander?.round || 0);
  const summaryRound = Number(latestState?.summary?.round || 0);
  const roundBase = Math.max(commanderRound, summaryRound, 1) - 1;
  let hash = 0;
  for (let index = 0; index < taskId.length; index += 1) {
    hash = (hash * 31 + taskId.charCodeAt(index)) >>> 0;
  }
  return (hash + Math.max(0, roundBase)) % total;
}

function authPositionPlan() {
  const workerProvider = normalizeProviderId($("#provider").val() || runtimeProviderSource(latestState?.activeTask || null, latestState?.draft || null));
  const summarizerProvider = normalizeProviderId($("#summarizerProvider").val() || summarizerProviderSource(latestState?.activeTask || null, latestState?.draft || null));
  const directMode = normalizeDirectBaselineMode($("#directBaselineMode").val());
  const directProvider = normalizeProviderId($("#directProvider").val() || workerProvider);
  const visibleWorkers = $("#workerControls .workercontrol[data-worker-id]").length
    ? collectVisibleWorkerRoster()
    : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null);
  const positions = [{ id: "commander", label: "Commander", provider: workerProvider }];
  (visibleWorkers || []).forEach(function (worker) {
    const workerId = String(worker?.id || "").trim().toUpperCase();
    if (!workerId) return;
    positions.push({
      id: workerId,
      label: workerId + " / " + displayWorkerLabel(worker),
      provider: workerProvider
    });
  });
  positions.push({ id: "commander_review", label: "Commander Review", provider: workerProvider });
  positions.push({ id: "summarizer", label: "Summarizer", provider: summarizerProvider });
  if (directMode !== "off") {
    positions.push({ id: "direct_baseline", label: "Single-thread baseline", provider: directProvider });
  }
  return positions;
}

function buildAuthAssignments(group) {
  const masks = Array.isArray(group?.masks) ? group.masks.filter(Boolean) : [];
  const keyCount = Math.max(0, Number(group?.keyCount || masks.length || 0));
  if (!keyCount || !masks.length) return [];
  const rotationOffset = authPreviewRotationOffset(keyCount);
  const providerId = normalizeProviderId(group?.provider || "openai");
  const positions = authPositionPlan().filter(function (position) {
    return normalizeProviderId(position.provider || "openai") === providerId;
  });
  return positions.map(function (position, index) {
    const keyIndex = (index + rotationOffset) % keyCount;
    return {
      label: position.label,
      keySlot: keyIndex + 1,
      masked: compactMaskedKey(masks[keyIndex] || ("slot " + (keyIndex + 1))),
      reused: index >= keyCount
    };
  });
}

function renderAuthProviderCards(force = false) {
  const $root = $("#authProviderCards");
  if (!$root.length) return;
  if (!force && hasFocusWithin("#authProviderCards")) return;

  const recommended = String(latestAuthStatus.recommendedBackend || "env");
  const inputsLocked = latestLoopActive || activeDispatchCount(latestState) > 0;
  const cards = (latestAuthStatus.providerOrder || []).map(function (providerId) {
    const group = authProviderGroup(providerId);
    const groupWritable = !!group.writable;
    const selectedMode = String(group.selectedMode || latestAuthStatus.defaultMode || "safe");
    const localActive = selectedMode === "local";
    const modeSummary = localActive
      ? "Local -> shared Auth.txt using provider prefixes."
      : ("Safe -> " + String(group.effectiveBackend || group.safeBackend || recommended));
    const rows = [];

    if (!groupWritable) {
      rows.push(`
        <div class="auth-key-row auth-key-row-readonly">
          <div class="auth-key-row-head">
            <div>
              <div class="auth-key-row-label">Read-only safe backend</div>
              <div class="auth-key-row-meta">${escapeHtml(group.failureDetail || latestAuthStatus.statusNote || "This backend is not editable from the browser.")}</div>
            </div>
          </div>
          <div class="auth-key-row-inputs">
            <input class="auth-key-input" type="text" value="${escapeHtml("Mode: Safe | Backend: " + (group.effectiveBackend || recommended))}" disabled />
          </div>
        </div>
      `);
    } else {
      (group.masks || []).forEach(function (masked, index) {
        rows.push(`
          <div class="auth-key-row" data-provider="${escapeHtml(providerId)}" data-auth-mode="stored" data-slot-index="${index}">
            <div class="auth-key-row-head">
              <div>
                <div class="auth-key-row-label">Slot ${index + 1}</div>
                <div class="auth-key-row-meta">Stored now as ${escapeHtml(compactMaskedKey(masked))}. Paste a replacement to swap it.</div>
              </div>
            </div>
            <div class="auth-key-row-inputs">
              <input class="auth-key-input" type="password" autocomplete="off" spellcheck="false" placeholder="Paste replacement key for slot ${index + 1}" ${inputsLocked ? "disabled" : ""} />
              <button type="button" class="auth-key-remove danger" data-provider="${escapeHtml(providerId)}" data-remove-mode="stored" data-slot-index="${index}" ${inputsLocked ? "disabled" : ""}>Remove</button>
            </div>
          </div>
        `);
      });

      authDynamicRows(providerId).forEach(function (row, index) {
        rows.push(`
          <div class="auth-key-row" data-provider="${escapeHtml(providerId)}" data-auth-mode="new" data-row-id="${escapeHtml(row.id)}">
            <div class="auth-key-row-head">
              <div>
                <div class="auth-key-row-label">New key ${index + 1}</div>
                <div class="auth-key-row-meta">Paste a ${escapeHtml(group.label)} key here and it will append into shared Auth.txt using the ${escapeHtml(providerId === "anthropic" ? "ant" : providerId === "minimax" ? "min" : providerId)} prefix.</div>
              </div>
            </div>
            <div class="auth-key-row-inputs">
              <input class="auth-key-input" type="password" autocomplete="off" spellcheck="false" placeholder="Paste new ${escapeHtml(group.label)} API key" value="${escapeHtml(row.value || "")}" ${inputsLocked ? "disabled" : ""} />
              <button type="button" class="auth-key-remove" data-provider="${escapeHtml(providerId)}" data-remove-mode="new" data-row-id="${escapeHtml(row.id)}" ${inputsLocked ? "disabled" : ""}>Remove</button>
            </div>
          </div>
        `);
      });
    }

    const previewBits = [];
    (group.masks || []).forEach(function (masked, index) {
      previewBits.push(`<span class="key-slot-chip">Slot ${index + 1} ${escapeHtml(compactMaskedKey(masked))}</span>`);
    });
    if (!previewBits.length) {
      previewBits.push(`<span class="key-slot-chip">${escapeHtml(group.failureDetail || ("No " + group.label + " keys configured."))}</span>`);
    }

    const assignmentBits = [];
    buildAuthAssignments(group).forEach(function (assignment) {
      assignmentBits.push(
        `<span class="key-slot-chip${assignment.reused ? " reused" : ""}"${assignment.reused ? ' title="This position reuses an earlier key because the pool is smaller than the lane count."' : ""}>${escapeHtml(assignment.label + " -> slot " + assignment.keySlot + " " + assignment.masked)}</span>`
      );
    });
    if (!assignmentBits.length) {
      assignmentBits.push(`<span class="key-slot-chip">No active lanes are currently routed to ${escapeHtml(group.label)}.</span>`);
    }

    return `
      <div class="auth-provider-card${group.hasKey ? "" : " is-empty"}" data-provider-card="${escapeHtml(providerId)}">
        <div class="auth-provider-card-head">
          <div class="auth-provider-card-title">${escapeHtml(group.label)}</div>
          <span class="secretmask">${escapeHtml(formatKeyCountLabel(group.keyCount))}</span>
        </div>
        <div class="auth-provider-card-meta">${escapeHtml(modeSummary)}</div>
        <div class="auth-provider-card-meta">${escapeHtml(group.failureDetail || (group.hasKey ? (group.label + " keys available.") : ("No " + group.label + " keys configured.")))}</div>
        <div class="auth-mode-switch" role="group" aria-label="${escapeHtml(group.label + " credential mode")}">
          <button type="button" class="auth-mode-toggle${localActive ? " active" : ""}" data-provider="${escapeHtml(providerId)}" data-auth-mode="local" ${inputsLocked ? "disabled" : ""}>Local</button>
          <button type="button" class="auth-mode-toggle${!localActive ? " active" : ""}" data-provider="${escapeHtml(providerId)}" data-auth-mode="safe" ${inputsLocked ? "disabled" : ""}>Safe</button>
        </div>
        <div class="key-pool-preview">${previewBits.join("")}</div>
        <div class="key-assignment-list">${assignmentBits.join("")}</div>
        <div class="auth-key-editor">${rows.join("")}</div>
        <div class="integration-actions integration-actions-split">
          <button type="button" class="add-auth-field" data-provider="${escapeHtml(providerId)}" ${(!groupWritable || inputsLocked) ? "disabled" : ""}>+ Key</button>
          <button type="button" class="clear-auth danger" data-provider="${escapeHtml(providerId)}" ${(!groupWritable || inputsLocked) ? "disabled" : ""}>Clear</button>
        </div>
      </div>
    `;
  });

  $root.html(cards.join(""));
}

function renderAuthEditor(force = false) {
  renderAuthProviderCards(force);
}

function renderAuthPoolPreview() {
  renderAuthProviderCards(false);
}

function renderAuthStatus(data) {
  const providerOrder = Array.isArray(data?.providerOrder) && data.providerOrder.length
    ? data.providerOrder.map(function (providerId) { return String(providerId || "").trim().toLowerCase(); }).filter(Boolean)
    : ["openai", "anthropic", "xai", "minimax"];
  const rawGroups = data?.providerGroups && typeof data.providerGroups === "object" ? data.providerGroups : {};
  const providerGroups = {};
  providerOrder.forEach(function (providerId) {
    const group = rawGroups[providerId] || {};
    providerGroups[providerId] = {
      provider: providerId,
      label: String(group.label || providerId),
      hasKey: !!group.hasKey,
      keyCount: Number(group.keyCount || 0),
      masks: Array.isArray(group.masks) ? group.masks.filter(Boolean) : [],
      selectedMode: String(group.selectedMode || data?.defaultMode || "safe"),
      selectedModeLabel: String(group.selectedModeLabel || (String(group.selectedMode || data?.defaultMode || "safe") === "local" ? "Local" : "Safe")),
      effectiveBackend: String(group.effectiveBackend || data?.backend || "env"),
      safeBackend: String(group.safeBackend || data?.recommendedBackend || "env"),
      writable: !!group.writable,
      managed: !!group.managed,
      failureMode: String(group.failureMode || ""),
      failureDetail: String(group.failureDetail || "")
    };
  });
  latestAuthStatus = {
    hasKey: !!data?.hasKey,
    keyCount: Number(data?.keyCount || 0),
    backend: String(data?.backend || "env"),
    writable: !!data?.writable,
    preferred: data?.preferred !== false,
    deprecated: !!data?.deprecated,
    preferredBackends: Array.isArray(data?.preferredBackends) ? data.preferredBackends : [],
    recommendedBackend: String(data?.recommendedBackend || "env"),
    defaultMode: String(data?.defaultMode || "safe"),
    statusNote: String(data?.statusNote || ""),
    rotationPolicy: data?.rotationPolicy || null,
    providerOrder: providerOrder,
    providerGroups: providerGroups,
    isolationNote: String(data?.isolationNote || ""),
    termsWarning: String(data?.termsWarning || "")
  };

  $("#apiKeyMasked").text(formatKeyCountLabel(latestAuthStatus.keyCount));
  const statusParts = [];
  if (latestAuthStatus.statusNote) statusParts.push(latestAuthStatus.statusNote);
  if (latestAuthStatus.deprecated) statusParts.push("Browser mutation stays enabled only for this transitional backend.");
  if (latestAuthStatus.rotationPolicy?.summary) statusParts.push("Rotation: " + latestAuthStatus.rotationPolicy.summary);
  if (!latestAuthStatus.hasKey) statusParts.push("Live mode needs at least one provider key.");
  $("#apiKeyStatus").text(statusParts.join(" "));
  $("#apiKeyIsolation").text(latestAuthStatus.isolationNote || "");
  $("#apiKeyTermsWarning").text(latestAuthStatus.termsWarning || "");
  renderAuthProviderCards(true);
  updateAuthButtons();
}

function refreshAuth() {
  $.getJSON(apiRoute(API.authStatus))
    .done(function (data) {
      renderAuthStatus(data);
    })
    .fail(function () {
      latestAuthStatus = {
        hasKey: false,
        keyCount: 0,
        backend: "env",
        writable: false,
        preferred: true,
        deprecated: false,
        preferredBackends: ["env", "external"],
        recommendedBackend: "env",
        defaultMode: "safe",
        statusNote: "",
        rotationPolicy: null,
        providerOrder: ["openai", "anthropic", "xai", "minimax"],
        providerGroups: {},
        isolationNote: "",
        termsWarning: ""
      };
      $("#apiKeyMasked").text("unavailable");
      $("#apiKeyStatus").text("Auth status could not be loaded.");
      $("#apiKeyIsolation").text("");
      $("#apiKeyTermsWarning").text("");
      $("#authProviderCards").html('<div class="integration-note">Auth status could not be loaded.</div>');
      updateAuthButtons();
    });
}

function clearAuthSaveTimer(timerKey) {
  if (!timerKey || !authSaveTimers[timerKey]) return;
  clearTimeout(authSaveTimers[timerKey]);
  delete authSaveTimers[timerKey];
}

function authSaveMeta(timerKey) {
  if (!authRowSaveState[timerKey]) {
    authRowSaveState[timerKey] = {
      inFlight: false,
      pendingValue: "",
      lastSubmitted: ""
    };
  }
  return authRowSaveState[timerKey];
}

function clearAuthSaveMeta(timerKey) {
  if (!timerKey) return;
  delete authRowSaveState[timerKey];
}

function handleAuthMutationSuccess(resp, successText, options = {}) {
  let out = resp;
  try { out = JSON.parse(resp); } catch (_) {}
  showMessage(successText + (out.message ? " | " + out.message : ""));
  if (typeof options.onSuccess === "function") {
    options.onSuccess(out);
  }
  refreshState();
}

function persistAuthSlot(slotIndex, apiKey, provider) {
  const trimmed = String(apiKey || "").trim();
  if (!trimmed || latestLoopActive) return;
  const normalizedProvider = String(provider || "openai").trim().toLowerCase();
  const timerKey = normalizedProvider + ":stored-" + String(slotIndex);
  const meta = authSaveMeta(timerKey);
  if (meta.inFlight || meta.lastSubmitted === trimmed) return;
  meta.inFlight = true;
  meta.pendingValue = trimmed;
  $.post(apiRoute(API.authKeys), { provider: normalizedProvider, replaceIndex: slotIndex, apiKey: trimmed })
    .done(function (resp) {
      meta.inFlight = false;
      meta.lastSubmitted = trimmed;
      handleAuthMutationSuccess(resp, authProviderGroup(normalizedProvider).label + " API key slot updated", {
        onSuccess: function () {
          renderAuthProviderCards(true);
        }
      });
    })
    .fail(function (xhr) {
      meta.inFlight = false;
      showMessage(authProviderGroup(normalizedProvider).label + " API key slot update failed: " + extractErrorMessage(xhr), true);
    });
}

function appendAuthKey(rowId, apiKey, provider) {
  const trimmed = String(apiKey || "").trim();
  if (!trimmed || latestLoopActive) return;
  const normalizedProvider = String(provider || "openai").trim().toLowerCase();
  const timerKey = normalizedProvider + ":" + rowId;
  const meta = authSaveMeta(timerKey);
  if (meta.inFlight || meta.lastSubmitted === trimmed) return;
  meta.inFlight = true;
  meta.pendingValue = trimmed;
  $.post(apiRoute(API.authKeys), { provider: normalizedProvider, appendKey: trimmed })
    .done(function (resp) {
      meta.inFlight = false;
      meta.lastSubmitted = trimmed;
      handleAuthMutationSuccess(resp, authProviderGroup(normalizedProvider).label + " API key added", {
        onSuccess: function () {
          removeAuthDynamicRow(normalizedProvider, rowId);
          clearAuthSaveMeta(timerKey);
          renderAuthProviderCards(true);
        }
      });
    })
    .fail(function (xhr) {
      meta.inFlight = false;
      showMessage(authProviderGroup(normalizedProvider).label + " API key append failed: " + extractErrorMessage(xhr), true);
    });
}

function removeAuthSlot(slotIndex, provider) {
  const normalizedProvider = String(provider || "openai").trim().toLowerCase();
  $.post(apiRoute(API.authKeys), { provider: normalizedProvider, removeIndex: slotIndex })
    .done(function (resp) {
      handleAuthMutationSuccess(resp, authProviderGroup(normalizedProvider).label + " API key removed", {
        onSuccess: function () {
          renderAuthProviderCards(true);
        }
      });
    })
    .fail(function (xhr) {
      showMessage(authProviderGroup(normalizedProvider).label + " API key removal failed: " + extractErrorMessage(xhr), true);
    });
}

function scheduleAuthRowSave($input, immediate = false) {
  if (!$input || !$input.length) return;
  const $row = $input.closest(".auth-key-row");
  const provider = String($row.data("provider") || "openai").trim().toLowerCase();
  const mode = String($row.data("authMode") || "");
  const rowId = String($row.data("rowId") || "");
  const slotIndex = Number($row.data("slotIndex"));
  const value = String($input.val() || "");
  const timerKey = provider + ":" + (mode === "stored" ? "stored-" + slotIndex : rowId);
  const trimmed = value.trim();
  const meta = authSaveMeta(timerKey);

  if (mode === "new" && rowId) {
    updateAuthDynamicRow(provider, rowId, value);
  }

  if (trimmed !== meta.pendingValue) {
    meta.lastSubmitted = "";
  }
  meta.pendingValue = trimmed;

  clearAuthSaveTimer(timerKey);

  const runner = function () {
    if (!trimmed) return;
    if (mode === "stored") {
      persistAuthSlot(slotIndex, trimmed, provider);
      return;
    }
    appendAuthKey(rowId, trimmed, provider);
  };

  if (immediate) {
    runner();
    return;
  }

  authSaveTimers[timerKey] = setTimeout(function () {
    delete authSaveTimers[timerKey];
    runner();
  }, 450);
}

function applyArtifactSelectionPair(leftArtifact, rightArtifact) {
  const artifacts = latestHistoryState?.artifacts || [];
  const names = new Set(artifacts.map(function (artifact) { return artifact.name; }));

  artifactSelections.left = leftArtifact && names.has(leftArtifact) ? leftArtifact : "";
  artifactSelections.right = rightArtifact && names.has(rightArtifact) ? rightArtifact : "";

  if (!artifactSelections.left) {
    const fallbackLeft = pickArtifact(artifacts, ["summary_output", "commander_review_output", "commander_output", "worker_output", "summary_round", "commander_review_round", "commander_round", "worker_step"], "");
    artifactSelections.left = fallbackLeft ? fallbackLeft.name : "";
  }
  if (!artifactSelections.right || artifactSelections.right === artifactSelections.left) {
    const fallbackRight = pickArtifact(artifacts, ["commander_review_output", "commander_output", "worker_output", "summary_output", "commander_review_round", "commander_round", "worker_step", "summary_round"], artifactSelections.left);
    artifactSelections.right = fallbackRight ? fallbackRight.name : "";
  }

  $("#artifactLeftSelect").html(buildArtifactOptions(artifacts, artifactSelections.left));
  $("#artifactRightSelect").html(buildArtifactOptions(artifacts, artifactSelections.right));

  loadArtifactPane("Left", artifactSelections.left);
  loadArtifactPane("Right", artifactSelections.right);
}

function renderJobHistory(jobs, recoveryWarning, queueLimit, contractWarnings) {
  const sections = [];
  const topLevelWarnings = Array.isArray(contractWarnings) ? contractWarnings.filter(Boolean) : [];

  if (topLevelWarnings.length) {
    sections.push(`
      <article class="history-card warning">
        <div class="history-title">Telemetry note</div>
        <div class="history-meta">${escapeHtml(topLevelWarnings.join(" | "))}</div>
      </article>
    `);
  }

  if (recoveryWarning) {
    sections.push(`
      <article class="history-card warning">
        <div class="history-title">Recovery note</div>
        <div class="history-meta">${escapeHtml(recoveryWarning)}</div>
      </article>
    `);
  }

  sections.push(`
    <article class="history-card">
      <div class="history-title">Queue policy</div>
      <div class="history-meta">Background loops can queue up to ${formatInteger(queueLimit || 0)} jobs. Target dispatches run as independent background jobs, and Answer Now can summarize from current checkpoints while other lanes are still running.</div>
    </article>
  `);

  if (!jobs || !jobs.length) {
    sections.push(`<div class="review-empty">No recent jobs yet.</div>`);
    return `<div class="history-stack">${sections.join("")}</div>`;
  }

  jobs.forEach(function (job) {
    const isTargetJob = String(job.jobType || "loop") === "target";
    const jobHealth = job?.executionHealth || null;
    const tone = jobExecutionHealthTone(jobHealth);
    const contractWarnings = Array.isArray(job?.contractWarnings) ? job.contractWarnings.filter(Boolean) : [];
    const title = truncateText(
      isTargetJob
        ? ((job.target === "answer_now" ? "Answer Now" : ("Dispatch " + String(job.target || "target"))) + " | " + (job.objective || job.taskId || job.jobId || "job"))
        : (job.objective || job.taskId || job.jobId || "Unknown job"),
      140
    );
    const metaLines = isTargetJob ? [
      "Status: " + (job.status || "unknown") + " | target " + String(job.target || "target") + (job.partialSummary ? " | partial summary" : ""),
      "Attempt " + formatInteger(job.attempt || 1) + " | tokens " + formatInteger(job.totalTokens || 0) + " | spend " + formatUsd(job.estimatedCostUsd || 0),
      "Queued " + (job.queuedAt || "n/a") + " | started " + (job.startedAt || "n/a") + " | finished " + (job.finishedAt || "n/a")
    ] : [
      "Status: " + (job.status || "unknown") + " | rounds " + formatInteger(job.completedRounds || 0) + "/" + formatInteger(job.rounds || 0) + " | workers " + formatInteger(job.workerCount || 0),
      "Attempt " + formatInteger(job.attempt || 1) + " | tokens " + formatInteger(job.totalTokens || 0) + " | spend " + formatUsd(job.estimatedCostUsd || 0),
      "Queued " + (job.queuedAt || "n/a") + " | started " + (job.startedAt || "n/a") + " | finished " + (job.finishedAt || "n/a")
    ];

    if (!isTargetJob && Number(job.queuePosition || 0) > 0) {
      metaLines.push("Queue position: " + formatInteger(job.queuePosition));
    }
    if (!isTargetJob && job.resumeOfJobId) {
      metaLines.push("Resume of: " + job.resumeOfJobId + " | resumed from round " + formatInteger(job.resumeFromRound || 1));
    } else if (!isTargetJob && job.retryOfJobId) {
      metaLines.push("Retry of: " + job.retryOfJobId);
    } else if (!isTargetJob && job.canResume) {
      metaLines.push("Resume point: round " + formatInteger(job.resumeFromRound || 1));
    }
    if (isTargetJob && job.batchId) {
      metaLines.push("Batch: " + job.batchId);
    }
    if (job.lastMessage) {
      metaLines.push("Note: " + job.lastMessage);
    }
    const jobTraceSummary = providerTraceReviewLine(job?.metadata?.providerTrace);
    if (jobTraceSummary) {
      metaLines.push("Provider trace: " + jobTraceSummary);
    }
    if (job.error) {
      metaLines.push("Error: " + job.error);
    }
    if (contractWarnings.length) {
      metaLines.push("Contract: " + contractWarnings.join(" | "));
    }
    metaLines.push("Execution: " + formatJobExecutionSummary(jobHealth));

    const actions = [];
    if (job.canResume) {
      actions.push(`<button type="button" class="manage-job" data-job-id="${escapeHtml(job.jobId || "")}" data-action="resume">Resume</button>`);
    }
    if (job.canRetry) {
      actions.push(`<button type="button" class="manage-job" data-job-id="${escapeHtml(job.jobId || "")}" data-action="retry">Retry</button>`);
    }
    if (job.canCancel) {
      actions.push(`<button type="button" class="manage-job danger" data-job-id="${escapeHtml(job.jobId || "")}" data-action="cancel">Cancel</button>`);
    }

    sections.push(`
      <article class="history-card${tone === "error" ? " error" : ""}${tone === "warning" ? " warning" : ""}${tone === "recovered" ? " recovered" : ""}${tone === "active" ? " active" : ""}">
        <div class="history-head">
          <div class="history-title">${escapeHtml(title)}</div>
          <div class="round-history-head-right">
            ${renderJobExecutionBadge(jobHealth)}
            <div class="history-title">${escapeHtml(job.jobId || "job")}</div>
          </div>
        </div>
        <div class="history-meta">${escapeHtml(metaLines.join("\n"))}</div>
        ${actions.length ? `<div class="history-actions">${actions.join("")}</div>` : ""}
      </article>
    `);
  });

  return `<div class="history-stack">${sections.join("")}</div>`;
}

function renderRoundHistory(rounds) {
  if (!rounds || !rounds.length) {
    return `<div class="review-empty">No round history yet.</div>`;
  }

  const summaryByTaskRound = {};
  (rounds || []).forEach(function (roundEntry) {
    if (roundEntry?.summaryArtifact?.name) {
      summaryByTaskRound[String(roundEntry.taskId || "") + ":" + String(roundEntry.round || "")] = roundEntry.summaryArtifact;
    }
  });

  return `
    <div class="round-history-stack">
      ${rounds.map(function (roundEntry) {
        const commanderArtifact = roundEntry.commanderArtifact || null;
        const commanderReviewArtifact = roundEntry.commanderReviewArtifact || null;
        const directBaselineArtifact = roundEntry.directBaselineArtifact || null;
        const summaryArtifact = roundEntry.summaryArtifact || null;
        const executionHealth = roundEntry.executionHealth || null;
        const tone = executionHealthTone(executionHealth);
        const previousSummary = summaryByTaskRound[String(roundEntry.taskId || "") + ":" + String(Number(roundEntry.round || 0) - 1)] || null;
        const primaryWorker = Array.isArray(roundEntry.workerArtifacts) && roundEntry.workerArtifacts.length ? roundEntry.workerArtifacts[0] : null;
        const topActions = [];

        if (summaryArtifact && directBaselineArtifact) {
          topActions.push(`<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(directBaselineArtifact.name)}">Summary vs baseline</button>`);
        }
        if (summaryArtifact && commanderReviewArtifact) {
          topActions.push(`<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(commanderReviewArtifact.name)}">Summary vs review</button>`);
        }
        if (summaryArtifact && commanderArtifact) {
          topActions.push(`<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(commanderArtifact.name)}">Summary vs commander</button>`);
        }
        if (summaryArtifact && primaryWorker) {
          topActions.push(`<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(primaryWorker.name)}">Summary vs lane</button>`);
        }
        if (summaryArtifact && previousSummary) {
          topActions.push(`<button type="button" class="load-round-compare" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(previousSummary.name)}">Summary vs previous</button>`);
        }
        if (!summaryArtifact && directBaselineArtifact && primaryWorker) {
          topActions.push(`<button type="button" class="load-artifact-pair" data-left="${escapeHtml(directBaselineArtifact.name)}" data-right="${escapeHtml(primaryWorker.name)}">Baseline vs lane</button>`);
        }

        return `
          <article class="round-history-card${executionHealth?.degraded ? " " + tone : ""}">
            <div class="round-history-head">
              <div class="round-history-title">Round ${escapeHtml(String(roundEntry.round || 0))}</div>
              <div class="round-history-head-right">
                ${renderExecutionHealthBadge(executionHealth)}
                <div class="round-history-title">${escapeHtml(roundEntry.taskId || "task")}</div>
              </div>
            </div>
            <div class="round-history-meta">${escapeHtml(truncateText(roundEntry.objective || "No objective recorded.", 180))}</div>
            <div class="round-history-meta">${escapeHtml("Captured " + (roundEntry.capturedAt || "n/a") + (summaryArtifact ? " | summary " + summaryArtifact.name + " | " + artifactOutputCapSummary(summaryArtifact) : ""))}</div>
            <div class="round-history-meta">${escapeHtml(formatExecutionHealthSummary(executionHealth))}</div>
            ${summaryArtifact && providerTraceReviewLine(summaryArtifact.providerTrace) ? `<div class="round-history-meta">${escapeHtml("Summary trace " + providerTraceReviewLine(summaryArtifact.providerTrace))}</div>` : ""}
            ${directBaselineArtifact ? `<div class="round-history-meta">${escapeHtml("Single-thread baseline " + directBaselineArtifact.name + " | " + artifactOutputCapSummary(directBaselineArtifact))}</div>` : ""}
            ${directBaselineArtifact && providerTraceReviewLine(directBaselineArtifact.providerTrace) ? `<div class="round-history-meta">${escapeHtml("Baseline trace " + providerTraceReviewLine(directBaselineArtifact.providerTrace))}</div>` : ""}
            ${commanderArtifact ? `<div class="round-history-meta">${escapeHtml("Commander draft " + commanderArtifact.name + " | " + artifactOutputCapSummary(commanderArtifact))}</div>` : ""}
            ${commanderArtifact && providerTraceReviewLine(commanderArtifact.providerTrace) ? `<div class="round-history-meta">${escapeHtml("Commander trace " + providerTraceReviewLine(commanderArtifact.providerTrace))}</div>` : ""}
            ${commanderReviewArtifact ? `<div class="round-history-meta">${escapeHtml("Commander review " + commanderReviewArtifact.name + " | " + artifactOutputCapSummary(commanderReviewArtifact))}</div>` : ""}
            ${commanderReviewArtifact && providerTraceReviewLine(commanderReviewArtifact.providerTrace) ? `<div class="round-history-meta">${escapeHtml("Review trace " + providerTraceReviewLine(commanderReviewArtifact.providerTrace))}</div>` : ""}
            ${topActions.length ? `<div class="round-history-actions">${topActions.join("")}</div>` : ""}
            <div class="round-history-workers">
              ${(roundEntry.workerArtifacts || []).map(function (artifact) {
                return `
                  <div class="round-worker-row">
                      <div>
                        <div class="history-title">${escapeHtml((artifact.worker || "worker") + " | " + (artifact.model || "model n/a"))} ${renderArtifactExecutionBadge(artifact)}</div>
                        <div class="round-worker-meta">${escapeHtml((artifact.name || "artifact") + " | " + artifactOutputCapSummary(artifact))}</div>
                        ${providerTraceReviewLine(artifact.providerTrace) ? `<div class="round-worker-meta">${escapeHtml("Trace " + providerTraceReviewLine(artifact.providerTrace))}</div>` : ""}
                      </div>
                     ${summaryArtifact
                        ? `<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(artifact.name)}">Compare vs summary</button>`
                        : (directBaselineArtifact ? `<button type="button" class="load-artifact-pair" data-left="${escapeHtml(directBaselineArtifact.name)}" data-right="${escapeHtml(artifact.name)}">Compare vs baseline</button>` : "")}
                   </div>
                 `;
               }).join("") || `<div class="review-empty small">No worker output artifacts were captured for this round.</div>`}
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderSessionArchives(sessions) {
  if (!sessions || !sessions.length) {
    return `<div class="review-empty">No session archives yet.</div>`;
  }

  return `
    <div class="session-archive-stack">
      ${sessions.map(function (session) {
        const contractWarnings = Array.isArray(session.contractWarnings) ? session.contractWarnings.filter(Boolean) : [];
        return `
          <article class="session-archive-card${contractWarnings.length ? " warning" : ""}">
            <div class="session-archive-head">
              <div class="session-archive-title">${escapeHtml(session.file || "archive")}</div>
              <div class="round-history-head-right">
                ${contractWarnings.length ? renderExecutionHealthBadge({ degraded: true, fallbackCount: 0, recoveredCount: 0 }, "Warning") : ""}
                <div class="session-archive-title">${escapeHtml(session.taskId || "no task")}</div>
              </div>
            </div>
            <div class="session-archive-meta">${escapeHtml("Archived " + (session.archivedAt || "n/a") + " | reason " + (session.reason || "unspecified"))}</div>
            <div class="session-archive-meta">${escapeHtml(session.carryContextPreview || "No carry-forward preview.")}</div>
            ${contractWarnings.length ? `<div class="session-archive-meta">${escapeHtml("Contract: " + contractWarnings.join(" | "))}</div>` : ""}
            <div class="session-archive-actions">
              <button type="button" class="export-archive" data-archive-file="${escapeHtml(session.file || "")}">Preview export</button>
              <button type="button" class="replay-session" data-archive-file="${escapeHtml(session.file || "")}">Replay</button>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderArtifactPolicy(policy) {
  if (!policy || typeof policy !== "object") {
    return `<div class="review-empty">No policy data.</div>`;
  }

  return `
    <div class="history-stack">
      <article class="policy-card">
        <div class="history-title">Surface policy</div>
        <div class="policy-copy">${escapeHtml("Public thread: " + (policy.publicThread || "structured_only"))}</div>
        <div class="policy-copy">${escapeHtml("Review: " + (policy.reviewSurface || "raw_output_exception"))}</div>
        <div class="policy-copy">${escapeHtml("Export: " + (policy.exportSurface || "raw_output_exception"))}</div>
      </article>
      ${(policy.rules || []).map(function (rule) {
        return `
          <article class="policy-card">
            <div class="policy-copy">${escapeHtml(rule)}</div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function suggestDefaultEvalArmIds(arms) {
  const list = Array.isArray(arms) ? arms : [];
  const picks = [];
  const direct = list.find(function (arm) { return arm?.type === "direct"; });
  const steered = list.find(function (arm) { return arm?.type === "steered"; });
  if (direct?.armId) picks.push(direct.armId);
  if (steered?.armId) picks.push(steered.armId);
  list.forEach(function (arm) {
    if (picks.length >= 2) return;
    if (arm?.armId && !picks.includes(arm.armId)) {
      picks.push(arm.armId);
    }
  });
  return picks;
}

function currentSelectedEvalArmIds() {
  const ids = [];
  $("#evalArmList .eval-arm-checkbox:checked").each(function () {
    const armId = String($(this).val() || "").trim();
    if (armId) ids.push(armId);
  });
  return ids;
}

function buildEvalSuiteOptions(suites, selectedSuiteId) {
  const options = [`<option value="">Choose suite</option>`];
  (suites || []).forEach(function (suite) {
    const suiteId = String(suite?.suiteId || "");
    const selected = suiteId === selectedSuiteId ? " selected" : "";
    options.push(`<option value="${escapeHtml(suiteId)}"${selected}>${escapeHtml((suite?.title || suiteId) + " (" + Number(suite?.caseCount || 0) + " cases)")}</option>`);
  });
  return options.join("");
}

function renderEvalArmList(arms) {
  const $root = $("#evalArmList");
  const selectedIds = currentSelectedEvalArmIds();
  const effectiveSelected = selectedIds.length ? selectedIds : suggestDefaultEvalArmIds(arms);
  if (!$root.length) return;
  if (!arms || !arms.length) {
    $root.html(`<div class="review-empty">No eval arms available.</div>`);
    return;
  }
  $root.html((arms || []).map(function (arm) {
    const armId = String(arm?.armId || "");
    const checked = effectiveSelected.includes(armId) ? " checked" : "";
    const workerProvider = arm?.provider || "openai";
    const summarizerProvider = arm?.summarizerProvider || workerProvider;
    const directProvider = arm?.directProvider || workerProvider;
    const summary = arm?.type === "steered"
      ? [
          (arm?.type || "arm"),
          directBaselineModeLabel(arm?.directBaselineMode || "off"),
          contextModeLabel(arm?.contextMode || "weighted"),
          providerLabel(workerProvider) + " " + modelLabel(arm?.model || "gpt-5-mini", workerProvider),
          providerLabel(summarizerProvider) + " " + modelLabel(arm?.summarizerModel || arm?.model || "gpt-5-mini", summarizerProvider) + " summarizer",
          normalizeDirectBaselineMode(arm?.directBaselineMode || "off") !== "off"
            ? (providerLabel(directProvider) + " " + modelLabel(arm?.directModel || arm?.model || "gpt-5-mini", directProvider) + " baseline")
            : "",
          (arm?.reasoningEffort || "low") + " reasoning"
        ].filter(Boolean).join(" | ")
      : [
          (arm?.type || "arm"),
          providerLabel(workerProvider) + " " + modelLabel(arm?.model || "gpt-5-mini", workerProvider),
          "single answer",
          (arm?.reasoningEffort || "low") + " reasoning"
        ].join(" | ");
    return `
      <label class="eval-arm-option">
        <input class="eval-arm-checkbox" type="checkbox" value="${escapeHtml(armId)}"${checked} />
        <span>
          <strong>${escapeHtml(arm?.title || armId)}</strong>
          <span class="eval-arm-meta">${escapeHtml(summary)}</span>
          <span class="eval-arm-copy">${escapeHtml(arm?.description || "No description.")}</span>
        </span>
      </label>
    `;
  }).join(""));
}

function renderEvalCatalog(data) {
  const suites = data?.suites || [];
  const arms = data?.arms || [];
  const selectedSuiteId = String($("#evalSuiteSelect").val() || data?.selectedRun?.suiteId || suites?.[0]?.suiteId || "");
  $("#evalSuiteSelect").html(buildEvalSuiteOptions(suites, selectedSuiteId));
  if (selectedSuiteId) {
    $("#evalSuiteSelect").val(selectedSuiteId);
  }
  renderEvalArmList(arms);

  const notes = [];
  if ((data?.suiteErrors || []).length) {
    notes.push("Suite manifest errors: " + data.suiteErrors.map(function (error) { return error.file + " - " + error.message; }).join(" | "));
  }
  if ((data?.armErrors || []).length) {
    notes.push("Arm manifest errors: " + data.armErrors.map(function (error) { return error.file + " - " + error.message; }).join(" | "));
  }
  if (!notes.length) {
    notes.push("Eval catalogs are loaded from isolated local manifests in data/evals/.");
  }
  $("#evalCatalogNote").text(notes.join(" "));
}

function buildEvalArtifactOptions(artifacts, selectedArtifactId) {
  const options = [`<option value="">Select artifact</option>`];
  (artifacts || []).forEach(function (artifact) {
    const artifactId = String(artifact?.artifactId || "");
    const selected = artifactId === selectedArtifactId ? " selected" : "";
    options.push(`<option value="${escapeHtml(artifactId)}"${selected}>${escapeHtml((artifact?.name || artifactId) + " [" + (artifact?.kind || "artifact") + "]")}</option>`);
  });
  return options.join("");
}

function pickEvalArtifact(artifacts, preferredKinds, excludeArtifactId) {
  const list = artifacts || [];
  const preferred = list.find(function (artifact) {
    return (!excludeArtifactId || artifact.artifactId !== excludeArtifactId) && preferredKinds.includes(artifact.kind);
  });
  if (preferred) return preferred;
  return list.find(function (artifact) {
    return !excludeArtifactId || artifact.artifactId !== excludeArtifactId;
  }) || null;
}

function setEvalArtifactPane(side, metaText, visualHtml, contentText) {
  $("#evalArtifact" + side + "Meta").text(metaText);
  $("#evalArtifact" + side + "Visual").html(visualHtml);
  $("#evalArtifact" + side + "Content").text(contentText);
}

function loadEvalArtifactPane(side, artifactId) {
  if (!artifactId || !selectedEvalRunId) {
    setEvalArtifactPane(side, "No artifact selected.", `<div class="review-empty">No artifact selected.</div>`, "No artifact selected.");
    return;
  }
  $.getJSON(apiRoute(API.evalArtifact), { runId: selectedEvalRunId, artifactId: artifactId })
    .done(function (data) {
      if (evalArtifactSelections[side.toLowerCase()] !== artifactId) return;
      evalArtifactContentCache[evalArtifactCacheKey(selectedEvalRunId, artifactId)] = data || null;
      setEvalArtifactPane(side, renderArtifactMeta(data), renderEvalArtifactVisual(data), renderArtifactContent(data));
    })
    .fail(function (xhr) {
      setEvalArtifactPane(side, "Artifact load failed.", `<div class="review-empty">Artifact load failed.</div>`, xhr.responseText || "Artifact load failed.");
    });
}

function syncEvalArtifactReview(artifacts) {
  const list = artifacts || [];
  const ids = new Set(list.map(function (artifact) { return artifact.artifactId; }));
  if (!evalArtifactSelections.left || !ids.has(evalArtifactSelections.left)) {
    const leftDefault = pickEvalArtifact(list, ["comparison", "score", "summary_output", "direct_output", "result"], "");
    evalArtifactSelections.left = leftDefault ? leftDefault.artifactId : "";
  }
  if (!evalArtifactSelections.right || !ids.has(evalArtifactSelections.right) || evalArtifactSelections.right === evalArtifactSelections.left) {
    const rightDefault = pickEvalArtifact(list, ["summary_output", "direct_output", "result", "worker_output", "score", "comparison"], evalArtifactSelections.left);
    evalArtifactSelections.right = rightDefault ? rightDefault.artifactId : "";
  }
  $("#evalArtifactLeftSelect").html(buildEvalArtifactOptions(list, evalArtifactSelections.left));
  $("#evalArtifactRightSelect").html(buildEvalArtifactOptions(list, evalArtifactSelections.right));
  loadEvalArtifactPane("Left", evalArtifactSelections.left);
  loadEvalArtifactPane("Right", evalArtifactSelections.right);
}

function applyEvalArtifactSelectionPair(leftArtifactId, rightArtifactId) {
  const artifacts = latestEvalHistory?.selectedRun?.artifacts || [];
  const ids = new Set(artifacts.map(function (artifact) { return artifact.artifactId; }));
  evalArtifactSelections.left = leftArtifactId && ids.has(leftArtifactId) ? leftArtifactId : "";
  evalArtifactSelections.right = rightArtifactId && ids.has(rightArtifactId) ? rightArtifactId : "";
  if (!evalArtifactSelections.left) {
    const leftDefault = pickEvalArtifact(artifacts, ["comparison", "score", "summary_output", "direct_output", "result"], "");
    evalArtifactSelections.left = leftDefault ? leftDefault.artifactId : "";
  }
  if (!evalArtifactSelections.right || evalArtifactSelections.right === evalArtifactSelections.left) {
    const rightDefault = pickEvalArtifact(artifacts, ["summary_output", "direct_output", "result", "worker_output", "comparison"], evalArtifactSelections.left);
    evalArtifactSelections.right = rightDefault ? rightDefault.artifactId : "";
  }
  $("#evalArtifactLeftSelect").html(buildEvalArtifactOptions(artifacts, evalArtifactSelections.left));
  $("#evalArtifactRightSelect").html(buildEvalArtifactOptions(artifacts, evalArtifactSelections.right));
  loadEvalArtifactPane("Left", evalArtifactSelections.left);
  loadEvalArtifactPane("Right", evalArtifactSelections.right);
}

function findEvalReplicateArtifactByKind(replicate, kind) {
  return (replicate?.artifacts || []).find(function (artifact) {
    return String(artifact?.kind || "").trim() === String(kind || "").trim();
  }) || null;
}

function renderEvalReplicateAnswerCompare(runId, replicate, answerPath, objective) {
  const directArtifact = findEvalReplicateArtifactByKind(replicate, "direct_output");
  const summaryArtifact = findEvalReplicateArtifactByKind(replicate, "summary_output");
  const resultArtifact = findEvalReplicateArtifactByKind(replicate, "result");
  const shouldCompare = answerPath === "both" || !!directArtifact;
  if (!shouldCompare) return "";

  const resultData = resultArtifact ? getCachedEvalArtifact(runId, resultArtifact.artifactId) : null;
  const summaryData = summaryArtifact ? getCachedEvalArtifact(runId, summaryArtifact.artifactId) : null;
  const directData = directArtifact ? getCachedEvalArtifact(runId, directArtifact.artifactId) : null;

  if (resultArtifact && !resultData) queueEvalArtifactFetch(runId, resultArtifact.artifactId);
  if (summaryArtifact && !summaryData) queueEvalArtifactFetch(runId, summaryArtifact.artifactId);
  if (directArtifact && !directData) queueEvalArtifactFetch(runId, directArtifact.artifactId);

  const resultContent = resultData?.content || {};
  const pressurized = summaryData
    ? extractEvalPrimaryAnswer(summaryData)
    : normalizeEvalAnswerEntry(
        {
          answer: replicate?.publicAnswer || resultContent?.publicAnswer || "",
          stance: resultContent?.summary?.frontAnswer?.stance || "",
          confidenceNote: resultContent?.summary?.frontAnswer?.confidenceNote || ""
        },
        "Pressurized answer",
        summaryData?.summary?.provider || resultContent?.provider || "",
        summaryData?.summary?.model || resultContent?.model || "",
        summaryData?.summary?.mode || resultContent?.mode || "",
        evalUsageForTarget(replicate?.usage || resultContent?.usage || null, "summarizer")
      );
  const baseline = directData
    ? extractEvalPrimaryAnswer(directData)
    : extractEvalBaselineAnswer(resultData);
  const comparison = resultContent?.comparison || replicate?.comparison || null;

  const pressurizedEntry = pressurized || {
    label: "Pressurized answer",
    answer: "",
    emptyMessage: summaryArtifact ? "Loading saved pressurized answer..." : "No pressurized answer saved in this run."
  };
  const baselineEntry = baseline || {
    label: "Single-thread baseline",
    answer: "",
    emptyMessage: directArtifact ? "Loading saved baseline answer..." : "No baseline answer saved in this run."
  };

  return `
    <div class="eval-inline-compare-stack">
      ${renderEvalCompareToggle(pressurizedEntry, baselineEntry, comparison)}
      ${renderEvalChatCompare(pressurizedEntry, baselineEntry, objective, comparison)}
      ${renderEvalHistoricalSummary(replicate, comparison, pressurizedEntry, baselineEntry)}
    </div>
  `;
}

function formatScoreSummary(scores, overallKey, label) {
  if (!scores || typeof scores !== "object" || !Object.keys(scores).length) {
    return label + ": n/a";
  }
  return label + ": " + Number(scores[overallKey] || 0).toFixed(1) + " overall";
}

function renderEvalRunHistory(runs, currentRunId) {
  if (!runs || !runs.length) {
    return `<div class="review-empty">No eval runs yet.</div>`;
  }
  return `
    <div class="history-stack">
      ${runs.map(function (run) {
        const qualityOverall = Number(run?.summary?.averageQuality?.overallQuality || 0).toFixed(1);
        const healthOverall = run?.summary?.averageAnswerHealth && Object.keys(run.summary.averageAnswerHealth).length
          ? Number(run.summary.averageAnswerHealth.overallHealth || 0).toFixed(1)
          : "n/a";
        const controlOverall = Number(run?.summary?.averageControl?.overallControl || 0).toFixed(1);
        return `
          <article class="history-card${String(run?.runId || "") === currentRunId ? " active" : ""}">
            <div class="history-head">
              <div class="history-title">${escapeHtml(run?.runId || "eval-run")}</div>
              <button type="button" class="select-eval-run" data-run-id="${escapeHtml(run?.runId || "")}">Open</button>
            </div>
            <div class="history-meta">${escapeHtml(
              "Status: " + (run?.status || "unknown") +
              " | suite " + (run?.suiteId || "n/a") +
              " | reps " + Number(run?.replicates || 0) +
              " | loops " + ((run?.loopSweep || []).join(", ") || "1")
            )}</div>
            <div class="history-meta">${escapeHtml(
              "Quality " + qualityOverall +
              " | Health " + healthOverall +
              " | Control " + controlOverall +
              " | Tokens " + formatInteger(run?.summary?.totalTokens || 0) +
              " | Spend " + formatUsd(run?.summary?.estimatedCostUsd || 0)
            )}</div>
            ${run?.current ? `<div class="history-meta">${escapeHtml("Running: " + [run.current.caseId, run.current.variantId, "r" + run.current.replicate].filter(Boolean).join(" | "))}</div>` : ""}
            ${run?.error ? `<div class="history-meta">${escapeHtml("Error: " + run.error)}</div>` : ""}
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderEvalRunDetail(run) {
  if (!run || typeof run !== "object") {
    return `<div class="review-empty">Pick a run to inspect case-by-case scoring and artifacts.</div>`;
  }
  const summary = run.summary || {};
  const topCards = `
    <div class="eval-summary-grid">
      <article class="history-card">
        <div class="history-title">${escapeHtml(run?.suite?.title || run?.suiteId || "Eval suite")}</div>
        <div class="history-meta">${escapeHtml((run?.status || "unknown") + " | judge " + (run?.judgeModel || "n/a"))}</div>
      </article>
      <article class="history-card">
        <div class="history-title">Quality</div>
        <div class="history-meta">${escapeHtml(formatScoreSummary(summary.averageQuality || {}, "overallQuality", "Average"))}</div>
      </article>
      <article class="history-card">
        <div class="history-title">Answer health</div>
        <div class="history-meta">${escapeHtml(formatScoreSummary(summary.averageAnswerHealth || {}, "overallHealth", "Average"))}</div>
      </article>
      <article class="history-card">
        <div class="history-title">Control</div>
        <div class="history-meta">${escapeHtml(formatScoreSummary(summary.averageControl || {}, "overallControl", "Average"))}</div>
      </article>
      <article class="history-card">
        <div class="history-title">Usage</div>
        <div class="history-meta">${escapeHtml("Tokens " + formatInteger(summary.totalTokens || 0) + " | Spend " + formatUsd(summary.estimatedCostUsd || 0))}</div>
      </article>
    </div>
  `;

  const caseCards = (run.cases || []).map(function (caseEntry) {
      const variantCards = (caseEntry.variants || []).map(function (variant) {
      const answerPath = normalizeDirectBaselineMode(variant?.answerPath || "off");
      const contextMode = contextModeLabel(variant?.contextMode || "weighted");
      const replicateRows = (variant.replicates || []).map(function (replicate) {
        const artifacts = replicate.artifacts || [];
        const scoreArtifact = artifacts.find(function (artifact) { return artifact.kind === "score"; });
        const comparisonArtifact = artifacts.find(function (artifact) { return artifact.kind === "comparison"; });
        const resultArtifact = artifacts.find(function (artifact) { return artifact.kind === "result"; });
        const directArtifact = artifacts.find(function (artifact) { return artifact.kind === "direct_output"; });
        const summaryArtifact = artifacts.find(function (artifact) { return artifact.kind === "summary_output"; });
        const workerArtifact = artifacts.find(function (artifact) { return artifact.kind === "worker_output"; });
        const primaryAnswerArtifact = summaryArtifact || directArtifact || resultArtifact || scoreArtifact;
        const buttons = [];
        if (scoreArtifact && primaryAnswerArtifact) {
          buttons.push(`<button type="button" class="load-eval-artifact-pair" data-left="${escapeHtml(scoreArtifact.artifactId)}" data-right="${escapeHtml(primaryAnswerArtifact.artifactId)}">Score vs answer</button>`);
        }
        if (summaryArtifact && directArtifact) {
          buttons.push(`<button type="button" class="load-eval-artifact-pair" data-left="${escapeHtml(summaryArtifact.artifactId)}" data-right="${escapeHtml(directArtifact.artifactId)}">Pressurized vs baseline</button>`);
        }
        if (comparisonArtifact && primaryAnswerArtifact) {
          buttons.push(`<button type="button" class="load-eval-artifact-pair" data-left="${escapeHtml(comparisonArtifact.artifactId)}" data-right="${escapeHtml(primaryAnswerArtifact.artifactId)}">Comparison vs answer</button>`);
        }
        if (summaryArtifact && workerArtifact) {
          buttons.push(`<button type="button" class="load-eval-artifact-pair" data-left="${escapeHtml(summaryArtifact.artifactId)}" data-right="${escapeHtml(workerArtifact.artifactId)}">Summary vs lane</button>`);
        }
        const comparison = replicate?.comparison || null;
        const inlineCompare = renderEvalReplicateAnswerCompare(
          run?.runId || selectedEvalRunId || "",
          replicate,
          answerPath,
          caseEntry.objective || caseEntry.title || ""
        );
        return `
          <div class="eval-replicate-row${replicate.status === "error" ? " warning" : ""}">
            <div>
              <div class="history-title">Replicate ${escapeHtml(String(replicate.replicate || 0))}</div>
              <div class="round-worker-meta">${escapeHtml(
                "Status " + (replicate.status || "unknown") +
                " | mode " + (replicate.mode || "n/a") +
                " | deterministic " + ((replicate.deterministic?.passedCount || 0) + "/" + (replicate.deterministic?.totalCount || 0))
              )}</div>
              <div class="round-worker-meta">${escapeHtml(
                "Quality " + Number(replicate.quality?.scores?.overallQuality || 0).toFixed(1) +
                " | Health " + Number(replicate.answerHealth?.scores?.overallHealth || 0).toFixed(1) +
                " | Control " + Number(replicate.control?.scores?.overallControl || 0).toFixed(1) +
                " | Tokens " + formatInteger(replicate.usage?.totalTokens || 0) +
                " | Spend " + formatUsd(replicate.usage?.estimatedCostUsd || 0)
              )}</div>
              ${comparison ? `<div class="round-worker-meta">${escapeHtml(
                "Compare " + String(comparison.verdict || "mixed") +
                " | delta " + Number(comparison.scoreDelta?.overallQuality || 0).toFixed(1) +
                " | diff " + Number(comparison.scores?.overallDifferentiation || 0).toFixed(1) +
                " | baseline quality " + Number(comparison.baselineQuality?.scores?.overallQuality || 0).toFixed(1)
              )}</div>` : ""}
              <div class="eval-answer-preview">${escapeHtml(truncateText(replicate.publicAnswer || replicate.error || "No answer captured.", 240))}</div>
            </div>
            ${inlineCompare}
            ${buttons.length ? `<div class="round-history-actions">${buttons.join("")}</div>` : ""}
          </div>
        `;
      }).join("") || `<div class="review-empty small">No replicates recorded yet.</div>`;

      return `
        <article class="eval-variant-card">
          <div class="round-history-head">
            <div class="round-history-title">${escapeHtml(variant.title || variant.variantId || "Variant")}</div>
            <div class="round-history-title">${escapeHtml((variant.type || "variant") + " | " + directBaselineModeLabel(answerPath) + " | " + contextMode + " | loops " + Number(variant.loopRounds || 0))}</div>
          </div>
          <div class="round-history-meta">${escapeHtml(
            providerLabel(variant.provider || "openai") + " " + modelLabel(variant.model || "gpt-5-mini", variant.provider || "openai") +
            (variant.type === "steered"
              ? (
                " | " + providerLabel(variant.summarizerProvider || variant.provider || "openai") + " " + modelLabel(variant.summarizerModel || variant.model || "gpt-5-mini", variant.summarizerProvider || variant.provider || "openai") + " summarizer" +
                (answerPath !== "off"
                  ? (" | " + providerLabel(variant.directProvider || variant.provider || "openai") + " " + modelLabel(variant.directModel || variant.model || "gpt-5-mini", variant.directProvider || variant.provider || "openai") + " baseline")
                  : "")
              )
              : "")
          )}</div>
          <div class="round-history-meta">${escapeHtml(
            "Pass rate " + Number(variant.aggregate?.deterministicPassRate || 0).toFixed(2) +
            " | Quality " + Number(variant.aggregate?.quality?.overallQuality || 0).toFixed(1) +
            " | Health " + Number(variant.aggregate?.answerHealth?.overallHealth || 0).toFixed(1) +
            " | Control " + Number(variant.aggregate?.control?.overallControl || 0).toFixed(1) +
            " | Tokens " + formatInteger(variant.aggregate?.totalTokens || 0) +
            " | Spend " + formatUsd(variant.aggregate?.estimatedCostUsd || 0)
          )}</div>
          ${variant.aggregate?.comparison?.replicateCount ? `<div class="round-history-meta">${escapeHtml(
            "Compare " + String(variant.aggregate.comparison.verdict || "mixed") +
            " | delta " + Number(variant.aggregate.comparison.averageScoreDelta?.overallQuality || 0).toFixed(2) +
            " | diff " + Number(variant.aggregate.comparison.averageScores?.overallDifferentiation || 0).toFixed(2) +
            " | wins " + Number(variant.aggregate.comparison.pressurizedWins || 0) +
            "/" + Number(variant.aggregate.comparison.baselineWins || 0) +
            "/" + Number(variant.aggregate.comparison.ties || 0)
          )}</div>` : ""}
          <div class="eval-replicate-stack">${replicateRows}</div>
        </article>
      `;
    }).join("");

    return `
      <article class="eval-case-card">
        <div class="history-head">
          <div class="history-title">${escapeHtml(caseEntry.title || caseEntry.caseId || "Case")}</div>
          <div class="history-title">${escapeHtml(caseEntry.caseId || "")}</div>
        </div>
        <div class="history-meta">${escapeHtml(truncateText(caseEntry.objective || "No objective recorded.", 220))}</div>
        <div class="eval-variant-stack">${variantCards || `<div class="review-empty small">No variants recorded for this case yet.</div>`}</div>
      </article>
    `;
  }).join("");

  return topCards + `<div class="eval-case-stack">${caseCards || `<div class="review-empty">No case results yet.</div>`}</div>`;
}

function refreshEvalHistory() {
  const params = selectedEvalRunId ? { runId: selectedEvalRunId } : {};
  $.getJSON(apiRoute(API.evalHistory), params)
    .done(function (data) {
      if (!data?.selectedRun && selectedEvalRunId && (data?.runs || []).length) {
        selectedEvalRunId = String(data.runs[0]?.runId || "");
        localStorage.setItem("loopSelectedEvalRunId", selectedEvalRunId);
        refreshEvalHistory();
        return;
      }
      latestEvalHistory = data;
      if (data?.selectedRunId) {
        selectedEvalRunId = String(data.selectedRunId);
        localStorage.setItem("loopSelectedEvalRunId", selectedEvalRunId);
      }
      renderEvalCatalog(data);
      $("#evalRunHistory").html(renderEvalRunHistory(data.runs || [], selectedEvalRunId));
      $("#evalRunDetail").html(renderEvalRunDetail(data.selectedRun || null));
      syncEvalArtifactReview((data.selectedRun || {}).artifacts || []);
    })
    .fail(function (xhr) {
      latestEvalHistory = null;
      $("#evalRunHistory").html(`<div class="review-empty">Eval history failed to load.</div>`);
      $("#evalRunDetail").html(`<div class="review-empty">Eval detail failed to load.</div>`);
      showMessage("Eval history load failed: " + extractErrorMessage(xhr), true);
    });
}

function loadExportPreview(archiveFile = "") {
  const requestKey = archiveFile ? "archive:" + archiveFile : "current";
  exportPreviewKey = requestKey;
  $("#exportPreview").text("Loading export preview...");

  const params = archiveFile ? { archiveFile } : {};
  $.getJSON(apiRoute(API.exportSession), params)
    .done(function (data) {
      if (exportPreviewKey !== requestKey) return;
      $("#exportPreview").text(pretty(data));
    })
    .fail(function (xhr) {
      if (exportPreviewKey !== requestKey) return;
      $("#exportPreview").text("Export preview failed.\n\n" + (xhr.responseText || "Unknown error"));
      showMessage("Export preview failed: " + extractErrorMessage(xhr), true);
    });
}

function renderWorkerPanels(task) {
  const $grid = $("#workerGrid");
  $grid.empty();

  if (!task || !task.workers || !task.workers.length) {
    $grid.append($("<div>").addClass("lane-card-empty").text("No active task."));
    return;
  }

  const workerState = task.stateWorkers || {};
  task.workers.forEach(function (worker) {
    const checkpoint = workerState[worker.id] || null;
    const $card = $("<div>").addClass("lane-card");
    const $head = $("<div>").addClass("lane-card-head");
    $head.append($("<div>").addClass("lane-card-title").text(worker.label + " | " + worker.role));
    $head.append($("<div>").addClass("lane-card-step").text(checkpoint ? "step " + (checkpoint.step || 0) : "waiting"));
    $card.append($head);
    const focusBits = [worker.focus, "model: " + worker.model];
    if (checkpoint?.localFileSources?.length) {
      focusBits.push(checkpoint.localFileSources.length + " local file" + (checkpoint.localFileSources.length === 1 ? "" : "s"));
    }
    if (checkpoint?.githubSources?.length) {
      focusBits.push(checkpoint.githubSources.length + " GitHub source" + (checkpoint.githubSources.length === 1 ? "" : "s"));
    }
    if (checkpoint?.researchSources?.length) {
      focusBits.push(checkpoint.researchSources.length + " web source" + (checkpoint.researchSources.length === 1 ? "" : "s"));
    }
    $card.append($("<div>").addClass("lane-card-focus").text(focusBits.join(" | ")));
    $card.append($("<div>").addClass("lane-card-copy").text(
      checkpoint
        ? truncateText(checkpoint.observation || checkpoint.requestToPeer || "Checkpoint available.", 220)
        : "No checkpoint yet."
    ));
    $grid.append($card);
  });
}

function allWorkerCheckpointsReady(task, stateWorkers) {
  const workers = task?.workers || [];
  if (!workers.length) return false;
  return workers.every(function (worker) {
    return !!stateWorkers?.[worker.id];
  });
}

function commanderRound(task) {
  return Number(task?.stateCommander?.round || 0);
}

function commanderReviewRound(task) {
  return Number(task?.stateCommanderReview?.round || 0);
}

function workerExpectedRound(task, workerId, stateWorkers) {
  const checkpoint = stateWorkers?.[workerId] || null;
  return Number(checkpoint?.step || 0) + 1;
}

function workerReadyForCommanderRound(task, workerId, stateWorkers) {
  const currentCommanderRound = commanderRound(task);
  if (currentCommanderRound <= 0) return false;
  return currentCommanderRound === workerExpectedRound(task, workerId, stateWorkers);
}

function summarizerReadyForCommanderRound(task, stateWorkers) {
  const currentCommanderRound = commanderRound(task);
  const currentCommanderReviewRound = commanderReviewRound(task);
  if (currentCommanderRound <= 0) return false;
  if (currentCommanderReviewRound !== currentCommanderRound) return false;
  const workers = task?.workers || [];
  if (!workers.length) return false;
  return workers.every(function (worker) {
    const checkpoint = stateWorkers?.[worker.id] || null;
    return Number(checkpoint?.step || 0) === currentCommanderRound;
  });
}

function commanderReviewReadyForCommanderRound(task, stateWorkers) {
  const currentCommanderRound = commanderRound(task);
  if (currentCommanderRound <= 0) return false;
  const workers = task?.workers || [];
  if (!workers.length) return false;
  return workers.every(function (worker) {
    const checkpoint = stateWorkers?.[worker.id] || null;
    return Number(checkpoint?.step || 0) === currentCommanderRound;
  });
}

function answerNowReady(state) {
  const task = state?.activeTask || null;
  const commander = state?.commander || task?.stateCommander || null;
  return !!task && Number(commander?.round || 0) > 0;
}

function syncComposerAnswerNowButton(state) {
  const $button = $("#answerNowPrompt");
  if (!$button.length) return;

  const partialAnswerActive = hasActiveDispatchTarget(state, "answer_now");
  const ready = answerNowReady(state);
  let title = "Queue a partial answer from the current commander draft and finished worker checkpoints.";

  if (partialAnswerActive) {
    title = "A partial answer is already being generated.";
  } else if (!state?.activeTask) {
    title = "Start a task first.";
  } else if (!ready) {
    title = "Answer Now needs a commander draft first.";
  }

  $button
    .prop("disabled", partialAnswerActive || !ready)
    .text(partialAnswerActive ? "Answering..." : "Answer Now")
    .attr("title", title)
    .attr("aria-label", title)
    .toggle(ready || partialAnswerActive);

  $("#sendPrompt").toggle(!(ready || partialAnswerActive));
}

function renderWorkerControls(task, loop, stateWorkers) {
  const $controls = $("#workerControls");
  $controls.empty();

  if (!task || !task.workers || !task.workers.length) {
    $controls.append($("<div>").addClass("workercontrol").text("No active task."));
    return;
  }

  const isActive = isWorkspaceBusy(loop, latestState);
  const summaryReady = allWorkerCheckpointsReady(task, stateWorkers || {});

  task.workers.forEach(function (worker) {
    const $card = $("<div>").addClass("workercontrol");
    $card.append($("<div>").addClass("workercontrol-title").text(worker.id + " | " + displayWorkerLabel(worker)));
    $card.append($("<div>").addClass("workercontrol-meta").text(worker.role + " | " + worker.focus));

    const $row = $("<div>").addClass("inlineform");
    $row.append(
      $("<select>").addClass("position-model").attr("data-position", worker.id).html(buildModelOptions(worker.model, task?.runtime?.provider || "openai")),
      $("<button>").addClass("save-model").attr("data-position", worker.id).prop("disabled", isActive).text("Save Model"),
      $("<button>").addClass("run-target").attr("data-target", worker.id).prop("disabled", isActive).text("Run " + worker.id)
    );
    $card.append($row);
    $controls.append($card);
  });

  const summarizerModel = task.summarizer?.model || task.runtime?.model || "gpt-5-mini";
  const summarizerProvider = task.summarizer?.provider || task.runtime?.provider || "openai";
  const vettingEnabled = !!task.runtime?.vetting?.enabled;
  const $summaryCard = $("<div>").addClass("workercontrol");
  $summaryCard.append($("<div>").addClass("workercontrol-title").text("Summarizer"));
  $summaryCard.append($("<div>").addClass("workercontrol-meta").text(
    summaryReady
      ? (vettingEnabled ? "Canonical merge lane | evidence vetter" : "Canonical merge lane")
      : "Canonical merge lane | waiting for all worker checkpoints"
  ));

  const $summaryRow = $("<div>").addClass("inlineform");
  $summaryRow.append(
    $("<select>").addClass("position-model").attr("data-position", "summarizer").html(buildModelOptions(summarizerModel, summarizerProvider)),
    $("<button>").addClass("save-model").attr("data-position", "summarizer").prop("disabled", isActive).text("Save Model"),
    $("<button>").addClass("run-target").attr("data-target", "summarizer").prop("disabled", isActive || !summaryReady).text("Summarize"),
    $("<button>").addClass("run-target secondary").attr("data-target", "answer_now").prop("disabled", commanderRound(task) <= 0 || hasActiveDispatchTarget(latestState, "answer_now")).text("Answer Now")
  );
  $summaryCard.append($summaryRow);
  $controls.append($summaryCard);
}

function workerDirectiveLabel(worker) {
  const typeId = String(worker?.type || "sceptic");
  return WORKER_TYPE_CATALOG[typeId]?.label || displayWorkerLabel(worker);
}

function workerTemperatureLabel(worker) {
  const temperatureId = String(worker?.temperature || "balanced");
  return WORKER_TEMPERATURE_CATALOG[temperatureId]?.label || temperatureId;
}

function clampNumber(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function dashboardWorkerMenuRoot() {
  return $();
}

function dashboardWorkerMenuBody(detailsElement) {
  return $(detailsElement).children(".workercontrol-body").first();
}

function restoreDashboardWorkerMenu(detailsElement) {
  const $body = dashboardWorkerMenuBody(detailsElement);
  if (!$body.length) return;
  $body.css({ top: "", left: "", right: "", width: "", maxWidth: "" });
}

function clearAllDashboardWorkerMenus() {
  return;
}

function shouldFloatDashboardWorkerMenus() {
  return false;
}

function clearDashboardWorkerMenuPosition(detailsElement) {
  const $body = dashboardWorkerMenuBody(detailsElement);
  if (!$body.length) return;
  $body.css({ top: "", left: "", right: "", width: "", maxWidth: "" });
}

function positionDashboardWorkerMenu(detailsElement) {
  restoreDashboardWorkerMenu(detailsElement);
  clearDashboardWorkerMenuPosition(detailsElement);
}

function refreshDashboardWorkerMenuPositions() {
  $("#workerControls .workercontrol-collapsible[open]").each(function () {
    positionDashboardWorkerMenu(this);
  });
}

function syncWorkerEditorModalVisibility() {
  const visible = !!(workerEditorModalState.kind && workerEditorModalState.key);
  $("#workerEditorModal").prop("hidden", !visible).attr("aria-hidden", visible ? "false" : "true");
  $("body").toggleClass("worker-editor-open", visible);
}

function buildWorkerControlFields(worker, isActive) {
  const workerId = String(worker?.id || "").trim();
  const harness = normalizeHarnessConfig(worker?.harness, "tight");
  const provider = runtimeProviderSource(latestState?.activeTask || null, latestState?.draft || null);
  const $body = $("<div>").addClass("worker-editor-grid");

  const $typeRow = $("<div>").addClass("workercontrol-field");
  $typeRow.append($("<label>").text("Directive"));
  $typeRow.append(
    $("<select>").addClass("worker-type").attr("data-worker-id", workerId).prop("disabled", isActive).html(buildWorkerTypeOptions(worker.type || "sceptic"))
  );
  $body.append($typeRow);

  const $temperatureRow = $("<div>").addClass("workercontrol-field");
  $temperatureRow.append($("<label>").text("Temperature"));
  $temperatureRow.append(
    $("<select>").addClass("worker-temperature").attr("data-worker-id", workerId).prop("disabled", isActive).html(buildWorkerTemperatureOptions(worker.temperature || "balanced"))
  );
  $body.append($temperatureRow);

  const $modelRow = $("<div>").addClass("workercontrol-field");
  $modelRow.append($("<label>").text("Model"));
  $modelRow.append(
    $("<select>").addClass("worker-model").attr("data-worker-id", workerId).prop("disabled", isActive).html(buildModelOptions(worker.model, provider))
  );
  $body.append($modelRow);

  const $harnessRow = $("<div>").addClass("workercontrol-field");
  $harnessRow.append($("<label>").text("Harness"));
  $harnessRow.append(
    $("<select>").addClass("worker-harness-profile").attr("data-worker-id", workerId).prop("disabled", isActive).html(buildHarnessConcisionOptions(harness.concision))
  );
  $body.append($harnessRow);

  const $instructionRow = $("<div>").addClass("workercontrol-field workercontrol-field-wide");
  $instructionRow.append($("<label>").text("Harness note"));
  $instructionRow.append(
    $("<textarea>")
      .addClass("worker-harness-instruction")
      .attr("data-worker-id", workerId)
      .prop("disabled", isActive)
      .attr("rows", "3")
      .attr("placeholder", "Optional extra instruction for this lane's harness.")
      .val(harness.instruction || "")
  );
  $body.append($instructionRow);

  return $body;
}

function buildSummarizerControlFields(summarizer, isActive) {
  const harness = normalizeHarnessConfig(summarizer?.harness, "expansive");
  const provider = normalizeProviderId($("#summarizerProvider").val() || summarizer?.provider || summarizerProviderSource(latestState?.activeTask || null, latestState?.draft || null));
  const $body = $("<div>").addClass("worker-editor-grid");

  const $modelRow = $("<div>").addClass("workercontrol-field");
  $modelRow.append($("<label>").text("Model"));
  $modelRow.append(
    $("<select>").addClass("summarizer-model-draft").prop("disabled", isActive).html(buildModelOptions(summarizer?.model || defaultModelForProvider(provider), provider))
  );
  $body.append($modelRow);

  const $harnessRow = $("<div>").addClass("workercontrol-field");
  $harnessRow.append($("<label>").text("Harness"));
  $harnessRow.append(
    $("<select>").addClass("summarizer-harness-profile").prop("disabled", isActive).html(buildHarnessConcisionOptions(harness.concision))
  );
  $body.append($harnessRow);

  const $instructionRow = $("<div>").addClass("workercontrol-field workercontrol-field-wide");
  $instructionRow.append($("<label>").text("Harness note"));
  $instructionRow.append(
    $("<textarea>")
      .addClass("summarizer-harness-instruction")
      .prop("disabled", isActive)
      .attr("rows", "3")
      .attr("placeholder", "Optional extra instruction for the main-thread answer harness.")
      .val(harness.instruction || "")
  );
  $body.append($instructionRow);

  return $body;
}

function renderWorkerEditorModal() {
  if (!workerEditorModalState.kind || !workerEditorModalState.key) {
    closeWorkerEditorModal();
    return;
  }
  const $title = $("#workerEditorTitle");
  const $meta = $("#workerEditorMeta");
  const $body = $("#workerEditorBody");
  if (!$title.length || !$meta.length || !$body.length) return;

  const task = latestState?.activeTask || null;
  const draft = latestState?.draft || null;
  const loop = latestState?.loop || null;
  const isActive = loop?.status === "running" || loop?.status === "queued";
  $body.empty();

  if (workerEditorModalState.kind === "worker") {
    const worker = visibleWorkerRosterSource(draft, task).find(function (candidate) {
      return normalizeWorkerControlKey(candidate?.id) === workerEditorModalState.key;
    });
    if (!worker) {
      closeWorkerEditorModal();
      return;
    }
    $title.text(displayWorkerLabel(worker));
    $meta.text(workerDirectiveLabel(worker) + " | " + workerTemperatureLabel(worker) + " | " + harnessConcisionLabel(worker.harness, "tight") + " | " + modelLabel(worker.model));
    $body.append(buildWorkerControlFields(worker, isActive));
  } else {
    const summarizer = visibleSummarizerSource(draft, task);
    $title.text("Main thread");
    $meta.text("Lead voice | " + harnessConcisionLabel(summarizer.harness, "expansive") + " | " + modelLabel(summarizer.model, summarizer.provider));
    $body.append(buildSummarizerControlFields(summarizer, isActive));
  }
  syncWorkerEditorModalVisibility();
}

function openWorkerEditorModal(kind, key) {
  workerEditorModalState = {
    kind: kind === "summarizer" ? "summarizer" : "worker",
    key: normalizeWorkerControlKey(key || "")
  };
  renderWorkerEditorModal();
  window.requestAnimationFrame(function () {
    const $focusTarget = $("#workerEditorBody select, #workerEditorBody textarea").filter(":enabled").first();
    ($focusTarget.length ? $focusTarget : $("#workerEditorClose")).trigger("focus");
  });
}

function closeWorkerEditorModal() {
  workerEditorModalState = { kind: "", key: "" };
  $("#workerEditorBody").empty();
  $("#workerEditorTitle").text("Worker");
  $("#workerEditorMeta").text("");
  syncWorkerEditorModalVisibility();
}

function syncWorkerEditorOverrideFromModalFields() {
  if ($("#workerEditorModal").prop("hidden")) return;
  if (workerEditorModalState.kind === "worker") {
    const workerId = String($("#workerEditorBody .worker-type").attr("data-worker-id") || workerEditorModalState.key || "").trim();
    if (!workerId) return;
    setWorkerEditorWorkerOverride(workerId, {
      type: String($("#workerEditorBody .worker-type").val() || "sceptic"),
      temperature: String($("#workerEditorBody .worker-temperature").val() || "balanced"),
      model: String($("#workerEditorBody .worker-model").val() || ""),
      harness: {
        concision: String($("#workerEditorBody .worker-harness-profile").val() || "tight"),
        instruction: String($("#workerEditorBody .worker-harness-instruction").val() || "").trim()
      }
    });
  } else if (workerEditorModalState.kind === "summarizer") {
    setWorkerEditorSummarizerOverride({
      model: String($("#workerEditorBody .summarizer-model-draft").val() || ""),
        harness: {
        concision: String($("#workerEditorBody .summarizer-harness-profile").val() || "expansive"),
        instruction: String($("#workerEditorBody .summarizer-harness-instruction").val() || "").trim()
      }
    });
  }
}

function renderHomeWorkerControls(task, draft, loop) {
  const $controls = $("#workerControls");
  reconcileWorkerEditorOverrides(draft, task);
  const workers = visibleWorkerRosterSource(draft, task);
  const summarizer = visibleSummarizerSource(draft, task);
  const workerState = task?.stateWorkers || {};
  const activeTarget = inferFrontActiveTarget(loop, latestState);
  const signature = JSON.stringify({
    mode: "draft",
    workers,
    summarizer,
    overrides: workerEditorOverrides,
    loopStatus: loop?.status || "idle",
    loopMessage: loop?.lastMessage || "",
    activeTarget,
    commanderRound: task?.stateCommander?.round || 0,
    commanderReviewRound: task?.stateCommanderReview?.round || 0,
    summaryPresent: !!task?.summary,
    workerSteps: workers.map(function (worker) {
      return [worker.id, workerState?.[worker.id]?.step || 0];
    })
  });
  if (signature === workerControlsSignature || hasFocusWithin("#workerControls")) return;
  workerControlsSignature = signature;
  $controls.empty();
  $controls.off("scroll.dashboardWorkerMenus");

  if (!workers.length) {
    $controls.append($("<div>").addClass("workercontrol").text("No workers configured."));
    refreshDashboardWorkerMenuPositions();
    return;
  }

  const isActive = loop?.status === "running" || loop?.status === "queued";
  workers.forEach(function (worker) {
    $controls.append(buildWorkerControlCard(worker, isActive, workerFrontStatus(worker.id, task, loop, latestState)));
  });
  $controls.append(buildSummarizerControlCard(summarizer, isActive, summarizerFrontStatus(task, loop, latestState)));
  $controls.off("scroll.dashboardWorkerMenus").on("scroll.dashboardWorkerMenus", function () {
    refreshDashboardWorkerMenuPositions();
  });
  refreshDashboardWorkerMenuPositions();
  if (workerEditorModalState.key && !hasFocusWithin("#workerEditorModal")) {
    renderWorkerEditorModal();
  }
}

function renderDebugTargetControls(task, loop, stateWorkers) {
  const $controls = $("#debugTargetControls");
  const currentCommander = task?.stateCommander || null;
  const currentCommanderReview = task?.stateCommanderReview || null;
  const timeoutConfig = currentTargetTimeoutsSource(task || null, latestState?.draft || null);
  const signature = JSON.stringify({
    taskId: task?.taskId || "",
    commanderRound: currentCommander?.round || 0,
    commanderReviewRound: currentCommanderReview?.round || 0,
    workers: task?.workers || [],
    loopStatus: loop?.status || "idle",
    dispatchStatus: latestState?.dispatch?.status || "idle",
    summaryReady: summarizerReadyForCommanderRound(task, stateWorkers || {}),
    targetTimeouts: timeoutConfig
  });
  if (signature === debugControlsSignature || hasFocusWithin("#debugTargetControls")) return;
  debugControlsSignature = signature;
  $controls.empty();

  if (!task || !task.workers || !task.workers.length) {
    $controls.append($("<div>").addClass("workercontrol").text("No active task."));
    return;
  }

  const isActive = isWorkspaceBusy(loop, latestState);
  const currentCommanderRound = commanderRound(task);
  const currentCommanderReviewRound = commanderReviewRound(task);
  const commanderReviewReady = commanderReviewReadyForCommanderRound(task, stateWorkers || {});
  const summaryReady = summarizerReadyForCommanderRound(task, stateWorkers || {});
  const commanderModel = task.summarizer?.model || task.runtime?.model || "gpt-5-mini";
  const partialAnswerActive = hasActiveDispatchTarget(latestState, "answer_now");
  const directBaselineEnabled = normalizeDirectBaselineMode(task?.runtime?.directBaselineMode || "off") !== "off";

  function buildTimeoutRow(target, currentValue, buttonLabel, disabled) {
    return $("<div>").addClass("inlineform debug-target-actions").append(
      $("<label>").addClass("debug-timeout-label").attr("for", "timeout-" + String(target)).text("Timeout"),
      $("<input>")
        .attr("id", "timeout-" + String(target))
        .attr("type", "number")
        .attr("min", "15")
        .attr("max", "3600")
        .attr("step", "5")
        .addClass("target-timeout-input")
        .attr("data-timeout-target", target)
        .val(currentValue),
      $("<span>").addClass("debug-timeout-suffix").text("s"),
      $("<button>").addClass("run-target").attr("data-target", target).prop("disabled", !!disabled).text(buttonLabel)
    );
  }

  if (directBaselineEnabled) {
    const directProvider = task?.runtime?.directProvider || task?.runtime?.provider || "openai";
    const directModel = task?.runtime?.directModel || task?.runtime?.model || "gpt-5-mini";
    const $directCard = $("<div>").addClass("workercontrol");
    $directCard.append($("<div>").addClass("workercontrol-title").text("Single-thread baseline"));
    $directCard.append(
      $("<div>").addClass("workercontrol-meta").text(
        providerLabel(directProvider) + " | " + modelLabel(directModel, directProvider)
      )
    );
    $directCard.append(
      buildTimeoutRow("direct_baseline", targetTimeoutSeconds(timeoutConfig, "direct_baseline"), "Run baseline", isActive || !!latestState?.directBaseline)
    );
    $controls.append($directCard);
  }

  const $commanderCard = $("<div>").addClass("workercontrol");
  $commanderCard.append($("<div>").addClass("workercontrol-title").text("Commander"));
  $commanderCard.append(
    $("<div>").addClass("workercontrol-meta").text(
      (currentCommanderRound > 0 ? "round " + currentCommanderRound : "ready for round 1") + " | " + commanderModel
    )
  );
  $commanderCard.append(buildTimeoutRow("commander", targetTimeoutSeconds(timeoutConfig, "commander"), "Run commander", isActive));
  $controls.append($commanderCard);

  task.workers.forEach(function (worker) {
    const checkpoint = stateWorkers?.[worker.id] || null;
    const expectedRound = workerExpectedRound(task, worker.id, stateWorkers || {});
    const $card = $("<div>").addClass("workercontrol");
    $card.append($("<div>").addClass("workercontrol-title").text(worker.id + " | " + worker.label));
    $card.append(
      $("<div>").addClass("workercontrol-meta").text(
        (checkpoint ? "step " + (checkpoint.step || 0) : "no checkpoint")
        + " | expects commander round " + expectedRound
        + " | " + worker.model
      )
    );
    $card.append(
      buildTimeoutRow(
        worker.id,
        targetTimeoutSeconds(timeoutConfig, worker.id),
        "Run " + worker.id,
        isActive || !workerReadyForCommanderRound(task, worker.id, stateWorkers || {})
      )
    );
    $controls.append($card);
  });

  const $reviewCard = $("<div>").addClass("workercontrol");
  $reviewCard.append($("<div>").addClass("workercontrol-title").text("Commander Review"));
  $reviewCard.append(
    $("<div>").addClass("workercontrol-meta").text(
      (currentCommanderReviewRound === currentCommanderRound && currentCommanderRound > 0
        ? "ready to summarize round " + currentCommanderRound
        : (commanderReviewReady ? "ready for round " + currentCommanderRound : "waiting on commander-aligned workers"))
      + " | " + commanderModel
    )
  );
  $reviewCard.append(buildTimeoutRow("commander_review", targetTimeoutSeconds(timeoutConfig, "commander_review"), "Run review", isActive || !commanderReviewReady));
  $controls.append($reviewCard);

  const $summaryCard = $("<div>").addClass("workercontrol");
  $summaryCard.append($("<div>").addClass("workercontrol-title").text("Summarizer"));
  $summaryCard.append(
    $("<div>").addClass("workercontrol-meta").text(
      (summaryReady ? "ready after review round " + currentCommanderRound : "waiting on commander review")
      + " | " + commanderModel
    )
  );
  $summaryCard.append(
    $("<div>").addClass("inlineform debug-target-actions").append(
      $("<label>").addClass("debug-timeout-label").attr("for", "timeout-summarizer").text("Timeout"),
      $("<input>")
        .attr("id", "timeout-summarizer")
        .attr("type", "number")
        .attr("min", "15")
        .attr("max", "3600")
        .attr("step", "5")
        .addClass("target-timeout-input")
        .attr("data-timeout-target", "summarizer")
        .val(targetTimeoutSeconds(timeoutConfig, "summarizer")),
      $("<span>").addClass("debug-timeout-suffix").text("s"),
      $("<button>").addClass("run-target").attr("data-target", "summarizer").prop("disabled", isActive || !summaryReady).text("Summarize"),
      $("<button>").addClass("run-target secondary").attr("data-target", "answer_now").prop("disabled", currentCommanderRound <= 0 || partialAnswerActive).text("Answer Now")
    )
  );
  $controls.append($summaryCard);
}

function renderRosterPanels(task, draft) {
  const $grid = $("#workerGrid");
  $grid.empty();

  const hasActiveWorkers = !!(task && Array.isArray(task.workers) && task.workers.length);
  const workers = hasActiveWorkers ? task.workers : stagedWorkerSource(draft, task);
  if (!workers.length) {
    $grid.append($("<div>").addClass("lane-card-empty").text("No workers configured."));
    return;
  }

  const workerState = task?.stateWorkers || {};
  const loop = latestState?.loop || {};
  workers.forEach(function (worker) {
    const checkpoint = workerState[worker.id] || null;
    const status = workerFrontStatus(worker.id, task, loop, latestState);
    const $card = $("<div>").addClass("lane-card " + statusClassName(status));
    const $head = $("<div>").addClass("lane-card-head");
    $head.append($("<div>").addClass("lane-card-title").text(displayWorkerLabel(worker) + " | " + (worker.type || worker.role)));
    $head.append($("<div>").addClass("lane-card-step").text(
      checkpoint ? (status?.label || "Done") + " | step " + (checkpoint.step || 0) : (status?.label || (task ? "Waiting" : "Ready"))
    ));
    $card.append($head);
    $card.append($("<div>").addClass("lane-card-focus").text(worker.focus + " | " + (worker.temperature || "balanced") + " | model: " + worker.model));
    $card.append($("<div>").addClass("lane-card-copy").text(
      checkpoint
        ? truncateText(checkpoint.observation || checkpoint.requestToPeer || "Checkpoint available.", 220)
        : (hasActiveWorkers ? "No checkpoint yet." : "Staged and ready for the next send.")
    ));
    $grid.append($card);
  });
}

function renderFooterCheckpoints(task) {
  const $list = $("#evalCheckpointList");
  if (!$list.length) return;
  $list.empty();

  const workers = task?.workers || [];
  const currentCommander = task?.stateCommander || null;
  const currentCommanderReview = task?.stateCommanderReview || null;
  const directBaseline = latestState?.directBaseline || task?.directBaseline || null;
  if (!workers.length && !currentCommander && !currentCommanderReview && !directBaseline) {
    $list.append($("<div>").addClass("footer-checkpoint-empty").text("No checkpoints yet."));
    return;
  }

  const workerState = task?.stateWorkers || {};
  const entries = workers.map(function (worker) {
    return { worker, checkpoint: workerState[worker.id] || null };
  }).sort(function (left, right) {
    const leftStep = left.checkpoint?.step || 0;
    const rightStep = right.checkpoint?.step || 0;
    if (!!left.checkpoint !== !!right.checkpoint) return left.checkpoint ? -1 : 1;
    return rightStep - leftStep;
  });

  if (!entries.some(function (entry) { return !!entry.checkpoint; })) {
    if (!currentCommander && !directBaseline) {
      $list.append($("<div>").addClass("footer-checkpoint-empty").text("Waiting for the first worker checkpoints."));
      return;
    }
  }

  if (currentCommander) {
    const commanderPreview = truncateText(currentCommander.answerDraft || currentCommander.leadDirection || "Commander draft available.", 88);
    const $item = $("<div>").addClass("footer-checkpoint-item compact-hover-card");
    const $head = $("<div>").addClass("footer-checkpoint-head");
    $head.append($("<div>").addClass("footer-checkpoint-title").text("Commander"));
    $head.append($("<div>").addClass("footer-checkpoint-step").text("round " + Number(currentCommander.round || 0)));
    $item.append($head);
    $item.append($("<div>").addClass("footer-checkpoint-copy").text(commanderPreview));
    appendCompactHoverPopup($item, [
      currentCommander.stance ? "Stance: " + truncateText(currentCommander.stance, 220) : "",
      currentCommander.leadDirection ? "Lead direction: " + truncateText(currentCommander.leadDirection, 280) : "",
      currentCommander.answerDraft ? "Draft: " + truncateText(currentCommander.answerDraft, 320) : "",
      currentCommander.whyThisDirection ? "Reason: " + truncateText(currentCommander.whyThisDirection, 240) : ""
    ]);
    $list.append($item);
  }

  if (currentCommanderReview) {
    const reviewPreview = truncateText(currentCommanderReview.answerDraft || currentCommanderReview.leadDirection || "Commander review available.", 88);
    const $item = $("<div>").addClass("footer-checkpoint-item compact-hover-card");
    const $head = $("<div>").addClass("footer-checkpoint-head");
    $head.append($("<div>").addClass("footer-checkpoint-title").text("Commander Review"));
    $head.append($("<div>").addClass("footer-checkpoint-step").text("round " + Number(currentCommanderReview.round || 0)));
    $item.append($head);
    $item.append($("<div>").addClass("footer-checkpoint-copy").text(reviewPreview));
    appendCompactHoverPopup($item, [
      currentCommanderReview.stance ? "Stance: " + truncateText(currentCommanderReview.stance, 220) : "",
      currentCommanderReview.leadDirection ? "Lead direction: " + truncateText(currentCommanderReview.leadDirection, 280) : "",
      currentCommanderReview.whyThisDirection ? "Reason: " + truncateText(currentCommanderReview.whyThisDirection, 240) : "",
      currentCommanderReview.controlAudit?.courseDecision ? "Course: " + formatCourseDecisionLabel(currentCommanderReview.controlAudit.courseDecision) : "",
      currentCommanderReview.dynamicLaneDecision?.shouldSpawn
        ? "Lane request: " + truncateText((currentCommanderReview.dynamicLaneDecision.suggestedLaneTypes || []).map(laneTypeLabel).join(", ") || currentCommanderReview.dynamicLaneDecision.reason || "", 220)
        : "",
      formatDynamicLaneResolution(currentCommanderReview.dynamicLaneResolution || {})
    ]);
    $list.append($item);
  }

  if (directBaseline) {
    const baselinePreview = truncateText(directBaseline.answer?.answer || "Single-thread baseline available.", 88);
    const $item = $("<div>").addClass("footer-checkpoint-item compact-hover-card");
    const $head = $("<div>").addClass("footer-checkpoint-head");
    $head.append($("<div>").addClass("footer-checkpoint-title").text("Single-thread baseline"));
    $head.append($("<div>").addClass("footer-checkpoint-step").text("round " + Number(directBaseline.round || 1)));
    $item.append($head);
    $item.append($("<div>").addClass("footer-checkpoint-copy").text(baselinePreview));
    appendCompactHoverPopup($item, [
      directBaseline.answer?.stance ? "Stance: " + truncateText(directBaseline.answer.stance, 220) : "",
      directBaseline.answer?.confidenceNote ? "Confidence: " + truncateText(directBaseline.answer.confidenceNote, 220) : "",
      "Provider: " + providerLabel(directBaseline.provider || "openai") + " | Model: " + modelLabel(directBaseline.model || "n/a", directBaseline.provider || "openai")
    ]);
    $list.append($item);
  }

  entries.forEach(function (entry) {
    if (!entry.checkpoint) return;
    const worker = entry.worker;
    const checkpoint = entry.checkpoint;
    const preview = truncateText(checkpoint.observation || checkpoint.requestToPeer || "Checkpoint available.", 88);
    const $item = $("<div>").addClass("footer-checkpoint-item compact-hover-card");
    const $head = $("<div>").addClass("footer-checkpoint-head");
    $head.append($("<div>").addClass("footer-checkpoint-title").text(displayWorkerLabel(worker)));
    $head.append($("<div>").addClass("footer-checkpoint-step").text("step " + (checkpoint.step || 0)));
    $item.append($head);
    $item.append($("<div>").addClass("footer-checkpoint-copy").text(preview));
    appendCompactHoverPopup($item, [
      "Role: " + (worker.role || "worker") + " | Model: " + modelLabel(worker.model),
      checkpoint.observation ? "Observation: " + truncateText(checkpoint.observation, 280) : "",
      checkpoint.requestToPeer ? "Peer steer: " + truncateText(checkpoint.requestToPeer, 220) : "",
      checkpoint.confidence != null ? "Confidence: " + Math.round(Number(checkpoint.confidence) * 100) + "%" : ""
    ]);
    $list.append($item);
  });
}

function buildWorkerControlCard(worker, isActive, status) {
  const workerId = String(worker.id || "").trim();
  const harness = normalizeHarnessConfig(worker?.harness, "tight");
  const $card = $("<div>")
    .addClass("workercontrol workercontrol-modal-card " + statusClassName(status))
    .attr("data-worker-id", workerId);

  const $summary = $("<button>")
    .attr("type", "button")
    .addClass("workercontrol-summary workercontrol-modal-trigger")
    .attr("data-worker-editor-kind", "worker")
    .attr("data-worker-id", workerId)
    .attr("aria-haspopup", "dialog")
    .prop("disabled", false);
  const $summaryMain = $("<div>").addClass("workercontrol-summary-main");
  $summaryMain.append($("<div>").addClass("workercontrol-title").text(displayWorkerLabel(worker)));
  $summaryMain.append(
    $("<div>").addClass("workercontrol-meta").text(
      workerDirectiveLabel(worker) + " | " + workerTemperatureLabel(worker) + " | " + harnessConcisionLabel(harness, "tight") + " | " + modelLabel(worker.model)
    )
  );
  $summary.append($summaryMain);
  $summary.append(buildStatusBadge(status));
  $summary.append($("<div>").addClass("workercontrol-summary-caret").attr("aria-hidden", "true").text(""));
  $card.append($summary);
  return $card;
}

function buildSummarizerControlCard(summarizer, isActive, status) {
  const harness = normalizeHarnessConfig(summarizer?.harness, "expansive");
  const $card = $("<div>")
    .addClass("workercontrol workercontrol-modal-card summarizer-control-card " + statusClassName(status))
    .attr("data-position-id", "summarizer");

  const $summary = $("<button>")
    .attr("type", "button")
    .addClass("workercontrol-summary workercontrol-modal-trigger")
    .attr("data-worker-editor-kind", "summarizer")
    .attr("data-position-id", "summarizer")
    .attr("aria-haspopup", "dialog");
  const $summaryMain = $("<div>").addClass("workercontrol-summary-main");
  $summaryMain.append($("<div>").addClass("workercontrol-title").text("Main thread"));
  $summaryMain.append(
    $("<div>").addClass("workercontrol-meta").text(
      "Lead voice | " + harnessConcisionLabel(harness, "expansive") + " | " + modelLabel(summarizer?.model || "gpt-5-mini", summarizer?.provider)
    )
  );
  $summary.append($summaryMain);
  $summary.append(buildStatusBadge(status));
  $summary.append($("<div>").addClass("workercontrol-summary-caret").attr("aria-hidden", "true").text(""));
  $card.append($summary);
  return $card;
}

function renderHomeRuntimeControls(task, draft, loop) {
  const $summary = $("#homeRuntimeSummary");
  const $grid = $("#homeQualityProfiles");
  const $apply = $("#applyHomeRuntime");
  if (!$summary.length || !$grid.length || !$apply.length) return;

  const stagedPayload = collectCommanderPayload();
  const stagedSnapshot = buildQualityProfileSnapshot();
  const stagedProfileId = detectQualityProfileId(stagedSnapshot);
  const stagedProfileName = profileDisplayName(stagedProfileId);
  const activeSnapshot = buildTaskQualityProfileSnapshot(task);
  const activeProfileId = detectQualityProfileId(activeSnapshot);
  const activeProfileName = profileDisplayName(activeProfileId);
  const isLoopActive = loop?.status === "running" || loop?.status === "queued";
  const hasTask = !!task;
  const runtimeMatches = hasTask && activeSnapshot ? runtimeSnapshotsMatch(stagedSnapshot, activeSnapshot) : false;
  const stagedCapabilities = providerCapabilities(stagedSnapshot.provider);
  const activeCapabilities = providerCapabilities(activeSnapshot?.provider || task?.runtime?.provider || stagedSnapshot.provider);

  $summary.empty();

  appendHomeRuntimeBlock(
    $summary,
    "Next send",
    stagedProfileName,
    [
      "Workers: " + providerLabel(stagedSnapshot.provider) + " / " + modelLabel(stagedSnapshot.model, stagedSnapshot.provider) + " | Summarizer: " + providerLabel(stagedSnapshot.summarizerProvider) + " / " + modelLabel(stagedSnapshot.summarizerModel, stagedSnapshot.summarizerProvider) + " | Reasoning: " + (stagedSnapshot.reasoningEffort || "low"),
      "Worker context: " + contextModeLabel(stagedSnapshot.contextMode),
      "Answer path: " + directBaselineModeLabel(stagedSnapshot.directBaselineMode) + (
        normalizeDirectBaselineMode(stagedSnapshot.directBaselineMode) === "off"
          ? ""
          : " | Baseline: " + providerLabel(stagedSnapshot.directProvider) + " / " + modelLabel(stagedSnapshot.directModel, stagedSnapshot.directProvider)
      ),
      "Budget: " + formatUsdBudget(stagedSnapshot.maxCostUsd) + " | " + formatTokenWall(stagedSnapshot.maxTotalTokens) + " | " + Number(stagedSnapshot.maxOutputTokens || 0).toLocaleString() + " max out",
      "Research: " + (stagedPayload.researchEnabled === "1" ? "on" : "off") + " | Vetting: " + (stagedPayload.vettingEnabled === "0" ? "off" : "on") + " | Auto loop: " + Number(stagedPayload.loopRounds || 0) + " rounds / " + Number(stagedPayload.loopDelayMs || 0) + " ms",
      (shouldShowOllamaBaseUrl(stagedSnapshot.provider, stagedSnapshot.summarizerProvider) || (normalizeDirectBaselineMode(stagedSnapshot.directBaselineMode) !== "off" && normalizeProviderId(stagedSnapshot.directProvider) === "ollama"))
        ? ("Ollama endpoint: " + normalizeOllamaBaseUrl(stagedSnapshot.ollamaBaseUrl))
        : "Ollama endpoint: inactive for this staged provider mix",
      "Provider capabilities: " + providerCapabilitySummary(stagedCapabilities),
      providerNoteSummary(stagedSnapshot.provider)
    ],
    false,
    providerLabel(stagedSnapshot.provider) + " -> " + providerLabel(stagedSnapshot.summarizerProvider) + " | " + (stagedPayload.executionMode || "live") + " mode"
  );

  if (hasTask && activeSnapshot) {
    appendHomeRuntimeBlock(
      $summary,
      "Active task",
      activeProfileName,
      [
        "Workers: " + providerLabel(activeSnapshot.provider) + " / " + modelLabel(activeSnapshot.model, activeSnapshot.provider) + " | Summarizer: " + providerLabel(activeSnapshot.summarizerProvider) + " / " + modelLabel(activeSnapshot.summarizerModel, activeSnapshot.summarizerProvider) + " | Reasoning: " + (activeSnapshot.reasoningEffort || "low"),
        "Worker context: " + contextModeLabel(activeSnapshot.contextMode),
        "Answer path: " + directBaselineModeLabel(activeSnapshot.directBaselineMode) + (
          normalizeDirectBaselineMode(activeSnapshot.directBaselineMode) === "off"
            ? ""
            : " | Baseline: " + providerLabel(activeSnapshot.directProvider) + " / " + modelLabel(activeSnapshot.directModel, activeSnapshot.directProvider)
        ),
        "Budget: " + formatUsdBudget(activeSnapshot.maxCostUsd) + " | " + formatTokenWall(activeSnapshot.maxTotalTokens) + " | " + Number(activeSnapshot.maxOutputTokens || 0).toLocaleString() + " max out",
        "Auto loop: " + Number(activeSnapshot.loopRounds || 0) + " rounds / " + Number(activeSnapshot.loopDelayMs || 0) + " ms",
        (shouldShowOllamaBaseUrl(activeSnapshot.provider, activeSnapshot.summarizerProvider) || (normalizeDirectBaselineMode(activeSnapshot.directBaselineMode) !== "off" && normalizeProviderId(activeSnapshot.directProvider) === "ollama"))
          ? ("Ollama endpoint: " + normalizeOllamaBaseUrl(activeSnapshot.ollamaBaseUrl))
          : "Ollama endpoint: inactive for this active provider mix",
        "Provider capabilities: " + providerCapabilitySummary(activeCapabilities),
        providerNoteSummary(activeSnapshot.provider)
      ],
      false,
      providerLabel(activeSnapshot.provider) + " -> " + providerLabel(activeSnapshot.summarizerProvider) + " | " + (task?.runtime?.executionMode || "live") + " mode"
    );

    appendHomeRuntimeBlock(
      $summary,
      runtimeMatches ? "Runtime sync" : "Runtime drift",
      runtimeMatches ? "Aligned" : "Sync needed",
      [
        runtimeMatches
          ? "Active task already matches the staged template."
          : "Next send and active task are different.",
        runtimeMatches
          ? "You can keep prompting without touching settings."
          : "Use Sync Active if you want the current task to adopt the staged profile, loop depth, and budget."
      ],
      !runtimeMatches,
      runtimeMatches ? "Staged and active runtime match." : "Staged and active runtime differ."
    );
  } else {
    appendHomeRuntimeBlock(
      $summary,
      "Active task",
      "Ready to start",
      ["Send will start a fresh task with the staged profile, roster, and loop settings."],
      false,
      "Next send will launch a new live task."
    );
  }

  $grid.empty();
  const stagedWorkerProvider = normalizeProviderId(stagedSnapshot.provider);
  const stagedSummarizerProvider = normalizeProviderId(stagedSnapshot.summarizerProvider || stagedSnapshot.provider);
  QUALITY_PROFILE_ORDER.forEach(function (profileId) {
    const profile = QUALITY_PROFILE_CATALOG[profileId];
    const workerModels = qualityProfileModelConfig(profileId, stagedWorkerProvider);
    const summarizerModels = qualityProfileModelConfig(profileId, stagedSummarizerProvider);
    const $button = $("<button>")
      .attr("type", "button")
      .addClass("quick-profile-chip compact-hover-card")
      .toggleClass("active", stagedProfileId === profileId)
      .attr("data-profile-id", profileId);
    $button.append($("<div>").addClass("quality-profile-eyebrow").text(profile.eyebrow));
    $button.append($("<div>").addClass("quick-profile-title").text(profile.label));
    appendCompactHoverPopup($button, [
      profile.description,
      "Workers: " + providerLabel(stagedWorkerProvider) + " / " + modelLabel(workerModels.workerModel, stagedWorkerProvider),
      "Summarizer: " + providerLabel(stagedSummarizerProvider) + " / " + modelLabel(summarizerModels.summarizerModel, stagedSummarizerProvider),
      "Budget: " + formatUsdBudget(profile.maxCostUsd) + " | " + formatTokenWall(profile.maxTotalTokens),
      "Reasoning: " + profile.reasoningEffort + " | Loop: " + Number(profile.loopRounds || 0) + " rounds"
    ]);
    $grid.append($button);
  });

  $apply.prop("disabled", isLoopActive || !hasTask);
  $apply.text(isLoopActive ? "Loop Active" : "Sync Active");
}

function renderListSection(label, items) {
  const normalized = (items || []).filter(Boolean);
  if (!normalized.length) return "";
  const htmlItems = normalized.map(function (item) {
    return "<li>" + escapeHtml(item) + "</li>";
  }).join("");
  return `
    <div class="message-block">
      <div class="message-block-label">${escapeHtml(label)}</div>
      <ul class="message-list">${htmlItems}</ul>
    </div>
  `;
}

function renderTextSection(label, text) {
  const normalized = String(text || "").trim();
  if (!normalized) return "";
  return `
    <div class="message-block">
      <div class="message-block-label">${escapeHtml(label)}</div>
      <div class="message-text">${escapeHtml(normalized)}</div>
    </div>
  `;
}

function renderPlainTextBlock(text) {
  const normalized = String(text || "").trim();
  if (!normalized) return "";
  return `<div class="message-body-plain">${escapeHtml(normalized)}</div>`;
}

function formatElapsedCompact(startedAt) {
  const raw = String(startedAt || "").trim();
  if (!raw) return "";
  const start = new Date(raw);
  const time = start.getTime();
  if (Number.isNaN(time)) return "";
  const deltaSeconds = Math.max(0, Math.round((Date.now() - time) / 1000));
  const hours = Math.floor(deltaSeconds / 3600);
  const minutes = Math.floor((deltaSeconds % 3600) / 60);
  const seconds = deltaSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function friendlyTargetLabel(target, task) {
  const id = String(target || "").trim();
  if (!id) return "Preparing";
  if (id === "commander") return "Commander";
  if (id === "commander_review") return "Commander Review";
  if (id === "direct_baseline") return "Single-thread baseline";
  if (id === "summarizer") return "Summarizer";
  if (id === "answer_now") return "Answer Now";
  const worker = (task?.workers || []).find(function (entry) {
    return String(entry?.id || "").trim().toUpperCase() === id.toUpperCase();
  });
  return worker ? `${worker.id} / ${displayWorkerLabel(worker)}` : id;
}

function latestCompletedSurface(task, workerState, state) {
  const entries = [];
  const commander = state?.commander || task?.stateCommander || null;
  const commanderReview = state?.commanderReview || task?.stateCommanderReview || null;
  const directBaseline = state?.directBaseline || task?.directBaseline || null;
  if (commander?.updatedAt || commander?.round) {
    entries.push({
      sortAt: String(commander.updatedAt || ""),
      label: "Commander",
      preview: String(commander.answerDraft || commander.leadDirection || "Commander draft ready.").trim()
    });
  }
  (task?.workers || []).forEach(function (worker) {
    const checkpoint = workerState?.[worker.id] || null;
    if (!checkpoint) return;
    entries.push({
      sortAt: String(checkpoint.updatedAt || ""),
      label: `${worker.id} / ${displayWorkerLabel(worker)}`,
      preview: String(checkpoint.observation || checkpoint.requestToPeer || "Checkpoint ready.").trim()
    });
  });
  if (commanderReview?.updatedAt || commanderReview?.round) {
    entries.push({
      sortAt: String(commanderReview.updatedAt || ""),
      label: "Commander Review",
      preview: String(commanderReview.whyThisDirection || commanderReview.answerDraft || commanderReview.leadDirection || "Review checkpoint ready.").trim()
    });
  }
  if (directBaseline?.capturedAt || directBaseline?.answer?.answer) {
    entries.push({
      sortAt: String(directBaseline.capturedAt || ""),
      label: "Single-thread baseline",
      preview: String(directBaseline.answer?.answer || "Baseline answer ready.").trim()
    });
  }
  entries.sort(function (left, right) {
    return String(right.sortAt || "").localeCompare(String(left.sortAt || ""));
  });
  return entries[0] || null;
}

function renderWaitingProgress(task, workerState, loop, state) {
  const usage = state?.usage || {};
  const executionHealth = state?.executionHealth || task?.executionHealth || {};
  const contractWarnings = Array.isArray(state?.contractWarnings) ? state.contractWarnings.filter(Boolean) : [];
  const activeTarget = inferFrontActiveTarget(loop, state);
  const directMode = normalizeDirectBaselineMode(task?.runtime?.directBaselineMode);
  const hasDirectBaseline = !!(state?.directBaseline || task?.directBaseline);
  const totalStages = directMode === "single"
    ? 1
    : ((task?.workers?.length || 0) + 3 + (directMode === "both" ? 1 : 0));
  const completedStages = directMode === "single"
    ? (hasDirectBaseline ? 1 : 0)
    : (
      (state?.commander || task?.stateCommander ? 1 : 0) +
      Object.keys(workerState || {}).length +
      (state?.commanderReview || task?.stateCommanderReview ? 1 : 0) +
      (task?.summary || state?.summary ? 1 : 0) +
      (directMode === "both" && hasDirectBaseline ? 1 : 0)
    );
  const latestDone = latestCompletedSurface(task, workerState, state);
  const latestIssue = executionHealth?.latestIssue || null;
  let executionNote = "";
  if (latestIssue) {
    if (latestIssue.usedMockFallback) {
      executionNote = `${latestIssue.label || friendlyTargetLabel(latestIssue.target, task)} fell back to mock. ${String(latestIssue.lastError || latestIssue.lastMessage || "").trim()}`;
    } else if (latestIssue.recoveredFromIncomplete) {
      executionNote = `${latestIssue.label || friendlyTargetLabel(latestIssue.target, task)} needed output-token recovery but still completed live.`;
    } else if (latestIssue.lastMessage) {
      executionNote = `${latestIssue.label || friendlyTargetLabel(latestIssue.target, task)} reported a degraded run. ${String(latestIssue.lastMessage || "").trim()}`;
    }
    if (executionNote && Number(executionHealth.issueCount || 0) > 1) {
      executionNote += ` ${executionHealth.issueCount} stages in this task have degraded behavior recorded.`;
    }
  }
  const sections = [
    `
      <div class="thread-progress-card">
        <div class="thread-progress-head">
          <div>
            <div class="thread-progress-kicker">Live status</div>
            <div class="thread-progress-title">${escapeHtml(friendlyTargetLabel(activeTarget || (directMode === "single" ? "direct_baseline" : "summarizer"), task))}</div>
          </div>
          <div class="thread-progress-badge ${escapeHtml(statusClassName({ key: activeTarget ? "running" : "waiting" }))}">${escapeHtml(activeTarget ? "Working" : "Waiting")}</div>
        </div>
        <div class="thread-progress-grid">
          <div class="thread-progress-stat">
            <span class="thread-progress-stat-label">Elapsed</span>
            <strong>${escapeHtml(formatElapsedCompact(loop?.startedAt || loop?.queuedAt) || "Just started")}</strong>
          </div>
          <div class="thread-progress-stat">
            <span class="thread-progress-stat-label">Completed</span>
            <strong>${escapeHtml(`${Math.min(completedStages, totalStages)} / ${totalStages} stages`)}</strong>
          </div>
          <div class="thread-progress-stat">
            <span class="thread-progress-stat-label">Tokens</span>
            <strong>${escapeHtml(Number(usage.totalTokens || 0).toLocaleString())}</strong>
          </div>
          <div class="thread-progress-stat">
            <span class="thread-progress-stat-label">Spend</span>
            <strong>${escapeHtml(formatUsd(usage.estimatedCostUsd || 0))}</strong>
          </div>
        </div>
      </div>
    `,
    renderTextSection("Loop message", loop?.lastMessage || "Working through the current stage."),
    executionNote ? renderTextSection("Execution note", truncateText(executionNote, 260)) : "",
    contractWarnings.length ? renderTextSection("State note", truncateText(contractWarnings.join(" "), 260)) : "",
    latestDone ? renderTextSection("Latest completed", `${latestDone.label}: ${truncateText(latestDone.preview, 220)}`) : "",
    directMode === "both" && hasDirectBaseline && !task?.summary && !state?.summary
      ? renderTextSection("Compare note", "The single-thread baseline is already captured in Review while the pressurized answer is still running.")
      : "",
    renderListSection("What you can do now", [
      directMode !== "single" && completedStages > 0 ? "Use Answer Now to force a partial front answer from completed work." : "",
      "Leave the tab open and the loop will keep polling live progress.",
      activeTarget ? `${friendlyTargetLabel(activeTarget, task)} is the current active stage.` : ""
    ])
  ];
  return sections.filter(Boolean).join("");
}

function buildLegacyAgentReplyText(summary) {
  if (!summary) return "";
  const paragraphs = [];
  const stableFindings = (summary.stableFindings || []).filter(Boolean);
  if (stableFindings.length) {
    paragraphs.push(stableFindings.join(" "));
  }

  const conflictTopics = (summary.conflicts || []).map(function (conflict) {
    return conflict?.topic;
  }).filter(Boolean);
  if (conflictTopics.length) {
    paragraphs.push("Remaining disagreement: " + conflictTopics.join("; ") + ".");
  }

  if (summary.recommendedNextAction) {
    paragraphs.push("Next step: " + summary.recommendedNextAction);
  }

  if (summary.vettingSummary) {
    paragraphs.push("Confidence note: " + summary.vettingSummary);
  }

  return paragraphs.join("\n\n").trim();
}

function buildAgentReplyText(summary) {
  const directAnswer = String(summary?.frontAnswer?.answer || "").trim();
  if (directAnswer) {
    return directAnswer;
  }
  return buildLegacyAgentReplyText(summary);
}

function buildWorkerInspector(checkpoints) {
  const entries = (checkpoints || []).filter(function (entry) {
    return !!entry?.checkpoint;
  });
  if (!entries.length) return "";

  const cards = entries.map(function (entry) {
    const checkpoint = entry.checkpoint || {};
    const insights = [];
    if (checkpoint.observation) {
      insights.push(truncateText(checkpoint.observation, 220));
    }
    if (checkpoint.requestToPeer) {
      insights.push("Peer steer: " + truncateText(checkpoint.requestToPeer, 180));
    }
    const confidence = checkpoint.confidence != null && !Number.isNaN(Number(checkpoint.confidence))
      ? "Confidence " + Math.round(Number(checkpoint.confidence) * 100) + "%"
      : "Checkpoint captured";
    return `
      <div class="lane-inspector-card ${escapeHtml(entry.worker.role || "")}">
        <div class="lane-inspector-head">
          <div class="lane-inspector-title">${escapeHtml(displayWorkerLabel(entry.worker))}</div>
          <div class="lane-inspector-tag">${escapeHtml(confidence)}</div>
        </div>
        <div class="lane-inspector-meta">${escapeHtml((entry.worker.type || entry.worker.role || "lane") + " | " + (entry.worker.model || "model n/a"))}</div>
        <div class="lane-inspector-copy">${escapeHtml(insights.join(" "))}</div>
      </div>
    `;
  }).join("");

  return `
    <details class="lane-inspector"${threadInspectorOpen ? " open" : ""}>
      <summary>Inspect worker lanes (${entries.length})</summary>
      <div class="lane-inspector-note">Internal lane output is hidden by default so the main answer stays readable.</div>
      <div class="lane-inspector-grid">
        ${cards}
      </div>
    </details>
  `;
}

function buildFallbackLineCatalog(task, workerState) {
  const catalog = [];
  const orderedFields = [
    ["benefits", "benefit"],
    ["detriments", "risk"],
    ["requiredCircumstances", "requirement"],
    ["invalidatingCircumstances", "invalidator"],
    ["immediateConsequences", "immediate_consequence"],
    ["downstreamConsequences", "downstream_consequence"],
    ["uncertainty", "uncertainty"],
    ["reversalConditions", "reversal_condition"],
    ["evidenceGaps", "evidence_gap"]
  ];

  (task?.workers || []).forEach(function (worker) {
    const checkpoint = workerState?.[worker.id];
    if (!checkpoint) return;
    let added = 0;

    function appendLine(refSuffix, kind, text, sourceUrls, supportLevel) {
      if (added >= 14) return;
      const content = truncateText(text, 300);
      if (!content) return;
      catalog.push({
        ref: worker.id + "." + refSuffix,
        workerId: worker.id,
        label: checkpoint.label || worker.label || displayWorkerLabel(worker),
        role: checkpoint.role || worker.role || "",
        step: Number(checkpoint.step || 0),
        kind: kind,
        text: content,
        supportLevel: truncateText(supportLevel, 32),
        sourceUrls: Array.isArray(sourceUrls) ? sourceUrls.filter(Boolean).slice(0, 8) : []
      });
      added += 1;
    }

    appendLine("observation", "observation", checkpoint.observation, [], "");
    (checkpoint.evidenceLedger || []).forEach(function (entry, index) {
      const claim = truncateText(entry?.claim || "", 220);
      const note = truncateText(entry?.note || "", 140);
      const combined = note ? (claim ? claim + " Evidence note: " + note : note) : claim;
      appendLine("evidenceLedger[" + index + "]", "evidence", combined, entry?.sourceUrls || [], entry?.supportLevel || "");
    });
    orderedFields.forEach(function (fieldPair) {
      const fieldName = fieldPair[0];
      const kind = fieldPair[1];
      (checkpoint[fieldName] || []).forEach(function (item, index) {
        appendLine(fieldName + "[" + index + "]", kind, item, [], "");
      });
    });
    (checkpoint.urlCitations || []).slice(0, 2).forEach(function (url, index) {
      appendLine("urlCitations[" + index + "]", "citation", url, [url], "cited");
    });
    appendLine("requestToPeer", "peer_steer", checkpoint.requestToPeer, [], "");
  });

  return catalog;
}

function getSummaryLineCatalog(summary, task, workerState) {
  const catalog = Array.isArray(summary?.lineCatalog) && summary.lineCatalog.length
    ? summary.lineCatalog
    : buildFallbackLineCatalog(task, workerState);
  const lineMap = {};
  catalog.forEach(function (entry) {
    if (entry?.ref) {
      lineMap[entry.ref] = entry;
    }
  });
  return { catalog, lineMap };
}

function renderReviewSourceUrls(urls) {
  const list = (urls || []).filter(Boolean);
  if (!list.length) return "";
  return `
    <div class="review-source-list">
      ${list.map(function (url) {
        return `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a>`;
      }).join("")}
    </div>
  `;
}

function renderReviewBlock(label, text) {
  const normalized = String(text || "").trim();
  if (!normalized) return "";
  return `
    <div class="review-block">
      <div class="review-block-label">${escapeHtml(label)}</div>
      <div class="review-block-text">${escapeHtml(normalized)}</div>
    </div>
  `;
}

function formatCourseDecisionLabel(decision) {
  const normalized = String(decision || "").trim().toLowerCase().replace(/[_-]+/g, " ");
  if (!normalized) return "";
  return normalized.replace(/\b\w/g, function (match) {
    return match.toUpperCase();
  });
}

function laneTypeLabel(typeId) {
  const normalized = String(typeId || "").trim().toLowerCase();
  return WORKER_TYPE_CATALOG[normalized]?.label || formatCourseDecisionLabel(normalized);
}

function formatDynamicLaneResolution(resolution) {
  const normalized = resolution && typeof resolution === "object" ? resolution : {};
  const status = String(normalized.status || "").trim();
  if (!status || status === "not_requested") return "";
  const rejected = Array.isArray(normalized.rejectedLaneTypes) ? normalized.rejectedLaneTypes : [];
  return [
    "Status: " + formatCourseDecisionLabel(status),
    normalized.selectedLaneType ? "Chosen lane: " + laneTypeLabel(normalized.selectedLaneType) : "",
    normalized.spawnedWorkerId ? "Spawned worker: " + normalized.spawnedWorkerId : "",
    Number(normalized.activationRound || 0) > 0 ? "Activation round: " + Number(normalized.activationRound) : "",
    normalized.selectedBecause ? "Why this lane won: " + normalized.selectedBecause : "",
    rejected.length
      ? "Rejected candidates: " + rejected.map(function (entry) {
          return laneTypeLabel(entry?.laneType) + " (" + String(entry?.reason || "").trim() + ")";
        }).join("; ")
      : ""
  ].filter(Boolean).join("\n");
}

function renderContributionAssessments(items) {
  if (!Array.isArray(items) || !items.length) return "";
  const lines = items.map(function (item) {
    const contribution = String(item?.contribution || "").trim();
    if (!contribution) return "";
    const value = String(item?.value || "").trim().toLowerCase();
    const effect = String(item?.effect || "").trim().toLowerCase();
    const reason = String(item?.reason || "").trim();
    const prefix = [effect ? formatCourseDecisionLabel(effect) : "", value ? value.toUpperCase() : ""].filter(Boolean).join(" | ");
    return [prefix, contribution, reason].filter(Boolean).join("\n");
  }).filter(Boolean);
  return lines.length ? renderReviewBlock("Contribution value checks", lines.join("\n\n")) : "";
}

function renderReviewLineSnippet(ref, entry) {
  if (!entry) {
    return `
      <div class="review-line-snippet missing">
        <div class="review-line-ref-row">
          <span class="line-ref-chip missing">${escapeHtml(ref)}</span>
        </div>
        <div class="review-line-text">Referenced line is not available in the current catalog.</div>
      </div>
    `;
  }
  return `
    <div class="review-line-snippet">
      <div class="review-line-ref-row">
        <a class="line-ref-chip" href="#${escapeHtml(lineAnchorId(ref))}">${escapeHtml(ref)}</a>
        ${entry.supportLevel ? `<span class="review-line-badge">${escapeHtml(entry.supportLevel)}</span>` : ""}
        <span class="review-line-meta">${escapeHtml((entry.label || entry.workerId || "line") + " | step " + (entry.step ?? 0))}</span>
      </div>
      <div class="review-line-text">${escapeHtml(entry.text || "")}</div>
      ${renderReviewSourceUrls(entry.sourceUrls || [])}
    </div>
  `;
}

function renderTraceLineSet(label, refs, lineMap, emptyText) {
  if (!refs || !refs.length) {
    return `
      <div class="review-trace-column">
        <div class="review-block-label">${escapeHtml(label)}</div>
        <div class="review-empty small">${escapeHtml(emptyText)}</div>
      </div>
    `;
  }
  return `
    <div class="review-trace-column">
      <div class="review-block-label">${escapeHtml(label)}</div>
      <div class="review-line-snippet-list">
        ${refs.map(function (ref) {
          return renderReviewLineSnippet(ref, lineMap[ref] || null);
        }).join("")}
      </div>
    </div>
  `;
}

function renderSummaryOpinion(summary, directBaseline) {
  if (!summary && !directBaseline) {
    return `<div class="review-empty">No answer artifact yet.</div>`;
  }
  const executionHealth = latestState?.executionHealth || latestState?.activeTask?.executionHealth || null;
  const contractWarnings = Array.isArray(latestState?.contractWarnings)
    ? latestState.contractWarnings.filter(Boolean)
    : (Array.isArray(latestState?.activeTask?.contractWarnings) ? latestState.activeTask.contractWarnings.filter(Boolean) : []);
  const frontAnswer = summary?.frontAnswer || {};
  const opinion = summary?.summarizerOpinion || {};
  const controlAudit = summary?.controlAudit || {};
  const dynamicLaneDecision = summary?.dynamicLaneDecision || {};
  const dynamicLaneResolution = summary?.dynamicLaneResolution || {};
  const directAnswer = directBaseline?.answer || {};
  const hasSummary = !!summary;
  const blocks = [
    executionHealth
      ? renderReviewBlock("Execution status", formatExecutionHealthSummary(executionHealth))
      : "",
    contractWarnings.length
      ? renderReviewBlock("State contract", contractWarnings.join("\n"))
      : "",
    hasSummary
      ? renderReviewBlock("Public answer", frontAnswer.answer || buildAgentReplyText(summary))
      : renderReviewBlock("Single-thread answer", directAnswer.answer || ""),
    directBaseline
      ? renderReviewBlock(
          "Single-thread baseline",
          [
            directAnswer.answer || "",
            directAnswer.stance ? "Stance: " + directAnswer.stance : "",
            directAnswer.confidenceNote ? "Confidence: " + directAnswer.confidenceNote : "",
            "Mode: " + String(directBaseline.mode || "n/a") + " | Provider: " + providerLabel(directBaseline.provider || "openai") + " | Model: " + modelLabel(directBaseline.model || "n/a", directBaseline.provider || "openai")
          ].filter(Boolean).join("\n\n")
        )
      : "",
    hasSummary ? renderReviewBlock("Lead direction", frontAnswer.leadDirection || frontAnswer.stance || "") : "",
    hasSummary ? renderReviewBlock("Absorbed adversarial pressure", frontAnswer.adversarialPressure || "") : "",
    hasSummary ? renderReviewBlock("Current stance", opinion.stance || frontAnswer.stance || "") : "",
    hasSummary ? renderReviewBlock("Why it landed here", opinion.because || "") : "",
    hasSummary ? renderReviewBlock("Integration mode", opinion.integrationMode || "") : "",
    hasSummary ? renderReviewBlock("Lead draft before pressure", controlAudit.leadDraft || "") : "",
    hasSummary ? renderReviewBlock("Control question", controlAudit.integrationQuestion || "") : "",
    hasSummary ? renderReviewBlock("Course decision", formatCourseDecisionLabel(controlAudit.courseDecision || "")) : "",
    hasSummary ? renderReviewBlock("Why course changed or held", controlAudit.courseDecisionReason || "") : "",
    hasSummary ? renderContributionAssessments(controlAudit.contributionAssessments || []) : "",
    hasSummary && Array.isArray(controlAudit.acceptedAdversarialPoints) && controlAudit.acceptedAdversarialPoints.length
      ? renderReviewBlock("Accepted adversarial points", controlAudit.acceptedAdversarialPoints.join("\n"))
      : "",
    hasSummary && Array.isArray(controlAudit.rejectedAdversarialPoints) && controlAudit.rejectedAdversarialPoints.length
      ? renderReviewBlock("Rejected adversarial points", controlAudit.rejectedAdversarialPoints.join("\n"))
      : "",
    hasSummary && Array.isArray(controlAudit.heldOutConcerns) && controlAudit.heldOutConcerns.length
      ? renderReviewBlock("Held-out concerns", controlAudit.heldOutConcerns.join("\n"))
      : "",
    hasSummary ? renderReviewBlock("Pre-release self-check", controlAudit.selfCheck || "") : "",
    hasSummary && dynamicLaneDecision.shouldSpawn
      ? renderReviewBlock(
          "Next-round lane request",
          [
            Array.isArray(dynamicLaneDecision.suggestedLaneTypes) && dynamicLaneDecision.suggestedLaneTypes.length
              ? "Types: " + dynamicLaneDecision.suggestedLaneTypes.map(laneTypeLabel).join(", ")
              : "",
            dynamicLaneDecision.requiredPressure ? "Missing pressure: " + dynamicLaneDecision.requiredPressure : "",
            dynamicLaneDecision.temperature ? "Temperature: " + dynamicLaneDecision.temperature : "",
            dynamicLaneDecision.instruction ? "Harness: " + dynamicLaneDecision.instruction : "",
            dynamicLaneDecision.reason || ""
          ].filter(Boolean).join("\n")
        )
      : "",
    hasSummary && formatDynamicLaneResolution(dynamicLaneResolution)
      ? renderReviewBlock("Lane resolution", formatDynamicLaneResolution(dynamicLaneResolution))
      : "",
    renderReviewBlock("Uncertainty", hasSummary ? (opinion.uncertainty || frontAnswer.confidenceNote || "") : (directAnswer.confidenceNote || "")),
    hasSummary ? renderReviewBlock("Recommended next action", summary.recommendedNextAction || "") : "",
    hasSummary ? renderReviewBlock("Vetting note", summary.vettingSummary || "") : ""
  ].filter(Boolean);
  return blocks.length ? `<div class="review-stack">${blocks.join("")}</div>` : `<div class="review-empty">No answer artifact yet.</div>`;
}

function renderSummaryTrace(summary, task, workerState) {
  if (!summary) {
    return `<div class="review-empty">No adjudication trace yet.</div>`;
  }
  const reviewTrace = Array.isArray(summary.reviewTrace) ? summary.reviewTrace : [];
  if (!reviewTrace.length) {
    return `<div class="review-empty">No adjudication trace yet.</div>`;
  }
  const lineMap = getSummaryLineCatalog(summary, task, workerState).lineMap;
  return `
    <div class="review-trace-list">
      ${reviewTrace.map(function (entry, index) {
        return `
          <details class="review-trace-item"${index === 0 ? " open" : ""}>
            <summary>
              <span>${escapeHtml(entry.topic || "Untitled topic")}</span>
              <span class="review-trace-summary">${escapeHtml(entry.judgment || "")}</span>
            </summary>
            <div class="review-trace-body">
              ${renderReviewBlock("Judgment", entry.judgment || "")}
              ${renderReviewBlock("Because", entry.because || "")}
              <div class="review-trace-columns">
                ${renderTraceLineSet("Supporting lines", entry.supportingLineRefs || [], lineMap, "No supporting line refs were cited.")}
                ${renderTraceLineSet("Challenging lines", entry.challengingLineRefs || [], lineMap, "No challenging line refs were cited.")}
              </div>
              ${(entry.openQuestions || []).length ? renderReviewBlock("Open questions", (entry.openQuestions || []).join("\n")) : ""}
            </div>
          </details>
        `;
      }).join("")}
    </div>
  `;
}

function renderSummaryLineCatalog(summary, task, workerState) {
  const lineCatalog = getSummaryLineCatalog(summary, task, workerState).catalog;
  if (!lineCatalog.length) {
    return `<div class="review-empty">No review lines yet.</div>`;
  }
  const groups = {};
  lineCatalog.forEach(function (entry) {
    const workerId = entry.workerId || "?";
    if (!groups[workerId]) {
      groups[workerId] = {
        workerId: workerId,
        label: entry.label || workerId,
        role: entry.role || "",
        entries: []
      };
    }
    groups[workerId].entries.push(entry);
  });
  const orderedWorkerIds = Object.keys(groups).sort();
  return `
    <div class="line-catalog-list">
      ${orderedWorkerIds.map(function (workerId, index) {
        const group = groups[workerId];
        return `
          <details class="line-catalog-worker"${index === 0 ? " open" : ""}>
            <summary>
              <span>${escapeHtml(group.label)}</span>
              <span class="review-trace-summary">${escapeHtml((group.role || "lane") + " | " + group.entries.length + " lines")}</span>
            </summary>
            <div class="line-catalog-grid">
              ${group.entries.map(function (entry) {
                return `
                  <article class="review-line-card" id="${escapeHtml(lineAnchorId(entry.ref))}">
                    <div class="review-line-ref-row">
                      <span class="line-ref-chip">${escapeHtml(entry.ref)}</span>
                      ${entry.supportLevel ? `<span class="review-line-badge">${escapeHtml(entry.supportLevel)}</span>` : ""}
                      <span class="review-line-meta">${escapeHtml((entry.kind || "line") + " | step " + (entry.step ?? 0))}</span>
                    </div>
                    <div class="review-line-text">${escapeHtml(entry.text || "")}</div>
                    ${renderReviewSourceUrls(entry.sourceUrls || [])}
                  </article>
                `;
              }).join("")}
            </div>
          </details>
        `;
      }).join("")}
    </div>
  `;
}

function renderSummaryReview(summary, directBaseline, task, workerState) {
  $("#summaryOpinion").html(renderSummaryOpinion(summary, directBaseline));
  $("#summaryTrace").html(renderSummaryTrace(summary, task, workerState));
  $("#summaryLineCatalog").html(renderSummaryLineCatalog(summary, task, workerState));
}

function buildConversationRenderSignature(task, summary, directBaseline, workerState, loop, state) {
  if (!task) return "empty";
  const elapsedMarker = formatElapsedCompact(loop?.startedAt || loop?.queuedAt);

  const workerSignature = (task.workers || []).map(function (worker) {
    const checkpoint = workerState?.[worker.id] || null;
    return {
      id: worker.id,
      step: checkpoint?.step || 0,
      observation: checkpoint?.observation || "",
      requestToPeer: checkpoint?.requestToPeer || "",
      confidence: checkpoint?.confidence ?? null
    };
  });

  return JSON.stringify({
    taskId: task.taskId || "",
    objective: task.objective || "",
    executionMode: task.runtime?.executionMode || "",
    frontMode: normalizeFrontMode(task?.runtime?.frontMode),
    summary: summary ? {
      round: summary.round || 0,
      frontAnswer: summary.frontAnswer || null,
      stableFindings: summary.stableFindings || [],
      conflicts: summary.conflicts || [],
      recommendedNextAction: summary.recommendedNextAction || "",
      vettingSummary: summary.vettingSummary || "",
      claimsNeedingVerification: summary.claimsNeedingVerification || []
    } : null,
    directBaseline: directBaseline ? {
      mode: directBaseline.mode || "",
      provider: directBaseline.provider || "",
      model: directBaseline.model || "",
      answer: directBaseline.answer || null
    } : null,
    workers: workerSignature,
    loop: {
      status: loop?.status || "idle",
      lastMessage: loop?.lastMessage || "",
      currentRound: loop?.currentRound || 0,
      elapsedMarker
    },
    usage: {
      totalTokens: state?.usage?.totalTokens || 0,
      estimatedCostUsd: state?.usage?.estimatedCostUsd || 0
    },
    arbiter: state?.arbiter ? {
      taskId: state.arbiter.taskId || "",
      round: state.arbiter.round || 0,
      scoredAt: state.arbiter.scoredAt || "",
      verdict: state.arbiter.comparison?.verdict || "",
      decisionRelation: state.arbiter.comparison?.decisionRelation || "",
      pressurizedAnswer: state.arbiter.pressurized?.answer || "",
      baselineAnswer: state.arbiter.baseline?.answer || ""
    } : null,
    contractWarnings: Array.isArray(state?.contractWarnings) ? state.contractWarnings : [],
    commanderRound: (state?.commander || task?.stateCommander || {}).round || 0,
    commanderReviewRound: (state?.commanderReview || task?.stateCommanderReview || {}).round || 0
  });
}

function currentFrontEvalPairKey(task, summary, directBaseline) {
  const pressurizedAnswer = String(buildAgentReplyText(summary) || "").trim();
  const baselineAnswer = String(directBaseline?.answer?.answer || "").trim();
  if (!task || !pressurizedAnswer || !baselineAnswer) return "";
  return [
    String(task?.taskId || ""),
    String(summary?.round || 0),
    String(summary?.mergedAt || ""),
    String(directBaseline?.capturedAt || ""),
    pressurizedAnswer,
    baselineAnswer
  ].join("||");
}

function arbiterMatchesCurrentPair(task, arbiter, summary, directBaseline) {
  if (!task || !arbiter || typeof arbiter !== "object") return false;
  const pressurizedAnswer = String(buildAgentReplyText(summary) || "").trim();
  const baselineAnswer = String(directBaseline?.answer?.answer || "").trim();
  if (!pressurizedAnswer || !baselineAnswer) return false;
  return String(arbiter.taskId || "") === String(task.taskId || "")
    && Number(arbiter.round || 0) === Number(summary?.round || 0)
    && String(arbiter.pressurized?.answer || "").trim() === pressurizedAnswer
    && String(arbiter.baseline?.answer || "").trim() === baselineAnswer;
}

function buildFrontEvalAnswerEntries(task, summary, directBaseline, state) {
  const summaryProvider = task?.summarizer?.provider || task?.runtime?.provider || "";
  const summaryModel = task?.summarizer?.model || task?.runtime?.model || "";
  const pressurizedPayload = summary?.frontAnswer && typeof summary.frontAnswer === "object"
    ? summary.frontAnswer
    : {
        answer: buildAgentReplyText(summary),
        stance: summary?.frontAnswer?.stance || "",
        confidenceNote: summary?.frontAnswer?.confidenceNote || ""
      };
  const baselinePayload = directBaseline?.answer && typeof directBaseline.answer === "object"
    ? directBaseline.answer
    : { answer: "" };
  return {
    pressurizedEntry: normalizeEvalAnswerEntry(
      pressurizedPayload,
      "Pressurized path",
      summaryProvider,
      summaryModel,
      "pressurized",
      evalUsageForTarget(state?.usage, "summarizer")
    ),
    baselineEntry: normalizeEvalAnswerEntry(
      baselinePayload,
      "Single-thread path",
      directBaseline?.provider || task?.runtime?.directProvider || task?.runtime?.provider || "",
      directBaseline?.model || task?.runtime?.directModel || "",
      directBaseline?.mode || "single",
      directBaseline?.responseMeta?.usageDelta || evalUsageForTarget(state?.usage, "direct_baseline")
    )
  };
}

function renderFrontEvalArbiterSummary(task, arbiter, comparison, similarity) {
  const metrics = [
    { label: "Pressurized quality", value: arbiter?.quality?.scores?.overallQuality != null ? Number(arbiter.quality.scores.overallQuality || 0).toFixed(1) : "" },
    { label: "Single quality", value: arbiter?.baselineQuality?.scores?.overallQuality != null ? Number(arbiter.baselineQuality.scores.overallQuality || 0).toFixed(1) : "" },
    { label: "Pressurized health", value: arbiter?.answerHealth?.scores?.overallHealth != null ? Number(arbiter.answerHealth.scores.overallHealth || 0).toFixed(1) : "" },
    { label: "Single health", value: arbiter?.baselineAnswerHealth?.scores?.overallHealth != null ? Number(arbiter.baselineAnswerHealth.scores.overallHealth || 0).toFixed(1) : "" },
    { label: "Differentiation", value: comparison?.scores?.overallDifferentiation != null ? Number(comparison.scores.overallDifferentiation || 0).toFixed(1) : "" },
    { label: "Similarity", value: similarity?.sequenceSimilarity != null ? Number(similarity.sequenceSimilarity || 0).toFixed(2) : "" }
  ];
  const judgeBits = [
    arbiter?.comparison?.verdict ? String(arbiter.comparison.verdict || "") : "",
    arbiter?.comparison?.decisionRelation ? "Relation " + String(arbiter.comparison.decisionRelation || "") : "",
    arbiter?.judge?.model ? modelLabel(arbiter.judge.model, arbiter.judge.provider || "openai") : "",
    arbiter?.judge?.live ? "Live judge" : "Fallback judge"
  ].filter(Boolean);
  const sections = [
    renderEvalMetricStrip(metrics),
    renderTextSection("Judge verdict", comparison?.verdict || ""),
    renderTextSection("Judge rationale", comparison?.rationale || ""),
    renderTextSection("Pressurized edge", comparison?.primaryEdge || ""),
    renderTextSection("Single-thread edge", comparison?.baselineEdge || "")
  ].filter(Boolean);
  if (!sections.length) return "";
  return `
    <section class="eval-visual-section">
      <div class="eval-section-head">
        <div class="eval-section-title">External arbiter</div>
        ${judgeBits.length ? `<div class="eval-section-meta">${escapeHtml(judgeBits.join(" | "))}</div>` : ""}
      </div>
      ${sections.join("")}
    </section>
  `;
}

function renderFrontEvalPane(options) {
  const metaBits = (options.metaBits || []).filter(Boolean);
  const note = String(options.note || "").trim();
  return `
    <section class="front-eval-pane${options.tone ? " " + escapeHtml(options.tone) : ""}">
      <div class="front-eval-pane-head">
        <div class="front-eval-pane-title">${escapeHtml(options.title || "Path")}</div>
        ${metaBits.length ? `<div class="front-eval-pane-meta">${escapeHtml(metaBits.join(" | "))}</div>` : ""}
      </div>
      <div class="front-eval-chat">
        <article class="front-chat-message user">
          <div class="front-chat-bubble">${escapeHtml(String(options.objective || "").trim() || "Waiting for the next prompt...")}</div>
        </article>
        <article class="front-chat-message assistant${options.pending ? " is-pending" : ""}">
          <div class="front-chat-bubble">${escapeHtml(String(options.answer || "").trim() || "Waiting for response...")}</div>
        </article>
      </div>
      ${note ? `<div class="front-eval-pane-note">${escapeHtml(note)}</div>` : ""}
    </section>
  `;
}

function renderFrontEvalTechnical(task, summary, directBaseline, workerState, loop, state, checkpoints) {
  const { pressurizedEntry, baselineEntry } = buildFrontEvalAnswerEntries(task, summary, directBaseline, state);
  const arbiter = state?.arbiter && typeof state.arbiter === "object" ? state.arbiter : null;
  const arbiterFresh = arbiterMatchesCurrentPair(task, arbiter, summary, directBaseline);
  const comparison = arbiterFresh ? (arbiter?.comparison || null) : null;
  const similarity = arbiterFresh ? (arbiter?.similarity || null) : null;
  const summaryBits = [];
  if (arbiterFresh && comparison?.verdict) {
    summaryBits.push(String(comparison.verdict || ""));
    if (comparison?.scoreDelta?.overallQuality != null) {
      summaryBits.push("delta " + Number(comparison.scoreDelta.overallQuality || 0).toFixed(1));
    }
  } else if (summary && directBaseline) {
    summaryBits.push(hasActiveDispatchTarget(state, "arbiter") ? "scoring latest answer pair" : "score pending");
  } else if (isWorkspaceBusy(loop, state)) {
    summaryBits.push("live log");
  }
  const sections = [
    pressurizedEntry && baselineEntry ? renderEvalAnswerCompare(pressurizedEntry, baselineEntry, comparison) : "",
    arbiterFresh ? renderFrontEvalArbiterSummary(task, arbiter, comparison, similarity) : "",
    comparison ? renderEvalComparisonVisual(Object.assign({}, comparison || {}, { comparison: comparison, similarity: similarity || {} })) : "",
    renderWaitingProgress(task, workerState, loop, state),
    buildWorkerInspector(checkpoints)
  ].filter(Boolean);
  if (!sections.length) return "";
  const defaultOpen = frontEvalTechnicalOpen || isWorkspaceBusy(loop, state) || (summary && directBaseline && !arbiterFresh);
  return `
    <details class="front-eval-technical"${defaultOpen ? " open" : ""}>
      <summary class="front-eval-technical-summary">
        <div>
          <div class="eval-section-title">Verification and live log</div>
          ${summaryBits.length ? `<div class="eval-section-meta">${escapeHtml(summaryBits.join(" | "))}</div>` : ""}
        </div>
        <span class="front-eval-technical-caret" aria-hidden="true">v</span>
      </summary>
      <div class="front-eval-technical-body">
        ${sections.join("")}
      </div>
    </details>
  `;
}

function renderFrontEvalConversation(task, summary, directBaseline, workerState, loop, state, checkpoints) {
  const { pressurizedEntry, baselineEntry } = buildFrontEvalAnswerEntries(task, summary, directBaseline, state);
  const arbiter = state?.arbiter && typeof state.arbiter === "object" ? state.arbiter : null;
  const arbiterFresh = arbiterMatchesCurrentPair(task, arbiter, summary, directBaseline);
  const summaryModel = task?.summarizer?.model || task?.runtime?.model || "";
  const summaryProvider = task?.summarizer?.provider || task?.runtime?.provider || "";
  const baselineProvider = directBaseline?.provider || task?.runtime?.directProvider || task?.runtime?.provider || "";
  const baselineModel = directBaseline?.model || task?.runtime?.directModel || "";
  const pressurizedAnswer = pressurizedEntry?.answer
    || (
      directBaseline?.answer?.answer
        ? "The single-thread baseline is ready. The pressurized lanes are still shaping the final answer."
        : "The pressurized lanes are still working through the current stage."
    );
  const baselineAnswer = baselineEntry?.answer || "The single-thread path is still preparing its answer.";
  const pressurizedMeta = [
    providerLabel(summaryProvider),
    modelLabel(summaryModel, summaryProvider),
    summary ? "Ready" : (inferFrontActiveTarget(loop, state) === "summarizer" ? "Summarizing" : "Working")
  ].filter(Boolean);
  const baselineMeta = [
    providerLabel(baselineProvider),
    modelLabel(baselineModel, baselineProvider),
    baselineEntry ? "Ready" : (isWorkspaceBusy(loop, state) ? "Working" : "Queued")
  ].filter(Boolean);
  const pressurizedNote = arbiterFresh && arbiter?.comparison?.primaryEdge
    ? "Judge edge: " + String(arbiter.comparison.primaryEdge || "")
    : (
      summary
        ? String(summary?.frontAnswer?.confidenceNote || "").trim()
        : ""
    );
  const baselineNote = arbiterFresh && arbiter?.comparison?.baselineEdge
    ? "Judge edge: " + String(arbiter.comparison.baselineEdge || "")
    : String(directBaseline?.answer?.confidenceNote || "").trim();

  return `
    <div class="front-eval-thread">
      <div class="front-eval-compare-grid">
        ${renderFrontEvalPane({
          title: "Pressurized path",
          tone: "primary",
          objective: task?.objective || "",
          answer: pressurizedAnswer,
          pending: !pressurizedEntry,
          metaBits: pressurizedMeta,
          note: pressurizedNote
        })}
        ${renderFrontEvalPane({
          title: "Single-thread path",
          tone: "secondary",
          objective: task?.objective || "",
          answer: baselineAnswer,
          pending: !baselineEntry,
          metaBits: baselineMeta,
          note: baselineNote
        })}
      </div>
      ${renderFrontEvalTechnical(task, summary, directBaseline, workerState, loop, state, checkpoints)}
    </div>
  `;
}

function maybeQueueFrontEvalArbiter(task, summary, directBaseline, loop, state) {
  if (!task || normalizeFrontMode(task?.runtime?.frontMode) !== "eval") {
    frontEvalArbiterRequestKey = "";
    return;
  }
  const pairKey = currentFrontEvalPairKey(task, summary, directBaseline);
  if (!pairKey) {
    frontEvalArbiterRequestKey = "";
    return;
  }
  if (arbiterMatchesCurrentPair(task, state?.arbiter || null, summary, directBaseline)) {
    frontEvalArbiterRequestKey = "";
    return;
  }
  if (frontEvalArbiterRequestKey === pairKey || hasActiveDispatchTarget(state, "arbiter") || isWorkspaceBusy(loop, state)) {
    return;
  }
  frontEvalArbiterRequestKey = pairKey;
  $.post(apiRoute(API.targetsBackground), { target: "arbiter" })
    .done(function () {
      setTimeout(refreshState, 250);
    })
    .fail(function (xhr) {
      frontEvalArbiterRequestKey = "";
      if (xhr?.status && Number(xhr.status) === 409) {
        return;
      }
      showMessage("Front eval scoring failed: " + (xhr?.responseText || "Unknown error"), true);
    });
}

function buildThreadMessage(options) {
  const sections = (options.sections || []).join("");
  const tag = String(options.tag || "").trim();
  return `
    <article class="thread-message ${escapeHtml(options.kind || "")} ${escapeHtml(options.variant || "")}">
      <div class="message-meta">
        <div class="message-author">${escapeHtml(options.author || "Message")}</div>
        ${tag ? `<div class="message-tag">${escapeHtml(tag)}</div>` : ""}
      </div>
      ${sections}
    </article>
  `;
}

function legacyRenderConversationThreadUnused(task, summary, workerState, loop) {
  const $thread = $("#conversationThread");
  const threadNode = $thread[0];

  if (!task) {
    threadRenderSignature = "empty";
    threadRenderTaskId = "";
    threadInspectorOpen = false;
    $thread.empty().addClass("is-empty");
    return;
  }

  const messages = [];
  $thread.removeClass("is-empty");
  messages.push(buildThreadMessage({
    kind: "commander",
    author: "You",
    tag: task.runtime?.executionMode === "live" ? "Live session" : "Mock session",
    sections: [
      renderTextSection("Prompt", task.objective || ""),
      renderTextSection("Session context", task.sessionContext || ""),
      renderListSection("Constraints", task.constraints || [])
    ]
  }));

  const checkpoints = (task.workers || [])
    .map(function (worker) {
      return { worker, checkpoint: workerState?.[worker.id] || null };
    })
    .sort(function (a, b) {
      const stepA = a.checkpoint?.step || 0;
      const stepB = b.checkpoint?.step || 0;
      if (stepA !== stepB) return stepA - stepB;
      return a.worker.id.localeCompare(b.worker.id);
    });

  checkpoints.forEach(function (entry) {
    if (!entry.checkpoint) return;
    const checkpoint = entry.checkpoint;
    messages.push(buildThreadMessage({
      kind: "worker",
      variant: entry.worker.role === "utility" ? "utility" : "adversarial",
      author: displayWorkerLabel(entry.worker),
      tag: entry.worker.focus,
      sections: [
        renderTextSection("Observation", checkpoint.observation || ""),
        renderListSection("Benefits", (checkpoint.benefits || []).slice(0, 3)),
        renderListSection("Detriments", (checkpoint.detriments || []).slice(0, 3)),
        renderTextSection("Request to peers", checkpoint.requestToPeer || "")
      ]
    }));
  });

  const missingWorkers = (task.workers || []).filter(function (worker) {
    return !workerState?.[worker.id];
  });

  if (missingWorkers.length) {
    messages.push(buildThreadMessage({
      kind: "summary",
      author: "Runtime",
      tag: loop?.status || "idle",
      sections: [
        renderTextSection("Waiting on lanes", missingWorkers.map(function (worker) { return worker.id; }).join(", "))
      ]
    }));
  }

  if (summary) {
    const conflictTopics = (summary.conflicts || []).map(function (conflict) {
      return conflict?.topic;
    }).filter(Boolean);

    messages.push(buildThreadMessage({
      kind: "summary",
      author: "Agent",
      tag: "Multistream summary | memory " + ($("#memoryVersion").text() || "0"),
      sections: [
        renderListSection("Stable findings", summary.stableFindings || []),
        renderListSection("Open conflicts", conflictTopics),
        renderTextSection("Recommended next action", summary.recommendedNextAction || ""),
        renderTextSection("Vetting summary", summary.vettingSummary || "")
      ]
    }));
  }

  $thread.html(messages.join(""));
  $thread.scrollTop($thread[0].scrollHeight);
}

function legacyApplyLoopUiUnused(state) {
  const loop = state.loop || null;
  const task = state.activeTask || null;
  const hasTask = !!task;
  const dispatchActive = activeDispatchCount(state) > 0;
  const isActive = isWorkspaceBusy(loop, state);
  const workers = activeWorkerSource(task, state.draft || null);
  const usage = state.usage || {};
  const budget = task?.runtime?.budget || {
    maxTotalTokens: state.draft?.maxTotalTokens ?? 0,
    maxCostUsd: state.draft?.maxCostUsd ?? 0
  };
  const research = task?.runtime?.research || {};
  const vetting = task?.runtime?.vetting || {};
  const summaryReady = allWorkerCheckpointsReady(task, state.workers || {});
  const providerTrace = activeProviderTraceSource(state).trace;

  syncWorkspaceStatus(task, state, workers, loop, usage, budget);
  updateTopologyPanel(task, loop, state);
  $("#loopNote").text(
    providerTrace
      ? providerTraceStatusText(providerTrace)
      : dispatchActive
      ? (state?.dispatch?.lastMessage || "Background target dispatch is in flight.")
      :
    loop?.lastMessage ||
    (!hasTask
      ? "Press Send to start the configured roster and loop automatically."
      : (
      (research.enabled ? "Workers can run grounded web research" : "Workers are running without web research") +
      " and the summarizer " + (vetting.enabled === false ? "merges only." : "acts as the evidence vetter.")
    ))
  );
  latestLoopActive = isActive;
  updateAuthButtons();
  syncComposerAnswerNowButton(state);

  $("#sendPrompt").prop("disabled", isActive);
  $("#summarize").prop("disabled", isActive || !hasTask || !summaryReady);
  $("#runRound").prop("disabled", isActive || !hasTask);
  $("#runLoop").prop("disabled", isActive || !hasTask);
  $("#addAdversarial").prop("disabled", isActive || workers.length >= 26);
  $("#applyCurrentModels").prop("disabled", isActive || !hasTask);
  $("#resetSession").prop("disabled", isActive);
  $("#resetState").prop("disabled", isActive);
  $("#cancelLoop").prop("disabled", !(loop?.status === "running" || loop?.status === "queued"));
}

function renderConversationThread(task, summary, directBaseline, workerState, loop, state) {
  const $thread = $("#conversationThread");
  const threadNode = $thread[0];

  if (!task) {
    threadRenderSignature = "empty";
    threadRenderTaskId = "";
    threadInspectorOpen = false;
    frontEvalTechnicalOpen = false;
    frontEvalArbiterRequestKey = "";
    $thread.removeClass("is-eval is-full");
    $thread.empty().addClass("is-empty");
    return;
  }

  const frontMode = normalizeFrontMode(task?.runtime?.frontMode);
  $thread.removeClass("is-empty").toggleClass("is-eval", frontMode === "eval").toggleClass("is-full", frontMode !== "eval");

  const nextTaskId = String(task.taskId || "");
  if (threadRenderTaskId !== nextTaskId) {
    threadRenderTaskId = nextTaskId;
    threadRenderSignature = "";
    threadInspectorOpen = false;
    frontEvalTechnicalOpen = false;
    frontEvalArbiterRequestKey = "";
  }

  const signature = buildConversationRenderSignature(task, summary, directBaseline, workerState, loop, state);
  if (signature === threadRenderSignature) {
    return;
  }

  const previousScrollTop = threadNode ? $thread.scrollTop() : 0;
  const wasNearBottom = threadNode
    ? (threadNode.scrollHeight - (previousScrollTop + threadNode.clientHeight)) < 48
    : true;

  const messages = [];
  messages.push(buildThreadMessage({
    kind: "commander",
    author: "You",
    sections: [
      renderPlainTextBlock(task.objective || "")
    ]
  }));

  const checkpoints = (task.workers || [])
    .map(function (worker) {
      return { worker, checkpoint: workerState?.[worker.id] || null };
    })
    .sort(function (a, b) {
      const stepA = a.checkpoint?.step || 0;
      const stepB = b.checkpoint?.step || 0;
      if (stepA !== stepB) return stepA - stepB;
      return a.worker.id.localeCompare(b.worker.id);
    });
  if (frontMode === "eval") {
    $thread.html(renderFrontEvalConversation(task, summary, directBaseline, workerState, loop, state, checkpoints));
    threadRenderSignature = signature;
    if (!threadNode || wasNearBottom) {
      $thread.scrollTop($thread[0].scrollHeight);
    } else {
      $thread.scrollTop(previousScrollTop);
    }
    return;
  }
  const directMode = normalizeDirectBaselineMode(task?.runtime?.directBaselineMode);
  const compareStillRunning = directMode === "both" && isWorkspaceBusy(loop, state) && !summary;

  if (summary) {
    messages.push(buildThreadMessage({
      kind: "summary",
      author: "Assistant",
      sections: [
        renderPlainTextBlock(buildAgentReplyText(summary))
      ]
    }));
  } else if (directBaseline?.answer?.answer && (directMode === "single" || !compareStillRunning)) {
    messages.push(buildThreadMessage({
      kind: "summary",
      author: "Assistant",
      tag: directMode === "single" ? "Single-thread baseline" : "Baseline fallback",
      sections: [
        renderPlainTextBlock(String(directBaseline.answer.answer || "").trim())
      ]
    }));
  } else {
    messages.push(buildThreadMessage({
      kind: "summary",
      author: "Assistant",
      tag: "Working",
      sections: [
        renderPlainTextBlock(
          directMode === "single"
            ? "Working through the single-thread baseline path."
            : (
              directMode === "both" && directBaseline?.answer?.answer
                ? "The single-thread baseline is ready in Review while the pressurized lanes finish shaping the final answer."
                : "Working through the live lanes and shaping the final answer."
            )
        ),
        renderWaitingProgress(task, workerState, loop, state)
      ]
    }));
  }

  $thread.html(messages.join(""));
  threadRenderSignature = signature;
  if (!threadNode || wasNearBottom) {
    $thread.scrollTop($thread[0].scrollHeight);
  } else {
    $thread.scrollTop(previousScrollTop);
  }
}

function applyLoopUi(state) {
  const loop = state.loop || null;
  const task = state.activeTask || null;
  const hasTask = !!task;
  const dispatchActive = activeDispatchCount(state) > 0;
  const isActive = isWorkspaceBusy(loop, state);
  const workers = activeWorkerSource(task, state.draft || null);
  const usage = state.usage || {};
  const budget = task?.runtime?.budget || {
    maxTotalTokens: state.draft?.maxTotalTokens ?? 0,
    maxCostUsd: state.draft?.maxCostUsd ?? 0
  };
  const research = task?.runtime?.research || {};
  const vetting = task?.runtime?.vetting || {};
  const summaryReady = allWorkerCheckpointsReady(task, state.workers || {});
  const stagedMode = state.draft?.executionMode || task?.runtime?.executionMode || "live";
  const activeMode = task?.runtime?.executionMode || "none";
  const stagedSnapshot = buildQualityProfileSnapshot();
  const activeSnapshot = buildTaskQualityProfileSnapshot(task);
  const stagedProfileName = profileDisplayName(detectQualityProfileId(stagedSnapshot));
  const activeProfileName = profileDisplayName(detectQualityProfileId(activeSnapshot));
  const headerProfileName = hasTask ? activeProfileName : stagedProfileName;
  const providerTrace = activeProviderTraceSource(state).trace;

  syncWorkspaceStatus(task, state, workers, loop, usage, budget);
  updateTopologyPanel(task, loop, state);
  $("#headerProfile").text(headerProfileName);
  $("#loopNote").text(
    providerTrace
      ? providerTraceStatusText(providerTrace)
      : dispatchActive
      ? (state?.dispatch?.lastMessage || "Background target dispatch is in flight.")
      :
    loop?.lastMessage ||
    (!hasTask
      ? "Press Send to start the configured roster and loop automatically. Next send is staged for the " + stagedProfileName + " profile in " + stagedMode + " mode."
      : (
      "Active task is running the " + activeProfileName + " profile in " + activeMode + " mode. " +
      (research.enabled ? "Workers can run grounded web research" : "Workers are running without web research") +
      " and the summarizer " + (vetting.enabled === false ? "merges only." : "acts as the evidence vetter.") +
      " Next send is staged for the " + stagedProfileName + " profile in " + stagedMode + " mode."
    ))
  );
  latestLoopActive = isActive;
  updateAuthButtons();
  syncComposerAnswerNowButton(state);

  $("#sendPrompt").prop("disabled", isActive);
  $("#summarize").prop("disabled", isActive || !hasTask || !summaryReady);
  $("#runRound").prop("disabled", isActive || !hasTask);
  $("#runLoop").prop("disabled", isActive || !hasTask);
  $("#addAdversarial").prop("disabled", isActive || workers.length >= 26);
  $("#applyCurrentModels").prop("disabled", isActive || !hasTask);
  $("#resetSession").prop("disabled", isActive);
  $("#resetState").prop("disabled", isActive);
  $("#cancelLoop").prop("disabled", !(loop?.status === "running" || loop?.status === "queued"));
}

function refreshState() {
  renderDispatchActivity();
  refreshAuth();

  $.getJSON(apiRoute(API.state))
    .done(function (data) {
      clearMessageIfMatching("State load failed:");
      latestState = data;
      renderDispatchActivity();
      const task = data.activeTask
        ? Object.assign({}, data.activeTask, {
            stateWorkers: data.workers || {},
            stateCommander: data.commander || null,
            stateCommanderReview: data.commanderReview || null,
            directBaseline: data.directBaseline || null,
            summary: data.summary || null
          })
        : null;
      syncCommanderForm(data.activeTask || null, data.draft || null);
      applyLoopUi(data);
      renderAddWorkerTypeControl(data.activeTask || null, data.draft || null, data.loop || null);
      renderHomeWorkerControls(data.activeTask || null, data.draft || null, data.loop || null);
      renderAuthStatus(latestAuthStatus);
      renderHomeRuntimeControls(data.activeTask || null, data.draft || null, data.loop || null);
      renderQualityProfileCards();
      renderDebugTargetControls(task, data.loop || null, data.workers || {});
      renderFooterCheckpoints(task);
      renderConversationThread(task, data.summary || null, data.directBaseline || null, data.workers || {}, data.loop || null, data);
      renderSummaryReview(data.summary || null, data.directBaseline || null, task, data.workers || {});
      maybeQueueFrontEvalArbiter(task, data.summary || null, data.directBaseline || null, data.loop || null, data);
      $("#summary").text(data.summary ? pretty(data.summary) : "No data.");
      $("#memory").text(pretty({
        activeTask: data.activeTask,
        draft: data.draft,
        directBaseline: data.directBaseline,
        arbiter: data.arbiter,
        usage: data.usage,
        loop: data.loop,
        memoryVersion: data.memoryVersion,
        lastUpdated: data.lastUpdated
      }));
    })
    .fail(function (xhr) {
      showMessage("State load failed: " + (xhr.responseText || "Unknown error"), true);
    });

  $.get(apiRoute(API.events))
    .done(function (data) {
      clearMessageIfMatching("Event load failed:");
      $("#events").text(data || "No events.");
    })
    .fail(function (xhr) {
      showMessage("Event load failed: " + (xhr.responseText || "Unknown error"), true);
    });

  $.get(apiRoute(API.steps))
    .done(function (data) {
      clearMessageIfMatching("Step load failed:");
      $("#steps").text(data || "No steps.");
    })
    .fail(function (xhr) {
      showMessage("Step load failed: " + (xhr.responseText || "Unknown error"), true);
    });

  $.getJSON(apiRoute(API.history))
    .done(function (data) {
      clearMessageIfMatching("History load failed:");
      latestHistoryState = data;
      $("#jobHistory").html(renderJobHistory(data.jobs || [], data.recoveryWarning || null, data.queueLimit || 0, data.contractWarnings || []));
      $("#roundHistory").html(renderRoundHistory(data.rounds || []));
      $("#sessionArchives").html(renderSessionArchives(data.sessions || []));
      $("#artifactPolicy").html(renderArtifactPolicy(data.artifactPolicy || null));
      syncArtifactReview(data.artifacts || []);
    })
    .fail(function (xhr) {
      latestHistoryState = null;
      showMessage("History load failed: " + (xhr.responseText || "Unknown error"), true);
    });
}

function extractErrorMessage(xhr) {
  try {
    const parsed = JSON.parse(xhr.responseText);
    if (parsed && parsed.message) {
      return parsed.message;
    }
  } catch (_) {}
  return xhr.responseText || "Request failed.";
}

function activeProviderTraceSource(state) {
  const loop = state?.loop || null;
  const loopBusy = !!state && isWorkspaceBusy(loop, state);
  if (loopBusy && loop?.providerTrace && typeof loop.providerTrace === "object") {
    return { trace: loop.providerTrace, source: "loop", entry: null };
  }
  const dispatchEntries = activeDispatchEntries(state);
  for (const entry of dispatchEntries) {
    if (entry?.providerTrace && typeof entry.providerTrace === "object") {
      return { trace: entry.providerTrace, source: "dispatch", entry: entry };
    }
  }
  if (loop?.providerTrace && typeof loop.providerTrace === "object") {
    return { trace: loop.providerTrace, source: "loop", entry: null };
  }
  return { trace: null, source: "", entry: null };
}

function renderDispatchCompanionNote(entries) {
  const labels = (Array.isArray(entries) ? entries : [])
    .map(function (entry) {
      return String(entry?.targetLabel || entry?.target || "").trim();
    })
    .filter(Boolean);
  if (!labels.length) return "";
  const visible = labels.slice(0, 3);
  const extra = labels.length > visible.length ? " +" + (labels.length - visible.length) + " more" : "";
  return `<div class="dispatch-activity-trace-note">Sidecars: ${escapeHtml(visible.join(", ") + extra)}</div>`;
}

function formatProviderTraceBits(trace) {
  const bits = [];
  if (trace?.model) {
    bits.push("model " + String(trace.model));
  }
  if (trace?.requestCount != null) {
    bits.push("request " + String(trace.requestCount));
  }
  const elapsed = formatElapsedDuration(trace?.startedAt || trace?.sentAt || trace?.updatedAt || 0);
  if (elapsed) {
    bits.push("elapsed " + elapsed);
  }
  if (trace?.providerProcessingMs != null) {
    bits.push("provider " + String(trace.providerProcessingMs) + "ms");
  }
  if (trace?.httpStatus != null) {
    bits.push("http " + String(trace.httpStatus));
  }
  if (trace?.rateLimitRequestsRemaining != null || trace?.rateLimitTokensRemaining != null) {
    const requests = trace?.rateLimitRequestsRemaining != null ? String(trace.rateLimitRequestsRemaining) + " req" : "";
    const tokens = trace?.rateLimitTokensRemaining != null ? String(trace.rateLimitTokensRemaining) + " tok" : "";
    bits.push("remaining " + [requests, tokens].filter(Boolean).join(" / "));
  }
  if (trace?.retryAfterSeconds != null) {
    bits.push("retry after " + String(trace.retryAfterSeconds) + "s");
  }
  if (trace?.ollamaLoadDurationMs != null) {
    bits.push("load " + String(trace.ollamaLoadDurationMs) + "ms");
  }
  if (trace?.ollamaEvalCount != null && trace?.ollamaEvalDurationMs != null) {
    bits.push("eval " + String(trace.ollamaEvalCount) + " tok / " + String(trace.ollamaEvalDurationMs) + "ms");
  }
  return bits;
}

function providerTraceSummaryLines(trace) {
  if (!trace || typeof trace !== "object") return [];
  const lines = [];
  const headline = [
    trace?.provider ? providerLabel(trace.provider) : "",
    String(trace?.targetLabel || trace?.target || "").trim(),
    String(trace?.stageLabel || trace?.stage || "").trim()
  ].filter(Boolean).join(" | ");
  if (headline) {
    lines.push(headline);
  }
  const timingBits = formatProviderTraceBits(trace);
  if (timingBits.length) {
    lines.push(timingBits.join(" | "));
  }
  const identityBits = [
    trace?.providerRequestId ? "request " + String(trace.providerRequestId) : "",
    trace?.providerResponseId ? "response " + String(trace.providerResponseId) : "",
    trace?.responseStatus ? "status " + String(trace.responseStatus) : "",
    trace?.error ? "error " + String(trace.error) : ""
  ].filter(Boolean);
  if (identityBits.length) {
    lines.push(identityBits.join(" | "));
  }
  return lines;
}

function providerTraceReviewLine(trace) {
  const lines = providerTraceSummaryLines(trace);
  return lines.length ? lines.join(" | ") : "";
}

function renderProviderTraceBanner(trace, sourceMeta) {
  const providerLabelText = String(trace?.providerLabel || trace?.provider || "Provider").trim();
  const targetLabelText = String(trace?.targetLabel || trace?.target || sourceMeta?.entry?.targetLabel || "Target").trim();
  const stageLabelText = String(trace?.stageLabel || trace?.stage || "In flight").trim();
  const requestId = String(trace?.providerRequestId || "").trim();
  const responseId = String(trace?.providerResponseId || "").trim();
  const responseStatus = String(trace?.responseStatus || "").trim();
  const error = String(trace?.error || "").trim();
  const stageTone = String(trace?.stage || "sending").trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-") || "sending";
  const bits = formatProviderTraceBits(trace);
  const noteBits = [
    requestId ? "request " + requestId : "",
    responseId ? "response " + responseId : "",
    responseStatus ? "status " + responseStatus : "",
    error || ""
  ].filter(Boolean);
  return `
    <div class="dispatch-activity-trace is-${escapeHtml(stageTone)}">
      <div class="dispatch-activity-trace-head">
        <strong>${escapeHtml(providerLabelText)}</strong>
        <span class="dispatch-activity-trace-target">${escapeHtml(targetLabelText)}</span>
        <span class="dispatch-activity-trace-stage">${escapeHtml(stageLabelText)}</span>
      </div>
      ${bits.length ? `<div class="dispatch-activity-trace-pills">${bits.map(function (bit) {
        return `<span class="dispatch-trace-pill">${escapeHtml(bit)}</span>`;
      }).join("")}</div>` : ""}
      ${noteBits.length ? `<div class="dispatch-activity-trace-note">${escapeHtml(noteBits.join(" | "))}</div>` : ""}
    </div>
  `;
}

function providerTraceStatusText(trace) {
  if (!trace || typeof trace !== "object") return "";
  const providerLabelText = String(trace?.providerLabel || trace?.provider || "Provider").trim();
  const targetLabelText = String(trace?.targetLabel || trace?.target || "Target").trim();
  const stageLabelText = String(trace?.stageLabel || trace?.stage || "In flight").trim();
  const bits = formatProviderTraceBits(trace);
  const summary = [providerLabelText, targetLabelText, stageLabelText].filter(Boolean).join(" | ");
  return [summary].concat(bits.slice(0, 3)).filter(Boolean).join(" | ");
}

function renderDispatchActivity() {
  const $banner = $("#dispatchActivity");
  if (!$banner.length) return;
  const entries = activeDispatchEntries(latestState);
  const loop = latestState?.loop || null;
  const busy = !!latestState && isWorkspaceBusy(loop, latestState);
  const providerTrace = activeProviderTraceSource(latestState);
  if (providerTrace.trace) {
    const companion = providerTrace.source === "loop" && entries.length
      ? renderDispatchCompanionNote(entries)
      : "";
    $banner.prop("hidden", false).html(renderProviderTraceBanner(providerTrace.trace, providerTrace) + companion);
    return;
  }
  if (!entries.length && !busy) {
    $banner.prop("hidden", true).empty();
    return;
  }
  const entry = entries[0] || null;
  const label = entry
    ? String(entry?.targetLabel || entry?.label || "Manual dispatch")
    : String(inferFrontActiveTarget(loop, latestState) || "Loop");
  const count = entries.length;
  const extra = count > 1 ? " + " + (count - 1) + " more" : "";
  const elapsed = formatElapsedDuration(entry?.startedAt || entry?.queuedAt || loop?.startedAt || loop?.queuedAt || 0);
  const note = String(entry?.lastMessage || loop?.lastMessage || "");
  $banner
    .prop("hidden", false)
    .html("<strong>Processing</strong> " + escapeHtml(label + extra) + " | waiting " + escapeHtml(elapsed) + " | " + escapeHtml(note || "long ultra-reasoning calls can take minutes."));
}

function beginManualDispatch(label) {
  manualDispatchSequence += 1;
  const entry = {
    id: "manual-" + manualDispatchSequence,
    label: String(label || "Manual dispatch"),
    startedAt: Date.now()
  };
  latestManualDispatchEntries.push(entry);
  latestManualDispatchCount = latestManualDispatchEntries.length;
  renderDispatchActivity();
  if (latestState) {
    applyLoopUi(latestState);
  }
  return entry.id;
}

function endManualDispatch(dispatchId) {
  latestManualDispatchEntries = latestManualDispatchEntries.filter(function (entry) {
    return entry.id !== dispatchId;
  });
  latestManualDispatchCount = latestManualDispatchEntries.length;
  renderDispatchActivity();
  if (latestState) {
    applyLoopUi(latestState);
  }
}

function postForm(url, payload, successText, options = {}) {
  const dispatchLabel = typeof options.manualDispatch === "string"
    ? options.manualDispatch
    : (options.manualDispatch && options.manualDispatch.label) || "";
  const manualDispatchId = dispatchLabel ? beginManualDispatch(dispatchLabel) : null;
  $.post(apiRoute(url), payload)
    .done(function (resp) {
      let out = resp;
      try { out = JSON.parse(resp); } catch (_) {}
      if (options.clearFormDirty) {
        formDirty = false;
      }
      showMessage(successText + (out.message ? " | " + out.message : ""));
      if (typeof options.onSuccess === "function") {
        options.onSuccess(out);
      }
      refreshState();
    })
    .fail(function (xhr) {
      showMessage(extractErrorMessage(xhr), true);
    })
    .always(function () {
      if (manualDispatchId) {
        endManualDispatch(manualDispatchId);
      }
    });
}

function applyCurrentRuntimeSettings(successText = "Current task runtime updated") {
  postForm(API.runtimeApply, {
    provider: $("#provider").val(),
    model: $("#model").val(),
    summarizerProvider: $("#summarizerProvider").val(),
    summarizerModel: $("#summarizerModel").val(),
    frontMode: normalizeFrontMode($("#frontMode").val()),
    contextMode: normalizeContextMode($("#contextMode").val()),
    directBaselineMode: normalizeDirectBaselineMode($("#directBaselineMode").val()),
    directProvider: $("#directProvider").val(),
    directModel: $("#directModel").val(),
    ollamaBaseUrl: normalizeOllamaBaseUrl($("#ollamaBaseUrl").val()),
    targetTimeouts: JSON.stringify(currentTargetTimeoutsSource(latestState?.activeTask || null, latestState?.draft || null)),
    reasoningEffort: $("#reasoningEffort").val(),
    maxCostUsd: $("#maxCostUsd").val(),
    maxTotalTokens: $("#maxTotalTokens").val(),
    maxOutputTokens: $("#maxOutputTokens").val(),
    loopRounds: $("#loopRounds").val(),
    loopDelayMs: $("#loopDelayMs").val(),
    researchEnabled: $("#researchEnabled").val(),
    researchExternalWebAccess: $("#researchExternalWebAccess").val(),
    researchDomains: $("#researchDomains").val(),
    localFilesEnabled: $("#localFilesEnabled").val(),
    localFileRoots: $("#localFileRoots").val(),
    githubToolsEnabled: $("#githubToolsEnabled").val(),
    githubAllowedRepos: $("#githubAllowedRepos").val(),
    dynamicSpinupEnabled: $("#dynamicSpinupEnabled").val(),
    vettingEnabled: $("#vettingEnabled").val()
  }, successText, {
    onSuccess: function () {
      workerControlsSignature = "";
      debugControlsSignature = "";
    }
  });
}

function saveDebugTargetTimeout(target, rawValue) {
  if (!latestState?.activeTask) {
    showMessage("No active task.", true);
    return;
  }
  const nextConfig = currentTargetTimeoutsSource(latestState.activeTask, latestState?.draft || null);
  const normalizedTarget = String(target || "").trim();
  const nextSeconds = clampTimeoutSeconds(rawValue, targetTimeoutSeconds(nextConfig, normalizedTarget));
  if (/^[A-Za-z]$/.test(normalizedTarget)) {
    nextConfig.workers[normalizedTarget.toUpperCase()] = nextSeconds;
  } else {
    switch (normalizedTarget.toLowerCase()) {
      case "direct_baseline":
        nextConfig.directBaseline = nextSeconds;
        break;
      case "commander":
        nextConfig.commander = nextSeconds;
        break;
      case "commander_review":
        nextConfig.commanderReview = nextSeconds;
        break;
      case "summarizer":
        nextConfig.summarizer = nextSeconds;
        break;
      case "answer_now":
        nextConfig.answerNow = nextSeconds;
        break;
      case "arbiter":
        nextConfig.arbiter = nextSeconds;
        break;
      default:
        nextConfig.workerDefault = nextSeconds;
        break;
    }
  }
  postForm(API.runtimeApply, { targetTimeouts: JSON.stringify(nextConfig) }, "Timeout updated", {
    onSuccess: function () {
      workerControlsSignature = "";
      debugControlsSignature = "";
    }
  });
}

function setActiveView(viewName) {
  const normalized = $(`.nav-btn[data-view="${viewName}"]`).length && $(`.workspace-view[data-view="${viewName}"]`).length
    ? String(viewName || "").trim()
    : "home";
  activeView = normalized;
  localStorage.setItem("loopActiveView", normalized);
  $(".nav-btn").removeClass("active").filter(`[data-view="${normalized}"]`).addClass("active");
  $(".workspace-view").removeClass("active").filter(`[data-view="${normalized}"]`).addClass("active");
}

$(function () {
  recentComposerAttachments = loadRecentComposerAttachments();
  populateStaticProviderSelect("#provider", "openai");
  populateStaticProviderSelect("#summarizerProvider", "openai");
  populateStaticProviderSelect("#directProvider", "openai");
  populateStaticModelSelect("#model", "gpt-5-mini", "openai");
  populateStaticModelSelect("#summarizerModel", "gpt-5-mini", "openai");
  populateStaticModelSelect("#directModel", "gpt-5-mini", "openai");
  $("#researchEnabled").val("0");
  $("#researchExternalWebAccess").val("1");
  $("#localFilesEnabled").val("0");
  $("#localFileRoots").val(".");
  $("#githubToolsEnabled").val("0");
  $("#githubAllowedRepos").val("");
  $("#dynamicSpinupEnabled").val("0");
  $("#vettingEnabled").val("1");
  $("#composerFileInput").attr("accept", COMPOSER_SUPPORTED_EXTENSIONS.join(","));
  applyCommanderForm(defaultDraftState());
  renderAddWorkerTypeControl(null, defaultDraftState(), null);
  setTheme(activeTheme);
  initializeSidebarBootstrapCollapse();
  setSidebarCollapsed(sidebarCollapsed);
  setActiveView(activeView);
  renderApiModeStatus();
  renderDispatchActivity();
  syncOperatorNoticeVisibility();
  refreshState();
  setInterval(refreshState, 2000);

  $(".nav-btn").on("click", function () {
    setActiveView($(this).data("view"));
    if (isMobileShell()) {
      setMobileSidebarOpen(false);
    }
  });

  $("#sidebarToggle").on("click", function () {
    if (isMobileShell()) {
      setMobileSidebarOpen(false);
      return;
    }
    setSidebarCollapsed(!sidebarCollapsed);
  });

  $("#mobileSidebarToggle, #sidebarBackdrop").on("click", function () {
    setMobileSidebarOpen(!mobileSidebarOpen);
  });

  $(window).on("resize", function () {
    syncShellChrome();
  });

  $(document).on("click", ".theme-toggle-btn", function () {
    setTheme(String($(this).data("themeOption") || "dark"));
  });

  $("#operatorNoticeAccept").on("click", function () {
    acceptOperatorNotice();
  });

  $(document).on("click", ".workercontrol-modal-trigger", function () {
    const kind = String($(this).data("workerEditorKind") || "worker");
    const key = kind === "summarizer"
      ? "summarizer"
      : String($(this).data("workerId") || $(this).closest(".workercontrol").data("workerId") || "");
    openWorkerEditorModal(kind, key);
  });

  $(document).on("click", "#workerEditorClose, [data-worker-editor-close='true']", function () {
    closeWorkerEditorModal();
  });

  $(document).on("input change", "#workerEditorModal .worker-type, #workerEditorModal .worker-temperature, #workerEditorModal .worker-model, #workerEditorModal .worker-harness-profile, #workerEditorModal .worker-harness-instruction, #workerEditorModal .summarizer-model-draft, #workerEditorModal .summarizer-harness-profile, #workerEditorModal .summarizer-harness-instruction", function () {
    syncWorkerEditorOverrideFromModalFields();
  });

  $(document).on("toggle", ".workercontrol-collapsible", function () {
    const $details = $(this);
    const workerKey = $details.data("workerId") || $details.data("positionId");
    if ($details.closest(".workers-dashboard-panel").length) {
      if (this.open) {
        $details.closest("#workerControls").find(".workercontrol-collapsible").not(this).each(function () {
          if (this.open) {
            this.open = false;
            setWorkerControlExpandedState($(this).data("workerId") || $(this).data("positionId"), false);
          }
          restoreDashboardWorkerMenu(this);
          clearDashboardWorkerMenuPosition(this);
        });
      }
      positionDashboardWorkerMenu(this);
    } else {
      restoreDashboardWorkerMenu(this);
      clearDashboardWorkerMenuPosition(this);
    }
    if (!this.open) {
      restoreDashboardWorkerMenu(this);
      clearDashboardWorkerMenuPosition(this);
    }
    setWorkerControlExpandedState(workerKey, this.open);
  });

  $(window).on("resize scroll", function () {
    refreshDashboardWorkerMenuPositions();
  });

  $(document).on("keydown", function (event) {
    if (event.key === "Escape" && !$("#workerEditorModal").prop("hidden")) {
      closeWorkerEditorModal();
    }
  });

  $("#provider, #summarizerProvider, #directProvider").on("change", function () {
    const workerProvider = normalizeProviderId($("#provider").val());
    const summarizerProvider = normalizeProviderId($("#summarizerProvider").val() || workerProvider);
    const directProvider = normalizeProviderId($("#directProvider").val() || workerProvider);
    $("#model").val(normalizeSelectedModelForProvider($("#model").val(), workerProvider));
    $("#summarizerModel").val(normalizeSelectedModelForProvider($("#summarizerModel").val(), summarizerProvider));
    $("#directModel").val(normalizeSelectedModelForProvider($("#directModel").val() || $("#model").val(), directProvider));
    syncDirectBaselineFields();
    syncOllamaBaseUrlField();
    refreshProviderModelSelects();
    enforceProviderCapabilitySelections(true);
    formDirty = true;
    renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
    renderQualityProfileCards();
    renderComposerTools();
    renderAuthPoolPreview();
    queueDraftSave();
  });

  $("#sessionContext, #objective, #constraints, #executionMode, #frontMode, #contextMode, #directBaselineMode, #model, #summarizerModel, #directModel, #ollamaBaseUrl, #reasoningEffort, #maxCostUsd, #maxTotalTokens, #maxOutputTokens, #loopRounds, #loopDelayMs, #researchEnabled, #researchExternalWebAccess, #localFilesEnabled, #localFileRoots, #githubToolsEnabled, #githubAllowedRepos, #dynamicSpinupEnabled, #vettingEnabled, #researchDomains").on("input change", function () {
    syncDirectBaselineFields();
    syncOllamaBaseUrlField();
    formDirty = true;
    renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
    renderQualityProfileCards();
    renderComposerTools();
    renderAuthPoolPreview();
    queueDraftSave();
  });

  $("#sendPrompt").on("click", function () {
    const payload = collectCommanderPayload();
    const visibleWorkers = collectVisibleWorkerRoster();
    const workers = visibleWorkers.length ? visibleWorkers : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null);
    const summarizerConfig = collectVisibleSummarizerConfig();

    if (!payload.objective) {
      showMessage("Objective is required.", true);
      return;
    }

    const effectiveDirectBaselineMode = payload.frontMode === "eval"
      ? "both"
      : payload.directBaselineMode;
    const startPayload = {
      sessionContext: buildSendSessionContext(payload.sessionContext),
      objective: payload.objective,
      constraints: JSON.stringify(payload.constraints),
      executionMode: payload.executionMode,
      frontMode: payload.frontMode,
      contextMode: payload.contextMode,
      directBaselineMode: effectiveDirectBaselineMode,
      provider: payload.provider,
      model: payload.model,
      summarizerProvider: summarizerConfig.provider || payload.summarizerProvider || payload.provider,
      summarizerModel: summarizerConfig.model || payload.summarizerModel,
      directProvider: payload.directProvider || payload.provider,
      directModel: payload.directModel || payload.model,
      ollamaBaseUrl: payload.ollamaBaseUrl,
      targetTimeouts: JSON.stringify(currentTargetTimeoutsSource(latestState?.activeTask || null, latestState?.draft || null)),
      summarizerHarness: JSON.stringify(normalizeHarnessConfig(summarizerConfig.harness, "expansive")),
      reasoningEffort: payload.reasoningEffort,
      maxCostUsd: payload.maxCostUsd,
      maxTotalTokens: payload.maxTotalTokens,
      maxOutputTokens: payload.maxOutputTokens,
      loopRounds: payload.loopRounds,
      loopDelayMs: payload.loopDelayMs,
      researchEnabled: payload.researchEnabled,
      researchExternalWebAccess: payload.researchExternalWebAccess,
      localFilesEnabled: payload.localFilesEnabled,
      localFileRoots: payload.localFileRoots,
      githubToolsEnabled: payload.githubToolsEnabled,
      githubAllowedRepos: payload.githubAllowedRepos,
      dynamicSpinupEnabled: payload.dynamicSpinupEnabled,
      vettingEnabled: payload.vettingEnabled,
      researchDomains: payload.researchDomains,
      workers: JSON.stringify(workers)
    };

    $.post(apiRoute(API.tasks), startPayload)
      .done(function (resp) {
        let out = resp;
        try { out = JSON.parse(resp); } catch (_) {}
        resetComposerSurface(true);
        $.post(apiRoute(API.loops), { rounds: payload.loopRounds, delayMs: payload.loopDelayMs })
          .done(function (loopResp) {
            let loopOut = loopResp;
            try { loopOut = JSON.parse(loopResp); } catch (_) {}
            formDirty = false;
            workerControlsSignature = "";
            debugControlsSignature = "";
            showMessage("Agent loop queued" + (loopOut.message ? " | " + loopOut.message : ""));
            setActiveView("home");
            refreshState();
          })
          .fail(function (xhr) {
            formDirty = false;
            showMessage("Task started but loop failed to queue: " + extractErrorMessage(xhr), true);
            refreshState();
          });
      })
      .fail(function (xhr) {
        showMessage(extractErrorMessage(xhr), true);
      });
  });

  $("#objective").on("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      $("#sendPrompt").trigger("click");
    }
  });

  $("#addWorkerType").on("change", function () {
    $(this).data("selectedType", $(this).val());
  });

  $("#summarize").on("click", function () {
    postForm(API.targetsBackground, { target: "summarizer" }, "Summarizer queued");
  });

  $("#runRound").on("click", function () {
    postForm(API.rounds, {}, "Round dispatch queued");
  });

  $("#runLoop").on("click", function () {
    const rounds = parseInt($("#loopRounds").val(), 10) || 3;
    const delayMs = parseInt($("#loopDelayMs").val(), 10) || 0;
    postForm(API.loops, { rounds, delayMs }, "Auto loop queued");
  });

  $("#addAdversarial").on("click", function () {
    postForm(API.workersAdd, {
      type: $("#addWorkerType").val()
    }, "Worker added", {
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
        $("#addWorkerType").removeData("selectedType");
      }
    });
  });

  $("#removeAdversarial").on("click", function () {
    postForm(API.workersRemove, {}, "Worker removed", {
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
        const visibleWorkers = visibleWorkerRosterSource(latestState?.draft || null, latestState?.activeTask || null);
        const lastWorker = visibleWorkers[visibleWorkers.length - 1];
        if (lastWorker) {
          delete workerEditorOverrides.workers[normalizeWorkerControlKey(lastWorker.id)];
          if (workerEditorModalState.kind === "worker" && workerEditorModalState.key === normalizeWorkerControlKey(lastWorker.id)) {
            closeWorkerEditorModal();
          }
        }
      }
    });
  });

  $("#applyCurrentModels").on("click", function () {
    applyCurrentRuntimeSettings("Current task runtime updated");
  });

  $("#applyHomeRuntime").on("click", function () {
    applyCurrentRuntimeSettings("Active task synced to staged runtime");
  });

  $(document).on("click", ".quality-profile-card, .quick-profile-chip", function () {
    applyQualityProfile(String($(this).data("profileId") || ""));
  });

  $("#cancelLoop").on("click", function () {
    postForm(API.loopsCancel, {}, "Cancel sent");
  });

  $("#refresh").on("click", refreshState);

  $("#composerToolMenuToggle").on("click", function (event) {
    event.preventDefault();
    event.stopPropagation();
    closeInlineHelpPopovers();
    composerToolMenuOpen = !composerToolMenuOpen;
    if (!composerToolMenuOpen) {
      composerRecentDrawerOpen = false;
    }
    renderComposerTools();
  });

  $(document).on("click", ".inline-help-trigger", function (event) {
    event.preventDefault();
    event.stopPropagation();
    const $help = $(this).closest(".inline-help");
    const shouldOpen = !$help.hasClass("open");
    closeInlineHelpPopovers($help);
    $help.toggleClass("open", shouldOpen);
    if (!shouldOpen) {
      this.blur();
    }
  });

  $(document).on("click", ".composer-tool-action", function () {
    const action = String($(this).data("toolAction") || "").trim();
    const capabilityState = enforceProviderCapabilitySelections(false);
    const capabilities = capabilityState.capabilities;
    const provider = capabilityState.provider;
    if (action === "upload") {
      composerToolMenuOpen = false;
      renderComposerTools();
      $("#composerFileInput").trigger("click");
      return;
    }
    if (action === "recent") {
      composerRecentDrawerOpen = !composerRecentDrawerOpen;
      composerToolMenuOpen = false;
      renderComposerTools();
      return;
    }
    if (action === "web-search") {
      if (!capabilities.webSearch) {
        composerToolMenuOpen = false;
        renderComposerTools();
        showMessage(providerLabel(provider) + " does not support live web search in this runtime.", false);
        return;
      }
      $("#researchEnabled").val($("#researchEnabled").val() === "1" ? "0" : "1");
      composerToolMenuOpen = false;
      markComposerConfigDirty();
      return;
    }
    if (action === "local-files") {
      if (!capabilities.localFiles) {
        composerToolMenuOpen = false;
        renderComposerTools();
        showMessage(providerLabel(provider) + " does not support local file tools in this runtime.", false);
        return;
      }
      $("#localFilesEnabled").val($("#localFilesEnabled").val() === "1" ? "0" : "1");
      composerToolMenuOpen = false;
      markComposerConfigDirty();
      return;
    }
    if (action === "github-tools") {
      if (!capabilities.githubTools) {
        composerToolMenuOpen = false;
        renderComposerTools();
        showMessage(providerLabel(provider) + " does not support GitHub tools in this runtime.", false);
        return;
      }
      $("#githubToolsEnabled").val($("#githubToolsEnabled").val() === "1" ? "0" : "1");
      composerToolMenuOpen = false;
      markComposerConfigDirty();
      return;
    }
    if (action === "sources") {
      if (!capabilities.webSearch) {
        composerSourceDrawerOpen = false;
        composerRecentDrawerOpen = false;
        composerToolMenuOpen = false;
        renderComposerTools();
        showMessage(providerLabel(provider) + " does not support live web search in this runtime.", false);
        return;
      }
      composerSourceDrawerOpen = !composerSourceDrawerOpen;
      composerRecentDrawerOpen = false;
      composerToolMenuOpen = false;
      if (composerSourceDrawerOpen && $("#researchEnabled").val() !== "1") {
        $("#researchEnabled").val("1");
        markComposerConfigDirty();
        return;
      }
      renderComposerTools();
      return;
    }
    if (action === "vetting") {
      $("#vettingEnabled").val($("#vettingEnabled").val() === "1" ? "0" : "1");
      composerToolMenuOpen = false;
      markComposerConfigDirty();
    }
  });

  $("#composerResearchDomainsInput").on("input change", function () {
    $("#researchDomains").val($(this).val());
    if (providerCapabilities($("#provider").val()).webSearch && String($(this).val() || "").trim()) {
      $("#researchEnabled").val("1");
    }
    markComposerConfigDirty();
  });

  $("#composerResearchModeSelect").on("change", function () {
    $("#researchExternalWebAccess").val($(this).val());
    if (providerCapabilities($("#provider").val()).webSearch) {
      $("#researchEnabled").val("1");
    }
    markComposerConfigDirty();
  });

  $("#localFileRoots").on("input change", function () {
    if (providerCapabilities($("#provider").val()).localFiles && String($(this).val() || "").trim()) {
      $("#localFilesEnabled").val("1");
    }
    markComposerConfigDirty();
  });

  $("#githubAllowedRepos").on("input change", function () {
    if (providerCapabilities($("#provider").val()).githubTools && String($(this).val() || "").trim()) {
      $("#githubToolsEnabled").val("1");
    }
    markComposerConfigDirty();
  });

  $("#composerFileInput").on("change", async function () {
    const files = Array.from(this.files || []);
    this.value = "";
    if (!files.length) return;

    const remainingSlots = Math.max(0, COMPOSER_ATTACHMENT_LIMIT - stagedComposerAttachments.length);
    if (remainingSlots <= 0) {
      showMessage("Remove a staged file before adding another one.", true);
      return;
    }

    const selectedFiles = files.slice(0, remainingSlots);
    const skippedForCount = files.length - selectedFiles.length;
    const staged = [];
    const rejected = [];

    for (const file of selectedFiles) {
      if (!supportedComposerFile(file)) {
        rejected.push(file.name + " (unsupported file type)");
        continue;
      }
      if (Number(file.size || 0) > COMPOSER_ATTACHMENT_MAX_BYTES) {
        rejected.push(file.name + " (over " + formatFileSize(COMPOSER_ATTACHMENT_MAX_BYTES) + ")");
        continue;
      }
      try {
        const rawText = await file.text();
        staged.push({
          id: buildAttachmentId("file"),
          name: file.name,
          size: Number(file.size || rawText.length || 0),
          type: file.type || "text/plain",
          text: rawText.slice(0, COMPOSER_ATTACHMENT_MAX_CHARS),
          truncated: rawText.length > COMPOSER_ATTACHMENT_MAX_CHARS,
          addedAt: new Date().toISOString()
        });
      } catch (_) {
        rejected.push(file.name + " (could not read)");
      }
    }

    staged.forEach(function (attachment) {
      stageComposerAttachment(attachment);
      storeRecentComposerAttachment(attachment);
    });

    if (staged.length) {
      showMessage("Staged " + staged.length + " file" + (staged.length === 1 ? "" : "s") + " for the next send.");
    }
    if (rejected.length || skippedForCount > 0) {
      const notes = [];
      if (rejected.length) notes.push("Skipped: " + rejected.join(", "));
      if (skippedForCount > 0) notes.push("Only " + COMPOSER_ATTACHMENT_LIMIT + " files can be staged at once.");
      showMessage(notes.join(" "), true);
    }
  });

  $(document).on("click", ".composer-attachment-remove", function () {
    removeComposerAttachment(String($(this).data("attachmentId") || ""));
  });

  $(document).on("click", ".composer-recent-file", function () {
    const recentId = String($(this).data("recentFileId") || "").trim();
    const attachment = recentComposerAttachments.find(function (entry) {
      return entry.id === recentId;
    });
    if (!attachment) return;
    stageComposerAttachment(Object.assign({}, attachment, { id: buildAttachmentId("file") }));
    composerRecentDrawerOpen = false;
    renderComposerTools();
    showMessage("Restaged " + attachment.name + " for the next send.");
  });

  $(document).on("click", function (event) {
    const $target = $(event.target);
    if (!$target.closest(".inline-help").length) {
      closeInlineHelpPopovers();
    }
    if ($target.closest("#composerTools").length) return;
    if (!composerToolMenuOpen && !composerRecentDrawerOpen && !composerSourceDrawerOpen) return;
    composerToolMenuOpen = false;
    composerRecentDrawerOpen = false;
    composerSourceDrawerOpen = false;
    renderComposerTools();
  });

  $(document).on("keydown", function (event) {
    if (event.key !== "Escape") return;
    closeInlineHelpPopovers();
    if (mobileSidebarOpen) {
      setMobileSidebarOpen(false);
    }
    if (composerToolMenuOpen || composerRecentDrawerOpen || composerSourceDrawerOpen) {
      composerToolMenuOpen = false;
      composerRecentDrawerOpen = false;
      composerSourceDrawerOpen = false;
      renderComposerTools();
    }
  });

  $("#resetSession").on("click", function () {
    if (!confirm("Archive the current session and load a fresh draft with short carry-forward context?")) return;
    postForm(API.sessionReset, {}, "Session reset", {
      clearFormDirty: true,
      onSuccess: function () {
        resetComposerSurface(true);
        workerControlsSignature = "";
        debugControlsSignature = "";
        setActiveView("home");
      }
    });
  });

  $(document).on("click", ".add-auth-field", function () {
    const provider = String($(this).data("provider") || "openai").trim().toLowerCase();
    authDynamicRows(provider).push({ id: nextAuthRowId(), value: "" });
    renderAuthProviderCards(true);
  });

  $(document).on("click", ".auth-mode-toggle", function () {
    const provider = String($(this).data("provider") || "openai").trim().toLowerCase();
    const mode = String($(this).data("authMode") || "safe").trim().toLowerCase();
    const group = authProviderGroup(provider);
    if (mode === String(group.selectedMode || "")) return;
    $.post(apiRoute(API.authMode), { provider: provider, mode: mode })
      .done(function (resp) {
        handleAuthMutationSuccess(resp, group.label + " credential mode updated", {
          onSuccess: function () {
            resetAuthDynamicRows(provider);
            renderAuthProviderCards(true);
          }
        });
      })
      .fail(function (xhr) {
        showMessage(group.label + " credential mode update failed: " + extractErrorMessage(xhr), true);
      });
  });

  $(document).on("click", ".clear-auth", function () {
    const provider = String($(this).data("provider") || "openai").trim().toLowerCase();
    const label = authProviderGroup(provider).label || provider;
    if (!confirm("Clear the stored transitional local " + label + " API key pool?")) return;

    $.post(apiRoute(API.authKeys), { provider: provider, clear: 1 })
      .done(function (resp) {
        handleAuthMutationSuccess(resp, label + " API key pool cleared", {
          onSuccess: function () {
            resetAuthDynamicRows(provider);
            renderAuthProviderCards(true);
          }
        });
      })
      .fail(function (xhr) {
        showMessage(label + " API key pool clear failed: " + extractErrorMessage(xhr), true);
      });
  });

  $(document).on("input", ".auth-key-input", function () {
    scheduleAuthRowSave($(this), false);
  });

  $(document).on("blur", ".auth-key-input", function () {
    scheduleAuthRowSave($(this), true);
  });

  $(document).on("click", ".auth-key-remove", function () {
    const provider = String($(this).data("provider") || "openai").trim().toLowerCase();
    const mode = String($(this).data("removeMode") || "");
    if (mode === "stored") {
      const slotIndex = Number($(this).data("slotIndex"));
      if (Number.isNaN(slotIndex)) return;
      removeAuthSlot(slotIndex, provider);
      return;
    }
    const rowId = String($(this).data("rowId") || "");
    clearAuthSaveTimer(provider + ":" + rowId);
    removeAuthDynamicRow(provider, rowId);
    renderAuthProviderCards(true);
  });

  $("#resetState").on("click", function () {
    if (!confirm("Reset state and clear active task?")) return;
    postForm(API.stateReset, {}, "State reset", {
      clearFormDirty: true,
      onSuccess: function () {
        resetComposerSurface(true);
        workerControlsSignature = "";
        debugControlsSignature = "";
      }
    });
  });

  $(document).on("click", ".run-target", function () {
    const target = $(this).data("target");
    postForm(API.targetsBackground, { target }, target === "answer_now" ? "Partial answer queued" : "Target queued");
  });

  $(document).on("change", ".target-timeout-input", function () {
    const target = String($(this).data("timeoutTarget") || "").trim();
    if (!target) return;
    const normalized = clampTimeoutSeconds($(this).val(), targetTimeoutSeconds(currentTargetTimeoutsSource(latestState?.activeTask || null, latestState?.draft || null), target));
    $(this).val(normalized);
    saveDebugTargetTimeout(target, normalized);
  });

  $(document).on("change", ".worker-type, .worker-temperature, .worker-model, .worker-harness-profile, .worker-harness-instruction, .summarizer-model-draft, .summarizer-harness-profile, .summarizer-harness-instruction", function () {
    renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
    renderQualityProfileCards();
    postForm(API.draft, buildDraftSavePayload({ summarizerConfig: collectVisibleSummarizerConfig() }), "Harness updated", {
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
      }
    });
  });

  $(document).on("click", ".save-model", function () {
    const positionId = $(this).data("position");
    const model = $(this).siblings("select.position-model").val();
    postForm(API.positionModel, { positionId, model }, "Model updated");
  });

  $(document).on("change", ".position-model", function () {
    const positionId = $(this).data("position");
    const model = $(this).val();
    postForm(API.positionModel, { positionId, model }, "Model updated");
  });

  $(document).on("toggle", ".lane-inspector", function () {
    threadInspectorOpen = $(this).prop("open");
  });

  $(document).on("toggle", ".front-eval-technical", function () {
    frontEvalTechnicalOpen = $(this).prop("open");
  });

  $("#exportCurrentSession").on("click", function () {
    loadExportPreview("");
  });

  $(document).on("click", ".load-artifact-pair, .load-round-compare", function () {
    applyArtifactSelectionPair(
      String($(this).data("left") || ""),
      String($(this).data("right") || "")
    );
  });

  $(document).on("click", ".export-archive", function () {
    loadExportPreview(String($(this).data("archiveFile") || ""));
  });

  $(document).on("click", ".replay-session", function () {
    const archiveFile = String($(this).data("archiveFile") || "").trim();
    if (!archiveFile) return;
    if (!confirm("Replay " + archiveFile + " into the active workspace?")) return;
    postForm(API.sessionReplay, { archiveFile }, "Archived session replayed", {
      clearFormDirty: true,
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
      }
    });
  });

  $(document).on("click", ".manage-job", function () {
    const action = String($(this).data("action") || "").trim();
    const jobId = String($(this).data("jobId") || "").trim();
    if (!action || !jobId) return;
    const successText = action === "resume"
      ? "Interrupted loop resumed"
      : (action === "retry" ? "Loop queued for retry" : "Job cancelled");
    postForm(API.jobsManage, { action, jobId }, successText, {
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
      }
    });
  });

  $("#artifactLeftSelect").on("change", function () {
    artifactSelections.left = $(this).val();
    loadArtifactPane("Left", artifactSelections.left);
  });

  $("#artifactRightSelect").on("change", function () {
    artifactSelections.right = $(this).val();
    loadArtifactPane("Right", artifactSelections.right);
  });

});
