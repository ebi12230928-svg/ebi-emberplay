(function () {
  const startBtn = document.getElementById("start-btn");
  const playArea = document.getElementById("play-area");
  const targetSentence = document.getElementById("target-sentence");
  const input = document.getElementById("typing-input");
  const resultReadout = document.getElementById("result-readout");

  let startTime = 0;
  let sentence = "";
  let submitted = false;

  startBtn.addEventListener("click", async () => {
    resultReadout.textContent = "";
    startBtn.disabled = true;
    try {
      const data = await EmberPlay.postJSON("/games/typingtest/start", {});
      sentence = data.sentence;
      targetSentence.textContent = sentence;
      input.value = "";
      input.disabled = false;
      playArea.style.display = "block";
      submitted = false;
      input.focus();
      startTime = performance.now();
    } catch (err) {
      alert(err.message);
    } finally {
      startBtn.disabled = false;
    }
  });

  input.addEventListener("input", async () => {
    if (submitted) return;
    if (input.value.length >= sentence.length) {
      submitted = true;
      input.disabled = true;
      const elapsed_ms = performance.now() - startTime;

      try {
        const data = await EmberPlay.postJSON("/games/typingtest/submit", { typed: input.value, elapsed_ms });
        if (data.reward > 0) {
          resultReadout.textContent = `正確さ${data.accuracy}% ・ ${data.chars_per_sec}文字/秒 ・ +${data.reward} Embers`;
          EmberPlay.flashResult(resultReadout, true, false);
          EmberPlay.updateBalance(data.balance, "win");
        } else {
          resultReadout.textContent = data.message || `正確さ${data.accuracy}%(報酬なし)`;
          EmberPlay.flashResult(resultReadout, false, true);
        }
      } catch (err) {
        alert(err.message);
      }
    }
  });
})();
