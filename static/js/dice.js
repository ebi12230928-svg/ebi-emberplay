(function () {
  const HOUSE_EDGE = 0.01;

  const wagerInput = document.getElementById("wager");
  const directionSelect = document.getElementById("direction");
  const targetInput = document.getElementById("target");
  const targetLabel = document.getElementById("target-label");
  const oddsReadout = document.getElementById("odds-readout");
  const rollBtn = document.getElementById("roll-btn");
  const track = document.getElementById("dice-track");
  const marker = document.getElementById("dice-marker");
  const resultReadout = document.getElementById("result-readout");

  function computeOdds() {
    const target = parseFloat(targetInput.value);
    const direction = directionSelect.value;
    let winChance, multiplier;

    if (direction === "under") {
      winChance = target;
      multiplier = (100 / target) * (1 - HOUSE_EDGE);
      track.style.setProperty("--split", target + "%");
    } else {
      winChance = 100 - target;
      multiplier = (100 / (100 - target)) * (1 - HOUSE_EDGE);
      track.style.setProperty("--split", (100 - target) + "%");
    }
    return { winChance, multiplier };
  }

  function refreshUI() {
    const target = parseFloat(targetInput.value);
    targetLabel.textContent = target.toFixed(2);
    const { winChance, multiplier } = computeOdds();
    oddsReadout.textContent = `${winChance.toFixed(2)}% ・ ${multiplier.toFixed(4)}x`;
  }

  targetInput.addEventListener("input", refreshUI);
  directionSelect.addEventListener("change", refreshUI);
  refreshUI();

  rollBtn.addEventListener("click", async () => {
    rollBtn.disabled = true;
    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        target: parseFloat(targetInput.value),
        direction: directionSelect.value,
      };
      const data = await EmberPlay.postJSON("/games/dice/roll", payload);

      marker.style.left = data.roll + "%";
      resultReadout.textContent = data.roll.toFixed(2);
      EmberPlay.flashResult(resultReadout, data.win, !data.win);

      EmberPlay.updateBalance(data.balance, data.win ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      rollBtn.disabled = false;
    }
  });
})();
