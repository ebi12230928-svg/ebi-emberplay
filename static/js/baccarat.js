(function () {
  const RANK_NAMES = { 1: "A", 11: "J", 12: "Q", 13: "K" };
  function rankLabel(r) { return RANK_NAMES[r] || String(r); }

  // バカラは役の判定にスート(絵柄)を使わないため、サーバー側はランクしか持っていない。
  // 見た目のリアリティのため、演出用としてスートをクライアント側で割り当てて表示する
  // (役の判定やフェアネスには一切影響しない、純粋に見た目だけの処理)
  const DISPLAY_SUITS = ["♠", "♥", "♦", "♣"];
  function toDisplayCard(rank, index) {
    return rankLabel(rank) + DISPLAY_SUITS[index % DISPLAY_SUITS.length];
  }

  const wagerInput = document.getElementById("wager");
  const betOnSelect = document.getElementById("bet-on");
  const playBtn = document.getElementById("play-btn");
  const bankerHandEl = document.getElementById("banker-hand");
  const bankerTotalEl = document.getElementById("banker-total");
  const playerHandEl = document.getElementById("player-hand");
  const playerTotalEl = document.getElementById("player-total");
  const resultReadout = document.getElementById("result-readout");

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        bet_on: betOnSelect.value,
      };
      const data = await EmberPlay.postJSON("/games/baccarat/play", payload);

      CardVisuals.renderHand(playerHandEl, data.player.map((r, i) => toDisplayCard(r, i)));
      playerTotalEl.textContent = "合計: " + data.player_total;
      CardVisuals.renderHand(bankerHandEl, data.banker.map((r, i) => toDisplayCard(r, i + 10)));
      bankerTotalEl.textContent = "合計: " + data.banker_total;

      const winnerLabel = { player: "Player", banker: "Banker", tie: "Tie" }[data.winner];
      let text = `${winnerLabel}の勝ち ・ `;
      text += data.multiplier > 1 ? `${data.multiplier.toFixed(2)}x` : (data.multiplier === 1 ? "PUSH" : "LOSE");
      resultReadout.textContent = text;
      EmberPlay.flashResult(resultReadout, data.multiplier > 1, data.multiplier === 0);

      EmberPlay.updateBalance(data.balance, data.multiplier > 1 ? "win" : (data.multiplier === 0 ? "loss" : null));
    } catch (err) {
      alert(err.message);
    } finally {
      playBtn.disabled = false;
    }
  });
})();
