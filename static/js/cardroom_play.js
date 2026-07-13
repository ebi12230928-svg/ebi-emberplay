(function () {
  const CODE = window.CARD_ROOM_CODE;
  const GAME_TYPE = window.CARD_GAME_TYPE;
  const CARD_GAMES = ["daifugo", "babanuki", "speed", "uno", "sevens", "concentration"];
  const IS_CARD_GAME = CARD_GAMES.includes(GAME_TYPE);

  const turnBanner = document.getElementById("player-turn-banner");
  const pileDisplay = document.getElementById("pile-display");
  const centerDisplay = document.getElementById("center-display");
  const boardDisplay = document.getElementById("board-display");
  const cardHand = document.getElementById("card-hand");
  const playBtn = document.getElementById("play-btn");
  const passBtn = document.getElementById("pass-btn");
  const drawBtn = document.getElementById("draw-btn");
  const resignBtn = document.getElementById("resign-btn");
  const playersStatus = document.getElementById("players-status");
  const gameLog = document.getElementById("game-log");
  const resultBanner = document.getElementById("result-banner");
  const howToPlayBtn = document.getElementById("how-to-play-btn");
  const howToPlayModal = document.getElementById("how-to-play-modal");
  const howToPlayTitle = document.getElementById("how-to-play-title");
  const howToPlayText = document.getElementById("how-to-play-text");
  const howToPlayClose = document.getElementById("how-to-play-close");
  const chatLog = document.getElementById("room-chat-log");
  const chatInput = document.getElementById("room-chat-input");
  const chatSendBtn = document.getElementById("room-chat-send");

  const SUITS = ["♠", "♥", "♦", "♣"];
  const RANK_LABELS = { 1: "A", 11: "J", 12: "Q", 13: "K" };
  const UNO_COLOR_HEX = { red: "#dc2626", yellow: "#eab308", green: "#16a34a", blue: "#2563eb", wild: "#444" };

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

  function renderUnoChip(card, opts) {
    opts = opts || {};
    const el = document.createElement("div");
    if (!card) { el.className = "card-chip back"; el.textContent = "🂠"; return el; }
    el.className = "card-chip" + (opts.selected ? " selected" : "");
    el.style.background = UNO_COLOR_HEX[card.color] || "#444";
    el.style.color = "#fff";
    const labelMap = { skip: "🚫", reverse: "🔁", draw2: "+2", wild: "★", wild4: "+4🌈" };
    el.innerHTML = labelMap[card.value] || card.value;
    return el;
  }

  let selectedCards = [];
  let selectedBoardCell = null;
  let lastLogLen = 0;

  async function fetchState() {
    try {
      const res = await fetch(`/cards/room/${CODE}/state`);
      const data = await res.json();
      if (data.error) {
        turnBanner.textContent = data.error;
        return;
      }
      render(data);
    } catch (err) { /* 次のポーリングに任せる */ }
  }

  function render(data) {
    const uidKey = String(data.my_id);
    const myHand = (data.hands && data.hands[uidKey]) || [];

    if ((data.log || []).length !== lastLogLen) {
      gameLog.innerHTML = (data.log || []).map((l) => `<div>${l}</div>`).join("");
      gameLog.scrollTop = gameLog.scrollHeight;
      lastLogLen = (data.log || []).length;
    }

    if (data.status === "finished") showResult(data);

    if (GAME_TYPE === "daifugo") renderDaifugo(data, uidKey, myHand);
    else if (GAME_TYPE === "babanuki") renderBabanuki(data, uidKey, myHand);
    else if (GAME_TYPE === "speed") renderSpeed(data, uidKey, myHand);
    else if (GAME_TYPE === "uno") renderUno(data, uidKey, myHand);
    else if (GAME_TYPE === "sevens") renderSevens(data, uidKey, myHand);
    else if (GAME_TYPE === "concentration") renderConcentration(data, uidKey);
    else renderBoardGame(data, uidKey);
  }

  function showResult(data) {
    resultBanner.style.display = "block";
    if (GAME_TYPE === "daifugo") {
      const order = (data.finished_order || []).map((uid, i) => `${i + 1}位: ${data.names[uid]}`).join(" / ");
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>${order}`;
    } else if (GAME_TYPE === "babanuki") {
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>😱 ${data.names[data.loser]} の負け!`;
    } else if (GAME_TYPE === "concentration") {
      const scoreText = Object.keys(data.scores || {}).map((uid) => `${data.names[uid]}: ${data.scores[uid]}ペア`).join(" / ");
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>${scoreText}${data.winner ? `<br>🏆 ${data.names[data.winner]} の勝ち!` : "<br>引き分けです。"}`;
    } else if (data.winner) {
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>🏆 ${data.names[data.winner]} の勝ち!`;
    } else if (data.is_draw) {
      resultBanner.innerHTML = `<strong>🏁 ゲーム終了!</strong><br>引き分けです。`;
    }
    playBtn.style.display = "none";
    passBtn.style.display = "none";
    drawBtn.style.display = "none";
    resignBtn.style.display = "none";
  }

  // ───────── 大富豪 ─────────
  function renderDaifugo(data, uidKey, myHand) {
    playBtn.style.display = "inline-block";
    passBtn.style.display = "inline-block";
    drawBtn.style.display = "none";
    resignBtn.style.display = "none";
    boardDisplay.style.display = "none";
    cardHand.style.display = "flex";

    pileDisplay.innerHTML = "";
    if (data.pile.length) data.pile.forEach((c) => pileDisplay.appendChild(renderCardChip(c)));
    else pileDisplay.innerHTML = '<span class="text-muted" style="font-size:12px;">(場は空です。自由に出せます)</span>';
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
        if (idx >= 0) selectedCards.splice(idx, 1); else selectedCards.push(c);
        renderDaifugo(data, uidKey, myHand);
      });
      cardHand.appendChild(chip);
    });

    playBtn.disabled = !isMyTurn || selectedCards.length === 0;
    passBtn.disabled = !isMyTurn || data.pile.length === 0;
    playBtn.onclick = async () => {
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "play", cards: selectedCards });
        selectedCards = []; fetchState();
      } catch (err) { alert(err.message); }
    };
    passBtn.onclick = async () => {
      try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "pass" }); fetchState(); }
      catch (err) { alert(err.message); }
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
    resignBtn.style.display = "none";
    boardDisplay.style.display = "none";
    cardHand.style.display = "flex";
    pileDisplay.innerHTML = '<span class="text-muted" style="font-size:12px;">左隣のプレイヤーからカードを引きます</span>';

    const isMyTurn = String(data.current_turn) === uidKey;
    turnBanner.textContent = isMyTurn ? "🎯 あなたの番です!カードを引いてください" : `${data.names[data.current_turn] || "?"} の番です…`;
    turnBanner.style.color = isMyTurn ? "var(--gold)" : "";

    cardHand.innerHTML = "";
    myHand.forEach((c) => cardHand.appendChild(renderCardChip(c)));

    drawBtn.disabled = !isMyTurn;
    drawBtn.onclick = async () => {
      try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "draw" }); fetchState(); }
      catch (err) { alert(err.message); }
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
    resignBtn.style.display = "none";
    boardDisplay.style.display = "none";
    cardHand.style.display = "flex";
    turnBanner.textContent = "⚡ 手番はありません。出せるカードがあればすぐに出せます!";

    centerDisplay.innerHTML = "";
    data.center.forEach((c, i) => {
      const chip = renderCardChip(c);
      chip.addEventListener("click", () => {
        if (selectedCards.length !== 1) { turnBanner.textContent = "先に手札から出したいカードを選んでください。"; return; }
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

    playersStatus.innerHTML = Object.keys(data.stock_counts || {}).map((uid) =>
      `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">補充札 ${data.stock_counts[uid]}枚</span></div>`
    ).join("");
  }

  async function submitSpeedPlay(card, pileIdx) {
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "play", card, pile_idx: pileIdx });
      selectedCards = []; fetchState();
    } catch (err) {
      alert(err.message);
      EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "refill_check" }).catch(() => {});
    }
  }

  // ───────── UNO ─────────
  function renderUno(data, uidKey, myHandRaw) {
    playBtn.style.display = "inline-block";
    passBtn.style.display = "none";
    drawBtn.style.display = "inline-block";
    resignBtn.style.display = "none";
    boardDisplay.style.display = "none";
    cardHand.style.display = "flex";

    const myHand = data.hands ? data.hands[uidKey] : [];
    pileDisplay.innerHTML = "";
    if (data.discard_top) {
      pileDisplay.appendChild(renderUnoChip(data.discard_top));
      const colorTag = document.createElement("div");
      colorTag.style.cssText = "width:100%; text-align:center; font-size:11px; margin-top:4px;";
      colorTag.textContent = `現在の色: ${data.current_color}`;
      pileDisplay.appendChild(colorTag);
    }

    const isMyTurn = String(data.current_turn) === uidKey;
    turnBanner.textContent = isMyTurn ? "🎯 あなたの番です!" : `${data.names[data.current_turn] || "?"} の番です…`;
    turnBanner.style.color = isMyTurn ? "var(--gold)" : "";

    cardHand.innerHTML = "";
    (myHand || []).forEach((c, i) => {
      const chip = renderUnoChip(c, { selected: selectedCards.includes(i) });
      chip.addEventListener("click", () => {
        selectedCards = selectedCards.includes(i) ? [] : [i];
        renderUno(data, uidKey, myHandRaw);
      });
      cardHand.appendChild(chip);
    });

    playBtn.disabled = !isMyTurn || selectedCards.length !== 1;
    drawBtn.disabled = !isMyTurn;
    playBtn.onclick = async () => {
      const card = myHand[selectedCards[0]];
      let color = null;
      if (card.color === "wild") {
        color = prompt("色を選んでください(red / yellow / green / blue)", "red");
        if (!color) return;
      }
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "play", card_index: selectedCards[0], color });
        selectedCards = []; fetchState();
      } catch (err) { alert(err.message); }
    };
    drawBtn.onclick = async () => {
      try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "draw" }); fetchState(); }
      catch (err) { alert(err.message); }
    };

    playersStatus.innerHTML = data.turn_order.map((uid) => {
      const status = String(uid) === String(data.current_turn) ? "🎯手番" : "";
      const cnt = (data.hand_counts && data.hand_counts[uid]) || 0;
      return `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">${status} ${cnt}枚</span></div>`;
    }).join("");
  }

  // ───────── 七並べ ─────────
  function renderSevens(data, uidKey, myHand) {
    playBtn.style.display = "inline-block";
    passBtn.style.display = "inline-block";
    drawBtn.style.display = "none";
    resignBtn.style.display = "none";
    boardDisplay.style.display = "none";
    cardHand.style.display = "flex";

    pileDisplay.innerHTML = "";
    const suitSymbols = ["♠", "♥", "♦", "♣"];
    suitSymbols.forEach((sym, i) => {
      const entry = data.table[i] || data.table[String(i)];
      const box = document.createElement("div");
      box.style.cssText = "text-align:center; margin: 0 6px; font-size:12px;";
      const red = i === 1 || i === 2;
      box.innerHTML = `<span style="color:${red ? '#dc2626' : '#fff'};">${sym}</span><br>${entry && entry.min !== null ? entry.min + "〜" + entry.max : "(7待ち)"}`;
      pileDisplay.appendChild(box);
    });

    const isMyTurn = String(data.current_turn) === uidKey;
    turnBanner.textContent = isMyTurn ? "🎯 あなたの番です!" : `${data.names[data.current_turn] || "?"} の番です…`;
    turnBanner.style.color = isMyTurn ? "var(--gold)" : "";

    cardHand.innerHTML = "";
    myHand.forEach((c) => {
      const chip = renderCardChip(c, { selected: selectedCards.includes(c) });
      chip.addEventListener("click", () => {
        selectedCards = selectedCards.includes(c) ? [] : [c];
        renderSevens(data, uidKey, myHand);
      });
      cardHand.appendChild(chip);
    });

    playBtn.disabled = !isMyTurn || selectedCards.length !== 1;
    passBtn.disabled = !isMyTurn;
    playBtn.onclick = async () => {
      try {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "play", card: selectedCards[0] });
        selectedCards = []; fetchState();
      } catch (err) { alert(err.message); }
    };
    passBtn.onclick = async () => {
      try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "pass" }); fetchState(); }
      catch (err) { alert(err.message); }
    };

    playersStatus.innerHTML = data.turn_order.map((uid) => {
      const status = String(uid) === String(data.current_turn) ? "🎯手番" : "";
      const cnt = data.hands[uid] ? data.hands[uid].length : 0;
      return `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">${status} ${cnt}枚</span></div>`;
    }).join("");
  }

  // ───────── 神経衰弱 ─────────
  function renderConcentration(data, uidKey) {
    playBtn.style.display = "none";
    passBtn.style.display = "none";
    drawBtn.style.display = "none";
    resignBtn.style.display = "none";
    boardDisplay.style.display = "block";
    cardHand.style.display = "none";
    pileDisplay.innerHTML = "";
    centerDisplay.innerHTML = "";

    const isMyTurn = String(data.current_turn) === uidKey;
    turnBanner.textContent = isMyTurn ? "🎯 あなたの番です!2枚めくろう" : `${data.names[data.current_turn] || "?"} の番です…`;
    turnBanner.style.color = isMyTurn ? "var(--gold)" : "";

    boardDisplay.innerHTML = "";
    const grid = document.createElement("div");
    grid.className = "board-grid";
    grid.style.gridTemplateColumns = "repeat(8, 1fr)";
    grid.style.maxWidth = "420px";

    for (let i = 0; i < 52; i++) {
      const cell = document.createElement("div");
      cell.className = "board-cell";
      cell.style.fontSize = "16px";
      if (data.matched[i]) {
        cell.innerHTML = "✅";
        cell.style.opacity = "0.35";
      } else if (data.revealed_positions.includes(i)) {
        const card = data.revealed_cards[String(i)];
        const chip = renderCardChip(card);
        chip.style.margin = "0";
        cell.appendChild(chip);
      } else {
        cell.innerHTML = '<span style="opacity:0.6;">🂠</span>';
        cell.addEventListener("click", async () => {
          if (!isMyTurn) return;
          try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "flip", position: i }); fetchState(); }
          catch (err) { alert(err.message); }
        });
      }
      grid.appendChild(cell);
    }
    boardDisplay.appendChild(grid);

    playersStatus.innerHTML = data.turn_order.map((uid) => {
      const status = String(uid) === String(data.current_turn) ? "🎯手番" : "";
      const score = (data.scores && data.scores[uid]) || 0;
      return `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">${status} ${score}ペア</span></div>`;
    }).join("");
  }

  // ───────── ボードゲーム共通(五目並べ・オセロ・チェッカー・モリス・将棋・三目並べ・コネクトフォー・チェス) ─────────
  function renderBoardGame(data, uidKey) {
    playBtn.style.display = "none";
    passBtn.style.display = GAME_TYPE === "othello" ? "inline-block" : "none";
    drawBtn.style.display = "none";
    resignBtn.style.display = (GAME_TYPE === "shogi" || GAME_TYPE === "chess") ? "inline-block" : "none";
    boardDisplay.style.display = "block";
    cardHand.style.display = "none";
    pileDisplay.innerHTML = "";
    centerDisplay.innerHTML = "";

    const isMyTurn = String(data.current_turn) === uidKey;
    turnBanner.textContent = isMyTurn ? "🎯 あなたの番です!" : `${data.names[data.current_turn] || "?"} の番です…`;
    turnBanner.style.color = isMyTurn ? "var(--gold)" : "";

    if (GAME_TYPE === "morris") renderMorris(data, uidKey, isMyTurn);
    else if (GAME_TYPE === "shogi") renderShogi(data, uidKey, isMyTurn);
    else if (GAME_TYPE === "chess") renderChess(data, uidKey, isMyTurn);
    else if (GAME_TYPE === "connect4") renderConnect4(data, uidKey, isMyTurn);
    else renderGridBoard(data, uidKey, isMyTurn);

    passBtn.onclick = async () => {
      try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "pass" }); fetchState(); }
      catch (err) { alert(err.message); }
    };
    resignBtn.onclick = async () => {
      if (!confirm("本当に投了しますか?")) return;
      try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "resign" }); fetchState(); }
      catch (err) { alert(err.message); }
    };

    playersStatus.innerHTML = data.turn_order.map((uid) =>
      `<div style="display:flex; justify-content:space-between; padding:4px 0;"><span>${data.names[uid]}</span><span class="mono text-muted">${String(uid) === String(data.current_turn) ? "🎯手番" : ""}</span></div>`
    ).join("");
  }

  const GRID_SYMBOLS = { gomoku: ["⚫", "⚪"], othello: ["⚫", "⚪"], checkers: ["🔴", "🔵"], tictactoe: ["❌", "⭕"] };

  function renderGridBoard(data, uidKey, isMyTurn) {
    const board = data.board;
    const size = board.length;
    boardDisplay.innerHTML = "";
    const grid = document.createElement("div");
    grid.className = "board-grid";
    grid.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
    const symbols = GRID_SYMBOLS[GAME_TYPE] || ["⚫", "⚪"];

    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = document.createElement("div");
        cell.className = "board-cell";
        const val = board[r][c];

        if (GAME_TYPE === "checkers") {
          if (val) {
            cell.innerHTML = `<span class="piece-token">${symbols[val.owner]}${val.king ? "👑" : ""}</span>`;
          }
          if (selectedBoardCell && selectedBoardCell[0] === r && selectedBoardCell[1] === c) cell.classList.add("selected");
          if (isLegalDest(data, r, c)) cell.classList.add("legal-move");
          cell.addEventListener("click", () => handleCheckersClick(data, r, c, isMyTurn));
        } else {
          if (val !== null && val !== undefined) cell.innerHTML = `<span class="piece-token">${symbols[val]}</span>`;
          if (GAME_TYPE === "othello" && isMyTurn && (data.legal_placements || []).some(([lr, lc]) => lr === r && lc === c)) {
            cell.classList.add("legal-move");
          }
          cell.addEventListener("click", async () => {
            if (!isMyTurn) return;
            try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "place", row: r, col: c }); fetchState(); }
            catch (err) { alert(err.message); }
          });
        }
        grid.appendChild(cell);
      }
    }
    boardDisplay.appendChild(grid);
  }

  async function handleCheckersClick(data, r, c, isMyTurn) {
    if (!isMyTurn) return;
    if (!selectedBoardCell) {
      selectedBoardCell = [r, c];
      render(data);
      return;
    }
    const [fr, fc] = selectedBoardCell;
    selectedBoardCell = null;
    if (fr === r && fc === c) { render(data); return; }
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "move", from_r: fr, from_c: fc, to_r: r, to_c: c });
      fetchState();
    } catch (err) { alert(err.message); render(data); }
  }

  // ナインメンズモリス: 24点の座標(標準的な三重四角形レイアウト、0-100%基準)
  const MORRIS_COORDS = [
    [0, 0], [50, 0], [100, 0], [16, 16], [50, 16], [83, 16], [0, 50], [16, 50], [33, 50],
    [66, 50], [83, 50], [100, 50], [16, 83], [50, 83], [83, 83], [0, 100], [50, 100], [100, 100],
    // ↑ 16点で標準モリス盤とは異なるため、24点の正しい配置に差し替え
  ];
  // 標準的な24点配置(3重の四角形+接続線)
  const MORRIS_POINTS = [
    [0, 0], [50, 0], [100, 0], [16.5, 16.5], [50, 16.5], [83.5, 16.5],
    [0, 50], [16.5, 50], [33, 50], [66, 50], [83.5, 50], [100, 50],
    [16.5, 83.5], [50, 83.5], [83.5, 83.5], [0, 100], [50, 100], [100, 100],
    [50, 33], [50, 66], [33, 33], [66, 33], [33, 66], [66, 66],
  ];

  function renderMorris(data, uidKey, isMyTurn) {
    boardDisplay.innerHTML = "";
    const container = document.createElement("div");
    container.className = "morris-board";
    const owner = data.turn_order.indexOf(parseInt(uidKey, 10));
    const symbols = ["⚫", "⚪"];

    data.board.forEach((val, i) => {
      const coords = MORRIS_POINTS[i] || [50, 50];
      const pt = document.createElement("div");
      pt.className = "morris-point";
      pt.style.left = coords[0] + "%";
      pt.style.top = coords[1] + "%";
      if (val !== null && val !== undefined) pt.innerHTML = `<span class="piece-token">${symbols[val]}</span>`;
      if (selectedBoardCell === i) pt.classList.add("selected");

      const isEmpty = val === null || val === undefined;
      if (isMyTurn && !data.must_remove) {
        if (data.phase === "placing" && isEmpty) {
          pt.classList.add("legal-move");
        } else if (data.phase === "moving" && selectedBoardCell !== null) {
          const dests = (data.legal_moves_map_morris || {})[String(selectedBoardCell)] || [];
          if (dests.includes(i)) pt.classList.add("legal-move");
        }
      }
      pt.addEventListener("click", () => handleMorrisClick(data, i, owner, isMyTurn));
      container.appendChild(pt);
    });
    boardDisplay.appendChild(container);

    if (data.must_remove) turnBanner.textContent += "(ミル成立!相手の駒をタップして取ってください)";
  }

  async function handleMorrisClick(data, point, owner, isMyTurn) {
    if (!isMyTurn) return;
    try {
      if (data.must_remove) {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "remove", point });
        fetchState();
        return;
      }
      if (data.phase === "placing") {
        await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "place", point });
        fetchState();
        return;
      }
      if (selectedBoardCell === null) {
        if (data.board[point] === owner) { selectedBoardCell = point; render(data); }
        return;
      }
      const from = selectedBoardCell;
      selectedBoardCell = null;
      await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "move", from_point: from, to_point: point });
      fetchState();
    } catch (err) { alert(err.message); selectedBoardCell = null; render(data); }
  }

  // コネクトフォー: 列をタップして落とす
  function renderConnect4(data, uidKey, isMyTurn) {
    boardDisplay.innerHTML = "";
    const board = data.board;
    const grid = document.createElement("div");
    grid.className = "board-grid";
    grid.style.gridTemplateColumns = "repeat(7, 1fr)";
    const symbols = ["🔴", "🟡"];

    for (let r = 0; r < 6; r++) {
      for (let c = 0; c < 7; c++) {
        const cell = document.createElement("div");
        cell.className = "board-cell";
        const val = board[r][c];
        if (val !== null && val !== undefined) cell.innerHTML = `<span class="piece-token">${symbols[val]}</span>`;
        cell.addEventListener("click", async () => {
          if (!isMyTurn) return;
          try { await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "place", col: c }); fetchState(); }
          catch (err) { alert(err.message); }
        });
        grid.appendChild(cell);
      }
    }
    boardDisplay.appendChild(grid);
  }

  // チェス
  const CHESS_LABELS = { p: "♟", r: "♜", n: "♞", b: "♝", q: "♛", k: "♚" };

  // 選択中の駒について、(r,c)が合法な移動先かどうかをサーバーから受け取ったマップで判定する
  function isLegalDest(data, r, c) {
    if (!selectedBoardCell || !data.legal_moves_map) return false;
    const key = `${selectedBoardCell[0]},${selectedBoardCell[1]}`;
    const dests = data.legal_moves_map[key];
    if (!dests) return false;
    return dests.some(([dr, dc]) => dr === r && dc === c);
  }

  function hasAnyLegalMoveFrom(data, r, c) {
    if (!data.legal_moves_map) return false;
    return !!data.legal_moves_map[`${r},${c}`];
  }

  function renderChess(data, uidKey, isMyTurn) {
    boardDisplay.innerHTML = "";
    const owner = data.turn_order.indexOf(parseInt(uidKey, 10));
    const grid = document.createElement("div");
    grid.className = "board-grid";
    grid.style.gridTemplateColumns = "repeat(8, 1fr)";

    for (let r = 0; r < 8; r++) {
      for (let c = 0; c < 8; c++) {
        const cell = document.createElement("div");
        cell.className = "board-cell";
        cell.style.fontSize = "22px";
        const piece = data.board[r][c];
        if (piece) {
          const label = CHESS_LABELS[piece.type] || piece.type;
          cell.innerHTML = `<span class="piece-token" style="color:${piece.owner === 0 ? '#fff' : '#111'}; -webkit-text-stroke: 0.5px #888;">${label}</span>`;
        }
        if (selectedBoardCell && selectedBoardCell[0] === r && selectedBoardCell[1] === c) cell.classList.add("selected");
        if (isLegalDest(data, r, c)) cell.classList.add("legal-move");
        cell.addEventListener("click", () => handleChessClick(data, r, c, owner, isMyTurn));
        grid.appendChild(cell);
      }
    }
    boardDisplay.appendChild(grid);
  }

  async function handleChessClick(data, r, c, owner, isMyTurn) {
    if (!isMyTurn) return;
    if (!selectedBoardCell) {
      const piece = data.board[r][c];
      if (piece && piece.owner === owner) { selectedBoardCell = [r, c]; render(data); }
      return;
    }
    const [fr, fc] = selectedBoardCell;
    selectedBoardCell = null;
    if (fr === r && fc === c) { render(data); return; }
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "move", from_r: fr, from_c: fc, to_r: r, to_c: c });
      fetchState();
    } catch (err) { alert(err.message); render(data); }
  }

  // 将棋
  const SHOGI_LABELS = { p: "歩", l: "香", n: "桂", s: "銀", g: "金", b: "角", r: "飛", k: "王", "+p": "と", "+l": "成香", "+n": "成桂", "+s": "成銀", "+b": "馬", "+r": "龍" };

  function renderShogi(data, uidKey, isMyTurn) {
    boardDisplay.innerHTML = "";
    const owner = data.turn_order.indexOf(parseInt(uidKey, 10));
    const grid = document.createElement("div");
    grid.className = "board-grid";
    grid.style.gridTemplateColumns = "repeat(9, 1fr)";

    for (let r = 0; r < 9; r++) {
      for (let c = 0; c < 9; c++) {
        const cell = document.createElement("div");
        cell.className = "board-cell";
        cell.style.fontSize = "13px";
        const piece = data.board[r][c];
        if (piece) {
          const label = SHOGI_LABELS[piece.type] || piece.type;
          cell.innerHTML = `<span class="piece-token" style="color:${piece.owner === owner ? '#fff' : '#f87171'};">${label}</span>`;
        }
        if (selectedBoardCell && selectedBoardCell[0] === r && selectedBoardCell[1] === c) cell.classList.add("selected");
        if (isLegalDest(data, r, c)) cell.classList.add("legal-move");
        cell.addEventListener("click", () => handleShogiClick(data, r, c, owner, isMyTurn));
        grid.appendChild(cell);
      }
    }
    boardDisplay.appendChild(grid);

    const hand = (data.hands && data.hands[String(owner)]) || [];
    if (hand.length) {
      const handDiv = document.createElement("div");
      handDiv.style.cssText = "margin-top:10px; text-align:center; font-size:12px;";
      handDiv.textContent = "持ち駒: " + hand.map((p) => SHOGI_LABELS[p] || p).join(" ");
      boardDisplay.appendChild(handDiv);
    }
  }

  async function handleShogiClick(data, r, c, owner, isMyTurn) {
    if (!isMyTurn) return;
    if (!selectedBoardCell) {
      const piece = data.board[r][c];
      if (piece && piece.owner === owner) { selectedBoardCell = [r, c]; render(data); }
      return;
    }
    const [fr, fc] = selectedBoardCell;
    selectedBoardCell = null;
    if (fr === r && fc === c) { render(data); return; }
    const promote = confirm("成りますか?(成れない場合は無視されます)");
    try {
      await EmberPlay.postJSON(`/cards/room/${CODE}/action`, { type: "move", from_r: fr, from_c: fc, to_r: r, to_c: c, promote });
      fetchState();
    } catch (err) { alert(err.message); render(data); }
  }

  // ───────── 遊び方 ─────────
  if (howToPlayBtn) {
    howToPlayBtn.addEventListener("click", async () => {
      try {
        const res = await fetch(`/cards/how-to-play/${GAME_TYPE}`);
        const data = await res.json();
        howToPlayTitle.textContent = `📖 ${data.label} の遊び方`;
        howToPlayText.textContent = data.text;
        howToPlayModal.style.display = "flex";
      } catch (err) { /* noop */ }
    });
  }
  if (howToPlayClose) howToPlayClose.addEventListener("click", () => { howToPlayModal.style.display = "none"; });

  // ───────── ルームチャット ─────────
  if (chatSendBtn) {
    chatSendBtn.addEventListener("click", sendChat);
    chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
  }
  async function sendChat() {
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = "";
    try { await EmberPlay.postJSON(`/cards/room/${CODE}/chat/send`, { message: text }); pollChat(); }
    catch (err) { /* noop */ }
  }
  async function pollChat() {
    try {
      const res = await fetch(`/cards/room/${CODE}/chat`);
      const data = await res.json();
      if (!chatLog || !data.messages) return;
      chatLog.innerHTML = data.messages.map((m) =>
        `<div style="margin-bottom:4px;"><strong style="color:${m.is_me ? 'var(--gold)' : 'var(--text)'};">${m.username}:</strong> ${m.message}</div>`
      ).join("");
      chatLog.scrollTop = chatLog.scrollHeight;
    } catch (err) { /* noop */ }
  }

  fetchState();
  pollChat();
  const pollMs = GAME_TYPE === "speed" ? 1200 : 2000;
  setInterval(fetchState, pollMs);
  setInterval(pollChat, 2500);
})();
