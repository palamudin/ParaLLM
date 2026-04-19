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
const QUALITY_PROFILE_CATALOG = {
  low: {
    label: "Low",
    eyebrow: "Lean spend",
    description: "Keeps every lane on a cheap capable model for everyday work without burning budget.",
    workerModel: "gpt-5-mini",
    summarizerModel: "gpt-5-mini",
    reasoningEffort: "low",
    maxCostUsd: 5,
    maxTotalTokens: 250000,
    maxOutputTokens: 1200,
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
    maxTotalTokens: 400000,
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
    maxTotalTokens: 800000,
    maxOutputTokens: 2800,
    loopRounds: 6,
    loopDelayMs: 1000
  },
  ultra: {
    label: "Ultra",
    eyebrow: "Cost wall only",
    description: "Removes the token wall and leaves spend as the main governor for maximum agentic pressure.",
    workerModel: "gpt-5.4",
    summarizerModel: "gpt-5.4",
    reasoningEffort: "xhigh",
    maxCostUsd: 75,
    maxTotalTokens: 0,
    maxOutputTokens: 4000,
    loopRounds: 8,
    loopDelayMs: 1000
  }
};
const QUALITY_PROFILE_ORDER = ["low", "mid", "high", "ultra"];
let latestAuthStatus = { hasKey: false, masked: null, last4: "" };
let latestLoopActive = false;
let artifactSelections = { left: "", right: "" };
let formDirty = false;
let lastSyncedFormSourceKey = "";
let activeView = localStorage.getItem("loopActiveView") || "home";
let latestState = null;
let latestHistoryState = null;
let draftSaveTimer = null;
let workerControlsSignature = "";
let debugControlsSignature = "";
let threadRenderSignature = "";
let threadRenderTaskId = "";
let threadInspectorOpen = false;
let exportPreviewKey = "";

