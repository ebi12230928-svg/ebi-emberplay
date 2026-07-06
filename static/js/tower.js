(function () {
  const wagerInput = document.getElementById("wager");
  const difficultySelect = document.getElementById("difficulty");
  const startBtn = document.getElementById("start-btn");
  const cashoutBtn = document.getElementById("cashout-btn");
  const multiplierReadout = document.getElementById("multiplier-readout");
  const rowsContainer = document.getElementById("tower-rows");
  const totalRows = parseInt(rowsContainer.dataset.totalRows, 10);

  let tilesPerRow = 3;
  let currentRow = 0;
  let active = false;

  function buildRows() {
    rowsContainer.innerHTML = "";
    for (let r = 0; r < totalRows; r++) {
      const rowEl = document.createElement("div");
      rowEl.style.display = "flex";
      rowEl.style.gap = "8px";
      rowEl.dataset.row = r;
      for (let t = 0; t < tilesPerRow; t++) {
        const tile = document.createElement("button");
        tile.className = "mine-tile";
        tile.style.flex = "1";
        tile.dataset.tile = t;
        tile.disabled = true;
        tile.addEventListener("click", () => onTileClick(r, t, tile));
        rowEl.appendChild(tile);
      }
      rowsContainer.appendChild(rowEl);
    }
    updateActiveRow();
  }

  function updateActiveRow() {
    [...rowsContainer.children].forEach((rowEl) => {
      const r = parseInt(rowEl.dataset.row, 10);
      [...rowEl.children].forEach((tile) => {
        if (tile.classList.contains("revealed") || tile.classList.contains("mine")) return;
        tile.disabled = !active || r !== currentRow;
      });
    });
  }

  function setActive(value) {
    active = value;
    startBtn.disabled = value;
    wagerInput.disabled = value;
    difficultySelect.disabled = value;
    cashoutBtn.disabled = !value || currentRow === 0;
    updateActiveRow();
  }

  startBtn.addEventListener("click", async () => {
    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        difficulty: difficultySelect.value,
      };
      const data = await EmberPlay.postJSON("/games/tower/start", payload);
      tilesPerRow = data.tiles_per_row;
      currentRow = 0;
      multiplierReadout.textContent = "1.0000x";
      buildRows();
      EmberPlay.updateBalance(data.balance, "loss");
      setActive(true);
    } catch (err) {
      alert(err.message);
    }
  });

  async function onTileClick(row, tile, tileEl) {
    if (row !== currentRow) return;
    try {
      const data = await EmberPlay.postJSON("/games/tower/reveal", { tile });

      if (data.hit_bad) {
        data.row_bad.forEach((idx) => {
          const rowEl = rowsContainer.children[row];
          rowEl.children[idx].classList.add("mine");
          rowEl.children[idx].textContent = "×";
        });
        multiplierReadout.textContent = "0.0000x";
        EmberPlay.updateBalance(data.balance, "loss");
        setActive(false);
        return;
      }

      tileEl.classList.add("revealed");
      tileEl.textContent = "◆";
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";

      if (data.reached_top) {
        EmberPlay.updateBalance(data.balance, "win");
        setActive(false);
        return;
      }

      currentRow = data.current_row;
      cashoutBtn.disabled = false;
      updateActiveRow();
    } catch (err) {
      alert(err.message);
    }
  }

  cashoutBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/tower/cashout", {});
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";
      EmberPlay.updateBalance(data.balance, "win");
      setActive(false);
    } catch (err) {
      alert(err.message);
    }
  });

  buildRows();
})();
