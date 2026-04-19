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
let latestAuthStatus = { hasKey: false, masked: null, last4: "" };
let latestLoopActive = false;
let artifactSelections = { left: "", right: "" };
let formDirty = false;
let lastSyncedFormSourceKey = "";
let activeView = localStorage.getItem("loopActiveView") || "home";

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
    updatedAt: ""
  };
}

function buildModelOptions(selectedValue) {
  return MODEL_ORDER.map(function (id) {
    const selected = id === selectedValue ? " selected" : "";
    return `<option value="${id}"${selected}>${MODEL_CATALOG[id].label}</option>`;
  }).join("");
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

function renderArtifactMeta(data) {
  const summary = data?.summary || {};
  const bits = [
    data?.name || "artifact",
    "kind: " + (data?.kind || "artifact") + " | storage: " + (data?.storage || "unknown"),
    "modified: " + (data?.modifiedAt || "n/a") + " | bytes: " + (data?.size ?? 0),
    "task: " + (summary.taskId || "n/a") + " | target: " + (summary.target || "n/a"),
    "mode: " + (summary.mode || "n/a") + " | model: " + (summary.model || "n/a"),
    "step: " + (summary.step ?? "-") + " | round: " + (summary.round ?? "-"),
    "responseId: " + (summary.responseId || "none")
  ];
  return bits.join("\n");
}

function renderArtifactContent(data) {
  const content = data?.content || {};
  const sections = [];

  if (content.rawOutputText) {
    sections.push("Raw Output Text\n" + content.rawOutputText);
  }

  if (Object.prototype.hasOwnProperty.call(content, "output")) {
    sections.push("Normalized Output\n" + pretty(content.output));
  } else {
    sections.push("Artifact Content\n" + pretty(content));
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
        task.runtime?.vetting?.enabled === false ? 0 : 1
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
        vettingEnabled: task.runtime?.vetting?.enabled === false ? false : true
      }
    };
  }

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
      safeDraft.vettingEnabled === false ? 0 : 1
    ].join("|"),
    values: safeDraft
  };
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
  $("#researchEnabled").val(safe.researchEnabled ? "1" : "0");
  $("#researchExternalWebAccess").val(safe.researchExternalWebAccess === false ? "0" : "1");
  $("#vettingEnabled").val(safe.vettingEnabled === false ? "0" : "1");
  $("#researchDomains").val((safe.researchDomains || []).join(", "));
  renderComposerContextPreview(safe.sessionContext || "", safe.constraints || []);
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
    researchEnabled: $("#researchEnabled").val(),
    researchExternalWebAccess: $("#researchExternalWebAccess").val(),
    vettingEnabled: $("#vettingEnabled").val(),
    researchDomains: $("#researchDomains").val().trim()
  };
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

function renderJobs(jobs, recoveryWarning) {
  const blocks = [];
  if (recoveryWarning) {
    blocks.push("Recovery note\n  " + recoveryWarning);
  }
  if (!jobs || !jobs.length) {
    blocks.push("No history.");
    return blocks.join("\n\n");
  }
  return blocks.concat(jobs.map(function (job) {
    const title = job.objective || job.taskId || job.jobId || "Unknown job";
    return [
      title,
      "  job: " + (job.jobId || "none"),
      "  status: " + (job.status || "unknown") + " | rounds: " + (job.completedRounds ?? 0) + "/" + (job.rounds ?? 0) + " | workers: " + (job.workerCount ?? 0),
      "  tokens: " + (job.totalTokens ?? 0) + " | spend: " + formatUsd(job.estimatedCostUsd || 0),
      "  mode: " + (job.mode || "background") + " | queued: " + (job.queuedAt || "n/a"),
      "  finished: " + (job.finishedAt || "n/a"),
      "  note: " + (job.lastMessage || "none")
    ].join("\n");
  })).join("\n\n");
}

