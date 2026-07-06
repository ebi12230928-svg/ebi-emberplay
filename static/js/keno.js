(function () {
  const wagerInput = document.getElementById("wager");
  const playBtn = document.getElementById("play-btn");
  const clearBtn = document.getElementById("clear-btn");
  const resultReadout = document.getElementById("result-readout");
  const picksReadout = document.getElementById("picks-readout");
  const grid = document.getElementById("keno-grid");
  const total = parseInt(grid.dataset.total, 10);
  const MAX_PICKS = 10;

  let picks = new Set();

  for (let i = 1; i <= total; i++) {
    const tile = document.createElement("button");
    tile.className = "mine-tile";
    tile.textContent = i;
    tile.style.fontSize = "13px";
    tile.dataset.num = i;
    tile.addEventListener("click", () => togglePick(i, tile));
    grid.appendChild(tile);
  }

  function togglePick(num, tile) {
    if (picks.has(num)) {
      picks.delete(num);
      tile.classList.remove("revealed");
    } else {
      if (picks.size >= MAX_PICKS) return;
      picks.add(num);
      tile.classList.add("revealed");
    }
    picksReadout.textContent = `選択中: ${picks.size}個`;
  }

  clearBtn.addEventListener("click", () => {
    picks.clear();
    [...grid.children].forEach((t) => {
      t.classList.remove("revealed", "mine");
      t.textContent = t.dataset.num;
    });
    picksReadout.textContent = "選択中: 0個";
    resultReadout.textContent = "--";
  });

  playBtn.addEventListener("click", async () => {
    if (picks.size === 0) {
      alert("数字を1つ以上選んでください。");
      return;
    }
    playBtn.disabled = true;
    try {
      const payload = { wager: parseInt(wagerInput.value, 10), picks: [...picks] };
      const data = await EmberPlay.postJSON("/games/keno/play", payload);

      [...grid.children].forEach((t) => {
        const n = parseInt(t.dataset.num, 10);
        if (data.drawn.includes(n)) {
          t.classList.add(picks.has(n) ? "revealed" : "mine");
        }
      });

      resultReadout.textContent = `${data.matches}マッチ ・ ${data.multiplier}x`;
      resultReadout.className = "result-readout " + (data.multiplier > 0 ? "win" : "loss");
      EmberPlay.updateBalance(data.balance, data.multiplier > 0 ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      playBtn.disabled = false;
    }
  });
})();
