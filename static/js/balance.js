window.EmberPlay = (function () {
  function formatNumber(n) {
    return Math.round(n).toLocaleString("en-US");
  }

  function renderOdometerDigits(valueEl, text) {
    const chars = text.split("");
    const existing = valueEl.querySelectorAll(".odo-char");

    if (existing.length !== chars.length) {
      valueEl.innerHTML = "";
      chars.forEach((c) => {
        const span = document.createElement("span");
        span.className = "odo-char";
        span.textContent = c;
        valueEl.appendChild(span);
      });
      return;
    }

    chars.forEach((c, i) => {
      const span = existing[i];
      if (span.textContent !== c) {
        span.textContent = c;
        span.classList.remove("odo-flip");
        void span.offsetWidth; // 強制リフローでアニメーションを再トリガー
        span.classList.add("odo-flip");
      }
    });
  }

  function updateBalance(newBalance, kind) {
    const odometer = document.getElementById("balance-odometer");
    const valueEl = document.getElementById("balance-value");
    if (!valueEl) return;

    renderOdometerDigits(valueEl, formatNumber(newBalance));

    if (odometer) {
      odometer.classList.remove("pulse-win", "pulse-loss");
      void odometer.offsetWidth;
      if (kind === "win") odometer.classList.add("pulse-win");
      if (kind === "loss") odometer.classList.add("pulse-loss");
    }
  }

  /** result-readout要素に、勝敗クラスを(連続で同じ結果でも)確実に再生されるよう設定する */
  function flashResult(el, isWin, isLoss) {
    if (!el) return;
    el.classList.remove("win", "loss");
    void el.offsetWidth; // 強制リフローでアニメーションを再トリガー
    if (isWin) {
      el.classList.add("win");
      if (window.EmberSound) window.EmberSound.playWin();
    } else if (isLoss) {
      el.classList.add("loss");
      if (window.EmberSound) window.EmberSound.playLose();
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

  async function toggleFavorite(btn) {
    const gameKey = btn.dataset.favKey;
    try {
      const res = await fetch("/favorites/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ game_key: gameKey }),
      });
      const data = await res.json();
      if (res.ok) {
        btn.classList.toggle("active", data.favorited);
      }
    } catch (err) {
      // 通信エラー時は見た目を変えない
    }
  }

  return { updateBalance, postJSON, formatNumber, flashResult, toggleFavorite };
})();

// ページ初期表示時にも残高をオドメーター形式で描画しておく
document.addEventListener("DOMContentLoaded", () => {
  const valueEl = document.getElementById("balance-value");
  if (valueEl && !valueEl.querySelector(".odo-char")) {
    const text = valueEl.textContent;
    valueEl.innerHTML = "";
    text.split("").forEach((c) => {
      const span = document.createElement("span");
      span.className = "odo-char";
      span.textContent = c;
      valueEl.appendChild(span);
    });
  }

  // 「動かなくなった場合はこちら」ボタン共通ハンドラ(data-cancel-url属性を持つ要素すべてに適用)
  document.querySelectorAll("[data-cancel-url]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("進行中のゲームを強制的に片付け、賭け金を返金します。よろしいですか？")) return;
      try {
        const res = await fetch(btn.dataset.cancelUrl, { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "エラーが発生しました。");
        location.reload();
      } catch (err) {
        alert(err.message);
      }
    });
  });
});
