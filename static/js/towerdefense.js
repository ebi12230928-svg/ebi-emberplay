(function () {
  const GRID_COLS = 8;
  const GRID_ROWS = 5;
  const MODE = window.TD_MODE || "normal";
  const MODE_CFG = (window.TD_MODES || {})[MODE] || { waves: 10, hp_mult: 1.0 };
  const TOTAL_WAVES = MODE_CFG.waves; // nullならエンドレス(上限なし)
  const MAX_TEAM = window.TD_MAX_TEAM || 6;
  const START_LIVES = 20;
  const SQUAD = window.TD_SQUAD || null;
  const DIFFICULTY = (SQUAD ? SQUAD.difficulty : 1.0) * MODE_CFG.hp_mult;

  const hudWaveTotal = document.getElementById("hud-wave-total");
  if (hudWaveTotal) hudWaveTotal.textContent = TOTAL_WAVES !== null ? ` / ${TOTAL_WAVES}` : "(エンドレス)";

  // 敵が通る道(セルの[row,col]の並び)。連続するマスは必ず上下左右に隣接する
  const PATH = [
    [2, 0], [2, 1], [2, 2], [1, 2], [0, 2], [0, 3], [0, 4], [1, 4], [2, 4], [3, 4], [4, 4],
    [4, 5], [4, 6], [3, 6], [2, 6], [1, 6], [0, 6], [0, 7],
  ];
  const PATH_SET = new Set(PATH.map(([r, c]) => r * GRID_COLS + c));

  const setupScreen = document.getElementById("setup-screen");
  if (!setupScreen) return; // キャラクター未所持の場合はゲーム自体を初期化しない

  // スクワッドの非ホストは、自分ではバトルを動かさず待機画面を出す
  if (SQUAD && !SQUAD.is_host) {
    setupScreen.style.display = "none";
    const waitEl = document.createElement("div");
    waitEl.className = "panel";
    waitEl.innerHTML = "<h3>ホストの操作を待っています…</h3><p class='text-muted' style='font-size:13px;'>ホストがバトルを開始・プレイすると、結果に応じて全員に報酬が配られます。このページを開いたままお待ちください。</p>";
    setupScreen.parentNode.insertBefore(waitEl, setupScreen);
    return;
  }

  const rosterGrid = document.getElementById("roster-grid");
  const selectedCountEl = document.getElementById("selected-count");
  const toPlacementBtn = document.getElementById("to-placement-btn");
  const placementScreen = document.getElementById("placement-screen");
  const placementRoster = document.getElementById("placement-roster");
  const tdGrid = document.getElementById("td-grid");
  const startWaveBtn = document.getElementById("start-wave-btn");
  const battleHud = document.getElementById("battle-hud");
  const hudLives = document.getElementById("hud-lives");
  const hudWave = document.getElementById("hud-wave");
  const hudKills = document.getElementById("hud-kills");
  const resultScreen = document.getElementById("result-screen");
  const resultTitle = document.getElementById("result-title");
  const resultDetail = document.getElementById("result-detail");
  const restartBtn = document.getElementById("restart-btn");

  let selectedCharacters = []; // 出撃メンバー(選択済み、まだ配置前)
  let placedTowers = []; // { char, row, col, cooldown }
  let activePlacementChar = null;

  // ───────── メンバー選択 ─────────
  if (SQUAD) {
    // スクワッドモードでは、参加者全員の持ち寄りキャラクターを自動的に全員選択済みにする
    rosterGrid.querySelectorAll(".td-roster-item").forEach((item) => {
      const key = item.dataset.key;
      selectedCharacters.push({
        key, realKey: item.dataset.realkey, name: item.dataset.name, icon: item.dataset.icon,
        attack: parseFloat(item.dataset.attack), range: parseFloat(item.dataset.range),
        speed: parseFloat(item.dataset.speed), splash: parseFloat(item.dataset.splash),
        color: item.dataset.color, rarity: item.dataset.rarity,
      });
    });
    setupScreen.style.display = "none";
    placementScreen.style.display = "block";
    buildGrid();
    renderPlacementRoster();
  } else {
    rosterGrid.querySelectorAll(".td-roster-item").forEach((item) => {
      item.addEventListener("click", () => {
        const key = item.dataset.key;
        const idx = selectedCharacters.findIndex((c) => c.key === key);
        if (idx >= 0) {
          selectedCharacters.splice(idx, 1);
          item.classList.remove("selected");
        } else {
          if (selectedCharacters.length >= MAX_TEAM) return;
          selectedCharacters.push({
            key, realKey: item.dataset.realkey, name: item.dataset.name, icon: item.dataset.icon,
            attack: parseFloat(item.dataset.attack), range: parseFloat(item.dataset.range),
            speed: parseFloat(item.dataset.speed), splash: parseFloat(item.dataset.splash),
            color: item.dataset.color, rarity: item.dataset.rarity,
          });
          item.classList.add("selected");
        }
        selectedCountEl.textContent = String(selectedCharacters.length);
        toPlacementBtn.disabled = selectedCharacters.length === 0;
      });
    });

    toPlacementBtn.addEventListener("click", () => {
      setupScreen.style.display = "none";
      placementScreen.style.display = "block";
      buildGrid();
      renderPlacementRoster();
    });
  }

  // ───────── グリッド構築 ─────────
  function buildGrid() {
    tdGrid.innerHTML = "";
    for (let r = 0; r < GRID_ROWS; r++) {
      for (let c = 0; c < GRID_COLS; c++) {
        const cell = document.createElement("div");
        const idx = r * GRID_COLS + c;
        cell.className = "td-cell " + (PATH_SET.has(idx) ? "path" : "buildable");
        cell.dataset.row = r;
        cell.dataset.col = c;
        if (!PATH_SET.has(idx)) {
          cell.addEventListener("click", () => placeOnCell(r, c, cell));
        }
        tdGrid.appendChild(cell);
      }
    }
  }

  function renderPlacementRoster() {
    placementRoster.innerHTML = "";
    selectedCharacters.forEach((c) => {
      const isPlaced = placedTowers.some((t) => t.uid === c.uid);
      const el = document.createElement("div");
      el.className = "panel td-roster-item" + (isPlaced ? " placed" : "");
      el.style.cssText = "flex: 0 0 64px; text-align:center; padding: 8px; border-color:" + c.color;
      el.innerHTML = `<div style="font-size:22px;">${c.icon}</div><div style="font-size:9px;">${c.name}</div>`;
      if (!isPlaced) {
        el.addEventListener("click", () => {
          activePlacementChar = c;
          Array.from(placementRoster.children).forEach((child) => child.style.outline = "none");
          el.style.outline = "2px solid var(--gold)";
        });
      }
      placementRoster.appendChild(el);
    });
  }

  let uidCounter = 0;
  function placeOnCell(row, col, cellEl) {
    if (!activePlacementChar) return;
    if (placedTowers.some((t) => t.row === row && t.col === col)) return;

    activePlacementChar.uid = activePlacementChar.uid || `u${uidCounter++}`;
    placedTowers.push({
      ...activePlacementChar, row, col, cooldownLeft: 0,
    });

    const towerEl = document.createElement("div");
    towerEl.className = "td-tower";
    towerEl.textContent = activePlacementChar.icon;
    towerEl.style.borderColor = activePlacementChar.color;
    towerEl.dataset.uid = activePlacementChar.uid;
    cellEl.appendChild(towerEl);
    cellEl.classList.remove("buildable");

    activePlacementChar = null;
    renderPlacementRoster();
    startWaveBtn.disabled = placedTowers.length === 0;
  }

  // ───────── バトル本体 ─────────
  let lives = START_LIVES;
  let currentWave = 0;
  let kills = 0;
  let enemies = [];
  let enemyUidCounter = 0;
  let spawnQueue = [];
  let spawnTimer = 0;
  let running = false;
  let lastFrameTime = 0;
  let battleEnded = false;

  function waveConfig(wave) {
    if (MODE === "lastboss") {
      // ラスボスモードは1体だけの非常に頑丈な敵と戦う特別な構成
      return {
        count: 1, hp: Math.round(3200 * DIFFICULTY), speed: 0.75, spawnInterval: 0, livesCost: 5, isBoss: true,
      };
    }
    const count = Math.round((5 + wave) * (1 + (DIFFICULTY - 1) * 0.5));
    const hp = Math.round((18 + wave * 7) * DIFFICULTY);
    const speed = 0.9 + wave * 0.035; // セル/秒
    const spawnInterval = Math.max(0.2, (0.75 - wave * 0.025) / Math.max(1, DIFFICULTY * 0.7));
    const livesCost = wave % 4 === 0 ? 2 : 1; // 4の倍数のウェーブは強敵で被害2倍
    return { count, hp, speed, spawnInterval, livesCost };
  }

  startWaveBtn.addEventListener("click", () => {
    placementScreen.style.display = "none";
    battleHud.style.display = "block";
    startWaveBtn.disabled = true;
    running = true;
    lastFrameTime = performance.now();
    startNextWave();
    requestAnimationFrame(gameLoop);
  });

  function startNextWave() {
    currentWave += 1;
    hudWave.textContent = String(currentWave);
    hudLives.textContent = String(lives);
    hudKills.textContent = String(kills);
    const cfg = waveConfig(currentWave);
    spawnQueue = Array(cfg.count).fill(cfg);
    spawnTimer = 0;
  }

  function cellCenter(row, col) {
    return { x: (col + 0.5) / GRID_COLS * 100, y: (row + 0.5) / GRID_ROWS * 100 };
  }

  function positionOnPath(t) {
    const i = Math.min(Math.floor(t), PATH.length - 2);
    const frac = t - i;
    const [r0, c0] = PATH[i];
    const [r1, c1] = PATH[i + 1];
    const row = r0 + (r1 - r0) * frac;
    const col = c0 + (c1 - c0) * frac;
    return { row, col, x: (col + 0.5) / GRID_COLS * 100, y: (row + 0.5) / GRID_ROWS * 100 };
  }

  function spawnEnemy(cfg) {
    const uid = `e${enemyUidCounter++}`;
    const el = document.createElement("div");
    el.className = "td-enemy";
    const emoji = cfg.isBoss ? "👑" : (currentWave % 4 === 0 ? "👹" : "🐛");
    if (cfg.isBoss) el.style.fontSize = "160%";
    el.innerHTML = `<span>${emoji}</span><div class="td-enemy-hp"><div class="td-enemy-hp-fill" style="width:100%;"></div></div>`;
    tdGrid.appendChild(el);
    enemies.push({
      uid, el, t: 0, hp: cfg.hp, maxHp: cfg.hp, speed: cfg.speed, livesCost: cfg.livesCost, dead: false,
    });
  }

  function spawnProjectile(fromRow, fromCol, toX, toY, color) {
    const from = cellCenter(fromRow, fromCol);
    const el = document.createElement("div");
    el.className = "td-projectile";
    el.style.left = from.x + "%";
    el.style.top = from.y + "%";
    el.style.background = color || "var(--ember)";
    tdGrid.appendChild(el);
    requestAnimationFrame(() => {
      el.style.transition = "left 0.15s linear, top 0.15s linear, opacity 0.15s linear";
      el.style.left = toX + "%";
      el.style.top = toY + "%";
    });
    setTimeout(() => el.remove(), 180);
  }

  function gameLoop(now) {
    if (!running) return;
    const dt = Math.min(0.05, (now - lastFrameTime) / 1000);
    lastFrameTime = now;

    // 敵のスポーン
    if (spawnQueue.length > 0) {
      spawnTimer -= dt;
      if (spawnTimer <= 0) {
        const cfg = spawnQueue.shift();
        spawnEnemy(cfg);
        spawnTimer = cfg.spawnInterval;
      }
    }

    // 敵の移動
    for (const enemy of enemies) {
      if (enemy.dead) continue;
      enemy.t += enemy.speed * dt;
      if (enemy.t >= PATH.length - 1) {
        enemy.dead = true;
        enemy.leaked = true;
        lives -= enemy.livesCost;
        enemy.el.remove();
        continue;
      }
      const pos = positionOnPath(enemy.t);
      enemy.row = pos.row;
      enemy.col = pos.col;
      enemy.el.style.left = pos.x + "%";
      enemy.el.style.top = pos.y + "%";
    }

    // タワーの攻撃
    for (const tower of placedTowers) {
      tower.cooldownLeft = (tower.cooldownLeft || 0) - dt;
      if (tower.cooldownLeft > 0) continue;

      const tCenter = { row: tower.row + 0.5, col: tower.col + 0.5 };
      let target = null;
      let bestT = -1;
      for (const enemy of enemies) {
        if (enemy.dead) continue;
        const dist = Math.hypot(enemy.row + 0.5 - tCenter.row, enemy.col + 0.5 - tCenter.col);
        if (dist <= tower.range && enemy.t > bestT) {
          bestT = enemy.t;
          target = enemy;
        }
      }

      if (target) {
        tower.cooldownLeft = tower.speed;
        const targets = tower.splash > 0
          ? enemies.filter((e) => !e.dead && Math.hypot(e.row - target.row, e.col - target.col) <= tower.splash)
          : [target];

        for (const t of targets) {
          t.hp -= tower.attack;
        }
        const targetPos = positionOnPath(target.t);
        spawnProjectile(tower.row, tower.col, targetPos.x, targetPos.y, tower.color);

        const towerEl = tdGrid.querySelector(`.td-tower[data-uid="${tower.uid}"]`);
        if (towerEl) {
          towerEl.classList.remove("attacking");
          void towerEl.offsetWidth;
          towerEl.classList.add("attacking");
        }
      }
    }

    // 死亡判定・描画更新
    enemies = enemies.filter((enemy) => {
      if (enemy.dead) return false;
      if (enemy.hp <= 0) {
        kills += 1;
        enemy.el.remove();
        return false;
      }
      const fill = enemy.el.querySelector(".td-enemy-hp-fill");
      if (fill) fill.style.width = Math.max(0, (enemy.hp / enemy.maxHp) * 100) + "%";
      return true;
    });

    hudLives.textContent = String(Math.max(0, lives));
    hudKills.textContent = String(kills);

    if (lives <= 0) {
      endBattle(false);
      return;
    }

    if (spawnQueue.length === 0 && enemies.length === 0 && !battleEnded) {
      if (TOTAL_WAVES !== null && currentWave >= TOTAL_WAVES) {
        endBattle(true);
        return;
      }
      battleEnded = "waiting"; // 次ウェーブ開始までの二重発火防止
      setTimeout(() => {
        if (running) startNextWave();
        battleEnded = false;
      }, 1500);
    }

    requestAnimationFrame(gameLoop);
  }

  async function endBattle(victory) {
    running = false;
    battleHud.style.display = "none";
    resultScreen.style.display = "block";
    resultTitle.textContent = victory ? "🏆 勝利!" : (MODE === "endless" ? "💥 力尽きました" : "💥 拠点が陥落しました");
    resultTitle.style.color = victory ? "var(--win)" : "var(--loss)";

    const wavesCleared = victory ? (TOTAL_WAVES || currentWave) : Math.max(0, currentWave - 1);
    resultDetail.textContent = `${wavesCleared}${TOTAL_WAVES !== null ? " / " + TOTAL_WAVES : ""} ウェーブ撃破 ・ 撃破数 ${kills}`;

    try {
      if (SQUAD) {
        const data = await EmberPlay.postJSON(`/squad/room/${SQUAD.room_id}/complete`, {
          waves_cleared: wavesCleared, mode: MODE,
        });
        resultDetail.textContent += ` ・ 参加者全員に +${data.reward_each} Embers(${data.member_count}人)`;
        EmberPlay.updateBalance(data.balance, null);
      } else {
        const usedKeys = [...new Set(placedTowers.map((t) => t.realKey))];
        const data = await EmberPlay.postJSON("/towerdefense/complete", {
          waves_cleared: wavesCleared, characters_used: usedKeys, mode: MODE,
        });
        resultDetail.textContent += ` ・ +${data.reward} Embers`;
        EmberPlay.updateBalance(data.balance, victory ? "win" : null);
      }
    } catch (err) {
      resultDetail.textContent += " ・ 報酬の反映に失敗しました";
    }
  }

  restartBtn.addEventListener("click", () => location.reload());
})();
