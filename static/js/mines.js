(function () {
  const wagerInput = document.getElementById("wager");
  const mineCountInput = document.getElementById("mine-count");
  const startBtn = document.getElementById("start-btn");
  const cashoutBtn = document.getElementById("cashout-btn");
  const multiplierReadout = document.getElementById("multiplier-readout");
  const grid = document.getElementById("mines-grid");
  const gridSize = parseInt(grid.dataset.gridSize, 10);

  let gameActive = false;

  function buildGrid() {
    grid.innerHTML = "";
    for (let i = 0; i < gridSize; i++) {
      const tile = document.createElement("button");
      tile.className = "mine-tile";
      tile.dataset.index = i;
      tile.disabled = !gameActive;
      tile.addEventListener("click", () => onTileClick(i));
      grid.appendChild(tile);
    }
  }

  function setGameActive(active) {
    gameActive = active;
    startBtn.disabled = active;
    wagerInput.disabled = active;
    mineCountInput.disabled = active;
    cashoutBtn.disabled = !active;
    [...grid.children].forEach((tile) => {
      tile.disabled = !active || tile.classList.contains("revealed") || tile.classList.contains("mine");
    });
  }

  buildGrid();

  startBtn.addEventListener("click", async () => {
    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        mine_count: parseInt(mineCountInput.value, 10),
      };
      const data = await EmberPlay.postJSON("/games/mines/start", payload);
      buildGrid();
      multiplierReadout.textContent = "1.0000x";
      EmberPlay.updateBalance(data.balance, "loss");
      setGameActive(true);
    } catch (err) {
      alert(err.message);
    }
  });

  async function onTileClick(index) {
    const tile = grid.children[index];
    if (tile.classList.contains("revealed") || tile.classList.contains("mine")) return;

    try {
      const data = await EmberPlay.postJSON("/games/mines/reveal", { tile: index });

      if (data.hit_mine) {
        data.mine_positions.forEach((pos) => {
          grid.children[pos].classList.add("mine");
          grid.children[pos].textContent = "×";
        });
        multiplierReadout.textContent = "0.0000x";
        EmberPlay.updateBalance(data.balance, "loss");
        setGameActive(false);
        return;
      }

      tile.classList.add("revealed");
      tile.textContent = "◆";
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";

      if (data.safe_tiles_left <= 0) {
        // 全ての安全マスを開けきった場合は自動キャッシュアウト
        await doCashout();
      }
    } catch (err) {
      alert(err.message);
    }
  }

  async function doCashout() {
    try {
      const data = await EmberPlay.postJSON("/games/mines/cashout", {});
      multiplierReadout.textContent = data.multiplier.toFixed(4) + "x";
      EmberPlay.updateBalance(data.balance, "win");
      setGameActive(false);
    } catch (err) {
      alert(err.message);
    }
  }

  cashoutBtn.addEventListener("click", doCashout);
})();
