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

  let selected = [];
  let mode = "normal";
  const MAX_TEAM = window.RPG_MAX_TEAM || 6;

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

  battleBtn.addEventListener("click", async () => {
    battleBtn.disabled = true;
    try {
      const data = await EmberPlay.postJSON("/rpgboss/battle", { characters: selected, mode });
      selectScreen.style.display = "none";
      battleScreen.style.display = "block";
      if (mode === "endless") {
        playEndlessLog(data);
      } else {
        bossLabel.textContent = { normal: "👹 通常ボス", raid: "🔥 レイド", lastboss: "💀 ラスボス" }[mode];
        playLog(data);
      }
    } catch (err) {
      alert(err.message);
      battleBtn.disabled = false;
    }
  });

  async function playLog(data) {
    bossHpBar.style.width = "100%";
    teamHpBar.style.width = "100%";
    bossHpText.textContent = `${data.boss_max_hp} / ${data.boss_max_hp}`;
    teamHpText.textContent = `${data.team_max_hp} / ${data.team_max_hp}`;

    for (const entry of data.log) {
      await new Promise((r) => setTimeout(r, 400));
      bossHpBar.style.width = Math.max(0, (entry.boss_hp / entry.boss_max_hp) * 100) + "%";
      bossHpText.textContent = `${entry.boss_hp} / ${entry.boss_max_hp}`;
      teamHpBar.style.width = Math.max(0, (entry.team_hp / entry.team_max_hp) * 100) + "%";
      teamHpText.textContent = `${entry.team_hp} / ${entry.team_max_hp}`;
      turnLog.textContent = `ターン${entry.turn}: チームが${entry.team_damage}ダメージ${entry.crit ? "(会心の一撃!)" : ""} / ボスが${entry.boss_damage}ダメージ`;
    }

    await new Promise((r) => setTimeout(r, 300));
    const win = data.victory;
    resultReadout.textContent = win
      ? `🏆 討伐成功! ・ ${data.turns}ターン ・ +${data.reward} Embers`
      : `💀 討伐失敗 ・ ${data.turns}ターン耐えた ・ +${data.reward} Embers`;
    EmberPlay.flashResult(resultReadout, win, !win);
    EmberPlay.updateBalance(data.balance, win ? "win" : null);
  }

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
