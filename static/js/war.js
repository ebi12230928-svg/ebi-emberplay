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
        resultReadout.className = "result-readout";
        setTieActive(true);
      } else {
        resultReadout.textContent = data.won ? "WIN" : "LOSE";
        resultReadout.className = "result-readout " + (data.won ? "win" : "loss");
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
      resultReadout.className = "result-readout " + (data.result === "win" ? "win" : (data.result === "lose" ? "loss" : ""));

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
      resultReadout.className = "result-readout";
      EmberPlay.updateBalance(data.balance, null);
      setTieActive(false);
    } catch (err) {
      alert(err.message);
    }
  });
})();
