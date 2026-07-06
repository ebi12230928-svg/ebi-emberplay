(function () {
  const wagerInput = document.getElementById("wager");
  const spinBtn = document.getElementById("spin-btn");
  const resultReadout = document.getElementById("result-readout");
  const reelEls = [document.getElementById("reel-0"), document.getElementById("reel-1"), document.getElementById("reel-2")];

  spinBtn.addEventListener("click", async () => {
    spinBtn.disabled = true;
    reelEls.forEach((el) => (el.textContent = "❔"));
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/slots/spin", { wager: parseInt(wagerInput.value, 10) });

      data.labels.forEach((label, i) => { reelEls[i].textContent = label; });

      if (data.multiplier > 0) {
        resultReadout.textContent = `WIN ・ ${data.multiplier.toFixed(2)}x`;
        resultReadout.className = "result-readout win";
      } else {
        resultReadout.textContent = "LOSE";
        resultReadout.className = "result-readout loss";
      }

      EmberPlay.updateBalance(data.balance, data.multiplier > 0 ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      spinBtn.disabled = false;
    }
  });
})();
