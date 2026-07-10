(function () {
  const wagerInput = document.getElementById("wager");
  const horseSelect = document.getElementById("horse-select");
  const raceBtn = document.getElementById("race-btn");
  const resultReadout = document.getElementById("result-readout");

  function resetTrack() {
    document.querySelectorAll('[id^="horse-"]').forEach((el) => {
      el.style.transition = "none";
      el.style.left = "0%";
    });
  }

  raceBtn.addEventListener("click", async () => {
    raceBtn.disabled = true;
    resultReadout.textContent = "";
    resetTrack();

    try {
      const payload = { wager: parseInt(wagerInput.value, 10), pick: horseSelect.value };
      const data = await EmberPlay.postJSON("/games/horserace/play", payload);

      // 少し待ってからアニメーション開始(resetの反映を確実にするため)
      await new Promise((r) => setTimeout(r, 50));

      const finishPositions = {}; // key -> ゴール位置(%)。1着が一番遠くまで進む
      const n = data.finish_order.length;
      data.finish_order.forEach((h, i) => {
        finishPositions[h.key] = 88 - i * (70 / n); // 1着=88%, 以降少しずつ手前
      });

      Object.keys(finishPositions).forEach((key) => {
        const el = document.getElementById(`horse-${key}`);
        if (!el) return;
        el.style.transition = "left 2.2s cubic-bezier(0.2, 0.6, 0.3, 1)";
        el.style.left = finishPositions[key] + "%";
      });

      setTimeout(() => {
        const winnerName = data.finish_order[0].name;
        if (data.won) {
          resultReadout.textContent = `🏆 ${winnerName} が優勝! WIN ・ ${data.multiplier}x`;
          EmberPlay.flashResult(resultReadout, true, false);
        } else {
          resultReadout.textContent = `🏆 ${winnerName} が優勝 ・ LOSE`;
          EmberPlay.flashResult(resultReadout, false, true);
        }
        EmberPlay.updateBalance(data.balance, data.won ? "win" : "loss");
        raceBtn.disabled = false;
      }, 2300);
    } catch (err) {
      alert(err.message);
      raceBtn.disabled = false;
    }
  });
})();
