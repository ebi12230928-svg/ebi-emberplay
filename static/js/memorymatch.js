(function () {
  const wagerInput = document.getElementById("wager");
  const playBtn = document.getElementById("play-btn");
  const resultReadout = document.getElementById("result-readout");
  const tiles = document.querySelectorAll("#grid .mine-tile");
  const pickCountEl = document.getElementById("pick-count");
  let selected = [];

  function resetGrid() {
    selected = [];
    pickCountEl.textContent = "0";
    playBtn.disabled = true;
    tiles.forEach((t) => {
      t.textContent = "❔";
      t.classList.remove("revealed", "mine");
      t.disabled = false;
    });
  }

  tiles.forEach((tile) => {
    tile.addEventListener("click", () => {
      const idx = parseInt(tile.dataset.index, 10);
      if (selected.includes(idx) || selected.length >= 2) return;
      selected.push(idx);
      tile.textContent = "🎴";
      tile.disabled = true;
      pickCountEl.textContent = String(selected.length);
      playBtn.disabled = selected.length !== 2;
    });
  });

  playBtn.addEventListener("click", async () => {
    playBtn.disabled = true;
    resultReadout.textContent = "";

    try {
      const data = await EmberPlay.postJSON("/games/memorymatch/play", {
        wager: parseInt(wagerInput.value, 10), picks: selected,
      });

      selected.forEach((idx, i) => {
        tiles[idx].textContent = data.revealed[i];
        tiles[idx].classList.add(data.matched ? "revealed" : "mine");
      });

      resultReadout.textContent = data.matched ? `MATCH! ・ ${data.multiplier}x` : "NO MATCH";
      EmberPlay.flashResult(resultReadout, data.matched, !data.matched);
      EmberPlay.updateBalance(data.balance, data.matched ? "win" : "loss");

      setTimeout(resetGrid, 1800);
    } catch (err) {
      alert(err.message);
      playBtn.disabled = false;
    }
  });
})();
