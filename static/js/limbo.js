(function () {
  const HOUSE_EDGE = 0.04;

  const wagerInput = document.getElementById("wager");
  const targetInput = document.getElementById("target");
  const oddsReadout = document.getElementById("odds-readout");
  const playBtn = document.getElementById("play-btn");
  const multiplierReadout = document.getElementById("multiplier-readout");

  function refreshOdds() {
    const target = parseFloat(targetInput.value) || 1.01;
    const winChance = ((1 - HOUSE_EDGE) / target) * 100;
    oddsReadout.textContent = `${winChance.toFixed(2)}%`;
  }

  targetInput.addEventListener("input", refreshOdds);
  refreshOdds();

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    multiplierReadout.className = "limbo-multiplier";
    multiplierReadout.textContent = "・・・";

    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        target: parseFloat(targetInput.value),
      };
      const data = await EmberPlay.postJSON("/games/limbo/play", payload);

      setTimeout(() => {
        multiplierReadout.textContent = data.result.toFixed(2) + "x";
        multiplierReadout.style.color = data.win ? "var(--win)" : "var(--loss)";
        EmberPlay.updateBalance(data.balance, data.win ? "win" : "loss");
      }, 400);
    } catch (err) {
      alert(err.message);
    } finally {
      setTimeout(() => { playBtn.disabled = false; }, 400);
    }
  });
})();
