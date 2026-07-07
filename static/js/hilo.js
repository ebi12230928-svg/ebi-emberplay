(function () {
  const wagerInput = document.getElementById("wager");
  const startBtn = document.getElementById("start-btn");
  const higherBtn = document.getElementById("higher-btn");
  const lowerBtn = document.getElementById("lower-btn");
  const passBtn = document.getElementById("pass-btn");
  const passesLeftEl = document.getElementById("passes-left");
  const cashoutBtn = document.getElementById("cashout-btn");
  const cardReadout = document.getElementById("card-readout");
  const multiplierReadout = document.getElementById("multiplier-readout");

  function setActive(active) {
    startBtn.disabled = active;
    wagerInput.disabled = active;
    higherBtn.disabled = !active;
    lowerBtn.disabled = !active;
    passBtn.disabled = !active || passesLeftEl.textContent === "0";
    cashoutBtn.disabled = !active;
  }

  startBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/start", { wager: parseInt(wagerInput.value, 10) });
      cardReadout.textContent = data.rank_label;
      EmberPlay.flashResult(cardReadout, false, false);
      multiplierReadout.textContent = "1.0000x";
      passesLeftEl.textContent = passesLeftEl.dataset.max || passesLeftEl.textContent;
      EmberPlay.updateBalance(data.balance, "loss");
      setActive(true);
    } catch (err) {
      alert(err.message);
    }
  });

  passBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/pass", {});
      cardReadout.textContent = data.rank_label + "(パス)";
      EmberPlay.flashResult(cardReadout, false, false);
      passesLeftEl.textContent = data.passes_left;
      passBtn.disabled = data.passes_left <= 0;
    } catch (err) {
      alert(err.message);
    }
  });

  async function guess(direction) {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/guess", { direction });

      if (data.push) {
        cardReadout.textContent = data.rank_label + " (プッシュ)";
        return;
      }

      cardReadout.textContent = data.rank_label;

      if (!data.won) {
        EmberPlay.flashResult(cardReadout, false, true);
        multiplierReadout.textContent = "0.0000x";
        setActive(false);
        if (data.balance !== undefined) {
          EmberPlay.updateBalance(data.balance, "loss");
        }
        return;
      }

      EmberPlay.flashResult(cardReadout, true, false);
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";
    } catch (err) {
      alert(err.message);
    }
  }

  higherBtn.addEventListener("click", () => guess("higher"));
  lowerBtn.addEventListener("click", () => guess("lower"));

  cashoutBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/cashout", {});
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";
      EmberPlay.updateBalance(data.balance, "win");
      setActive(false);
    } catch (err) {
      alert(err.message);
    }
  });
})();
