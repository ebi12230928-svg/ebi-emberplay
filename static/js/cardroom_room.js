(function () {
  const CODE = window.CARD_ROOM_CODE;
  const IS_OWNER = window.CARD_IS_OWNER;
  const GAME_LABELS = window.CARD_GAME_LABELS || {};

  const playerCountEl = document.getElementById("player-count");
  const playerListEl = document.getElementById("player-list");
  const gameTypeDisplay = document.getElementById("game-type-display");
  const startBtn = document.getElementById("start-btn");
  const ownerGameSelect = document.getElementById("owner-game-select");
  const daifugoRules = document.getElementById("daifugo-rules");
  const eightGiriCheck = document.getElementById("rule-eight-giri");
  const revolutionCheck = document.getElementById("rule-revolution");

  let redirected = false;

  if (ownerGameSelect) {
    ownerGameSelect.addEventListener("change", saveGameSettings);
    if (daifugoRules) {
      ownerGameSelect.addEventListener("change", () => {
        daifugoRules.style.display = ownerGameSelect.value === "daifugo" ? "block" : "none";
      });
    }
  }
  if (eightGiriCheck) eightGiriCheck.addEventListener("change", saveGameSettings);
  if (revolutionCheck) revolutionCheck.addEventListener("change", saveGameSettings);

  async function saveGameSettings() {
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/set-game`, {
        game_type: ownerGameSelect.value,
        rules: {
          eight_giri: eightGiriCheck ? eightGiriCheck.checked : false,
          revolution: revolutionCheck ? revolutionCheck.checked : false,
        },
      });
    } catch (err) {
      alert(err.message);
    }
  }

  if (startBtn) {
    startBtn.addEventListener("click", async () => {
      startBtn.disabled = true;
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/start`, {});
        window.location.href = `/cards/room/${CODE}/play`;
      } catch (err) {
        alert(err.message);
        startBtn.disabled = false;
      }
    });
  }

  async function poll() {
    try {
      const res = await fetch(`/cards/room/${CODE}/poll`);
      const data = await res.json();
      if (data.error) return;

      playerCountEl.textContent = String(data.players.length);
      playerListEl.innerHTML = data.players.map((p) => `<div style="padding:6px 0; border-top:1px solid var(--panel-border);">${p.username}</div>`).join("");
      gameTypeDisplay.textContent = `ゲーム: ${GAME_LABELS[data.game_type] || data.game_type}`;

      if (data.status === "playing" && !redirected) {
        redirected = true;
        window.location.href = `/cards/room/${CODE}/play`;
      }
    } catch (err) {
      // 次回のポーリングに任せる
    }
  }

  poll();
  setInterval(poll, 2000);
})();
