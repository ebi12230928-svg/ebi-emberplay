(function () {
  const wagerInput = document.getElementById("wager");
  const symbolSelect = document.getElementById("symbol-select");
  const upBtn = document.getElementById("up-btn");
  const downBtn = document.getElementById("down-btn");
  const priceDisplay = document.getElementById("price-display");
  const resultReadout = document.getElementById("result-readout");
  const countdownText = document.getElementById("countdown-text");

  async function start(pick) {
    if (!wagerInput || !symbolSelect) return;
    try {
      const payload = { wager: parseInt(wagerInput.value, 10), symbol: symbolSelect.value, pick };
      const data = await EmberPlay.postJSON("/games/market/start", payload);
      priceDisplay.textContent = `$${data.start_price}`;
      EmberPlay.updateBalance(data.balance, null);
      location.reload(); // 予想受付中の表示に切り替えるため再読み込み
    } catch (err) {
      alert(err.message);
    }
  }

  if (upBtn) upBtn.addEventListener("click", () => start("up"));
  if (downBtn) downBtn.addEventListener("click", () => start("down"));

  if (window.EMBERPLAY_MARKET_HAS_GAME) {
    const poll = async () => {
      try {
        const data = await EmberPlay.postJSON("/games/market/resolve", {});
        if (!data.resolved) {
          if (countdownText) countdownText.textContent = `結果判定まで残り${data.remaining}秒...`;
          setTimeout(poll, 2000);
          return;
        }

        priceDisplay.textContent = `$${data.end_price}`;
        const labels = { win: "WIN", lose: "LOSE", push: "PUSH(価格が変わりませんでした)" };
        resultReadout.textContent = `${labels[data.outcome]} ・ ${data.multiplier}x`;
        EmberPlay.flashResult(resultReadout, data.outcome === "win", data.outcome === "lose");
        EmberPlay.updateBalance(data.balance, data.outcome === "win" ? "win" : (data.outcome === "lose" ? "loss" : null));

        setTimeout(() => location.reload(), 2500);
      } catch (err) {
        setTimeout(poll, 3000);
      }
    };
    poll();
  }
})();
