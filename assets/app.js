function showMessage(text, isError = false) {
  $("#message").text(text).css("color", isError ? "#ff8d8d" : "#67b0ff");
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
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
      "  status: " + (job.status || "unknown") + " | rounds: " + (job.completedRounds ?? 0) + "/" + (job.rounds ?? 0),
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

function applyLoopUi(loop) {
  const isActive = loop?.status === "running" || loop?.status === "queued";
  $("#loopJobId").text(loop?.jobId || "none");
  $("#loopStatus").text(loop?.status || "idle");
  $("#loopProgress").text((loop?.completedRounds ?? 0) + " / " + (loop?.totalRounds ?? 0));
  $("#loopNote").text(loop?.lastMessage || "Autonomous mode runs A -> B -> Summarizer repeatedly.");

  const disableWhileRunning = [
    "#startTask",
    "#runA",
    "#runB",
    "#summarize",
    "#runRound",
    "#runLoop",
    "#resetState"
  ];

  disableWhileRunning.forEach(function (selector) {
    $(selector).prop("disabled", isActive);
  });
  $("#cancelLoop").prop("disabled", !isActive);
}

function refreshState() {
  $.getJSON("api/get_state.php")
    .done(function (data) {
      $("#taskId").text(data.activeTask?.taskId || "none");
      $("#memoryVersion").text(data.memoryVersion ?? 0);
      applyLoopUi(data.loop || null);
      $("#workerA").text(data.workers?.A ? pretty(data.workers.A) : "No data.");
      $("#workerB").text(data.workers?.B ? pretty(data.workers.B) : "No data.");
      $("#summary").text(data.summary ? pretty(data.summary) : "No data.");
      $("#memory").text(pretty({
        activeTask: data.activeTask,
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
  refreshState();
  setInterval(refreshState, 2000);

  $("#startTask").on("click", function () {
    const objective = $("#objective").val().trim();
    const constraints = $("#constraints").val().split(/\r?\n/).map(x => x.trim()).filter(Boolean);
    const executionMode = $("#executionMode").val();
    const model = $("#model").val().trim();
    const reasoningEffort = $("#reasoningEffort").val();
    if (!objective) {
      showMessage("Objective is required.", true);
      return;
    }
    postForm("api/start_task.php", {
      objective,
      constraints: JSON.stringify(constraints),
      executionMode,
      model,
      reasoningEffort
    }, "Task started");
  });

  $("#runA").on("click", function () {
    postForm("api/run_ps.php", { target: "A" }, "Worker A ran");
  });

  $("#runB").on("click", function () {
    postForm("api/run_ps.php", { target: "B" }, "Worker B ran");
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

  $("#cancelLoop").on("click", function () {
    postForm("api/cancel_loop.php", {}, "Cancel sent");
  });

  $("#refresh").on("click", refreshState);

  $("#resetState").on("click", function () {
    if (!confirm("Reset state and clear active task?")) return;
    postForm("api/reset_state.php", {}, "State reset");
  });
});
