(function () {
  const wagerInput = document.getElementById("wager");
  const scratchBtn = document.getElementById("scratch-btn");
  const resultReadout = document.getElementById("result-readout");
  const cellEls = [document.getElementById("cell-0"), document.getElementById("cell-1"), document.getElementById("cell-2")];

  scratchBtn.addEventListener("click", async () => {
    scratchBtn.disabled = true;
    cellEls.forEach((el) => { el.textContent = "🎫"; el.classList.remove("revealed"); });
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/scratch/play", { wager: parseInt(wagerInput.value, 10) });

      data.labels.forEach((label, i) => {
        setTimeout(() => {
          cellEls[i].textContent = label;
          cellEls[i].classList.add("revealed");
        }, i * 200);
      });

      setTimeout(() => {
        if (data.multiplier > 0) {
          resultReadout.textContent = `WIN ・ ${data.multiplier.toFixed(2)}x`;
          resultReadout.className = "result-readout win";
        } else {
          resultReadout.textContent = "LOSE";
          resultReadout.className = "result-readout loss";
        }
        EmberPlay.updateBalance(data.balance, data.multiplier > 0 ? "win" : "loss");
      }, 700);
    } catch (err) {
      alert(err.message);
    } finally {
      setTimeout(() => { scratchBtn.disabled = false; }, 700);
    }
  });
})();
