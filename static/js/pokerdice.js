(function () {
  const wagerInput = document.getElementById("wager");
  const rollBtn = document.getElementById("roll-btn");
  const resultReadout = document.getElementById("result-readout");
  const cells = document.querySelectorAll("#dice-row .scratch-cell");

  rollBtn.addEventListener("click", async () => {
    rollBtn.disabled = true;
    cells.forEach((c) => { c.textContent = "❔"; c.classList.remove("revealed"); });
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/pokerdice/play", { wager: parseInt(wagerInput.value, 10) });

      data.dice.forEach((face, i) => {
        setTimeout(() => {
          cells[i].textContent = face;
          cells[i].classList.add("revealed");
        }, i * 120);
      });

      setTimeout(() => {
        const win = data.multiplier > 0;
        resultReadout.textContent = `${data.category} ・ ${win ? data.multiplier + "x" : "LOSE"}`;
        EmberPlay.flashResult(resultReadout, win, !win);
        EmberPlay.updateBalance(data.balance, win ? "win" : "loss");
        rollBtn.disabled = false;
      }, 700);
    } catch (err) {
      alert(err.message);
      rollBtn.disabled = false;
    }
  });
})();
