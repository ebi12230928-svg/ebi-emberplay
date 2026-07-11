(function () {
  const ROOM_ID = window.SQUAD_ROOM_ID;
  const MODE = window.SQUAD_MODE;
  const IS_HOST = window.SQUAD_IS_HOST;
  const MAX_CHARS = window.SQUAD_MAX_CHARS || 4;

  const memberList = document.getElementById("member-list");
  const memberCountEl = document.getElementById("member-count");
  const difficultyEl = document.getElementById("difficulty-display");
  const readyBtn = document.getElementById("ready-btn");
  const startBtn = document.getElementById("start-btn");
  const charItems = document.querySelectorAll(".char-select-item");

  let mySelected = [];
  let isReady = false;
  let redirected = false;
  let selectedTier = "normal";

  document.querySelectorAll(".tier-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tier-btn").forEach((b) => b.classList.remove("btn-ember"));
      document.querySelectorAll(".tier-btn").forEach((b) => b.classList.add("btn-ghost"));
      btn.classList.add("btn-ember");
      btn.classList.remove("btn-ghost");
      selectedTier = btn.dataset.tier;
    });
  });

  charItems.forEach((item) => {
    item.addEventListener("click", async () => {
      const key = item.dataset.key;
      const idx = mySelected.indexOf(key);
      if (idx >= 0) {
        mySelected.splice(idx, 1);
        item.style.outline = "none";
      } else {
        if (mySelected.length >= MAX_CHARS) return;
        mySelected.push(key);
        item.style.outline = "2px solid var(--gold)";
      }
      try {
        await EmberPlay.postJSON(`/squad/room/${ROOM_ID}/select`, { characters: mySelected });
      } catch (err) {
        alert(err.message);
      }
    });
  });

  readyBtn.addEventListener("click", async () => {
    try {
      const data = await fetch(`/squad/room/${ROOM_ID}/ready`, { method: "POST" }).then((r) => r.json());
      isReady = data.ready;
      readyBtn.textContent = isReady ? "準備を解除する" : "準備完了にする";
      readyBtn.className = isReady ? "btn btn-ghost" : "btn btn-ember";
    } catch (err) {
      alert("通信エラーが発生しました。");
    }
  });

  if (startBtn) {
    startBtn.addEventListener("click", async () => {
      startBtn.disabled = true;
      try {
        await EmberPlay.postJSON(`/squad/room/${ROOM_ID}/start`, {});
        if (MODE === "towerdefense") {
          location.href = `/towerdefense?squad_room=${ROOM_ID}&mode=${selectedTier}`;
        } else {
          const data = await EmberPlay.postJSON("/rpgboss/squad-battle", { room_id: ROOM_ID, mode: selectedTier });
          showRpgResult(data);
        }
      } catch (err) {
        alert(err.message);
        startBtn.disabled = false;
      }
    });
  }

  function showRpgResult(data) {
    const el = document.createElement("div");
    el.className = "panel";
    el.style.marginTop = "16px";
    el.innerHTML = `
      <h3>${data.victory ? "🏆 討伐成功!" : "💀 討伐失敗"}</h3>
      <p class="mono text-muted">${data.turns}ターン ・ 参加者全員に +${data.reward_each} Embers(${data.member_count}人)</p>
    `;
    document.querySelector(".panel").parentNode.appendChild(el);
    setTimeout(() => location.reload(), 3000);
  }

  function renderMembers(room) {
    memberCountEl.textContent = String(room.members.length);
    difficultyEl.textContent = room.difficulty_scale;
    memberList.innerHTML = "";
    room.members.forEach((m) => {
      const row = document.createElement("div");
      row.style.cssText = "display:flex; justify-content: space-between; padding: 8px 0; border-top: 1px solid var(--panel-border);";
      row.innerHTML = `
        <span>${m.avatar} ${m.username}${m.user_id === room.host_id ? " 👑" : ""}</span>
        <span class="mono" style="color: ${m.ready ? "var(--win)" : "var(--text-muted)"};">
          ${m.ready ? "準備完了" : "準備中"} ・ ${m.characters.length}体編成
        </span>
      `;
      memberList.appendChild(row);
    });

    if (startBtn) {
      const allReady = room.members.length > 0 && room.members.every((m) => m.ready);
      startBtn.disabled = !allReady;
    }
  }

  async function poll() {
    try {
      const res = await fetch(`/squad/room/${ROOM_ID}/poll`);
      const room = await res.json();
      if (room.error) return;
      renderMembers(room);

      if (room.status === "battling" && !redirected) {
        redirected = true;
        if (MODE === "towerdefense") {
          location.href = `/towerdefense?squad_room=${ROOM_ID}`;
        }
        // rpgbossの場合はホストが結果を出すまで、このままポーリングを続ける
      }
      if (room.status === "finished" && room.result && !IS_HOST) {
        redirected = true;
        location.reload();
      }
    } catch (err) {
      // 通信エラーは次回のポーリングに任せる
    }
  }

  poll();
  setInterval(poll, 2500);
})();
