(function () {
  const anteInput = document.getElementById("ante");
  const dealBtn = document.getElementById("deal-btn");
  const playBtn = document.getElementById("play-btn");
  const foldBtn = document.getElementById("fold-btn");
  const dealerHandEl = document.getElementById("dealer-hand");
  const dealerHandNameEl = document.getElementById("dealer-hand-name");
  const playerHandEl = document.getElementById("player-hand");
  const playerHandNameEl = document.getElementById("player-hand-name");
  const resultReadout = document.getElementById("result-readout");
  const payoutDetailEl = document.getElementById("payout-detail");

  const RESULT_LABELS = {
    win: "WIN", lose: "LOSE", push: "PUSH",
    dealer_not_qualified: "ディーラー未クオリファイ(Ante払い戻し)", folded: "FOLD",
  };

  function setActive(dealing) {
    dealBtn.disabled = dealing;
    anteInput.disabled = dealing;
    playBtn.disabled = !dealing;
    foldBtn.disabled = !dealing;
  }

  dealBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/threecardpoker/deal", { ante: parseInt(anteInput.value, 10) });
      playerHandEl.textContent = data.player_hand.join(" ");
      playerHandNameEl.textContent = data.player_hand_name;
      dealerHandEl.textContent = "??? ??? ???";
      dealerHandNameEl.textContent = "";
      resultReadout.textContent = "";
      payoutDetailEl.textContent = "";
      EmberPlay.updateBalance(data.balance, "loss");
      setActive(true);
    } catch (err) {
      alert(err.message);
    }
  });

  function renderResult(data) {
    dealerHandEl.textContent = data.dealer_hand.join(" ");
    dealerHandNameEl.textContent = data.dealer_hand_name;

    const label = RESULT_LABELS[data.result] || data.result;
    resultReadout.textContent = label;
    const isWin = data.result === "win" || data.result === "dealer_not_qualified";
    EmberPlay.flashResult(resultReadout, isWin, data.result === "lose");

    payoutDetailEl.textContent =
      `Ante配当: ${data.ante_payout} ・ Play配当: ${data.play_payout} ・ Anteボーナス: ${data.ante_bonus_payout} ・ 合計: ${data.total_payout}`;

    EmberPlay.updateBalance(data.balance, data.total_payout > 0 ? "win" : "loss");
    setActive(false);
  }

  playBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/threecardpoker/play", {});
      renderResult(data);
    } catch (err) {
      alert(err.message);
    }
  });

  foldBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/threecardpoker/fold", {});
      renderResult(data);
    } catch (err) {
      alert(err.message);
    }
  });
})();
