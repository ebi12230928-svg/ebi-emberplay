(function () {
  const balanceEl = document.getElementById("demo-balance");
  const resetBtn = document.getElementById("reset-btn");

  function updateBalance(newBalance) {
    balanceEl.textContent = Math.round(newBalance).toLocaleString("en-US");
  }

  async function post(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "エラーが発生しました。");
    return data;
  }

  // タブ切り替え
  document.querySelectorAll(".demo-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".demo-tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".demo-panel").forEach((p) => (p.style.display = "none"));
      tab.classList.add("active");
      document.getElementById(`panel-${tab.dataset.tab}`).style.display = "block";
    });
  });

  resetBtn.addEventListener("click", async () => {
    const data = await post("/demo/reset", {});
    updateBalance(data.balance);
  });

  // ── Dice ──
  const diceTarget = document.getElementById("dice-target");
  const diceTargetVal = document.getElementById("dice-target-val");
  diceTarget.addEventListener("input", () => (diceTargetVal.textContent = diceTarget.value));

  async function playDice(direction) {
    try {
      const data = await post("/demo/dice", {
        wager: parseInt(document.getElementById("dice-wager").value, 10),
        target: parseInt(diceTarget.value, 10),
        direction,
      });
      document.getElementById("dice-result").textContent = data.roll.toFixed(2);
      const readout = document.getElementById("dice-readout");
      readout.textContent = data.win ? `WIN ・ ${data.multiplier}x` : "LOSE";
      EmberPlay.flashResult(readout, data.win, !data.win);
      updateBalance(data.balance);
    } catch (err) {
      alert(err.message);
    }
  }
  document.getElementById("dice-under-btn").addEventListener("click", () => playDice("under"));
  document.getElementById("dice-over-btn").addEventListener("click", () => playDice("over"));

  // ── Limbo ──
  document.getElementById("limbo-btn").addEventListener("click", async () => {
    try {
      const data = await post("/demo/limbo", {
        wager: parseInt(document.getElementById("limbo-wager").value, 10),
        target: parseFloat(document.getElementById("limbo-target").value),
      });
      document.getElementById("limbo-result").textContent = data.result.toFixed(2) + "x";
      const readout = document.getElementById("limbo-readout");
      readout.textContent = data.win ? "WIN" : "LOSE";
      EmberPlay.flashResult(readout, data.win, !data.win);
      updateBalance(data.balance);
    } catch (err) {
      alert(err.message);
    }
  });

  // ── Coin Flip ──
  async function playCoinflip(side) {
    try {
      const data = await post("/demo/coinflip", {
        wager: parseInt(document.getElementById("coinflip-wager").value, 10),
        side,
      });
      document.getElementById("coinflip-result").textContent = data.result === "heads" ? "表" : "裏";
      const readout = document.getElementById("coinflip-readout");
      readout.textContent = data.win ? `WIN ・ ${data.multiplier}x` : "LOSE";
      EmberPlay.flashResult(readout, data.win, !data.win);
      updateBalance(data.balance);
    } catch (err) {
      alert(err.message);
    }
  }
  document.getElementById("heads-btn").addEventListener("click", () => playCoinflip("heads"));
  document.getElementById("tails-btn").addEventListener("click", () => playCoinflip("tails"));

  // ── Slots ──
  document.getElementById("slots-btn").addEventListener("click", async () => {
    try {
      const data = await post("/demo/slots", {
        wager: parseInt(document.getElementById("slots-wager").value, 10),
      });
      data.labels.forEach((label, i) => {
        document.getElementById(`slots-reel-${i}`).textContent = label;
      });
      const readout = document.getElementById("slots-readout");
      readout.textContent = data.multiplier > 0 ? `WIN ・ ${data.multiplier}x` : "LOSE";
      EmberPlay.flashResult(readout, data.multiplier > 0, data.multiplier <= 0);
      updateBalance(data.balance);
    } catch (err) {
      alert(err.message);
    }
  });
})();
