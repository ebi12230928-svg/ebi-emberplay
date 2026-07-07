(function () {
  const wagerInput = document.getElementById("wager");
  const andarBtn = document.getElementById("andar-btn");
  const baharBtn = document.getElementById("bahar-btn");
  const jokerEl = document.getElementById("joker-card");
  const andarCardsEl = document.getElementById("andar-cards");
  const baharCardsEl = document.getElementById("bahar-cards");
  const resultReadout = document.getElementById("result-readout");

  async function play(pick) {
    andarBtn.disabled = true;
    baharBtn.disabled = true;
    resultReadout.textContent = "";
    jokerEl.textContent = "...";
    andarCardsEl.textContent = "";
    baharCardsEl.textContent = "";

    try {
      const payload = { wager: parseInt(wagerInput.value, 10), pick };
      const data = await EmberPlay.postJSON("/games/andarbahar/play", payload);

      jokerEl.textContent = data.joker;
      andarCardsEl.textContent = data.andar_cards.join(" ");
      baharCardsEl.textContent = data.bahar_cards.join(" ");

      resultReadout.textContent = `${data.winner.toUpperCase()}の勝ち ・ ${data.won ? data.multiplier + "x" : "LOSE"}`;
      EmberPlay.flashResult(resultReadout, data.won, !data.won);

      EmberPlay.updateBalance(data.balance, data.won ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      andarBtn.disabled = false;
      baharBtn.disabled = false;
    }
  }

  andarBtn.addEventListener("click", () => play("andar"));
  baharBtn.addEventListener("click", () => play("bahar"));
})();
