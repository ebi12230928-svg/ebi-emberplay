(function () {
  const wagerInput = document.getElementById("wager");
  const betTypeSelect = document.getElementById("bet-type");
  const startBtn = document.getElementById("start-btn");
  const rollBtn = document.getElementById("roll-btn");
  const pointReadout = document.getElementById("point-readout");
  const resultReadout = document.getElementById("result-readout");
  const dieEls = [document.getElementById("die-0"), document.getElementById("die-1")];
  const DIE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"];

  function showDice(dice) {
    dice.forEach((d, i) => { dieEls[i].textContent = DIE_FACES[d - 1]; });
  }

  function setActive(inProgress) {
    startBtn.disabled = inProgress;
    wagerInput.disabled = inProgress;
    betTypeSelect.disabled = inProgress;
    rollBtn.disabled = !inProgress;
  }

  function finish(data) {
    showDice(data.dice);
    setActive(false);
    if (data.push) {
      resultReadout.textContent = "PUSH(バー12)";
      EmberPlay.flashResult(resultReadout, false, false);
      EmberPlay.updateBalance(data.balance, null);
    } else {
      resultReadout.textContent = data.won ? "WIN" : "LOSE";
      EmberPlay.flashResult(resultReadout, data.won, !data.won);
      EmberPlay.updateBalance(data.balance, data.won ? "win" : "loss");
    }
    pointReadout.textContent = "";
  }

  startBtn.addEventListener("click", async () => {
    resultReadout.textContent = "";
    pointReadout.textContent = "";
    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        bet_type: betTypeSelect.value,
      };
      const data = await EmberPlay.postJSON("/games/craps/start", payload);
      showDice(data.dice);

      if (data.resolved) {
        finish(data);
      } else {
        pointReadout.textContent = `ポイント: ${data.point}(7またはポイントが出るまでロール)`;
        EmberPlay.updateBalance(data.balance, null);
        setActive(true);
      }
    } catch (err) {
      alert(err.message);
    }
  });

  rollBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/craps/roll", {});
      showDice(data.dice);
      if (data.resolved) {
        finish(data);
      } else {
        pointReadout.textContent = `ポイント: ${data.point}(7またはポイントが出るまでロール)`;
      }
    } catch (err) {
      alert(err.message);
    }
  });
})();
