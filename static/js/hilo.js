(function () {
  const wagerInput = document.getElementById("wager");
  const startBtn = document.getElementById("start-btn");
  const higherBtn = document.getElementById("higher-btn");
  const lowerBtn = document.getElementById("lower-btn");
  const passBtn = document.getElementById("pass-btn");
  const passesLeftEl = document.getElementById("passes-left");
  const cashoutBtn = document.getElementById("cashout-btn");
  const cardReadout = document.getElementById("card-readout");
  const cardDisplay = document.getElementById("card-display");
  const multiplierReadout = document.getElementById("multiplier-readout");

  // ハイローは大小の比較にスート(絵柄)を使わないため、サーバー側はランクしか持っていない。
  // 見た目のリアリティのため、演出用としてスートをクライアント側で割り当てる
  // (勝敗の判定やフェアネスには一切影響しない、純粋に見た目だけの処理)
  const DISPLAY_SUITS = ["♠", "♥", "♦", "♣"];
  let suitCounter = 0;
  function showCard(rankLabel) {
    if (!cardDisplay || !window.CardVisuals) return;
    const label = rankLabel + DISPLAY_SUITS[suitCounter % DISPLAY_SUITS.length];
    suitCounter += 1;
    cardDisplay.innerHTML = "";
    const card = CardVisuals.renderPlayingCard(label);
    card.classList.add("playing-card-deal-in");
    card.style.width = "100px";
    card.style.height = "142px";
    card.querySelectorAll(".pc-corner").forEach((el) => { el.style.fontSize = "20px"; });
    card.querySelector(".pc-center").style.fontSize = "48px";
    cardDisplay.appendChild(card);
    if (window.EmberSound) window.EmberSound.playCardFlip();
  }

  function setActive(active) {
    startBtn.disabled = active;
    wagerInput.disabled = active;
    higherBtn.disabled = !active;
    lowerBtn.disabled = !active;
    passBtn.disabled = !active || passesLeftEl.textContent === "0";
    cashoutBtn.disabled = !active;
  }

  startBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/start", { wager: parseInt(wagerInput.value, 10) });
      showCard(data.rank_label);
      cardReadout.textContent = data.rank_label;
      EmberPlay.flashResult(cardReadout, false, false);
      multiplierReadout.textContent = "1.0000x";
      passesLeftEl.textContent = passesLeftEl.dataset.max || passesLeftEl.textContent;
      EmberPlay.updateBalance(data.balance, "loss");
      setActive(true);
    } catch (err) {
      alert(err.message);
    }
  });

  passBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/pass", {});
      showCard(data.rank_label);
      cardReadout.textContent = data.rank_label + "(パス)";
      EmberPlay.flashResult(cardReadout, false, false);
      passesLeftEl.textContent = data.passes_left;
      passBtn.disabled = data.passes_left <= 0;
    } catch (err) {
      alert(err.message);
    }
  });

  async function guess(direction) {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/guess", { direction });

      if (data.push) {
        showCard(data.rank_label);
        cardReadout.textContent = data.rank_label + " (プッシュ)";
        return;
      }

      showCard(data.rank_label);
      cardReadout.textContent = data.rank_label;

      if (!data.won) {
        EmberPlay.flashResult(cardReadout, false, true);
        multiplierReadout.textContent = "0.0000x";
        setActive(false);
        if (data.balance !== undefined) {
          EmberPlay.updateBalance(data.balance, "loss");
        }
        return;
      }

      EmberPlay.flashResult(cardReadout, true, false);
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";
    } catch (err) {
      alert(err.message);
    }
  }

  higherBtn.addEventListener("click", () => guess("higher"));
  lowerBtn.addEventListener("click", () => guess("lower"));

  cashoutBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/hilo/cashout", {});
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";
      EmberPlay.updateBalance(data.balance, "win");
      setActive(false);
    } catch (err) {
      alert(err.message);
    }
  });
})();
