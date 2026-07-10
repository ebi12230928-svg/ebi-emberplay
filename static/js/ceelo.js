(function () {
  const wagerInput = document.getElementById("wager");
  const rollBtn = document.getElementById("roll-btn");
  const resultReadout = document.getElementById("result-readout");
  const dieEls = [document.getElementById("die-0"), document.getElementById("die-1"), document.getElementById("die-2")];
  const DIE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];

  rollBtn.addEventListener("click", async () => {
    rollBtn.disabled = true;
    dieEls.forEach((el) => (el.textContent = "🎲"));
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/ceelo/play", { wager: parseInt(wagerInput.value, 10) });
      data.dice.forEach((d, i) => { dieEls[i].textContent = DIE_FACES[d - 1]; });
      resultReadout.textContent = data.won ? `WIN ・ ${data.multiplier}x` : "LOSE";
      EmberPlay.flashResult(resultReadout, data.won, !data.won);
      EmberPlay.updateBalance(data.balance, data.won ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      rollBtn.disabled = false;
    }
  });
})();
