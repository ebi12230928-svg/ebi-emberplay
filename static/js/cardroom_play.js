(function () {
  const CODE = window.CARD_ROOM_CODE;
  const GAME_TYPE = window.CARD_GAME_TYPE;

  const turnBanner = document.getElementById("player-turn-banner");
  const pileDisplay = document.getElementById("pile-display");
  const centerDisplay = document.getElementById("center-display");
  const cardHand = document.getElementById("card-hand");
  const playBtn = document.getElementById("play-btn");
  const passBtn = document.getElementById("pass-btn");
  const drawBtn = document.getElementById("draw-btn");
  const playersStatus = document.getElementById("players-status");
  const gameLog = document.getElementById("game-log");
  const resultBanner = document.getElementById("result-banner");

  const SUITS = ["♠", "♥", "♦", "♣"];
  const RANK_LABELS = { 1: "A", 11: "J", 12: "Q", 13: "K" };

  function cardLabel(card) {
    if (card === 52) return { text: "JOKER", suit: "🃏", red: false };
    const rank = (card % 13) + 1;
    const suit = Math.floor(card / 13);
    return { text: (RANK_LABELS[rank] || String(rank)), suit: SUITS[suit], red: suit === 1 || suit === 2 };
  }

  function renderCardChip(card, opts) {
    opts = opts || {};
    const el = document.createElement("div");
    if (card === "?") {
      el.className = "card-chip back";
      el.textContent = "🂠";
      return el;
    }
    const info = cardLabel(card);
    el.className = "card-chip" + (info.red ? " red" : "") + (opts.selected ? " selected" : "") + (opts.disabled ? " disabled" : "");
    el.innerHTML = `${info.suit}<br>${info.text}`;
    return el;
  }

  let selectedCards = [];

  async function fetchState() {
    try {
      const res = await fetch(`/cards/room/${CODE}/state`);
      const data = await res.json();
      if (data.error) {
        turnBanner.textContent = data.error;
        return;
      }
      render(data);
    } catch (err) {
      // 次のポーリングに任せる
    }
  }

  function render(data) {
    const uidKey = String(data.my_id);
    const myHand = data.hands[uidKey] || [];

    gameLog.innerHTML = (data.log || []).map((l) => `<div>${l}</div>`).join("");
    gameLog.scrollTop = gameLog.scrollHeight;

    if (data.status === "finished") {
      showResult(data);
    }

    if (GAME_TYPE === "daifugo") renderDaifugo(data, uidKey, myHand);
    else if (GAME_TYPE === "babanuki") renderBabanuki(data, uidKey, myHand);
    else if (GAME_TYPE === "speed") renderSpeed(data, uidKey, myHand);
  }

  function showResult(data) {
    resultBanner.style.display = "block";
    if (GAME_TYPE === "daifugo") {
      const order = (data.finished_order || []).map((uid, i) => `${i + 1}位: ${data.names[uid]}`).join(" / ");
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>${order}`;
    } else if (GAME_TYPE === "babanuki") {
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>😱 ${data.names[data.loser]} の負け!`;
    } else if (GAME_TYPE === "speed") {
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>🏆 ${data.names[data.winner]} の勝ち!`;
    }
    playBtn.style.display = "none";
    passBtn.style.display = "none";
    drawBtn.style.display = "none";
  }

  // ───────── 大富豪 ─────────
  function renderDaifugo(data, uidKey, myHand) {
    playBtn.style.display = "inline-block";
    passBtn.style.display = "inline-block";
    drawBtn.style.display = "none";

    pileDisplay.innerHTML = "";
    if (data.pile.length) {
      data.pile.forEach((c) => pileDisplay.appendChild(renderCardChip(c)));
    } else {
      pileDisplay.innerHTML = '<span class="text-muted" style="font-size:12px;">(場は空です。自由に出せます)</span>';
    }
    if (data.revolution) {
      const rev = document.createElement("div");
      rev.style.cssText = "width:100%; text-align:center; color: var(--loss); font-size:12px; font-weight:700;";
      rev.textContent = "⚡革命中(強さが逆転しています)";
      pileDisplay.appendChild(rev);
    }

    const isMyTurn = String(data.current_turn) === uidKey;
    turnBanner.textContent = isMyTurn ? "🎯 あなたの番です!" : `${data.names[data.current_turn] || "?"} の番です…`;
    turnBanner.style.color = isMyTurn ? "var(--gold)" : "";

    cardHand.innerHTML = "";
    myHand.forEach((c) => {
      const chip = renderCardChip(c, { selected: selectedCards.includes(c) });
      chip.addEventListener("click", () => {
        const idx = selectedCards.indexOf(c);
        if (idx >= 0) selectedCards.splice(idx, 1);
        else selectedCards.push(c);
        renderDaifugo(data, uidKey, myHand);
      });
      cardHand.appendChild(chip);
    });

    playBtn.disabled = !isMyTurn || selectedCards.length === 0;
    passBtn.disabled = !isMyTurn || data.pile.length === 0;

    playBtn.onclick = async () => {
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "play", cards: selectedCards });
        selectedCards = [];
        fetchState();
      } catch (err) { alert(err.message); }
    };
    passBtn.onclick = async () => {
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "pass" });
        fetchState();
      } catch (err) { alert(err.message); }
    };

    playersStatus.innerHTML = data.turn_order.map((uid) => {
      const finishedIdx = data.finished_order.indexOf(uid);
      const status = finishedIdx >= 0 ? `🏁${finishedIdx + 1}位` : (String(uid) === String(data.current_turn) ? "🎯手番" : "");
      const cnt = data.hands[uid] ? data.hands[uid].length : 0;
      return `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">${status} ${cnt}枚</span></div>`;
    }).join("");
  }

  // ───────── ババ抜き ─────────
  function renderBabanuki(data, uidKey, myHand) {
    playBtn.style.display = "none";
    passBtn.style.display = "none";
    drawBtn.style.display = "inline-block";
    pileDisplay.innerHTML = '<span class="text-muted" style="font-size:12px;">左隣のプレイヤーからカードを引きます</span>';

    const isMyTurn = String(data.current_turn) === uidKey;
    turnBanner.textContent = isMyTurn ? "🎯 あなたの番です!カードを引いてください" : `${data.names[data.current_turn] || "?"} の番です…`;
    turnBanner.style.color = isMyTurn ? "var(--gold)" : "";

    cardHand.innerHTML = "";
    myHand.forEach((c) => cardHand.appendChild(renderCardChip(c)));

    drawBtn.disabled = !isMyTurn;
    drawBtn.onclick = async () => {
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "draw" });
        fetchState();
      } catch (err) { alert(err.message); }
    };

    playersStatus.innerHTML = data.turn_order.map((uid) => {
      const out = (data.out || []).includes(uid);
      const status = out ? "✅上がり" : (String(uid) === String(data.current_turn) ? "🎯手番" : "");
      const cnt = data.hands[uid] ? data.hands[uid].length : 0;
      return `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">${status} ${cnt}枚</span></div>`;
    }).join("");
  }

  // ───────── スピード ─────────
  function renderSpeed(data, uidKey, myHand) {
    playBtn.style.display = "none";
    passBtn.style.display = "none";
    drawBtn.style.display = "none";
    turnBanner.textContent = "⚡ 手番はありません。出せるカードがあればすぐに出せます!";

    centerDisplay.innerHTML = "";
    data.center.forEach((c, i) => {
      const chip = renderCardChip(c);
      chip.addEventListener("click", () => {
        if (selectedCards.length !== 1) {
          turnBanner.textContent = "先に手札から出したいカードを選んでください。";
          return;
        }
        submitSpeedPlay(selectedCards[0], i);
      });
      centerDisplay.appendChild(chip);
    });

    cardHand.innerHTML = "";
    myHand.forEach((c) => {
      const chip = renderCardChip(c, { selected: selectedCards.includes(c) });
      chip.addEventListener("click", () => {
        selectedCards = selectedCards.includes(c) ? [] : [c];
        renderSpeed(data, uidKey, myHand);
      });
      cardHand.appendChild(chip);
    });

    playersStatus.innerHTML = Object.keys(data.stock_counts || {}).map((uid) => {
      return `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">補充札 ${data.stock_counts[uid]}枚</span></div>`;
    }).join("");
  }

  async function submitSpeedPlay(card, pileIdx) {
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "play", card, pile_idx: pileIdx });
      selectedCards = [];
      fetchState();
    } catch (err) {
      alert(err.message);
      EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "refill_check" }).catch(() => {});
    }
  }

  fetchState();
  const pollMs = GAME_TYPE === "speed" ? 1200 : 2000;
  setInterval(fetchState, pollMs);
})();
