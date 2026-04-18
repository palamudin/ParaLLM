function showMessage(text, isError = false) {
  $("#message").text(text).css("color", isError ? "#ff8d8d" : "#67b0ff");
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function refreshState() {
  $.getJSON("api/get_state.php")
    .done(function (data) {
      $("#taskId").text(data.activeTask?.taskId || "none");
      $("#memoryVersion").text(data.memoryVersion ?? 0);
      $("#workerA").text(data.workers?.A ? pretty(data.workers.A) : "No data.");
      $("#workerB").text(data.workers?.B ? pretty(data.workers.B) : "No data.");
      $("#summary").text(data.summary ? pretty(data.summary) : "No data.");
      $("#memory").text(pretty({
        activeTask: data.activeTask,
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

  $("#refresh").on("click", refreshState);

  $("#resetState").on("click", function () {
    if (!confirm("Reset state and clear active task?")) return;
    postForm("api/reset_state.php", {}, "State reset");
  });
});
