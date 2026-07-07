(function () {
  const wagerInput = document.getElementById("wager");
  const sideSelect = document.getElementById("side");
  const flipBtn = document.getElementById("flip-btn");
  const resultReadout = document.getElementById("result-readout");

  flipBtn.addEventListener("click", async () => {
    flipBtn.disabled = true;
    resultReadout.textContent = "...";
    try {
      const payload = { wager: parseInt(wagerInput.value, 10), side: sideSelect.value };
      const data = await EmberPlay.postJSON("/games/coinflip/play", payload);

      resultReadout.textContent = data.result.toUpperCase();
      EmberPlay.flashResult(resultReadout, data.win, !data.win);
      EmberPlay.updateBalance(data.balance, data.win ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      flipBtn.disabled = false;
    }
  });
})();