function renderArtifacts(artifacts) {
  if (!artifacts || !artifacts.length) return "No history.";
  return artifacts.map(function (artifact) {
    return [
      artifact.name || "artifact",
      "  kind: " + (artifact.kind || "artifact") + " | task: " + (artifact.taskId || "unknown") + " | slot: " + (artifact.worker || "-") + " | step/round: " + (artifact.roundOrStep ?? "-"),
      "  modified: " + (artifact.modifiedAt || "n/a") + " | bytes: " + (artifact.size ?? 0)
    ].join("\n");
  }).join("\n\n");
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
    $card.append($("<div>").addClass("workercontrol-title").text(worker.id + " · " + worker.label));
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

function buildThreadMessage(options) {
  const sections = (options.sections || []).join("");
  return `
    <article class="thread-message ${escapeHtml(options.kind || "")} ${escapeHtml(options.variant || "")}">
      <div class="message-meta">
        <div class="message-author">${escapeHtml(options.author || "Message")}</div>
        <div class="message-tag">${escapeHtml(options.tag || "")}</div>
      </div>
      ${sections}
    </article>
  `;
}

function renderConversationThread(task, summary, workerState, loop) {
  const $thread = $("#conversationThread");

  if (!task) {
    $thread.html(`
      <div class="empty-thread">
        <div>
          <div class="empty-thread-title">No active task yet.</div>
          <div class="empty-thread-copy">Start a task from the composer below. Settings and debug stay out of the way until you need them.</div>
        </div>
      </div>
    `);
    return;
  }

  const messages = [];
  messages.push(buildThreadMessage({
    kind: "commander",
    author: "Commander",
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
      author: entry.worker.label,
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
      author: "Summarizer",
      tag: "Memory version " + ($("#memoryVersion").text() || "0"),
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

function applyLoopUi(state) {
  const loop = state.loop || null;
  const task = state.activeTask || null;
  const hasTask = !!task;
  const isActive = loop?.status === "running" || loop?.status === "queued";
  const workers = task?.workers || [];
  const usage = state.usage || {};
  const budget = task?.runtime?.budget || {};
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
    (
      (research.enabled ? "Workers can run grounded web research" : "Workers are running without web research") +
      " and the summarizer " + (vetting.enabled === false ? "merges only." : "acts as the evidence vetter.")
    )
  );
  $("#usageTokens").text((usage.totalTokens ?? 0) + " / " + (budget.maxTotalTokens ?? 0));
  $("#usageWebSearchCalls").text(usage.webSearchCalls ?? 0);
  $("#usageCost").text(formatUsd(usage.estimatedCostUsd || 0) + " / " + formatUsd(budget.maxCostUsd || 0));

  latestLoopActive = isActive;
  updateAuthButtons();

  $("#startTask").prop("disabled", isActive);
  $("#summarize").prop("disabled", isActive || !hasTask || !summaryReady);
  $("#runRound").prop("disabled", isActive || !hasTask);
  $("#runLoop").prop("disabled", isActive || !hasTask);
  $("#addAdversarial").prop("disabled", isActive || !hasTask || workers.length >= 26);
  $("#applyCurrentModels").prop("disabled", isActive || !hasTask);
  $("#resetSession").prop("disabled", isActive);
  $("#resetState").prop("disabled", isActive);
  $("#cancelLoop").prop("disabled", !isActive);
}

function refreshState() {
  refreshAuth();

  $.getJSON("api/get_state.php")
    .done(function (data) {
      const task = data.activeTask ? Object.assign({}, data.activeTask, { stateWorkers: data.workers || {} }) : null;
      syncCommanderForm(data.activeTask || null, data.draft || null);
      applyLoopUi(data);
      renderWorkerControls(data.activeTask || null, data.loop || null, data.workers || {});
      renderWorkerPanels(task);
      renderConversationThread(data.activeTask || null, data.summary || null, data.workers || {}, data.loop || null);
      $("#summary").text(data.summary ? pretty(data.summary) : "No data.");
      $("#memory").text(pretty({
        activeTask: data.activeTask,
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
      $("#historyJobs").text(renderJobs(data.jobs || [], data.recoveryWarning || null));
      $("#historyArtifacts").text(renderArtifacts(data.artifacts || []));
      syncArtifactReview(data.artifacts || []);
    })
    .fail(function (xhr) {
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
  setActiveView(activeView);
  refreshState();
  setInterval(refreshState, 2000);

  $(".nav-btn").on("click", function () {
    setActiveView($(this).data("view"));
  });

  $("#sessionContext, #objective, #constraints, #executionMode, #model, #summarizerModel, #reasoningEffort, #maxCostUsd, #maxTotalTokens, #maxOutputTokens, #researchEnabled, #researchExternalWebAccess, #vettingEnabled, #researchDomains").on("input change", function () {
    formDirty = true;
    renderComposerContextPreview($("#sessionContext").val().trim(), $("#constraints").val().split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean));
  });

  $("#startTask").on("click", function () {
    const payload = collectCommanderPayload();

    if (!payload.objective) {
      showMessage("Objective is required.", true);
      return;
    }

    postForm("api/start_task.php", {
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
      researchEnabled: payload.researchEnabled,
      researchExternalWebAccess: payload.researchExternalWebAccess,
      vettingEnabled: payload.vettingEnabled,
      researchDomains: payload.researchDomains
    }, "Task started", {
      clearFormDirty: true,
      onSuccess: function () {
        setActiveView("home");
      }
    });
  });

  $("#summarize").on("click", function () {
    postForm("api/run_ps.php", { target: "summarizer" }, "Summarizer ran");
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
    postForm("api/add_adversarial.php", {}, "Adversarial worker added");
  });

  $("#applyCurrentModels").on("click", function () {
    postForm("api/apply_runtime_models.php", {
      model: $("#model").val(),
      summarizerModel: $("#summarizerModel").val()
    }, "Current task models updated");
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
    postForm("api/reset_state.php", {}, "State reset", { clearFormDirty: true });
  });

  $(document).on("click", ".run-target", function () {
    const target = $(this).data("target");
    postForm("api/run_ps.php", { target }, "Target ran");
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

  $("#artifactLeftSelect").on("change", function () {
    artifactSelections.left = $(this).val();
    loadArtifactPane("Left", artifactSelections.left);
  });

  $("#artifactRightSelect").on("change", function () {
    artifactSelections.right = $(this).val();
    loadArtifactPane("Right", artifactSelections.right);
  });
});
