(function () {
  const wagerInput = document.getElementById("wager");
  const playerChoiceEl = document.getElementById("player-choice");
  const houseChoiceEl = document.getElementById("house-choice");
  const resultReadout = document.getElementById("result-readout");
  const EMOJI = { rock: "✊", paper: "✋", scissors: "✌️" };
  const buttons = {
    rock: document.getElementById("rock-btn"),
    paper: document.getElementById("paper-btn"),
    scissors: document.getElementById("scissors-btn"),
  };

  async function play(pick) {
    Object.values(buttons).forEach((b) => (b.disabled = true));
    playerChoiceEl.textContent = EMOJI[pick];
    houseChoiceEl.textContent = "❔";
    resultReadout.textContent = "";

    try {
      const payload = { wager: parseInt(wagerInput.value, 10), pick };
      const data = await EmberPlay.postJSON("/games/rps/play", payload);

      houseChoiceEl.textContent = EMOJI[data.house_pick];

      const labels = { win: "WIN", lose: "LOSE", push: "PUSH" };
      resultReadout.textContent = `${labels[data.outcome]} ・ ${data.multiplier}x`;
      EmberPlay.flashResult(resultReadout, data.outcome === "win", data.outcome === "lose");

      EmberPlay.updateBalance(data.balance, data.outcome === "win" ? "win" : (data.outcome === "lose" ? "loss" : null));
    } catch (err) {
      alert(err.message);
    } finally {
      Object.values(buttons).forEach((b) => (b.disabled = false));
    }
  }

  buttons.rock.addEventListener("click", () => play("rock"));
  buttons.paper.addEventListener("click", () => play("paper"));
  buttons.scissors.addEventListener("click", () => play("scissors"));
})();
