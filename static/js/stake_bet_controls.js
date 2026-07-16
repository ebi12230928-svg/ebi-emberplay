/*
  Stakeでおなじみの「½」「2×」ボタンと、金額チップのクリックでベット額を調整する共通スクリプト。
  各ゲームのページで #wager 入力欄と一緒に読み込むだけで動作する。
*/
(function () {
  const wagerInput = document.getElementById("wager") || document.getElementById("ante");
  if (!wagerInput) return;

  const halfBtn = document.getElementById("wager-half");
  const doubleBtn = document.getElementById("wager-double");

  function currentWager() {
    const v = parseInt(wagerInput.value, 10);
    return Number.isFinite(v) && v > 0 ? v : 0;
  }

  function setWager(v) {
    wagerInput.value = String(Math.max(1, Math.round(v)));
    wagerInput.dispatchEvent(new Event("change"));
  }

  if (halfBtn) {
    halfBtn.addEventListener("click", () => {
      const v = currentWager();
      if (v > 0) setWager(Math.max(1, Math.floor(v / 2)));
    });
  }
  if (doubleBtn) {
    doubleBtn.addEventListener("click", () => {
      const v = currentWager();
      if (v > 0) setWager(v * 2);
    });
  }

  document.querySelectorAll(".wager-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      setWager(parseInt(btn.dataset.amount, 10));
    });
  });
})();
