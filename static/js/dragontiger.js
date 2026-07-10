(function () {
  const wagerInput = document.getElementById("wager");
  const dragonCard = document.getElementById("dragon-card");
  const tigerCard = document.getElementById("tiger-card");
  const resultReadout = document.getElementById("result-readout");
  const buttons = document.querySelectorAll(".pick-btn");

  const LABELS = { win: "WIN", lose: "LOSE", tie: "TIE(半額返金)" };

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      buttons.forEach((b) => (b.disabled = true));
      dragonCard.textContent = "--";
      tigerCard.textContent = "--";
      resultReadout.textContent = "";

      try {
        const payload = { wager: parseInt(wagerInput.value, 10), pick: btn.dataset.pick };
        const data = await EmberPlay.postJSON("/games/dragontiger/play", payload);

        dragonCard.textContent = data.dragon;
        tigerCard.textContent = data.tiger;
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
