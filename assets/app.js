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

function showMessage(text, isError = false) {
  $("#message").text(text).css("color", isError ? "#ff8d8d" : "#67b0ff");
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function formatUsd(value) {
  const amount = Number(value || 0);
  return "$" + amount.toFixed(4);
}

function buildModelOptions(selectedValue) {
  return MODEL_ORDER.map(function (id) {
    const selected = id === selectedValue ? " selected" : "";
    return `<option value="${id}"${selected}>${MODEL_CATALOG[id].label}</option>`;
  }).join("");
}

function populateStaticModelSelect(selector, selectedValue) {
  const $select = $(selector);
  $select.html(buildModelOptions(selectedValue));
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
      ? "Stored in Auth.txt. Only the last 4 characters are shown."
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
      "  status: " + (job.status || "unknown") +
        " | rounds: " + (job.completedRounds ?? 0) + "/" + (job.rounds ?? 0) +
        " | workers: " + (job.workerCount ?? 0),
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
      "  kind: " + (artifact.kind || "artifact") +
        " | task: " + (artifact.taskId || "unknown") +
        " | slot: " + (artifact.worker || "-") +
        " | step/round: " + (artifact.roundOrStep ?? "-"),
      "  modified: " + (artifact.modifiedAt || "n/a") + " | bytes: " + (artifact.size ?? 0)
    ].join("\n");
  }).join("\n\n");
}

function renderWorkerPanels(task) {
  const $grid = $("#workerGrid");
  $grid.empty();

  if (!task || !task.workers || !task.workers.length) {
    $grid.append($("<div>").addClass("panel").append($("<pre>").text("No active task.")));
    return;
  }

  const workerState = task.stateWorkers || {};
  task.workers.forEach(function (worker) {
    const checkpoint = workerState[worker.id] || null;
    const $panel = $("<div>").addClass("panel workerpanel");
    $panel.append($("<h2>").text(worker.label + " - " + worker.role));
    $panel.append($("<div>").addClass("worker-meta").text("focus: " + worker.focus + " | model: " + worker.model));
    $panel.append($("<pre>").text(checkpoint ? pretty(checkpoint) : "No data."));
    $grid.append($panel);
  });
}

function renderWorkerControls(task, loop) {
  const $controls = $("#workerControls");
  $controls.empty();

  if (!task || !task.workers || !task.workers.length) {
    $controls.append($("<div>").addClass("workercontrol").text("No active task."));
    return;
  }

  const isActive = loop?.status === "running" || loop?.status === "queued";
  task.workers.forEach(function (worker) {
    const $card = $("<div>").addClass("workercontrol");
    $card.append($("<div>").addClass("workercontrol-title").text(worker.id + " | " + worker.label));
    $card.append($("<div>").addClass("workercontrol-meta").text(worker.role + " | " + worker.focus));

    const $row = $("<div>").addClass("inlineform");
    const $select = $("<select>")
      .addClass("position-model")
      .attr("data-position", worker.id)
      .html(buildModelOptions(worker.model));
    const $save = $("<button>")
      .addClass("save-model")
      .attr("data-position", worker.id)
      .prop("disabled", isActive)
      .text("Save Model");
    const $run = $("<button>")
      .addClass("run-target")
      .attr("data-target", worker.id)
      .prop("disabled", isActive)
      .text("Run " + worker.id);

    $row.append($select, $save, $run);
    $card.append($row);
    $controls.append($card);
  });

  const summarizerModel = task.summarizer?.model || task.runtime?.model || "gpt-5-mini";
  const $summaryCard = $("<div>").addClass("workercontrol");
  $summaryCard.append($("<div>").addClass("workercontrol-title").text("Summarizer"));
  $summaryCard.append($("<div>").addClass("workercontrol-meta").text("Canonical merge lane"));
  const $summaryRow = $("<div>").addClass("inlineform");
  $summaryRow.append(
    $("<select>").addClass("position-model").attr("data-position", "summarizer").html(buildModelOptions(summarizerModel)),
    $("<button>").addClass("save-model").attr("data-position", "summarizer").prop("disabled", isActive).text("Save Model"),
    $("<button>").addClass("run-target").attr("data-target", "summarizer").prop("disabled", isActive).text("Summarize")
  );
  $summaryCard.append($summaryRow);
  $controls.append($summaryCard);
}

function syncTaskForm(task) {
  if (!task) return;
  $("#objective").val(task.objective || "");
  $("#constraints").val((task.constraints || []).join("\n"));
  $("#executionMode").val(task.runtime?.executionMode || "live");
  $("#model").val(task.runtime?.model || "gpt-5-mini");
  $("#summarizerModel").val(task.summarizer?.model || task.runtime?.model || "gpt-5-mini");
  $("#reasoningEffort").val(task.runtime?.reasoningEffort || "low");
  $("#maxCostUsd").val(task.runtime?.budget?.maxCostUsd ?? 1.0);
  $("#maxTotalTokens").val(task.runtime?.budget?.maxTotalTokens ?? 120000);
  $("#maxOutputTokens").val(task.runtime?.budget?.maxOutputTokens ?? 1200);
}

