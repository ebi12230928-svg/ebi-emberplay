(function () {
  const wagerInput = document.getElementById("wager");
  const playBtn = document.getElementById("play-btn");
  const resultReadout = document.getElementById("result-readout");
  const drawnEls = document.querySelectorAll("#drawn-numbers div");
  const digitSelects = [document.getElementById("digit-0"), document.getElementById("digit-1"), document.getElementById("digit-2")];

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    drawnEls.forEach((el) => (el.textContent = "❔"));
    resultReadout.textContent = "";

    try {
      const pick = digitSelects.map((s) => parseInt(s.value, 10));
      const data = await EmberPlay.postJSON("/games/lottery/play", { wager: parseInt(wagerInput.value, 10), pick });

      data.drawn.forEach((d, i) => { drawnEls[i].textContent = d; });
      const win = data.multiplier > 0;
      resultReadout.textContent = `${data.matches}桁一致 ・ ${win ? data.multiplier + "x" : "LOSE"}`;
      EmberPlay.flashResult(resultReadout, win, !win);
      EmberPlay.updateBalance(data.balance, win ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      playBtn.disabled = false;
    }
  });
})();
