(function () {
  const wagerInput = document.getElementById("wager");
  const startBtn = document.getElementById("start-btn");
  const cashoutBtn = document.getElementById("cashout-btn");
  const multiplierReadout = document.getElementById("multiplier-readout");

  let startedAtMs = null;
  let growthRate = 0;
  let animFrame = null;
  let active = false;

  function setActive(value) {
    active = value;
    startBtn.disabled = value;
    wagerInput.disabled = value;
    cashoutBtn.disabled = !value;
  }

  function tick() {
    if (!active) return;
    const elapsed = (Date.now() - startedAtMs) / 1000;
    const mult = Math.exp(growthRate * Math.max(elapsed, 0));
    multiplierReadout.textContent = mult.toFixed(2) + "x";
    animFrame = requestAnimationFrame(tick);
  }

  startBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/crash/start", { wager: parseInt(wagerInput.value, 10) });
      startedAtMs = new Date(data.started_at).getTime();
      growthRate = data.growth_rate;
      multiplierReadout.style.color = "var(--text)";
      EmberPlay.updateBalance(data.balance, "loss");
      setActive(true);
      tick();
    } catch (err) {
      alert(err.message);
    }
  });

  cashoutBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/crash/cashout", {});
      cancelAnimationFrame(animFrame);
      setActive(false);

      if (data.busted) {
        multiplierReadout.textContent = data.crash_point.toFixed(2) + "x";
        multiplierReadout.style.color = "var(--loss)";
        EmberPlay.updateBalance(data.balance, "loss");
      } else {
        multiplierReadout.textContent = data.multiplier.toFixed(2) + "x";
        multiplierReadout.style.color = "var(--win)";
        EmberPlay.updateBalance(data.balance, "win");
      }
    } catch (err) {
      alert(err.message);
    }
  });
})();
