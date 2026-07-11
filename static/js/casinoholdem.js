(function () {
  const wagerInput = document.getElementById("wager");
  const playBtn = document.getElementById("play-btn");
  const resultReadout = document.getElementById("result-readout");
  const dealerHoleEl = document.getElementById("dealer-hole");
  const communityEl = document.getElementById("community");
  const playerHoleEl = document.getElementById("player-hole");
  const dealerLabelEl = document.getElementById("dealer-hand-label");
  const playerLabelEl = document.getElementById("player-hand-label");

  const LABELS = { win: "WIN", lose: "LOSE", push: "PUSH", dealer_no_qualify: "ディーラー不成立(返金)" };

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    dealerHoleEl.textContent = "🂠 🂠";
    communityEl.textContent = "❔ ❔ ❔ ❔ ❔";
    playerHoleEl.textContent = "🂠 🂠";
    dealerLabelEl.textContent = "";
    playerLabelEl.textContent = "";
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/casinoholdem/play", { wager: parseInt(wagerInput.value, 10) });

      communityEl.textContent = data.community.join(" ");
      playerHoleEl.textContent = data.player_hole.join(" ");
      playerLabelEl.textContent = data.player_hand;

      setTimeout(() => {
        dealerHoleEl.textContent = data.dealer_hole.join(" ");
        dealerLabelEl.textContent = data.dealer_hand;

        const win = data.outcome === "win";
        const lose = data.outcome === "lose";
        resultReadout.textContent = `${LABELS[data.outcome]} ・ ${data.multiplier}x`;
        EmberPlay.flashResult(resultReadout, win, lose);
        EmberPlay.updateBalance(data.balance, win ? "win" : (lose ? "loss" : null));
        playBtn.disabled = false;
      }, 500);
    } catch (err) {
      alert(err.message);
      playBtn.disabled = false;
    }
  });
})();
