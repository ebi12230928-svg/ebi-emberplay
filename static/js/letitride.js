(function () {
  const wagerInput = document.getElementById("wager");
  const playBtn = document.getElementById("play-btn");
  const cardsEl = document.getElementById("cards");
  const handLabelEl = document.getElementById("hand-label");
  const resultReadout = document.getElementById("result-readout");

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    cardsEl.textContent = "🂠 🂠 🂠 🂠 🂠";
    handLabelEl.textContent = "";
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/letitride/play", { wager: parseInt(wagerInput.value, 10) });

      cardsEl.textContent = data.cards.join(" ");
      handLabelEl.textContent = data.hand;

      const win = data.multiplier > 0;
      resultReadout.textContent = win ? `WIN ・ ${data.multiplier}x` : "LOSE";
      EmberPlay.flashResult(resultReadout, win, !win);
      EmberPlay.updateBalance(data.balance, win ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      playBtn.disabled = false;
    }
  });
})();
