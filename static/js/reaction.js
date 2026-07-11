(function () {
  const box = document.getElementById("reaction-box");
  const resultReadout = document.getElementById("result-readout");

  let state = "idle"; // idle -> waiting -> ready -> done
  let readyAt = 0;
  let timer = null;

  function reset() {
    state = "idle";
    box.textContent = "タップしてスタート";
    box.style.background = "var(--bg-raised)";
  }

  box.addEventListener("click", async () => {
    if (state === "idle" || state === "done") {
      state = "waiting";
      box.textContent = "赤色の間は待って...";
      box.style.background = "rgba(214, 69, 69, 0.25)";
      resultReadout.textContent = "";

      const delay = 1200 + Math.random() * 2500;
      timer = setTimeout(() => {
        state = "ready";
        readyAt = performance.now();
        box.textContent = "今タップ!";
        box.style.background = "rgba(76, 175, 109, 0.35)";
      }, delay);
      return;
    }

    if (state === "waiting") {
      clearTimeout(timer);
      resultReadout.textContent = "早すぎます!緑色になるまで待ってください。";
      EmberPlay.flashResult(resultReadout, false, true);
      reset();
      return;
    }

    if (state === "ready") {
      const elapsed = performance.now() - readyAt;
      state = "done";
      box.textContent = `${Math.round(elapsed)}ms`;
      box.style.background = "var(--bg-raised)";

      try {
        const data = await EmberPlay.postJSON("/games/reaction/submit", { elapsed_ms: elapsed });
        resultReadout.textContent = `${Math.round(elapsed)}ms ・ +${data.reward} Embers`;
        EmberPlay.flashResult(resultReadout, true, false);
        EmberPlay.updateBalance(data.balance, "win");
      } catch (err) {
        resultReadout.textContent = err.message;
      }
    }
  });
})();
