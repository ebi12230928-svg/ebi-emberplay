(function () {
  const RED_NUMBERS = new Set([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]);

  const wagerInput = document.getElementById("wager");
  const betTypeSelect = document.getElementById("bet-type");
  const straightField = document.getElementById("straight-field");
  const straightValue = document.getElementById("straight-value");
  const spinBtn = document.getElementById("spin-btn");
  const resultReadout = document.getElementById("result-readout");

  function refreshFields() {
    straightField.style.display = betTypeSelect.value === "straight" ? "block" : "none";
  }
  betTypeSelect.addEventListener("change", refreshFields);
  refreshFields();

  spinBtn.addEventListener("click", async () => {
    spinBtn.disabled = true;
    resultReadout.textContent = "...";

    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        bet_type: betTypeSelect.value,
        value: betTypeSelect.value === "straight" ? straightValue.value : null,
      };
      const data = await EmberPlay.postJSON("/games/american-roulette/spin", payload);

      const num = parseInt(data.pocket, 10);
      const color = data.pocket === "0" || data.pocket === "00" ? "GREEN" : (RED_NUMBERS.has(num) ? "RED" : "BLACK");
      resultReadout.textContent = `${data.pocket} (${color})`;
      EmberPlay.flashResult(resultReadout, data.win, !data.win);

      EmberPlay.updateBalance(data.balance, data.win ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      spinBtn.disabled = false;
    }
  });
})();
