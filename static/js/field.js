(function () {
  const wagerInput = document.getElementById("wager");
  const rollBtn = document.getElementById("roll-btn");
  const resultReadout = document.getElementById("result-readout");
  const dieEls = [document.getElementById("die-0"), document.getElementById("die-1")];
  const DIE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];

  rollBtn.addEventListener("click", async () => {
    rollBtn.disabled = true;
    dieEls.forEach((el) => (el.textContent = "🎲"));
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/field/play", { wager: parseInt(wagerInput.value, 10) });
      data.dice.forEach((d, i) => { dieEls[i].textContent = DIE_FACES[d - 1]; });
      const win = data.multiplier > 0;
      resultReadout.textContent = `合計 ${data.total} ・ ${win ? "WIN " + data.multiplier + "x" : "LOSE"}`;
      EmberPlay.flashResult(resultReadout, win, !win);
      EmberPlay.updateBalance(data.balance, win ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      rollBtn.disabled = false;
    }
  });
})();
