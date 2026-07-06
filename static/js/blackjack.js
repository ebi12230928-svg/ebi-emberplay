(function () {
  const wagerInput = document.getElementById("wager");
  const startBtn = document.getElementById("start-btn");
  const hitBtn = document.getElementById("hit-btn");
  const standBtn = document.getElementById("stand-btn");
  const doubleBtn = document.getElementById("double-btn");
  const dealerHandEl = document.getElementById("dealer-hand");
  const dealerTotalEl = document.getElementById("dealer-total");
  const playerHandEl = document.getElementById("player-hand");
  const playerTotalEl = document.getElementById("player-total");
  const resultReadout = document.getElementById("result-readout");

  function setActive(active, canDouble) {
    startBtn.disabled = active;
    wagerInput.disabled = active;
    hitBtn.disabled = !active;
    standBtn.disabled = !active;
    doubleBtn.disabled = !active || !canDouble;
  }

  function renderInProgress(data) {
    playerHandEl.textContent = data.player.join(" ");
    playerTotalEl.textContent = "合計: " + data.player_total;
    if (data.dealer_upcard) {
      dealerHandEl.textContent = data.dealer_upcard + " ??";
      dealerTotalEl.textContent = "";
    }
    resultReadout.textContent = "";
    resultReadout.className = "result-readout";
  }

  function renderFinished(data) {
    playerHandEl.textContent = data.player.join(" ");
    playerTotalEl.textContent = "合計: " + data.player_total;
    dealerHandEl.textContent = data.dealer.join(" ");
    dealerTotalEl.textContent = "合計: " + data.dealer_total;

    let text;
    if (data.multiplier > 1) text = `WIN ・ ${data.multiplier.toFixed(2)}x`;
    else if (data.multiplier === 1) text = "PUSH";
    else text = "LOSE";

    resultReadout.textContent = text;
    resultReadout.className = "result-readout " + (data.multiplier > 1 ? "win" : (data.multiplier === 0 ? "loss" : ""));

    EmberPlay.updateBalance(data.balance, data.multiplier > 1 ? "win" : (data.multiplier === 0 ? "loss" : null));
    setActive(false, false);
  }

  startBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/blackjack/start", { wager: parseInt(wagerInput.value, 10) });
      EmberPlay.updateBalance(data.balance, "loss");

      if (data.finished) {
        renderFinished(data);
      } else {
        renderInProgress(data);
        setActive(true, data.can_double);
      }
    } catch (err) {
      alert(err.message);
    }
  });

  hitBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/blackjack/hit", {});
      if (data.finished) {
        renderFinished(data);
      } else {
        renderInProgress(data);
        setActive(true, false);
      }
    } catch (err) {
      alert(err.message);
    }
  });

  standBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/blackjack/stand", {});
      renderFinished(data);
    } catch (err) {
      alert(err.message);
    }
  });

  doubleBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/blackjack/double", {});
      renderFinished(data);
    } catch (err) {
      alert(err.message);
    }
  });
})();
