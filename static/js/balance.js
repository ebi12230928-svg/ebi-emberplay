window.EmberPlay = (function () {
  function formatNumber(n) {
    return Math.round(n).toLocaleString("en-US");
  }

  function updateBalance(newBalance, kind) {
    const odometer = document.getElementById("balance-odometer");
    const valueEl = document.getElementById("balance-value");
    if (!valueEl) return;

    valueEl.textContent = formatNumber(newBalance);

    if (odometer) {
      odometer.classList.remove("pulse-win", "pulse-loss");
      // 強制リフローでアニメーションを再トリガー
      void odometer.offsetWidth;
      if (kind === "win") odometer.classList.add("pulse-win");
      if (kind === "loss") odometer.classList.add("pulse-loss");
    }
  }

  async function postJSON(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "エラーが発生しました。");
    }
    return data;
  }

  return { updateBalance, postJSON, formatNumber };
})();
