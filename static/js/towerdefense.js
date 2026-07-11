(function () {
  const GRID_COLS = 8;
  const GRID_ROWS = 5;
  const MODE = window.TD_MODE || "normal";
  const MODE_CFG = (window.TD_MODES || {})[MODE] || { waves: 10, hp_mult: 1.0 };
  const TOTAL_WAVES = MODE_CFG.waves; // nullならエンドレス(上限なし)
  const MAX_TEAM = window.TD_MAX_TEAM || 6;
  const START_LIVES = 20;
  const MAX_LIVES = 30; // regenアビリティでの回復上限
  const START_GOLD = 150;
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
  const fxLayer = document.getElementById("td-fx-layer") || tdGrid;
  const startWaveBtn = document.getElementById("start-wave-btn");
  const battleHud = document.getElementById("battle-hud");
  const hudLives = document.getElementById("hud-lives");
  const hudWave = document.getElementById("hud-wave");
  const hudKills = document.getElementById("hud-kills");
  const hudGold = document.getElementById("hud-gold");
  const upgradePanel = document.getElementById("upgrade-panel");
  const resultScreen = document.getElementById("result-screen");
  const resultTitle = document.getElementById("result-title");
  const resultDetail = document.getElementById("result-detail");
  const restartBtn = document.getElementById("restart-btn");

  let selectedCharacters = []; // 出撃メンバー(選択済み、まだ配置前)
  let placedTowers = []; // { char, row, col, cooldown, level, abilities }
  let activePlacementChar = null;

  function parseAbilities(raw) {
    try {
      return JSON.parse(raw || "[]");
    } catch (e) {
      return [];
    }
  }

  function charFromDataset(item) {
    return {
      key: item.dataset.key, realKey: item.dataset.realkey, name: item.dataset.name, icon: item.dataset.icon,
      attack: parseFloat(item.dataset.attack), range: parseFloat(item.dataset.range),
      speed: parseFloat(item.dataset.speed), splash: parseFloat(item.dataset.splash),
      color: item.dataset.color, rarity: item.dataset.rarity, abilities: parseAbilities(item.dataset.abilities),
    };
  }

  // ───────── メンバー選択 ─────────
  if (SQUAD) {
    // スクワッドモードでは、参加者全員の持ち寄りキャラクターを自動的に全員選択済みにする
    rosterGrid.querySelectorAll(".td-roster-item").forEach((item) => {
      selectedCharacters.push(charFromDataset(item));
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
          selectedCharacters.push(charFromDataset(item));
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

  function abilityIcons(abilities) {
    const ICONS = {
      aoe: "💥", splash: "🌊", poison: "☠️", fire: "🔥", slow: "🧊", stun: "⭐",
      pierce: "🏹", lifesteal: "🩸", crit_boost: "✨", armor_break: "🔨", regen: "💚", gold_boost: "💰",
    };
    return (abilities || []).map((a) => ICONS[a] || "").join("");
  }

  function renderPlacementRoster() {
    placementRoster.innerHTML = "";
    selectedCharacters.forEach((c) => {
      const isPlaced = placedTowers.some((t) => t.uid === c.uid);
      const el = document.createElement("div");
      el.className = "panel td-roster-item" + (isPlaced ? " placed" : "");
      el.style.cssText = "flex: 0 0 68px; text-align:center; padding: 8px; border-color:" + c.color;
      el.innerHTML = `<div style="font-size:22px;">${c.icon}</div><div style="font-size:9px;">${c.name}</div><div style="font-size:10px;">${abilityIcons(c.abilities)}</div>`;
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
      ...activePlacementChar, row, col, cooldownLeft: 0, level: 0,
    });

    const towerEl = document.createElement("div");
    towerEl.className = "td-tower";
    towerEl.innerHTML = `<span class="td-tower-icon">${activePlacementChar.icon}</span>`;
    towerEl.style.borderColor = activePlacementChar.color;
    towerEl.dataset.uid = activePlacementChar.uid;
    cellEl.appendChild(towerEl);
    cellEl.classList.remove("buildable");
    const placedUid = activePlacementChar.uid;
    towerEl.addEventListener("click", (e) => {
      e.stopPropagation();
      if (running) openUpgradePanel(placedUid);
    });

    activePlacementChar = null;
    renderPlacementRoster();
    startWaveBtn.disabled = placedTowers.length === 0;
  }

  // ───────── タワーのアップグレード ─────────
  function upgradeCost(tower) {
    return Math.round(35 * Math.pow(1.6, tower.level));
  }

  function openUpgradePanel(uid) {
    const tower = placedTowers.find((t) => t.uid === uid);
    if (!tower || !upgradePanel) return;
    const cost = upgradeCost(tower);
    upgradePanel.style.display = "block";
    upgradePanel.innerHTML = `
      <div style="display:flex; justify-content: space-between; align-items:center;">
        <div><strong>${tower.icon} ${tower.name}</strong> ・ Lv.${tower.level + 1}</div>
        <button type="button" id="upgrade-close" class="btn btn-ghost" style="padding:2px 8px; font-size:11px;">✕</button>
      </div>
      <p class="mono text-muted" style="font-size:12px; margin:4px 0;">現在の攻撃力: ${tower.attack.toFixed(1)}</p>
      <button type="button" id="upgrade-buy" class="btn btn-ember" style="font-size:12px; padding:6px 12px;">
        ${cost}💰 でアップグレード(攻撃力+20%)
      </button>
    `;
    document.getElementById("upgrade-close").addEventListener("click", () => { upgradePanel.style.display = "none"; });
    document.getElementById("upgrade-buy").addEventListener("click", () => {
      if (gold < cost) { alert("ゴールドが足りません。"); return; }
      gold -= cost;
      tower.attack = Math.round(tower.attack * 1.2 * 10) / 10;
      tower.level += 1;
      updateGoldDisplay();
      openUpgradePanel(uid);
    });
  }

  // ───────── バトル本体 ─────────
  let lives = START_LIVES;
  let gold = START_GOLD;
  let currentWave = 0;
  let kills = 0;
  let enemies = [];
  let enemyUidCounter = 0;
  let spawnQueue = [];
  let spawnTimer = 0;
  let running = false;
  let lastFrameTime = 0;
  let battleEnded = false;
  let regenTimer = 0;

  function updateGoldDisplay() {
    if (hudGold) hudGold.textContent = String(gold);
  }

  let speedMultiplier = 1;
  document.querySelectorAll(".speed-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      speedMultiplier = parseInt(btn.dataset.speed, 10);
      document.querySelectorAll(".speed-btn").forEach((b) => {
        b.classList.toggle("btn-ember", b === btn);
        b.classList.toggle("btn-ghost", b !== btn);
      });
    });
  });

  function waveConfig(wave) {
    if (MODE === "lastboss") {
      // ラスボスモードは1体だけの非常に頑丈な敵と戦う特別な構成(通常モードの何倍もの強さ)
      return {
        count: 1, hp: Math.round(9000 * DIFFICULTY), speed: 0.65, spawnInterval: 0, livesCost: 8, isBoss: true,
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
    updateGoldDisplay();
    startNextWave();
    requestAnimationFrame(gameLoop);
  });

  function goldBoostCount() {
    return placedTowers.filter((t) => t.abilities.includes("gold_boost")).length;
  }

  function grantWaveGold() {
    const base = 25 + currentWave * 4;
    const bonus = Math.round(base * goldBoostCount() * 0.3);
    gold += base + bonus;
    updateGoldDisplay();
  }

  function startNextWave() {
    if (currentWave > 0) grantWaveGold(); // 2ウェーブ目以降、前のウェーブクリア分のゴールドを付与
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
    el.innerHTML = `<div class="td-enemy-shadow"></div><span class="td-enemy-sprite">${emoji}</span><div class="td-enemy-hp"><div class="td-enemy-hp-fill" style="width:100%;"></div></div>`;
    tdGrid.appendChild(el);
    enemies.push({
      uid, el, t: 0, hp: cfg.hp, maxHp: cfg.hp, baseSpeed: cfg.speed, speed: cfg.speed,
      livesCost: cfg.livesCost, dead: false,
      poison: null, fire: null, slowUntil: 0, stunUntil: 0, armorBreakUntil: 0,
    });
  }

  function spawnBeam(fromRow, fromCol, toX, toY, color) {
    const from = cellCenter(fromRow, fromCol);
    const rect = tdGrid.getBoundingClientRect();
    const dx = (toX - from.x) / 100 * rect.width;
    const dy = (toY - from.y) / 100 * rect.height;
    const length = Math.hypot(dx, dy);
    const angle = Math.atan2(dy, dx) * (180 / Math.PI);

    const el = document.createElement("div");
    el.className = "td-beam";
    el.style.left = from.x + "%";
    el.style.top = from.y + "%";
    el.style.width = length + "px";
    el.style.background = `linear-gradient(90deg, ${color || "var(--ember)"}, transparent)`;
    el.style.transform = `rotate(${angle}deg)`;
    fxLayer.appendChild(el);
    setTimeout(() => el.remove(), 200);
  }

  function spawnProjectile(fromRow, fromCol, toX, toY, color) {
    const from = cellCenter(fromRow, fromCol);
    const c = color || "var(--ember)";
    const el = document.createElement("div");
    el.className = "td-projectile";
    el.style.left = from.x + "%";
    el.style.top = from.y + "%";
    el.innerHTML = `
      <svg viewBox="0 0 20 20" width="16" height="16">
        <circle cx="10" cy="10" r="7" fill="${c}" opacity="0.9"/>
        <circle cx="10" cy="10" r="9" fill="none" stroke="${c}" stroke-width="1.5" opacity="0.5"/>
      </svg>`;
    el.style.filter = `drop-shadow(0 0 6px ${c})`;
    fxLayer.appendChild(el);

    // 弾が通った跡が一瞬光の尾を引くように、複数の残像を等間隔で残す
    const steps = 4;
    for (let i = 1; i <= steps; i++) {
      setTimeout(() => {
        const trail = document.createElement("div");
        trail.className = "td-projectile-trail";
        trail.style.left = (from.x + (toX - from.x) * (i / steps)) + "%";
        trail.style.top = (from.y + (toY - from.y) * (i / steps)) + "%";
        trail.style.background = c;
        fxLayer.appendChild(trail);
        setTimeout(() => trail.remove(), 180);
      }, i * 15);
    }

    requestAnimationFrame(() => {
      el.style.transition = "left 0.22s ease-out, top 0.22s ease-out, opacity 0.22s linear";
      el.style.left = toX + "%";
      el.style.top = toY + "%";
    });
    setTimeout(() => el.remove(), 260);
  }

  function spawnDamageNumber(x, y, amount, kind) {
    const el = document.createElement("div");
    el.className = "td-dmg-number" + (kind ? ` td-dmg-${kind}` : "");
    el.textContent = kind === "heal" ? `+${amount}` : `-${Math.round(amount)}`;
    // 同時多発の数字が完全に重なって読めなくならないよう、わずかに横方向へばらける
    const jitter = (Math.random() - 0.5) * 4;
    el.style.left = (x + jitter) + "%";
    el.style.top = y + "%";
    fxLayer.appendChild(el);
    setTimeout(() => el.remove(), 900);
  }

  function spawnDeathEffect(x, y) {
    const el = document.createElement("div");
    el.className = "td-death-fx";
    el.style.left = x + "%";
    el.style.top = y + "%";
    el.textContent = "💥";
    fxLayer.appendChild(el);
    setTimeout(() => el.remove(), 500);
  }

  function flashEnemyHit(enemy) {
    enemy.el.classList.remove("td-hit-flash");
    void enemy.el.offsetWidth;
    enemy.el.classList.add("td-hit-flash");
  }

  function spawnImpact(x, y, color) {
    const el = document.createElement("div");
    el.className = "td-impact-fx";
    el.style.left = x + "%";
    el.style.top = y + "%";
    const c = color || "#ffffff";
    // 絵文字ではなく実際のSVGで斬撃(スラッシュ)の軌跡を描画する
    el.innerHTML = `
      <svg viewBox="0 0 100 100" width="46" height="46">
        <path d="M15 75 Q50 10 90 30" stroke="${c}" stroke-width="7" fill="none" stroke-linecap="round" opacity="0.95"/>
        <path d="M20 85 Q55 25 85 15" stroke="#ffffff" stroke-width="3" fill="none" stroke-linecap="round" opacity="0.8"/>
      </svg>`;
    fxLayer.appendChild(el);
    setTimeout(() => el.remove(), 280);
  }

  function spawnHitSpark(x, y) {
    const el = document.createElement("div");
    el.className = "td-spark-fx";
    el.style.left = x + "%";
    el.style.top = y + "%";
    el.innerHTML = `
      <svg viewBox="0 0 40 40" width="30" height="30">
        <g stroke="#fff" stroke-width="3" stroke-linecap="round">
          <line x1="20" y1="2" x2="20" y2="12"/>
          <line x1="20" y1="28" x2="20" y2="38"/>
          <line x1="2" y1="20" x2="12" y2="20"/>
          <line x1="28" y1="20" x2="38" y2="20"/>
        </g>
      </svg>`;
    fxLayer.appendChild(el);
    setTimeout(() => el.remove(), 200);
  }

  function knockbackEnemy(enemy) {
    if (enemy.dead) return;
    enemy.el.classList.remove("td-knockback");
    void enemy.el.offsetWidth;
    enemy.el.classList.add("td-knockback");
  }

  function applyDamage(enemy, amount) {
    let dmg = amount;
    if (enemy.armorBreakUntil > performance.now()) dmg *= 1.2;
    enemy.hp -= dmg;
    const pos = positionOnPath(enemy.t);
    spawnDamageNumber(pos.x, pos.y, dmg);
    flashEnemyHit(enemy);
  }

  function applyOnHitEffects(enemy, tower, abilities, now) {
    if (abilities.includes("poison")) {
      enemy.poison = { damage: Math.max(1, Math.round(tower.attack * 0.15)), ticksLeft: 4, timer: 0.6, interval: 0.6 };
    }
    if (abilities.includes("fire")) {
      enemy.fire = { damage: Math.max(1, Math.round(tower.attack * 0.25)), ticksLeft: 3, timer: 0.5, interval: 0.5 };
    }
    if (abilities.includes("slow")) {
      enemy.slowUntil = now + 2000;
    }
    if (abilities.includes("stun") && Math.random() < 0.2) {
      enemy.stunUntil = now + 600;
    }
    if (abilities.includes("armor_break")) {
      enemy.armorBreakUntil = now + 3000;
    }
  }

  function gameLoop(now) {
    if (!running) return;
    const dt = Math.min(0.05, (now - lastFrameTime) / 1000) * speedMultiplier;
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

    // regenアビリティ: 5秒ごとにライフ回復
    if (placedTowers.some((t) => t.abilities.includes("regen"))) {
      regenTimer += dt;
      if (regenTimer >= 5) {
        regenTimer = 0;
        if (lives < MAX_LIVES) {
          lives = Math.min(MAX_LIVES, lives + 1);
        }
      }
    }

    // 敵の移動・状態異常の処理
    for (const enemy of enemies) {
      if (enemy.dead) continue;

      // 毒・炎のダメージオーバータイム処理
      for (const dot of [enemy.poison, enemy.fire]) {
        if (dot && dot.ticksLeft > 0) {
          dot.timer -= dt;
          if (dot.timer <= 0) {
            enemy.hp -= dot.damage;
            dot.ticksLeft -= 1;
            dot.timer = dot.interval;
            const pos = positionOnPath(enemy.t);
            spawnDamageNumber(pos.x, pos.y, dot.damage, dot === enemy.poison ? "poison" : "fire");
          }
        }
      }

      // 鈍足・気絶の解除判定
      const isSlowed = enemy.slowUntil > now;
      const isStunned = enemy.stunUntil > now;
      const currentSpeed = isStunned ? 0 : (isSlowed ? enemy.baseSpeed * 0.5 : enemy.baseSpeed);

      enemy.t += currentSpeed * dt;
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
      enemy.el.classList.toggle("td-enemy-slowed", isSlowed && !isStunned);
      enemy.el.classList.toggle("td-enemy-stunned", isStunned);
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
        const abilities = tower.abilities || [];
        const hasAoe = tower.splash > 0 || abilities.includes("aoe") || abilities.includes("splash");
        const splashRadius = Math.max(tower.splash, hasAoe ? 1 : 0);

        let targets = splashRadius > 0
          ? enemies.filter((e) => !e.dead && Math.hypot(e.row - target.row, e.col - target.col) <= splashRadius)
          : [target];

        // 貫通: 経路上でtargetより先(t値が大きい)にいる、最も近い別の敵にも追加ダメージ
        let pierceTarget = null;
        if (abilities.includes("pierce")) {
          pierceTarget = enemies
            .filter((e) => !e.dead && e !== target && !targets.includes(e) && e.t > target.t)
            .sort((a, b) => a.t - b.t)[0] || null;
        }

        const isCrit = Math.random() < (abilities.includes("crit_boost") ? 0.35 : 0.08);

        for (const real of targets) {
          if (real.dead) continue;
          const dmg = tower.attack * (isCrit ? 1.6 : 1);
          applyDamage(real, dmg);
          applyOnHitEffects(real, tower, abilities, now);
        }
        if (pierceTarget) {
          const dmg = tower.attack * 0.5 * (isCrit ? 1.6 : 1);
          applyDamage(pierceTarget, dmg);
          applyOnHitEffects(pierceTarget, tower, abilities, now);
        }

        if (abilities.includes("lifesteal") && Math.random() < 0.05 && lives < MAX_LIVES) {
          lives += 1;
          const pos = positionOnPath(target.t);
          spawnDamageNumber(pos.x, pos.y, 1, "heal");
        }

        const targetPos = positionOnPath(target.t);
        spawnBeam(tower.row, tower.col, targetPos.x, targetPos.y, tower.color);
        spawnProjectile(tower.row, tower.col, targetPos.x, targetPos.y, tower.color);

        const towerEl = tdGrid.querySelector(`.td-tower[data-uid="${tower.uid}"]`);
        if (towerEl) {
          // タワーを攻撃対象の方向へ向ける(実際に狙って戦っている様子を出す)
          const tCenterPx = cellCenter(tower.row, tower.col);
          const angle = Math.atan2(targetPos.y - tCenterPx.y, targetPos.x - tCenterPx.x) * (180 / Math.PI);
          towerEl.style.transform = `rotate(${angle}deg)`;
          const iconEl = towerEl.querySelector(".td-tower-icon");
          if (iconEl) iconEl.style.transform = `rotate(${-angle}deg)`; // アイコン自体の向きは正立させる

          towerEl.classList.remove("attacking");
          void towerEl.offsetWidth;
          towerEl.classList.add("attacking");
        }

        // 弾が着弾するタイミングで、命中の斬撃エフェクト+火花+敵のノックバックを発生させる(戦っている様子の演出)
        setTimeout(() => {
          spawnImpact(targetPos.x, targetPos.y, tower.color);
          spawnHitSpark(targetPos.x, targetPos.y);
          knockbackEnemy(target);
        }, 140);
      }
    }

    // 死亡判定・描画更新
    enemies = enemies.filter((enemy) => {
      if (enemy.dead) return false;
      if (enemy.hp <= 0) {
        kills += 1;
        const pos = positionOnPath(enemy.t);
        spawnDeathEffect(pos.x, pos.y);
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
        grantWaveGold();
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
    if (upgradePanel) upgradePanel.style.display = "none";
    resultScreen.style.display = "block";
    resultTitle.textContent = victory ? "🏆 勝利!" : (MODE === "endless" ? "💥 力尽きました" : "💥 拠点が陥落しました");
    resultTitle.style.color = victory ? "var(--win)" : "var(--loss)";

    const wavesCleared = victory ? (TOTAL_WAVES || currentWave) : Math.max(0, currentWave - 1);
    resultDetail.textContent = `${wavesCleared}${TOTAL_WAVES !== null ? " / " + TOTAL_WAVES : ""} ウェーブ撃破 ・ 撃破数 ${kills} ・ 残りゴールド ${gold}`;

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
        if (MODE === "endless" && data.rank_message) {
          resultDetail.textContent += ` ・ ${data.rank_message}`;
        }
      }
    } catch (err) {
      resultDetail.textContent += " ・ 報酬の反映に失敗しました";
    }
  }

  restartBtn.addEventListener("click", () => location.reload());
})();
