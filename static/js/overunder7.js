(function () {
  const wagerInput = document.getElementById("wager");
  const resultReadout = document.getElementById("result-readout");
  const dieEls = [document.getElementById("die-0"), document.getElementById("die-1")];
  const DIE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];
  const buttons = document.querySelectorAll(".pick-btn");

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      buttons.forEach((b) => (b.disabled = true));
      dieEls.forEach((el) => (el.textContent = "🎲"));
      resultReadout.textContent = "";

      try {
        const payload = { wager: parseInt(wagerInput.value, 10), pick: btn.dataset.pick };
        const data = await EmberPlay.postJSON("/games/overunder7/play", payload);

        data.dice.forEach((d, i) => { dieEls[i].textContent = DIE_FACES[d - 1]; });
        resultReadout.textContent = `合計 ${data.total} ・ ${data.won ? "WIN " + data.multiplier + "x" : "LOSE"}`;
        EmberPlay.flashResult(resultReadout, data.won, !data.won);
        EmberPlay.updateBalance(data.balance, data.won ? "win" : "loss");
      } catch (err) {
        alert(err.message);
      } finally {
        buttons.forEach((b) => (b.disabled = false));
      }
    });
  });
})();
