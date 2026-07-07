(function () {
  const wagerInput = document.getElementById("wager");
  const playBtn = document.getElementById("play-btn");
  const resultReadout = document.getElementById("result-readout");
  const card1El = document.getElementById("card-1");
  const card2El = document.getElementById("card-2");
  const card3El = document.getElementById("card-3");
  const card4El = document.getElementById("card-4");

  const OUTCOME_LABELS = { win: "WIN", lose: "LOSE", push: "PUSH" };

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    resultReadout.textContent = "";
    card1El.textContent = "--";
    card2El.textContent = "--";
    card3El.textContent = "--";
    card4El.textContent = "--";

    try {
      const data = await EmberPlay.postJSON("/games/reddog/play", { wager: parseInt(wagerInput.value, 10) });

      card1El.textContent = data.card1;
      card2El.textContent = data.card2;
      if (data.third_card) card3El.textContent = data.third_card;
      if (data.fourth_card) card4El.textContent = data.fourth_card;

      const label = OUTCOME_LABELS[data.outcome] || data.outcome;
      resultReadout.textContent = `${label} ・ ${data.multiplier}x`;
      EmberPlay.flashResult(resultReadout, data.outcome === "win", data.outcome === "lose");

      EmberPlay.updateBalance(data.balance, data.outcome === "win" ? "win" : (data.outcome === "lose" ? "loss" : null));
    } catch (err) {
      alert(err.message);
    } finally {
      playBtn.disabled = false;
    }
  });
})();
