(function () {
  const wagerInput = document.getElementById("wager");
  const fishBtn = document.getElementById("fish-btn");
  const catchDisplay = document.getElementById("catch-display");
  const resultReadout = document.getElementById("result-readout");

  fishBtn.addEventListener("click", async () => {
    fishBtn.disabled = true;
    catchDisplay.textContent = "🎣";
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/fishing/play", { wager: parseInt(wagerInput.value, 10) });
      setTimeout(() => {
        catchDisplay.textContent = data.label;
        const win = data.multiplier >= 1;
        resultReadout.textContent = `${data.label} ・ ${data.multiplier}x`;
        EmberPlay.flashResult(resultReadout, win, !win);
        EmberPlay.updateBalance(data.balance, win ? "win" : "loss");
        fishBtn.disabled = false;
      }, 500);
    } catch (err) {
      alert(err.message);
      fishBtn.disabled = false;
    }
  });
})();