function showMessage(text, isError = false) {
  $("#message").text(text || "").css({
    color: isError ? "#fecaca" : "#8ce7ff",
    borderColor: isError ? "rgba(248, 113, 113, 0.28)" : "rgba(76, 201, 240, 0.22)",
    background: isError ? "rgba(61, 25, 25, 0.76)" : "rgba(14, 33, 50, 0.76)"
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

function lineAnchorId(ref) {
  return "line-ref-" + String(ref || "").replace(/[^a-zA-Z0-9_-]+/g, "-");
}

function defaultDraftState() {
  return {
    objective: "",
    constraints: [],
    sessionContext: "",
    executionMode: "live",
    model: "gpt-5-mini",
    summarizerModel: "gpt-5-mini",
    reasoningEffort: "low",
    maxCostUsd: 5.0,
    maxTotalTokens: 250000,
    maxOutputTokens: 1200,
    researchEnabled: false,
    researchExternalWebAccess: true,
    researchDomains: [],
    vettingEnabled: true,
    loopRounds: 3,
    loopDelayMs: 1000,
    workers: [
      { id: "A", type: "proponent", label: "Proponent", role: "utility", focus: "benefits, feasibility, leverage, momentum, practical execution", temperature: "balanced", model: "gpt-5-mini" },
      { id: "B", type: "sceptic", label: "Sceptic", role: "adversarial", focus: "failure modes, downside, hidden coupling, consequences, externalities", temperature: "cool", model: "gpt-5-mini" }
    ],
    updatedAt: ""
  };
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

function buildModelOptions(selectedValue) {
  return MODEL_ORDER.map(function (id) {
    const selected = id === selectedValue ? " selected" : "";
    return `<option value="${id}"${selected}>${MODEL_CATALOG[id].label}</option>`;
  }).join("");
}

function modelLabel(modelId) {
  return MODEL_CATALOG[modelId]?.label || String(modelId || "Model");
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
  if (!$select.length) return;

  const workers = stagedWorkerSource(draft, task);
  const isActive = loop?.status === "running" || loop?.status === "queued";
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

function renderArtifactMeta(data) {
  const summary = data?.summary || {};
  const bits = [
    data?.name || "artifact",
    "kind: " + (data?.kind || "artifact") + " | storage: " + (data?.storage || "unknown"),
    "modified: " + (data?.modifiedAt || "n/a") + " | bytes: " + (data?.size ?? 0),
    "task: " + (summary.taskId || "n/a") + " | target: " + (summary.target || "n/a"),
    "mode: " + (summary.mode || "n/a") + " | model: " + (summary.model || "n/a"),
    "step: " + (summary.step ?? "-") + " | round: " + (summary.round ?? "-"),
    "responseId: " + (summary.responseId || "none"),
    "output cap: " + artifactOutputCapSummary(summary),
    "raw output policy: " + (data?.policy?.reviewSurface || "review_only") + " | public thread: " + (data?.policy?.publicThread || "structured_only")
  ];
  return bits.join("\n");
}

function renderArtifactContent(data) {
  const content = data?.content || {};
  const sections = [];

  if (Object.prototype.hasOwnProperty.call(content, "output")) {
    sections.push("Canonical Structured Output\n" + pretty(content.output));
  } else {
    sections.push("Artifact Content\n" + pretty(content));
  }

  if (content.rawOutputText) {
    sections.push("Review-Only Raw Output\nThis raw text is kept for auditability and replay. The structured output above remains the canonical source of truth.\n\n" + content.rawOutputText);
  }

  return sections.join("\n\n");
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

  $.getJSON("api/get_artifact.php", { name: artifactName })
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
    const leftDefault = pickArtifact(list, ["summary_output", "summary_round", "worker_output", "worker_step"], "");
    artifactSelections.left = leftDefault ? leftDefault.name : "";
  }

  if (!artifactSelections.right || !names.has(artifactSelections.right) || artifactSelections.right === artifactSelections.left) {
    const rightDefault = pickArtifact(list, ["worker_output", "worker_step", "summary_output", "summary_round"], artifactSelections.left);
    artifactSelections.right = rightDefault ? rightDefault.name : "";
  }

  $("#artifactLeftSelect").html(buildArtifactOptions(list, artifactSelections.left));
  $("#artifactRightSelect").html(buildArtifactOptions(list, artifactSelections.right));

  loadArtifactPane("Left", artifactSelections.left);
  loadArtifactPane("Right", artifactSelections.right);
}

function populateStaticModelSelect(selector, selectedValue) {
  $(selector).html(buildModelOptions(selectedValue));
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
        safeDraft.model || "gpt-5-mini",
        safeDraft.summarizerModel || "gpt-5-mini",
        safeDraft.reasoningEffort || "low",
        safeDraft.maxCostUsd ?? 5.0,
        safeDraft.maxTotalTokens ?? 250000,
        safeDraft.maxOutputTokens ?? 1200,
        safeDraft.researchEnabled ? 1 : 0,
        safeDraft.researchExternalWebAccess === false ? 0 : 1,
        JSON.stringify(safeDraft.researchDomains || []),
        safeDraft.vettingEnabled === false ? 0 : 1,
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
        task.runtime?.model || "gpt-5-mini",
        task.summarizer?.model || task.runtime?.model || "gpt-5-mini",
        task.runtime?.reasoningEffort || "low",
        task.runtime?.budget?.maxCostUsd ?? 5.0,
        task.runtime?.budget?.maxTotalTokens ?? 250000,
        task.runtime?.budget?.maxOutputTokens ?? 1200,
        task.runtime?.research?.enabled ? 1 : 0,
        task.runtime?.research?.externalWebAccess === false ? 0 : 1,
        JSON.stringify(task.runtime?.research?.domains || []),
        task.runtime?.vetting?.enabled === false ? 0 : 1,
        task.preferredLoop?.rounds ?? 3,
        task.preferredLoop?.delayMs ?? 1000,
        JSON.stringify(task.workers || [])
      ].join("|"),
      values: {
        objective: task.objective || "",
        constraints: task.constraints || [],
        sessionContext: task.sessionContext || "",
        executionMode: task.runtime?.executionMode || "live",
        model: task.runtime?.model || "gpt-5-mini",
        summarizerModel: task.summarizer?.model || task.runtime?.model || "gpt-5-mini",
        reasoningEffort: task.runtime?.reasoningEffort || "low",
        maxCostUsd: task.runtime?.budget?.maxCostUsd ?? 5.0,
        maxTotalTokens: task.runtime?.budget?.maxTotalTokens ?? 250000,
        maxOutputTokens: task.runtime?.budget?.maxOutputTokens ?? 1200,
        researchEnabled: task.runtime?.research?.enabled ? true : false,
        researchExternalWebAccess: task.runtime?.research?.externalWebAccess === false ? false : true,
        researchDomains: task.runtime?.research?.domains || [],
        vettingEnabled: task.runtime?.vetting?.enabled === false ? false : true,
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
    ? constraints.slice(0, 3).join(" · ")
    : "No constraints configured.";
  $("#sessionContextPreview").text(contextText);
  $("#constraintsPreview").text(truncateText(constraintText, 220));
}

function applyCommanderForm(values) {
  const safe = Object.assign({}, defaultDraftState(), values || {});
  $("#sessionContext").val(safe.sessionContext || "");
  $("#objective").val(safe.objective || "");
  $("#constraints").val((safe.constraints || []).join("\n"));
  $("#executionMode").val(safe.executionMode || "live");
  $("#model").val(safe.model || "gpt-5-mini");
  $("#summarizerModel").val(safe.summarizerModel || safe.model || "gpt-5-mini");
  $("#reasoningEffort").val(safe.reasoningEffort || "low");
  $("#maxCostUsd").val(safe.maxCostUsd ?? 5.0);
  $("#maxTotalTokens").val(safe.maxTotalTokens ?? 250000);
  $("#maxOutputTokens").val(safe.maxOutputTokens ?? 1200);
  $("#loopRounds").val(safe.loopRounds ?? 3);
  $("#loopDelayMs").val(safe.loopDelayMs ?? 1000);
  $("#researchEnabled").val(safe.researchEnabled ? "1" : "0");
  $("#researchExternalWebAccess").val(safe.researchExternalWebAccess === false ? "0" : "1");
  $("#vettingEnabled").val(safe.vettingEnabled === false ? "0" : "1");
  $("#researchDomains").val((safe.researchDomains || []).join(", "));
  renderQualityProfileCards();
  renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
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
    model: $("#model").val(),
    summarizerModel: $("#summarizerModel").val(),
    reasoningEffort: $("#reasoningEffort").val(),
    maxCostUsd: parseFloat($("#maxCostUsd").val()) || 0,
    maxTotalTokens: parseInt($("#maxTotalTokens").val(), 10) || 0,
    maxOutputTokens: parseInt($("#maxOutputTokens").val(), 10) || 0,
    loopRounds: parseInt($("#loopRounds").val(), 10) || 1,
    loopDelayMs: parseInt($("#loopDelayMs").val(), 10) || 0,
    researchEnabled: $("#researchEnabled").val(),
    researchExternalWebAccess: $("#researchExternalWebAccess").val(),
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

function stagedWorkerSource(draft, task) {
  if (Array.isArray(draft?.workers) && draft.workers.length) {
    return draft.workers;
  }
  if (task && Array.isArray(task.workers) && task.workers.length) {
    return task.workers;
  }
  return defaultDraftState().workers;
}

function collectVisibleWorkerRoster() {
  const workers = [];
  $("#workerControls .workercontrol").each(function () {
    const $card = $(this);
    const id = String($card.data("workerId") || "").trim();
    if (!id) return;
    const fallback = WORKER_TYPE_CATALOG[$card.find(".worker-type").val()] || WORKER_TYPE_CATALOG.sceptic;
    workers.push({
      id,
      type: $card.find(".worker-type").val(),
      temperature: $card.find(".worker-temperature").val(),
      model: $card.find(".worker-model").val(),
      label: fallback.label,
      role: fallback.role,
      focus: fallback.focus
    });
  });
  return workers;
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
  payload.constraints = JSON.stringify(payload.constraints);
  payload.workers = JSON.stringify(roster.length ? roster : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null));
  return payload;
}

function buildProfileAppliedWorkerRoster(modelId) {
  const visibleWorkers = collectVisibleWorkerRoster();
  const baseWorkers = visibleWorkers.length
    ? visibleWorkers
    : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null);
  return baseWorkers.map(function (worker) {
    return Object.assign({}, worker, { model: modelId });
  });
}

function setVisibleWorkerModels(modelId) {
  $("#workerControls .worker-model").each(function () {
    $(this).val(modelId);
  });
}

function buildQualityProfileSnapshot() {
  const payload = collectCommanderPayload();
  const workerSource = collectVisibleWorkerRoster();
  const roster = workerSource.length
    ? workerSource
    : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null);
  return {
    model: String(payload.model || ""),
    summarizerModel: String(payload.summarizerModel || payload.model || ""),
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
  if (comparable.model !== profile.workerModel) return false;
  if (comparable.summarizerModel !== profile.summarizerModel) return false;
  if (comparable.reasoningEffort !== profile.reasoningEffort) return false;
  if (Number(comparable.maxCostUsd) !== Number(profile.maxCostUsd)) return false;
  if (Number(comparable.maxTotalTokens) !== Number(profile.maxTotalTokens)) return false;
  if (Number(comparable.maxOutputTokens) !== Number(profile.maxOutputTokens)) return false;
  if (Number(comparable.loopRounds) !== Number(profile.loopRounds)) return false;
  if (Number(comparable.loopDelayMs) !== Number(profile.loopDelayMs)) return false;
  return (comparable.workerModels.length ? comparable.workerModels : [comparable.model]).every(function (modelId) {
    return modelId === profile.workerModel;
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
    model: String(task?.runtime?.model || "gpt-5-mini"),
    summarizerModel: String(task?.summarizer?.model || task?.runtime?.model || "gpt-5-mini"),
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
  if (left.model !== right.model) return false;
  if (left.summarizerModel !== right.summarizerModel) return false;
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

function appendHomeRuntimeBlock($root, label, value, metaLines, warning = false) {
  const $block = $("<div>").addClass("home-runtime-block");
  if (warning) $block.addClass("warning");
  $block.append($("<div>").addClass("home-runtime-label").text(label));
  $block.append($("<div>").addClass("home-runtime-value").text(value));
  (metaLines || []).filter(Boolean).forEach(function (line) {
    $block.append($("<div>").addClass("home-runtime-meta").text(line));
  });
  $root.append($block);
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

  $summary.empty();

  appendHomeRuntimeBlock(
    $summary,
    "Next send",
    stagedProfileName + " · " + (stagedPayload.executionMode || "live") + " mode",
    [
      "Workers: " + modelLabel(stagedSnapshot.model) + " | Summarizer: " + modelLabel(stagedSnapshot.summarizerModel) + " | Reasoning: " + (stagedSnapshot.reasoningEffort || "low"),
      "Budget: " + formatUsdBudget(stagedSnapshot.maxCostUsd) + " | " + formatTokenWall(stagedSnapshot.maxTotalTokens) + " | " + Number(stagedSnapshot.maxOutputTokens || 0).toLocaleString() + " max out",
      "Research: " + (stagedPayload.researchEnabled === "1" ? "on" : "off") + " | Vetting: " + (stagedPayload.vettingEnabled === "0" ? "off" : "on") + " | Auto loop: " + Number(stagedPayload.loopRounds || 0) + " rounds / " + Number(stagedPayload.loopDelayMs || 0) + " ms"
    ]
  );

  if (hasTask && activeSnapshot) {
    appendHomeRuntimeBlock(
      $summary,
      "Active task",
      activeProfileName + " · " + (task?.runtime?.executionMode || "live") + " mode",
      [
        "Workers: " + modelLabel(activeSnapshot.model) + " | Summarizer: " + modelLabel(activeSnapshot.summarizerModel) + " | Reasoning: " + (activeSnapshot.reasoningEffort || "low"),
        "Budget: " + formatUsdBudget(activeSnapshot.maxCostUsd) + " | " + formatTokenWall(activeSnapshot.maxTotalTokens) + " | " + Number(activeSnapshot.maxOutputTokens || 0).toLocaleString() + " max out",
        "Auto loop: " + Number(activeSnapshot.loopRounds || 0) + " rounds / " + Number(activeSnapshot.loopDelayMs || 0) + " ms"
      ]
    );

    appendHomeRuntimeBlock(
      $summary,
      runtimeSnapshotsMatch(stagedSnapshot, activeSnapshot) ? "Runtime sync" : "Runtime drift",
      runtimeSnapshotsMatch(stagedSnapshot, activeSnapshot)
        ? "Active task already matches the staged template."
        : "Next send and active task are different.",
      [
        runtimeSnapshotsMatch(stagedSnapshot, activeSnapshot)
          ? "You can keep prompting without touching settings."
          : "Use Sync Active if you want the current task to adopt the staged profile, loop depth, and budget."
      ],
      !runtimeSnapshotsMatch(stagedSnapshot, activeSnapshot)
    );
  } else {
    appendHomeRuntimeBlock(
      $summary,
      "Active task",
      "No active task yet.",
      ["Send will start a fresh task with the staged profile, roster, and loop settings."]
    );
  }

  $grid.empty();
  QUALITY_PROFILE_ORDER.forEach(function (profileId) {
    const profile = QUALITY_PROFILE_CATALOG[profileId];
    const $button = $("<button>")
      .attr("type", "button")
      .addClass("quick-profile-chip")
      .toggleClass("active", stagedProfileId === profileId)
      .attr("data-profile-id", profileId);
    $button.append($("<div>").addClass("quality-profile-eyebrow").text(profile.eyebrow));
    $button.append($("<div>").addClass("quick-profile-title").text(profile.label));
    $button.append($("<div>").addClass("quick-profile-meta").text(
      modelLabel(profile.workerModel) + " workers | " +
      modelLabel(profile.summarizerModel) + " summarizer | " +
      formatUsdBudget(profile.maxCostUsd)
    ));
    $button.append($("<div>").addClass("quick-profile-meta").text(
      profile.reasoningEffort + " reasoning | " + formatTokenWall(profile.maxTotalTokens) + " | " + Number(profile.loopRounds || 0) + " rounds"
    ));
    $grid.append($button);
  });

  $apply.prop("disabled", isLoopActive || !hasTask);
  $apply.text(isLoopActive ? "Loop Active" : "Sync Active");
}

function renderQualityProfileCards() {
  const $root = $("#qualityProfileCards");
  const $status = $("#qualityProfileStatus");
  if (!$root.length || !$status.length) return;

  const snapshot = buildQualityProfileSnapshot();
  const activeProfileId = detectQualityProfileId(snapshot);
  const distinctWorkerModels = Array.from(new Set((snapshot.workerModels || []).filter(Boolean)));
  const workerModelSummary = distinctWorkerModels.length === 1
    ? modelLabel(distinctWorkerModels[0])
    : (distinctWorkerModels.length > 1 ? "mixed worker models" : modelLabel(snapshot.model));

  $root.empty();
  QUALITY_PROFILE_ORDER.forEach(function (profileId) {
    const profile = QUALITY_PROFILE_CATALOG[profileId];
    const tokenText = Number(profile.maxTotalTokens) > 0 ? Number(profile.maxTotalTokens).toLocaleString() + " local tokens" : "cost wall only";
    const $button = $("<button>")
      .attr("type", "button")
      .addClass("quality-profile-card")
      .toggleClass("active", activeProfileId === profileId)
      .attr("data-profile-id", profileId);
    $button.append($("<div>").addClass("quality-profile-eyebrow").text(profile.eyebrow));
    $button.append($("<div>").addClass("quality-profile-title").text(profile.label));
    $button.append($("<div>").addClass("quality-profile-copy").text(profile.description));
    $button.append($("<div>").addClass("quality-profile-meta").text(
      "Workers: " + modelLabel(profile.workerModel) +
      " | Summarizer: " + modelLabel(profile.summarizerModel) +
      " | Reasoning: " + profile.reasoningEffort +
      " | Budget: " + formatUsdBudget(profile.maxCostUsd) +
      " | " + tokenText +
      " | Loop: " + Number(profile.loopRounds || 0) + " rounds"
    ));
    $root.append($button);
  });

  if (activeProfileId) {
    const profile = QUALITY_PROFILE_CATALOG[activeProfileId];
    $status.text(
      profile.label +
      " matches the current runtime template. " +
      "Workers use " + modelLabel(profile.workerModel) +
      ", summarizer uses " + modelLabel(profile.summarizerModel) +
      ", the token wall is " + (profile.maxTotalTokens > 0 ? Number(profile.maxTotalTokens).toLocaleString() : "off") +
      ", and auto loop depth is " + Number(profile.loopRounds || 0) + " rounds."
    );
    return;
  }

  $status.text(
    "Manual mix active. Workers are on " + workerModelSummary +
    ", summarizer is on " + modelLabel(snapshot.summarizerModel) +
    ", reasoning is " + (snapshot.reasoningEffort || "unset") +
    ", and auto loop depth is " + Number(snapshot.loopRounds || 0) + " rounds. Click a profile to snap the whole runtime back into a tested template."
  );
}

function applyQualityProfile(profileId) {
  const profile = QUALITY_PROFILE_CATALOG[profileId];
  if (!profile) return;

  $("#model").val(profile.workerModel);
  $("#summarizerModel").val(profile.summarizerModel);
  $("#reasoningEffort").val(profile.reasoningEffort);
  $("#maxCostUsd").val(profile.maxCostUsd);
  $("#maxTotalTokens").val(profile.maxTotalTokens);
  $("#maxOutputTokens").val(profile.maxOutputTokens);
  $("#loopRounds").val(profile.loopRounds);
  $("#loopDelayMs").val(profile.loopDelayMs);

  const workerRoster = buildProfileAppliedWorkerRoster(profile.workerModel);
  setVisibleWorkerModels(profile.workerModel);
  formDirty = true;
  renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
  renderQualityProfileCards();

  postForm("api/save_draft.php", buildDraftSavePayload({ workerRoster }), profile.label + " profile applied", {
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
    $.post("api/save_draft.php", buildDraftSavePayload()).fail(function (xhr) {
      showMessage("Draft save failed: " + extractErrorMessage(xhr), true);
    });
  }, 350);
}

function hasFocusWithin(selector) {
  const active = document.activeElement;
  return !!active && $(active).closest(selector).length > 0;
}

function updateAuthButtons() {
  $("#saveAuth").prop("disabled", latestLoopActive);
  $("#clearAuth").prop("disabled", latestLoopActive || !latestAuthStatus.hasKey);
}

function renderAuthStatus(data) {
  latestAuthStatus = {
    hasKey: !!data?.hasKey,
    masked: data?.masked || null,
    last4: data?.last4 || ""
  };

  $("#apiKeyMasked").text(latestAuthStatus.masked || "none");
  $("#apiKeyStatus").text(
    latestAuthStatus.hasKey
      ? "Stored locally. Only the last 4 characters are shown in the UI."
      : "No key stored. Live mode needs a key."
  );
  updateAuthButtons();
}

function refreshAuth() {
  $.getJSON("api/get_auth_status.php")
    .done(function (data) {
      renderAuthStatus(data);
    })
    .fail(function () {
      latestAuthStatus = { hasKey: false, masked: null, last4: "" };
      $("#apiKeyMasked").text("unavailable");
      $("#apiKeyStatus").text("Auth status could not be loaded.");
      updateAuthButtons();
    });
}

function applyArtifactSelectionPair(leftArtifact, rightArtifact) {
  const artifacts = latestHistoryState?.artifacts || [];
  const names = new Set(artifacts.map(function (artifact) { return artifact.name; }));

  artifactSelections.left = leftArtifact && names.has(leftArtifact) ? leftArtifact : "";
  artifactSelections.right = rightArtifact && names.has(rightArtifact) ? rightArtifact : "";

  if (!artifactSelections.left) {
    const fallbackLeft = pickArtifact(artifacts, ["summary_output", "worker_output", "summary_round", "worker_step"], "");
    artifactSelections.left = fallbackLeft ? fallbackLeft.name : "";
  }
  if (!artifactSelections.right || artifactSelections.right === artifactSelections.left) {
    const fallbackRight = pickArtifact(artifacts, ["worker_output", "summary_output", "worker_step", "summary_round"], artifactSelections.left);
    artifactSelections.right = fallbackRight ? fallbackRight.name : "";
  }

  $("#artifactLeftSelect").html(buildArtifactOptions(artifacts, artifactSelections.left));
  $("#artifactRightSelect").html(buildArtifactOptions(artifacts, artifactSelections.right));

  loadArtifactPane("Left", artifactSelections.left);
  loadArtifactPane("Right", artifactSelections.right);
}

function renderJobHistory(jobs, recoveryWarning, queueLimit) {
  const sections = [];

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
      <div class="history-meta">Background loops can queue up to ${formatInteger(queueLimit || 0)} jobs. Interrupted jobs can resume from the next unfinished round, while retry starts a fresh attempt.</div>
    </article>
  `);

  if (!jobs || !jobs.length) {
    sections.push(`<div class="review-empty">No recent jobs yet.</div>`);
    return `<div class="history-stack">${sections.join("")}</div>`;
  }

  jobs.forEach(function (job) {
    const title = truncateText(job.objective || job.taskId || job.jobId || "Unknown job", 140);
    const metaLines = [
      "Status: " + (job.status || "unknown") + " | rounds " + formatInteger(job.completedRounds || 0) + "/" + formatInteger(job.rounds || 0) + " | workers " + formatInteger(job.workerCount || 0),
      "Attempt " + formatInteger(job.attempt || 1) + " | tokens " + formatInteger(job.totalTokens || 0) + " | spend " + formatUsd(job.estimatedCostUsd || 0),
      "Queued " + (job.queuedAt || "n/a") + " | started " + (job.startedAt || "n/a") + " | finished " + (job.finishedAt || "n/a")
    ];

    if (Number(job.queuePosition || 0) > 0) {
      metaLines.push("Queue position: " + formatInteger(job.queuePosition));
    }
    if (job.resumeOfJobId) {
      metaLines.push("Resume of: " + job.resumeOfJobId + " | resumed from round " + formatInteger(job.resumeFromRound || 1));
    } else if (job.retryOfJobId) {
      metaLines.push("Retry of: " + job.retryOfJobId);
    } else if (job.canResume) {
      metaLines.push("Resume point: round " + formatInteger(job.resumeFromRound || 1));
    }
    if (job.lastMessage) {
      metaLines.push("Note: " + job.lastMessage);
    }
    if (job.error) {
      metaLines.push("Error: " + job.error);
    }

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
      <article class="history-card${["interrupted", "error", "budget_exhausted"].includes(String(job.status || "")) ? " warning" : ""}">
        <div class="history-head">
          <div class="history-title">${escapeHtml(title)}</div>
          <div class="history-title">${escapeHtml(job.jobId || "job")}</div>
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
        const summaryArtifact = roundEntry.summaryArtifact || null;
        const previousSummary = summaryByTaskRound[String(roundEntry.taskId || "") + ":" + String(Number(roundEntry.round || 0) - 1)] || null;
        const primaryWorker = Array.isArray(roundEntry.workerArtifacts) && roundEntry.workerArtifacts.length ? roundEntry.workerArtifacts[0] : null;
        const topActions = [];

        if (summaryArtifact && primaryWorker) {
          topActions.push(`<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(primaryWorker.name)}">Summary vs lane</button>`);
        }
        if (summaryArtifact && previousSummary) {
          topActions.push(`<button type="button" class="load-round-compare" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(previousSummary.name)}">Summary vs previous</button>`);
        }
        if (summaryArtifact) {
          topActions.push(`<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(primaryWorker?.name || summaryArtifact.name)}">Load in compare view</button>`);
        }

        return `
          <article class="round-history-card">
            <div class="round-history-head">
              <div class="round-history-title">Round ${escapeHtml(String(roundEntry.round || 0))}</div>
              <div class="round-history-title">${escapeHtml(roundEntry.taskId || "task")}</div>
            </div>
            <div class="round-history-meta">${escapeHtml(truncateText(roundEntry.objective || "No objective recorded.", 180))}</div>
            <div class="round-history-meta">${escapeHtml("Captured " + (roundEntry.capturedAt || "n/a") + (summaryArtifact ? " | summary " + summaryArtifact.name + " | " + artifactOutputCapSummary(summaryArtifact) : ""))}</div>
            ${topActions.length ? `<div class="round-history-actions">${topActions.join("")}</div>` : ""}
            <div class="round-history-workers">
              ${(roundEntry.workerArtifacts || []).map(function (artifact) {
                return `
                  <div class="round-worker-row">
                    <div>
                      <div class="history-title">${escapeHtml((artifact.worker || "worker") + " | " + (artifact.model || "model n/a"))}</div>
                      <div class="round-worker-meta">${escapeHtml((artifact.name || "artifact") + " | " + artifactOutputCapSummary(artifact))}</div>
                    </div>
                    ${summaryArtifact ? `<button type="button" class="load-artifact-pair" data-left="${escapeHtml(summaryArtifact.name)}" data-right="${escapeHtml(artifact.name)}">Compare vs summary</button>` : ""}
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
        return `
          <article class="session-archive-card">
            <div class="session-archive-head">
              <div class="session-archive-title">${escapeHtml(session.file || "archive")}</div>
              <div class="session-archive-title">${escapeHtml(session.taskId || "no task")}</div>
            </div>
            <div class="session-archive-meta">${escapeHtml("Archived " + (session.archivedAt || "n/a") + " | reason " + (session.reason || "unspecified"))}</div>
            <div class="session-archive-meta">${escapeHtml(session.carryContextPreview || "No carry-forward preview.")}</div>
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

function loadExportPreview(archiveFile = "") {
  const requestKey = archiveFile ? "archive:" + archiveFile : "current";
  exportPreviewKey = requestKey;
  $("#exportPreview").text("Loading export preview...");

  const params = archiveFile ? { archiveFile } : {};
  $.getJSON("api/export_session.php", params)
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
    $head.append($("<div>").addClass("lane-card-title").text(worker.label + " · " + worker.role));
    $head.append($("<div>").addClass("lane-card-step").text(checkpoint ? "step " + (checkpoint.step || 0) : "waiting"));
    $card.append($head);
    $card.append($("<div>").addClass("lane-card-focus").text(worker.focus + " | model: " + worker.model));
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

function renderWorkerControls(task, loop, stateWorkers) {
  const $controls = $("#workerControls");
  $controls.empty();

  if (!task || !task.workers || !task.workers.length) {
    $controls.append($("<div>").addClass("workercontrol").text("No active task."));
    return;
  }

  const isActive = loop?.status === "running" || loop?.status === "queued";
  const summaryReady = allWorkerCheckpointsReady(task, stateWorkers || {});

  task.workers.forEach(function (worker) {
    const $card = $("<div>").addClass("workercontrol");
    $card.append($("<div>").addClass("workercontrol-title").text(worker.id + " · " + displayWorkerLabel(worker)));
    $card.append($("<div>").addClass("workercontrol-meta").text(worker.role + " | " + worker.focus));

    const $row = $("<div>").addClass("inlineform");
    $row.append(
      $("<select>").addClass("position-model").attr("data-position", worker.id).html(buildModelOptions(worker.model)),
      $("<button>").addClass("save-model").attr("data-position", worker.id).prop("disabled", isActive).text("Save Model"),
      $("<button>").addClass("run-target").attr("data-target", worker.id).prop("disabled", isActive).text("Run " + worker.id)
    );
    $card.append($row);
    $controls.append($card);
  });

  const summarizerModel = task.summarizer?.model || task.runtime?.model || "gpt-5-mini";
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
    $("<select>").addClass("position-model").attr("data-position", "summarizer").html(buildModelOptions(summarizerModel)),
    $("<button>").addClass("save-model").attr("data-position", "summarizer").prop("disabled", isActive).text("Save Model"),
    $("<button>").addClass("run-target").attr("data-target", "summarizer").prop("disabled", isActive || !summaryReady).text("Summarize")
  );
  $summaryCard.append($summaryRow);
  $controls.append($summaryCard);
}

function renderHomeWorkerControls(task, draft, loop) {
  const $controls = $("#workerControls");
  const workers = stagedWorkerSource(draft, task);
  const signature = JSON.stringify({
    mode: "draft",
    workers,
    loopStatus: loop?.status || "idle"
  });
  if (signature === workerControlsSignature || hasFocusWithin("#workerControls")) return;
  workerControlsSignature = signature;
  $controls.empty();

  if (!workers.length) {
    $controls.append($("<div>").addClass("workercontrol").text("No workers configured."));
    return;
  }

  const isActive = loop?.status === "running" || loop?.status === "queued";
  workers.forEach(function (worker) {
    const $card = $("<div>").addClass("workercontrol").attr("data-worker-id", worker.id);
    $card.append($("<div>").addClass("workercontrol-title").text(worker.id + " · " + displayWorkerLabel(worker)));
    $card.append($("<div>").addClass("workercontrol-meta").text(worker.role + " | " + worker.focus));

    const $typeRow = $("<div>").addClass("workercontrol-field");
    $typeRow.append($("<label>").text("Directive"));
    $typeRow.append(
      $("<select>").addClass("worker-type").attr("data-worker-id", worker.id).prop("disabled", isActive).html(buildWorkerTypeOptions(worker.type || "sceptic"))
    );
    $card.append($typeRow);

    const $temperatureRow = $("<div>").addClass("workercontrol-field");
    $temperatureRow.append($("<label>").text("Temperature"));
    $temperatureRow.append(
      $("<select>").addClass("worker-temperature").attr("data-worker-id", worker.id).prop("disabled", isActive).html(buildWorkerTemperatureOptions(worker.temperature || "balanced"))
    );
    $card.append($temperatureRow);

    const $modelRow = $("<div>").addClass("workercontrol-field");
    $modelRow.append($("<label>").text("Model"));
    $modelRow.append(
      $("<select>").addClass("worker-model").attr("data-worker-id", worker.id).prop("disabled", isActive).html(buildModelOptions(worker.model))
    );
    $card.append($modelRow);

    $controls.append($card);
  });
}

function renderDebugTargetControls(task, loop, stateWorkers) {
  const $controls = $("#debugTargetControls");
  const signature = JSON.stringify({
    taskId: task?.taskId || "",
    workers: task?.workers || [],
    loopStatus: loop?.status || "idle",
    summaryReady: allWorkerCheckpointsReady(task, stateWorkers || {})
  });
  if (signature === debugControlsSignature || hasFocusWithin("#debugTargetControls")) return;
  debugControlsSignature = signature;
  $controls.empty();

  if (!task || !task.workers || !task.workers.length) {
    $controls.append($("<div>").addClass("workercontrol").text("No active task."));
    return;
  }

  const isActive = loop?.status === "running" || loop?.status === "queued";
  const summaryReady = allWorkerCheckpointsReady(task, stateWorkers || {});
  task.workers.forEach(function (worker) {
    const checkpoint = stateWorkers?.[worker.id] || null;
    const $card = $("<div>").addClass("workercontrol");
    $card.append($("<div>").addClass("workercontrol-title").text(worker.id + " · " + worker.label));
    $card.append($("<div>").addClass("workercontrol-meta").text((checkpoint ? "step " + (checkpoint.step || 0) : "no checkpoint") + " | " + worker.model));
    $card.append(
      $("<div>").addClass("inlineform").append(
        $("<button>").addClass("run-target").attr("data-target", worker.id).prop("disabled", isActive).text("Run " + worker.id)
      )
    );
    $controls.append($card);
  });

  const summarizerModel = task.summarizer?.model || task.runtime?.model || "gpt-5-mini";
  const $summaryCard = $("<div>").addClass("workercontrol");
  $summaryCard.append($("<div>").addClass("workercontrol-title").text("Summarizer"));
  $summaryCard.append($("<div>").addClass("workercontrol-meta").text((summaryReady ? "ready" : "waiting on workers") + " | " + summarizerModel));
  $summaryCard.append(
    $("<div>").addClass("inlineform").append(
      $("<button>").addClass("run-target").attr("data-target", "summarizer").prop("disabled", isActive || !summaryReady).text("Summarize")
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
  workers.forEach(function (worker) {
    const checkpoint = workerState[worker.id] || null;
    const $card = $("<div>").addClass("lane-card");
    const $head = $("<div>").addClass("lane-card-head");
    $head.append($("<div>").addClass("lane-card-title").text(displayWorkerLabel(worker) + " · " + (worker.type || worker.role)));
    $head.append($("<div>").addClass("lane-card-step").text(checkpoint ? "step " + (checkpoint.step || 0) : (task ? "waiting" : "ready")));
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

function renderSummaryOpinion(summary) {
  if (!summary) {
    return `<div class="review-empty">No summary yet.</div>`;
  }
  const frontAnswer = summary.frontAnswer || {};
  const opinion = summary.summarizerOpinion || {};
  const blocks = [
    renderReviewBlock("Public answer", frontAnswer.answer || buildAgentReplyText(summary)),
    renderReviewBlock("Lead direction", frontAnswer.leadDirection || frontAnswer.stance || ""),
    renderReviewBlock("Absorbed adversarial pressure", frontAnswer.adversarialPressure || ""),
    renderReviewBlock("Current stance", opinion.stance || frontAnswer.stance || ""),
    renderReviewBlock("Why it landed here", opinion.because || ""),
    renderReviewBlock("Integration mode", opinion.integrationMode || ""),
    renderReviewBlock("Uncertainty", opinion.uncertainty || frontAnswer.confidenceNote || ""),
    renderReviewBlock("Recommended next action", summary.recommendedNextAction || ""),
    renderReviewBlock("Vetting note", summary.vettingSummary || "")
  ].filter(Boolean);
  return blocks.length ? `<div class="review-stack">${blocks.join("")}</div>` : `<div class="review-empty">No summary yet.</div>`;
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

function renderSummaryReview(summary, task, workerState) {
  $("#summaryOpinion").html(renderSummaryOpinion(summary));
  $("#summaryTrace").html(renderSummaryTrace(summary, task, workerState));
  $("#summaryLineCatalog").html(renderSummaryLineCatalog(summary, task, workerState));
}

function buildConversationRenderSignature(task, summary, workerState) {
  if (!task) return "empty";

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
    summary: summary ? {
      round: summary.round || 0,
      frontAnswer: summary.frontAnswer || null,
      stableFindings: summary.stableFindings || [],
      conflicts: summary.conflicts || [],
      recommendedNextAction: summary.recommendedNextAction || "",
      vettingSummary: summary.vettingSummary || "",
      claimsNeedingVerification: summary.claimsNeedingVerification || []
    } : null,
    workers: workerSignature
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
    $thread.html(`
      <div class="empty-thread">
        <div>
          <div class="empty-thread-title">No active task yet.</div>
          <div class="empty-thread-copy">Send a prompt below. The assistant will answer here, and the internal lane trace will stay in Review.</div>
        </div>
      </div>
    `);
    return;
  }

  const messages = [];
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
      tag: "Multistream summary · memory " + ($("#memoryVersion").text() || "0"),
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
  const isActive = loop?.status === "running" || loop?.status === "queued";
  const workers = activeWorkerSource(task, state.draft || null);
  const usage = state.usage || {};
  const budget = task?.runtime?.budget || {
    maxTotalTokens: state.draft?.maxTotalTokens ?? 0,
    maxCostUsd: state.draft?.maxCostUsd ?? 0
  };
  const research = task?.runtime?.research || {};
  const vetting = task?.runtime?.vetting || {};
  const summaryReady = allWorkerCheckpointsReady(task, state.workers || {});

  $("#taskId").text(task?.taskId || "none");
  $("#headerTaskId").text(task?.taskId || "none");
  $("#memoryVersion").text(state.memoryVersion ?? 0);
  $("#workerCount").text(workers.length || 0);
  $("#headerWorkerCount").text(workers.length || 0);
  $("#loopJobId").text(loop?.jobId || "none");
  $("#loopStatus").text(loop?.status || "idle");
  $("#headerLoopStatus").text(loop?.status || "idle");
  $("#loopProgress").text((loop?.completedRounds ?? 0) + " / " + (loop?.totalRounds ?? 0));
  $("#loopNote").text(
    loop?.lastMessage ||
    (!hasTask
      ? "Press Send to start the configured roster and loop automatically."
      : (
      (research.enabled ? "Workers can run grounded web research" : "Workers are running without web research") +
      " and the summarizer " + (vetting.enabled === false ? "merges only." : "acts as the evidence vetter.")
    ))
  );
  $("#usageTokens").text((usage.totalTokens ?? 0) + " / " + (budget.maxTotalTokens ?? 0));
  $("#usageWebSearchCalls").text(usage.webSearchCalls ?? 0);
  $("#usageCost").text(formatUsd(usage.estimatedCostUsd || 0) + " / " + formatUsd(budget.maxCostUsd || 0));

  latestLoopActive = isActive;
  updateAuthButtons();

  $("#sendPrompt").prop("disabled", isActive);
  $("#summarize").prop("disabled", isActive || !hasTask || !summaryReady);
  $("#runRound").prop("disabled", isActive || !hasTask);
  $("#runLoop").prop("disabled", isActive || !hasTask);
  $("#addAdversarial").prop("disabled", isActive || workers.length >= 26);
  $("#applyCurrentModels").prop("disabled", isActive || !hasTask);
  $("#resetSession").prop("disabled", isActive);
  $("#resetState").prop("disabled", isActive);
  $("#cancelLoop").prop("disabled", !isActive);
}

function renderConversationThread(task, summary, workerState, loop) {
  const $thread = $("#conversationThread");
  const threadNode = $thread[0];

  if (!task) {
    threadRenderSignature = "empty";
    threadRenderTaskId = "";
    threadInspectorOpen = false;
    $thread.html(`
      <div class="empty-thread">
        <div>
          <div class="empty-thread-title">No active task yet.</div>
          <div class="empty-thread-copy">Send a prompt below. The assistant will answer here, and the internal lane trace will stay in Review.</div>
        </div>
      </div>
    `);
    return;
  }

  const nextTaskId = String(task.taskId || "");
  if (threadRenderTaskId !== nextTaskId) {
    threadRenderTaskId = nextTaskId;
    threadRenderSignature = "";
    threadInspectorOpen = false;
  }

  const signature = buildConversationRenderSignature(task, summary, workerState);
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

  if (summary) {
    messages.push(buildThreadMessage({
      kind: "summary",
      author: "Assistant",
      sections: [
        renderPlainTextBlock(buildAgentReplyText(summary))
      ]
    }));
  } else {
    const waitingText = "Thinking through the prompt and shaping a final answer.";

    messages.push(buildThreadMessage({
      kind: "summary",
      author: "Assistant",
      sections: [
        renderPlainTextBlock(waitingText)
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
  const isActive = loop?.status === "running" || loop?.status === "queued";
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

  $("#taskId").text(task?.taskId || "none");
  $("#headerTaskId").text(task?.taskId || "none");
  $("#headerProfile").text(headerProfileName);
  $("#memoryVersion").text(state.memoryVersion ?? 0);
  $("#workerCount").text(workers.length || 0);
  $("#headerWorkerCount").text(workers.length || 0);
  $("#loopJobId").text(loop?.jobId || "none");
  $("#loopStatus").text(loop?.status || "idle");
  $("#headerLoopStatus").text(loop?.status || "idle");
  $("#loopProgress").text((loop?.completedRounds ?? 0) + " / " + (loop?.totalRounds ?? 0));
  $("#loopNote").text(
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
  $("#usageTokens").text((usage.totalTokens ?? 0) + " / " + (budget.maxTotalTokens ?? 0));
  $("#usageWebSearchCalls").text(usage.webSearchCalls ?? 0);
  $("#usageCost").text(formatUsd(usage.estimatedCostUsd || 0) + " / " + formatUsd(budget.maxCostUsd || 0));

  latestLoopActive = isActive;
  updateAuthButtons();

  $("#sendPrompt").prop("disabled", isActive);
  $("#summarize").prop("disabled", isActive || !hasTask || !summaryReady);
  $("#runRound").prop("disabled", isActive || !hasTask);
  $("#runLoop").prop("disabled", isActive || !hasTask);
  $("#addAdversarial").prop("disabled", isActive || workers.length >= 26);
  $("#applyCurrentModels").prop("disabled", isActive || !hasTask);
  $("#resetSession").prop("disabled", isActive);
  $("#resetState").prop("disabled", isActive);
  $("#cancelLoop").prop("disabled", !isActive);
}

function refreshState() {
  refreshAuth();

  $.getJSON("api/get_state.php")
    .done(function (data) {
      latestState = data;
      const task = data.activeTask ? Object.assign({}, data.activeTask, { stateWorkers: data.workers || {} }) : null;
      syncCommanderForm(data.activeTask || null, data.draft || null);
      applyLoopUi(data);
      renderAddWorkerTypeControl(data.activeTask || null, data.draft || null, data.loop || null);
      renderHomeWorkerControls(data.activeTask || null, data.draft || null, data.loop || null);
      renderHomeRuntimeControls(data.activeTask || null, data.draft || null, data.loop || null);
      renderQualityProfileCards();
      renderDebugTargetControls(data.activeTask || null, data.loop || null, data.workers || {});
      renderRosterPanels(task, data.draft || null);
      renderConversationThread(data.activeTask || null, data.summary || null, data.workers || {}, data.loop || null);
      renderSummaryReview(data.summary || null, data.activeTask || null, data.workers || {});
      $("#summary").text(data.summary ? pretty(data.summary) : "No data.");
      $("#memory").text(pretty({
        activeTask: data.activeTask,
        draft: data.draft,
        usage: data.usage,
        loop: data.loop,
        memoryVersion: data.memoryVersion,
        lastUpdated: data.lastUpdated
      }));
    })
    .fail(function (xhr) {
      showMessage("State load failed: " + (xhr.responseText || "Unknown error"), true);
    });

  $.get("api/get_events.php")
    .done(function (data) {
      $("#events").text(data || "No events.");
    })
    .fail(function (xhr) {
      showMessage("Event load failed: " + (xhr.responseText || "Unknown error"), true);
    });

  $.get("api/get_steps.php")
    .done(function (data) {
      $("#steps").text(data || "No steps.");
    })
    .fail(function (xhr) {
      showMessage("Step load failed: " + (xhr.responseText || "Unknown error"), true);
    });

  $.getJSON("api/get_history.php")
    .done(function (data) {
      latestHistoryState = data;
      $("#jobHistory").html(renderJobHistory(data.jobs || [], data.recoveryWarning || null, data.queueLimit || 0));
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

function postForm(url, payload, successText, options = {}) {
  $.post(url, payload)
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
    });
}

function applyCurrentRuntimeSettings(successText = "Current task runtime updated") {
  postForm("api/apply_runtime_models.php", {
    model: $("#model").val(),
    summarizerModel: $("#summarizerModel").val(),
    reasoningEffort: $("#reasoningEffort").val(),
    maxCostUsd: $("#maxCostUsd").val(),
    maxTotalTokens: $("#maxTotalTokens").val(),
    maxOutputTokens: $("#maxOutputTokens").val(),
    loopRounds: $("#loopRounds").val(),
    loopDelayMs: $("#loopDelayMs").val()
  }, successText, {
    onSuccess: function () {
      workerControlsSignature = "";
      debugControlsSignature = "";
    }
  });
}

function setActiveView(viewName) {
  activeView = viewName;
  localStorage.setItem("loopActiveView", viewName);
  $(".nav-btn").removeClass("active").filter(`[data-view="${viewName}"]`).addClass("active");
  $(".workspace-view").removeClass("active").filter(`[data-view="${viewName}"]`).addClass("active");
}

$(function () {
  populateStaticModelSelect("#model", "gpt-5-mini");
  populateStaticModelSelect("#summarizerModel", "gpt-5-mini");
  $("#researchEnabled").val("0");
  $("#researchExternalWebAccess").val("1");
  $("#vettingEnabled").val("1");
  applyCommanderForm(defaultDraftState());
  renderAddWorkerTypeControl(null, defaultDraftState(), null);
  setActiveView(activeView);
  refreshState();
  setInterval(refreshState, 2000);

  $(".nav-btn").on("click", function () {
    setActiveView($(this).data("view"));
  });

  $("#sessionContext, #objective, #constraints, #executionMode, #model, #summarizerModel, #reasoningEffort, #maxCostUsd, #maxTotalTokens, #maxOutputTokens, #loopRounds, #loopDelayMs, #researchEnabled, #researchExternalWebAccess, #vettingEnabled, #researchDomains").on("input change", function () {
    formDirty = true;
    renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
    renderQualityProfileCards();
    queueDraftSave();
  });

  $("#sendPrompt").on("click", function () {
    const payload = collectCommanderPayload();
    const visibleWorkers = collectVisibleWorkerRoster();
    const workers = visibleWorkers.length ? visibleWorkers : stagedWorkerSource(latestState?.draft || null, latestState?.activeTask || null);

    if (!payload.objective) {
      showMessage("Objective is required.", true);
      return;
    }

    const startPayload = {
      sessionContext: payload.sessionContext,
      objective: payload.objective,
      constraints: JSON.stringify(payload.constraints),
      executionMode: payload.executionMode,
      model: payload.model,
      summarizerModel: payload.summarizerModel,
      reasoningEffort: payload.reasoningEffort,
      maxCostUsd: payload.maxCostUsd,
      maxTotalTokens: payload.maxTotalTokens,
      maxOutputTokens: payload.maxOutputTokens,
      loopRounds: payload.loopRounds,
      loopDelayMs: payload.loopDelayMs,
      researchEnabled: payload.researchEnabled,
      researchExternalWebAccess: payload.researchExternalWebAccess,
      vettingEnabled: payload.vettingEnabled,
      researchDomains: payload.researchDomains,
      workers: JSON.stringify(workers)
    };

    $.post("api/start_task.php", startPayload)
      .done(function (resp) {
        let out = resp;
        try { out = JSON.parse(resp); } catch (_) {}
        $.post("api/start_loop.php", { rounds: payload.loopRounds, delayMs: payload.loopDelayMs })
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
    postForm("api/run_target.php", { target: "summarizer" }, "Summarizer ran");
  });

  $("#runRound").on("click", function () {
    postForm("api/run_round.php", {}, "Round ran");
  });

  $("#runLoop").on("click", function () {
    const rounds = parseInt($("#loopRounds").val(), 10) || 3;
    const delayMs = parseInt($("#loopDelayMs").val(), 10) || 0;
    postForm("api/start_loop.php", { rounds, delayMs }, "Auto loop queued");
  });

  $("#addAdversarial").on("click", function () {
    postForm("api/add_adversarial.php", {
      type: $("#addWorkerType").val()
    }, "Worker added", {
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
        $("#addWorkerType").removeData("selectedType");
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
    postForm("api/cancel_loop.php", {}, "Cancel sent");
  });

  $("#refresh").on("click", refreshState);

  $("#resetSession").on("click", function () {
    if (!confirm("Archive the current session and load a fresh draft with short carry-forward context?")) return;
    postForm("api/reset_session.php", {}, "Session reset", {
      clearFormDirty: true,
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
        setActiveView("home");
      }
    });
  });

  $("#saveAuth").on("click", function () {
    const apiKey = $("#apiKeyInput").val().trim();
    if (!apiKey) {
      showMessage("Enter an API key to save.", true);
      return;
    }

    $.post("api/set_auth.php", { apiKey })
      .done(function (resp) {
        let out = resp;
        try { out = JSON.parse(resp); } catch (_) {}
        $("#apiKeyInput").val("");
        showMessage("API key saved" + (out.message ? " | " + out.message : ""));
        refreshState();
      })
      .fail(function (xhr) {
        showMessage("API key update failed: " + extractErrorMessage(xhr), true);
      });
  });

  $("#clearAuth").on("click", function () {
    if (!confirm("Clear the stored API key from Auth.txt?")) return;

    $.post("api/set_auth.php", { clear: 1 })
      .done(function (resp) {
        let out = resp;
        try { out = JSON.parse(resp); } catch (_) {}
        $("#apiKeyInput").val("");
        showMessage("API key cleared" + (out.message ? " | " + out.message : ""));
        refreshState();
      })
      .fail(function (xhr) {
        showMessage("API key clear failed: " + extractErrorMessage(xhr), true);
      });
  });

  $("#resetState").on("click", function () {
    if (!confirm("Reset state and clear active task?")) return;
    postForm("api/reset_state.php", {}, "State reset", {
      clearFormDirty: true,
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
      }
    });
  });

  $(document).on("click", ".run-target", function () {
    const target = $(this).data("target");
    postForm("api/run_target.php", { target }, "Target ran");
  });

  $(document).on("change", ".worker-type, .worker-temperature, .worker-model", function () {
    const $card = $(this).closest(".workercontrol");
    const workerId = String($card.data("workerId") || "").trim();
    if (!workerId) return;
    renderHomeRuntimeControls(latestState?.activeTask || null, latestState?.draft || null, latestState?.loop || null);
    renderQualityProfileCards();
    postForm("api/update_worker.php", {
      workerId,
      type: $card.find(".worker-type").val(),
      temperature: $card.find(".worker-temperature").val(),
      model: $card.find(".worker-model").val()
    }, "Worker updated", {
      onSuccess: function () {
        workerControlsSignature = "";
        debugControlsSignature = "";
      }
    });
  });

  $(document).on("click", ".save-model", function () {
    const positionId = $(this).data("position");
    const model = $(this).siblings("select.position-model").val();
    postForm("api/set_worker_model.php", { positionId, model }, "Model updated");
  });

  $(document).on("change", ".position-model", function () {
    const positionId = $(this).data("position");
    const model = $(this).val();
    postForm("api/set_worker_model.php", { positionId, model }, "Model updated");
  });

  $(document).on("toggle", ".lane-inspector", function () {
    threadInspectorOpen = $(this).prop("open");
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
    postForm("api/replay_session.php", { archiveFile }, "Archived session replayed", {
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
    postForm("api/manage_job.php", { action, jobId }, successText, {
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
