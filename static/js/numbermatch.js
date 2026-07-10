(function () {
  const wagerInput = document.getElementById("wager");
  const resultNumber = document.getElementById("result-number");
  const resultReadout = document.getElementById("result-readout");
  const buttons = document.querySelectorAll(".pick-btn");

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      buttons.forEach((b) => (b.disabled = true));
      resultNumber.textContent = "❔";
      resultReadout.textContent = "";

      try {
        const payload = { wager: parseInt(wagerInput.value, 10), pick: parseInt(btn.dataset.pick, 10) };
        const data = await EmberPlay.postJSON("/games/numbermatch/play", payload);

        resultNumber.textContent = data.result;
        resultReadout.textContent = data.won ? `WIN ・ ${data.multiplier}x` : "LOSE";
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
