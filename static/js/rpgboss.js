(function () {
  const selectScreen = document.getElementById("select-screen");
  if (!selectScreen) return;

  const battleBtn = document.getElementById("battle-btn");
  const selectedCountEl = document.getElementById("selected-count");
  const battleScreen = document.getElementById("battle-screen");
  const bossLabel = document.getElementById("boss-label");
  const bossHpBar = document.getElementById("boss-hp-bar");
  const bossHpText = document.getElementById("boss-hp-text");
  const teamHpBar = document.getElementById("team-hp-bar");
  const teamHpText = document.getElementById("team-hp-text");
  const turnLog = document.getElementById("turn-log");
  const resultReadout = document.getElementById("result-readout");
  const bossSprite = document.getElementById("rpg-boss-sprite");
  const teamSprites = document.getElementById("rpg-team-sprites");
  const rpgFxLayer = document.getElementById("rpg-fx-layer");
  const manualControls = document.getElementById("manual-controls");
  const attackBtn = document.getElementById("attack-btn");
  const spellButtonsEl = document.getElementById("spell-buttons");

  let selected = [];
  let mode = "normal";
  const MAX_TEAM = window.RPG_MAX_TEAM || 6;
  const BOSS_ICONS = { normal: "👹", raid: "🔥👹", lastboss: "💀👑" };

  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("selected", "btn-ember"));
      document.querySelectorAll(".mode-btn").forEach((b) => b.classList.add("btn-ghost"));
      btn.classList.add("selected", "btn-ember");
      btn.classList.remove("btn-ghost");
      mode = btn.dataset.mode;
    });
  });
  document.querySelector('.mode-btn[data-mode="normal"]').classList.add("btn-ember");

  document.querySelectorAll(".char-pick").forEach((item) => {
    item.addEventListener("click", () => {
      const key = item.dataset.key;
      const idx = selected.indexOf(key);
      if (idx >= 0) {
        selected.splice(idx, 1);
        item.style.outline = "none";
      } else {
        if (selected.length >= MAX_TEAM) return;
        selected.push(key);
        item.style.outline = "2px solid var(--gold)";
      }
      selectedCountEl.textContent = String(selected.length);
      battleBtn.disabled = selected.length === 0;
    });
  });

  function spawnDamageNumber(target, amount, kind) {
    if (!rpgFxLayer) return;
    const rect = target.getBoundingClientRect();
    const arenaRect = document.getElementById("rpg-arena").getBoundingClientRect();
    const x = ((rect.left + rect.width / 2 - arenaRect.left) / arenaRect.width) * 100;
    const y = ((rect.top - arenaRect.top) / arenaRect.height) * 100;
    const el = document.createElement("div");
    el.className = "rpg-dmg-number" + (kind === "heal" ? " heal" : "");
    el.textContent = kind === "heal" ? `+${amount}` : `-${amount}`;
    el.style.left = x + "%";
    el.style.top = Math.max(5, y) + "%";
    rpgFxLayer.appendChild(el);
    setTimeout(() => el.remove(), 800);
  }

  function flashBoss() {
    bossSprite.classList.remove("rpg-hit");
    void bossSprite.offsetWidth;
    bossSprite.classList.add("rpg-hit");
  }

  battleBtn.addEventListener("click", async () => {
    battleBtn.disabled = true;
    try {
      if (mode === "endless") {
        const data = await EmberPlay.postJSON("/rpgboss/battle", { characters: selected, mode });
        selectScreen.style.display = "none";
        battleScreen.style.display = "block";
        manualControls.style.display = "none";
        bossSprite.textContent = "♾️";
        teamSprites.innerHTML = "";
        playEndlessLog(data);
      } else {
        await startManualBattle();
      }
    } catch (err) {
      alert(err.message);
      battleBtn.disabled = false;
    }
  });

  // ───────── ボタン操作式バトル(通常/レイド/ラスボス) ─────────
  let battleState = null;
  let mySpells = [];
  let spellCooldowns = {};

  async function startManualBattle() {
    const data = await EmberPlay.postJSON("/rpgboss/battle/start", { characters: selected, mode });
    battleState = {
      boss_hp: data.boss_max_hp, boss_max_hp: data.boss_max_hp,
      team_hp: data.team_max_hp, team_max_hp: data.team_max_hp,
      boss_atk: data.boss_atk, turns: 0,
    };
    mySpells = data.spells || [];
    spellCooldowns = {};

    selectScreen.style.display = "none";
    battleScreen.style.display = "block";
    manualControls.style.display = "block";
    bossSprite.textContent = BOSS_ICONS[mode] || "👹";
    bossLabel.textContent = `${BOSS_ICONS[mode] || "👹"} ${data.boss_label}`;
    teamSprites.innerHTML = selected.map((key) => {
      const el = document.querySelector(`.char-pick[data-key="${key}"]`);
      return `<span class="rpg-team-icon">${el ? el.dataset.icon : "🧙"}</span>`;
    }).join("");

    renderBattleBars();
    renderSpellButtons();
    turnLog.textContent = "ボタンを押して攻撃しよう!";
    attackBtn.disabled = false;
    attackBtn.onclick = () => doTurn("attack");
  }

  function renderBattleBars() {
    bossHpBar.style.width = Math.max(0, (battleState.boss_hp / battleState.boss_max_hp) * 100) + "%";
    bossHpText.textContent = `${Math.round(battleState.boss_hp)} / ${battleState.boss_max_hp}`;
    teamHpBar.style.width = Math.max(0, (battleState.team_hp / battleState.team_max_hp) * 100) + "%";
    teamHpText.textContent = `${Math.round(battleState.team_hp)} / ${battleState.team_max_hp}`;
  }

  function renderSpellButtons() {
    spellButtonsEl.innerHTML = "";
    mySpells.forEach((spell) => {
      const onCooldown = (spellCooldowns[spell.key] || 0) > 0;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-ghost spell-btn" + (onCooldown ? " on-cooldown" : "");
      btn.innerHTML = `${spell.icon}<br><span style="font-size:10px;">${spell.name}${onCooldown ? `(あと${spellCooldowns[spell.key]})` : ""}</span>`;
      if (!onCooldown) btn.addEventListener("click", () => doTurn(spell.key));
      spellButtonsEl.appendChild(btn);
    });
  }

  async function doTurn(action) {
    attackBtn.disabled = true;
    Array.from(spellButtonsEl.children).forEach((b) => (b.style.pointerEvents = "none"));
    try {
      const data = await EmberPlay.postJSON("/rpgboss/turn", {
        characters: selected, mode, action,
        boss_hp: battleState.boss_hp, team_hp: battleState.team_hp,
        boss_atk: battleState.boss_atk, team_max_hp: battleState.team_max_hp,
      });

      battleState.turns += 1;
      flashBoss();
      spawnDamageNumber(bossSprite, data.team_damage, "damage");
      if (data.heal_amount > 0) spawnDamageNumber(teamSprites, data.heal_amount, "heal");
      if (data.boss_damage > 0) spawnDamageNumber(teamSprites, data.boss_damage, "damage");

      battleState.boss_hp = data.new_boss_hp;
      battleState.team_hp = data.new_team_hp;
      renderBattleBars();

      let logText = `ターン${battleState.turns}: `;
      if (action !== "attack") {
        const spell = mySpells.find((s) => s.key === action);
        logText += `${spell ? spell.icon + spell.name : "魔法"}を使用!`;
        spellCooldowns[action] = 3;
      } else {
        logText += "通常攻撃!";
      }
      logText += ` チームが${data.team_damage}ダメージ${data.crit ? "(会心の一撃!)" : ""}`;
      if (data.effect_text) logText += ` ・ ${data.effect_text}`;
      if (data.boss_damage > 0) logText += ` / ボスが${data.boss_damage}ダメージ`;
      turnLog.textContent = logText;

      Object.keys(spellCooldowns).forEach((k) => { if (spellCooldowns[k] > 0) spellCooldowns[k] -= 1; });
      renderSpellButtons();

      await new Promise((r) => setTimeout(r, 500));

      if (battleState.boss_hp <= 0) {
        await finishManualBattle(true);
      } else if (battleState.team_hp <= 0 || battleState.turns >= 40) {
        await finishManualBattle(false);
      } else {
        attackBtn.disabled = false;
        Array.from(spellButtonsEl.children).forEach((b) => (b.style.pointerEvents = ""));
      }
    } catch (err) {
      alert(err.message);
      attackBtn.disabled = false;
      Array.from(spellButtonsEl.children).forEach((b) => (b.style.pointerEvents = ""));
    }
  }

  async function finishManualBattle(victory) {
    manualControls.style.display = "none";
    turnLog.textContent = victory ? "🏆 ボスを撃破した!" : "💀 チームが力尽きた…";
    try {
      const data = await EmberPlay.postJSON("/rpgboss/manual-complete", {
        mode, victory, turns: battleState.turns,
      });
      let resultText = victory
        ? `🏆 討伐成功! ・ ${battleState.turns}ターン ・ +${data.reward} Embers`
        : `💀 討伐失敗 ・ ${battleState.turns}ターン耐えた ・ +${data.reward} Embers`;
      if (data.looted_spell) {
        resultText += ` ・ 🎁 ${data.looted_spell.icon}${data.looted_spell.name} を入手!`;
      }
      resultReadout.textContent = resultText;
      EmberPlay.flashResult(resultReadout, victory, !victory);
      EmberPlay.updateBalance(data.balance, victory ? "win" : null);
    } catch (err) {
      resultReadout.textContent = "結果の反映に失敗しました。";
    }
  }

  // ───────── エンドレスモード(従来の自動バトル) ─────────
  async function playEndlessLog(data) {
    bossHpBar.style.width = "100%";
    teamHpBar.style.width = "100%";
    teamHpText.textContent = `${data.team_max_hp} / ${data.team_max_hp}`;

    let currentBoss = 0;
    for (const entry of data.log) {
      if (entry.boss_number !== currentBoss) {
        currentBoss = entry.boss_number;
        bossLabel.textContent = `♾️ ${currentBoss}体目のボス`;
        bossHpBar.style.width = "100%";
      }
      await new Promise((r) => setTimeout(r, 280));
      bossHpBar.style.width = Math.max(0, (entry.boss_hp / entry.boss_max_hp) * 100) + "%";
      bossHpText.textContent = `${entry.boss_hp} / ${entry.boss_max_hp}`;
      teamHpBar.style.width = Math.max(0, (entry.team_hp / entry.team_max_hp) * 100) + "%";
      teamHpText.textContent = `${entry.team_hp} / ${entry.team_max_hp}`;
      turnLog.textContent = `${currentBoss}体目 ターン${entry.turn}: チームが${entry.team_damage}ダメージ / ボスが${entry.boss_damage}ダメージ`;
    }

    await new Promise((r) => setTimeout(r, 300));
    resultReadout.textContent = `♾️ ${data.bosses_beaten}体撃破して力尽きました ・ +${data.reward} Embers`;
    if (data.reached_cap) resultReadout.textContent = `♾️ 上限の${data.bosses_beaten}体を撃破!(これ以上は計算上限のため打ち切り) ・ +${data.reward} Embers`;
    EmberPlay.flashResult(resultReadout, data.bosses_beaten > 0, data.bosses_beaten === 0);
    EmberPlay.updateBalance(data.balance, data.bosses_beaten > 0 ? "win" : null);
  }
})();
