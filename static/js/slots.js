(function () {
  const themeId = window.EMBERPLAY_SLOT_THEME;
  const wagerInput = document.getElementById("wager");
  const spinBtn = document.getElementById("spin-btn");
  const resultReadout = document.getElementById("result-readout");
  const reelEls = [document.getElementById("reel-0"), document.getElementById("reel-1"), document.getElementById("reel-2")];

  // スピン中に一瞬だけ流れる、それっぽい絵柄(実際の結果とは無関係の演出用)
  const SPIN_DECOY = ["🍒", "🍋", "🔔", "⭐", "💎", "👑", "🍀", "7️⃣"];
  let spinTimers = [];

  function startReelSpin(el) {
    el.classList.add("reel-spinning");
    const timer = setInterval(() => {
      el.textContent = SPIN_DECOY[Math.floor(Math.random() * SPIN_DECOY.length)];
    }, 60);
    return timer;
  }

  function stopReel(el, timer, label, delay) {
    return new Promise((resolve) => {
      setTimeout(() => {
        clearInterval(timer);
        el.classList.remove("reel-spinning");
        el.textContent = label;
        el.classList.add("reel-stopped");
        setTimeout(() => el.classList.remove("reel-stopped"), 260);
        resolve();
      }, delay);
    });
  }

  spinBtn.addEventListener("click", async () => {
    spinBtn.disabled = true;
    resultReadout.textContent = "";
    spinTimers = reelEls.map((el) => startReelSpin(el));

    try {
      const dataPromise = EmberPlay.postJSON(`/games/slots/${themeId}/spin`, { wager: parseInt(wagerInput.value, 10) });
      // 最低でも少しはスピン演出が見えるよう、通信と並行して待つ
      const [data] = await Promise.all([dataPromise, new Promise((r) => setTimeout(r, 350))]);

      // リールを1つずつ、時間差で止めていく(Stakeのスロットにならったテンポ)
      await stopReel(reelEls[0], spinTimers[0], data.labels[0], 0);
      await stopReel(reelEls[1], spinTimers[1], data.labels[1], 220);
      await stopReel(reelEls[2], spinTimers[2], data.labels[2], 260);

      if (data.multiplier > 0) {
        resultReadout.textContent = `WIN ・ ${data.multiplier.toFixed(2)}x`;
        EmberPlay.flashResult(resultReadout, true, false);
        if (data.multiplier >= 20 && window.EmberSound) window.EmberSound.playBigWin();
        if (data.multiplier >= 10) {
          reelEls.forEach((el) => el.classList.add("reel-jackpot"));
          setTimeout(() => reelEls.forEach((el) => el.classList.remove("reel-jackpot")), 900);
        }
      } else {
        resultReadout.textContent = "LOSE";
        EmberPlay.flashResult(resultReadout, false, true);
      }

      EmberPlay.updateBalance(data.balance, data.multiplier > 0 ? "win" : "loss");
    } catch (err) {
      spinTimers.forEach((t) => clearInterval(t));
      reelEls.forEach((el) => el.classList.remove("reel-spinning"));
      alert(err.message);
    } finally {
      spinBtn.disabled = false;
    }
  });
})();
