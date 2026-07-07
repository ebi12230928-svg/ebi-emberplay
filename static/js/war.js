(function () {
  const wagerInput = document.getElementById("wager");
  const startBtn = document.getElementById("start-btn");
  const warBtn = document.getElementById("war-btn");
  const surrenderBtn = document.getElementById("surrender-btn");
  const dealerCardEl = document.getElementById("dealer-card");
  const playerCardEl = document.getElementById("player-card");
  const resultReadout = document.getElementById("result-readout");

  function setTieActive(active) {
    startBtn.disabled = active;
    wagerInput.disabled = active;
    warBtn.disabled = !active;
    surrenderBtn.disabled = !active;
  }

  startBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/war/start", { wager: parseInt(wagerInput.value, 10) });
      dealerCardEl.textContent = data.dealer_rank;
      playerCardEl.textContent = data.player_rank;
      EmberPlay.updateBalance(data.balance, data.tie ? null : (data.won ? "win" : "loss"));

      if (data.tie) {
        resultReadout.textContent = "TIE";
        EmberPlay.flashResult(resultReadout, false, false);
        setTieActive(true);
      } else {
        resultReadout.textContent = data.won ? "WIN" : "LOSE";
        EmberPlay.flashResult(resultReadout, data.won, !data.won);
        setTieActive(false);
      }
    } catch (err) {
      alert(err.message);
    }
  });

  warBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/war/go-to-war", {});
      dealerCardEl.textContent = data.dealer_rank;
      playerCardEl.textContent = data.player_rank;

      const labels = { win: "WIN", lose: "LOSE", push: "PUSH" };
      resultReadout.textContent = labels[data.result] || data.result;
      EmberPlay.flashResult(resultReadout, data.result === "win", data.result === "lose");

      EmberPlay.updateBalance(data.balance, data.result === "win" ? "win" : (data.result === "lose" ? "loss" : null));
      setTieActive(false);
    } catch (err) {
      alert(err.message);
    }
  });

  surrenderBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/war/surrender", {});
      resultReadout.textContent = "SURRENDERED";
      EmberPlay.flashResult(resultReadout, false, false);
      EmberPlay.updateBalance(data.balance, null);
      setTieActive(false);
    } catch (err) {
      alert(err.message);
    }
  });
})();
