(function () {
  const wagerInput = document.getElementById("wager");
  const playerTotalEl = document.getElementById("player-total");
  const bankerTotalEl = document.getElementById("banker-total");
  const resultReadout = document.getElementById("result-readout");
  const buttons = document.querySelectorAll(".pick-btn");

  const LABELS = { win: "WIN", lose: "LOSE", tie_push: "TIE(返金)" };

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      buttons.forEach((b) => (b.disabled = true));
      playerTotalEl.textContent = "-";
      bankerTotalEl.textContent = "-";
      resultReadout.textContent = "";

      try {
        const payload = { wager: parseInt(wagerInput.value, 10), bet_on: btn.dataset.pick };
        const data = await EmberPlay.postJSON("/games/dragonbonus/play", payload);

        playerTotalEl.textContent = data.player_total;
        bankerTotalEl.textContent = data.banker_total;
        resultReadout.textContent = `${LABELS[data.outcome]} ・ ${data.multiplier}x`;
        EmberPlay.flashResult(resultReadout, data.outcome === "win", data.outcome === "lose");
        EmberPlay.updateBalance(data.balance, data.outcome === "win" ? "win" : (data.outcome === "lose" ? "loss" : null));
      } catch (err) {
        alert(err.message);
      } finally {
        buttons.forEach((b) => (b.disabled = false));
      }
    });
  });
})();