function applyLoopUi(state) {
  const loop = state.loop || null;
  const task = state.activeTask || null;
  const hasTask = !!task;
  const isActive = loop?.status === "running" || loop?.status === "queued";
  const workers = task?.workers || [];
  const usage = state.usage || {};
  const budget = task?.runtime?.budget || {};

  $("#taskId").text(task?.taskId || "none");
  $("#memoryVersion").text(state.memoryVersion ?? 0);
  $("#loopJobId").text(loop?.jobId || "none");
  $("#loopStatus").text(loop?.status || "idle");
  $("#loopProgress").text((loop?.completedRounds ?? 0) + " / " + (loop?.totalRounds ?? 0));
  $("#loopNote").text(loop?.lastMessage || "Autonomous mode runs all configured workers and then summarizes.");
  $("#workerCount").text(workers.length || 0);
  $("#usageTokens").text((usage.totalTokens ?? 0) + " / " + (budget.maxTotalTokens ?? 0));
  $("#usageCost").text(formatUsd(usage.estimatedCostUsd || 0) + " / " + formatUsd(budget.maxCostUsd || 0));

  latestLoopActive = isActive;
  updateAuthButtons();

  $("#startTask").prop("disabled", isActive);
  $("#summarize").prop("disabled", isActive || !hasTask);
  $("#runRound").prop("disabled", isActive || !hasTask);
  $("#runLoop").prop("disabled", isActive || !hasTask);
  $("#addAdversarial").prop("disabled", isActive || !hasTask || (workers.length >= 26));
  $("#resetState").prop("disabled", isActive);
  $("#cancelLoop").prop("disabled", !isActive);
}

function refreshState() {
  refreshAuth();

  $.getJSON("api/get_state.php")
    .done(function (data) {
      const task = data.activeTask ? Object.assign({}, data.activeTask, { stateWorkers: data.workers || {} }) : null;
      syncTaskForm(data.activeTask || null);
      applyLoopUi(data);
      renderWorkerControls(data.activeTask || null, data.loop || null);
      renderWorkerPanels(task);
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
      showMessage("State load failed: " + xhr.responseText, true);
    });

  $.get("api/get_events.php")
    .done(function (data) {
      $("#events").text(data || "No events.");
    })
    .fail(function (xhr) {
      showMessage("Event load failed: " + xhr.responseText, true);
    });

  $.get("api/get_steps.php")
    .done(function (data) {
      $("#steps").text(data || "No steps.");
    })
    .fail(function (xhr) {
      showMessage("Step load failed: " + xhr.responseText, true);
    });

  $.getJSON("api/get_history.php")
    .done(function (data) {
      $("#historyJobs").text(renderJobs(data.jobs || [], data.recoveryWarning || null));
      $("#historyArtifacts").text(renderArtifacts(data.artifacts || []));
    })
    .fail(function (xhr) {
      showMessage("History load failed: " + xhr.responseText, true);
    });
}

function postForm(url, payload, successText) {
  $.post(url, payload)
    .done(function (resp) {
      let out = resp;
      try { out = JSON.parse(resp); } catch (_) {}
      showMessage(successText + (out.message ? " | " + out.message : ""));
      refreshState();
    })
    .fail(function (xhr) {
      showMessage("Request failed: " + xhr.responseText, true);
    });
}

$(function () {
  populateStaticModelSelect("#model", "gpt-5-mini");
  populateStaticModelSelect("#summarizerModel", "gpt-5-mini");
  refreshState();
  setInterval(refreshState, 2000);

  $("#startTask").on("click", function () {
    const objective = $("#objective").val().trim();
    const constraints = $("#constraints").val().split(/\r?\n/).map(x => x.trim()).filter(Boolean);
    const executionMode = $("#executionMode").val();
    const model = $("#model").val();
    const summarizerModel = $("#summarizerModel").val();
    const reasoningEffort = $("#reasoningEffort").val();
    const maxCostUsd = parseFloat($("#maxCostUsd").val()) || 0;
    const maxTotalTokens = parseInt($("#maxTotalTokens").val(), 10) || 0;
    const maxOutputTokens = parseInt($("#maxOutputTokens").val(), 10) || 0;

    if (!objective) {
      showMessage("Objective is required.", true);
      return;
    }

    postForm("api/start_task.php", {
      objective,
      constraints: JSON.stringify(constraints),
      executionMode,
      model,
      summarizerModel,
      reasoningEffort,
      maxCostUsd,
      maxTotalTokens,
      maxOutputTokens
    }, "Task started");
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

  $("#cancelLoop").on("click", function () {
    postForm("api/cancel_loop.php", {}, "Cancel sent");
  });

  $("#refresh").on("click", refreshState);

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
        showMessage("API key update failed: " + xhr.responseText, true);
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
        showMessage("API key clear failed: " + xhr.responseText, true);
      });
  });

  $("#resetState").on("click", function () {
    if (!confirm("Reset state and clear active task?")) return;
    postForm("api/reset_state.php", {}, "State reset");
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
});
