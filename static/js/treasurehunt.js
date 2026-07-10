(function () {
  const wagerInput = document.getElementById("wager");
  const playBtn = document.getElementById("play-btn");
  const resultReadout = document.getElementById("result-readout");
  const tiles = document.querySelectorAll("#grid .mine-tile");
  const pickCountEl = document.getElementById("pick-count");
  const NEEDED = window.EMBERPLAY_PICK_COUNT;
  let selected = [];

  function resetGrid() {
    selected = [];
    pickCountEl.textContent = "0";
    playBtn.disabled = true;
    tiles.forEach((t) => {
      t.textContent = "🗺️";
      t.classList.remove("revealed", "mine");
      t.disabled = false;
    });
  }

  tiles.forEach((tile) => {
    tile.addEventListener("click", () => {
      const idx = parseInt(tile.dataset.index, 10);
      if (selected.includes(idx) || selected.length >= NEEDED) return;
      selected.push(idx);
      tile.textContent = "🚩";
      tile.disabled = true;
      pickCountEl.textContent = String(selected.length);
      playBtn.disabled = selected.length !== NEEDED;
    });
  });

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/treasurehunt/play", {
        wager: parseInt(wagerInput.value, 10), picks: selected,
      });

      data.traps.forEach((idx) => {
        const t = tiles[idx];
        t.textContent = "💣";
        t.classList.add(selected.includes(idx) ? "mine" : "revealed");
      });
      selected.forEach((idx) => {
        if (!data.traps.includes(idx)) {
          tiles[idx].textContent = "💎";
          tiles[idx].classList.add("revealed");
        }
      });

      resultReadout.textContent = data.won ? `WIN ・ ${data.multiplier}x` : "LOSE";
      EmberPlay.flashResult(resultReadout, data.won, !data.won);
      EmberPlay.updateBalance(data.balance, data.won ? "win" : "loss");

      setTimeout(resetGrid, 1800);
    } catch (err) {
      alert(err.message);
      playBtn.disabled = false;
    }
  });
})();
