(function () {
  const wagerInput = document.getElementById("wager");
  const betTypeSelect = document.getElementById("bet-type");
  const valueField = document.getElementById("value-field");
  const valueSelect = document.getElementById("value-select");
  const totalField = document.getElementById("total-field");
  const totalSelect = document.getElementById("total-select");
  const rollBtn = document.getElementById("roll-btn");
  const resultReadout = document.getElementById("result-readout");
  const dieEls = [document.getElementById("die-0"), document.getElementById("die-1"), document.getElementById("die-2")];

  const NEEDS_NUMBER = new Set(["specific_triple", "double_specific", "single_number"]);
  const DIE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];

  function refreshFields() {
    const t = betTypeSelect.value;
    valueField.style.display = NEEDS_NUMBER.has(t) ? "block" : "none";
    totalField.style.display = t === "total" ? "block" : "none";
  }
  betTypeSelect.addEventListener("change", refreshFields);
  refreshFields();

  rollBtn.addEventListener("click", async () => {
    rollBtn.disabled = true;
    resultReadout.textContent = "";
    dieEls.forEach((el) => (el.textContent = "🎲"));

    try {
      const betType = betTypeSelect.value;
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        bet_type: betType,
        value: betType === "total" ? parseInt(totalSelect.value, 10) : (NEEDS_NUMBER.has(betType) ? parseInt(valueSelect.value, 10) : null),
      };
      const data = await EmberPlay.postJSON("/games/sicbo/play", payload);

      data.dice.forEach((d, i) => { dieEls[i].textContent = DIE_FACES[d - 1]; });

      if (data.multiplier > 0) {
        resultReadout.textContent = `合計 ${data.total} ・ WIN ・ ${data.multiplier}x`;
        EmberPlay.flashResult(resultReadout, true, false);
      } else {
        resultReadout.textContent = `合計 ${data.total} ・ LOSE`;
        EmberPlay.flashResult(resultReadout, false, true);
      }

      EmberPlay.updateBalance(data.balance, data.multiplier > 0 ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      rollBtn.disabled = false;
    }
  });
})();
