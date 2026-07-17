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
  const jokerCheck = document.getElementById("rule-joker");
  const tenSuteCheck = document.getElementById("rule-ten-sute");
  const howToPlayBtn = document.getElementById("how-to-play-btn");
  const howToPlayModal = document.getElementById("how-to-play-modal");
  const howToPlayTitle = document.getElementById("how-to-play-title");
  const howToPlayText = document.getElementById("how-to-play-text");
  const howToPlayClose = document.getElementById("how-to-play-close");
  const chatLog = document.getElementById("room-chat-log");
  const chatInput = document.getElementById("room-chat-input");
  const chatSendBtn = document.getElementById("room-chat-send");

  let redirected = false;
  let currentGameType = null;

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
  if (jokerCheck) jokerCheck.addEventListener("change", saveGameSettings);
  if (tenSuteCheck) tenSuteCheck.addEventListener("change", saveGameSettings);

  async function saveGameSettings() {
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/set-game`, {
        game_type: ownerGameSelect.value,
        rules: {
          eight_giri: eightGiriCheck ? eightGiriCheck.checked : false,
          revolution: revolutionCheck ? revolutionCheck.checked : false,
          joker: jokerCheck ? jokerCheck.checked : false,
          ten_sute: tenSuteCheck ? tenSuteCheck.checked : false,
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

  document.querySelectorAll(".bot-add-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/add-bot`, { difficulty: btn.dataset.difficulty });
        poll();
      } catch (err) {
        alert(err.message);
      }
    });
  });

  async function removePlayer(userId) {
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/remove-player`, { user_id: userId });
      poll();
    } catch (err) {
      alert(err.message);
    }
  }

  if (howToPlayBtn) {
    howToPlayBtn.addEventListener("click", async () => {
      if (!currentGameType) return;
      try {
        const res = await fetch(`/cards/how-to-play/${currentGameType}`);
        const data = await res.json();
        howToPlayTitle.textContent = `📖 ${data.label} の遊び方`;
        howToPlayText.textContent = data.text;
        howToPlayModal.style.display = "flex";
      } catch (err) { /* noop */ }
    });
  }
  if (howToPlayClose) howToPlayClose.addEventListener("click", () => { howToPlayModal.style.display = "none"; });

  if (chatSendBtn) {
    chatSendBtn.addEventListener("click", sendChat);
    chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
  }
  async function sendChat() {
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = "";
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/chat/send`, { message: text });
      pollChat();
    } catch (err) { /* noop */ }
  }
  const CHAT_NAME_COLORS = ["#ff6fa8", "#3fa9dc", "#7a5fd6", "#e08a2e", "#2ba86a", "#d6455f"];
  function chatColorFor(username) {
    let hash = 0;
    for (let i = 0; i < username.length; i++) hash = (hash * 31 + username.charCodeAt(i)) >>> 0;
    return CHAT_NAME_COLORS[hash % CHAT_NAME_COLORS.length];
  }

  async function pollChat() {
    try {
      const res = await fetch(`/cards/room/${CODE}/chat`);
      const data = await res.json();
      if (!chatLog || !data.messages) return;
      chatLog.innerHTML = data.messages.map((m) =>
        `<div style="margin-bottom:4px; color:#3a2145;"><strong style="color:${m.is_me ? '#ff4fa0' : chatColorFor(m.username)};">${m.username}${m.is_me ? "(あなた)" : ""}:</strong> ${m.message}</div>`
      ).join("");
      chatLog.scrollTop = chatLog.scrollHeight;
    } catch (err) { /* noop */ }
  }

  async function poll() {
    try {
      const res = await fetch(`/cards/room/${CODE}/poll`);
      const data = await res.json();
      if (data.error) return;
      currentGameType = data.game_type;

      playerCountEl.textContent = String(data.players.length);
      playerListEl.innerHTML = data.players.map((p) => {
        const botTag = p.is_bot ? ' <span style="color:var(--text-muted); font-size:11px;">🤖</span>' : "";
        const removeBtn = (IS_OWNER && p.user_id !== data.owner_id)
          ? `<button type="button" class="btn btn-ghost remove-player-btn" data-uid="${p.user_id}" style="padding:2px 8px; font-size:11px;">除外</button>` : "";
        return `<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-top:1px solid var(--panel-border);"><span>${p.username}${botTag}</span>${removeBtn}</div>`;
      }).join("");
      document.querySelectorAll(".remove-player-btn").forEach((btn) => {
        btn.addEventListener("click", () => removePlayer(parseInt(btn.dataset.uid, 10)));
      });
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
  pollChat();
  setInterval(poll, 2000);
  setInterval(pollChat, 2500);
})();
