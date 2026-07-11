(function () {
  const startBtn = document.getElementById("start-btn");
  const statusText = document.getElementById("status-text");
  const resultReadout = document.getElementById("result-readout");
  const cells = document.querySelectorAll("#board .mine-tile");

  const SYMBOLS = { X: "❌", O: "⭕" };

  function renderBoard(board) {
    board.forEach((v, i) => {
      cells[i].textContent = v ? SYMBOLS[v] : "";
    });
  }

  function setCellsEnabled(board, enabled) {
    cells.forEach((c, i) => {
      c.disabled = !enabled || !!board[i];
    });
  }

  startBtn.addEventListener("click", async () => {
    resultReadout.textContent = "";
    statusText.textContent = "あなたのターンです。";
    try {
      const data = await EmberPlay.postJSON("/games/tictactoe/start", {});
      renderBoard(data.board);
      setCellsEnabled(data.board, true);
    } catch (err) {
      alert(err.message);
    }
  });

  cells.forEach((cell) => {
    cell.addEventListener("click", async () => {
      const idx = parseInt(cell.dataset.cell, 10);
      setCellsEnabled(Array(9).fill("X"), false); // 通信中は全マス無効化

      try {
        const data = await EmberPlay.postJSON("/games/tictactoe/move", { cell: idx });
        renderBoard(data.board);

        if (data.status === "playing") {
          setCellsEnabled(data.board, true);
          statusText.textContent = "あなたのターンです。";
        } else {
          const labels = { won: "あなたの勝ち!", lost: "AIの勝ち", draw: "引き分け" };
          resultReadout.textContent = `${labels[data.status]}${data.reward > 0 ? ` ・ +${data.reward}` : ""}`;
          EmberPlay.flashResult(resultReadout, data.status === "won", data.status === "lost");
          if (data.reward > 0) EmberPlay.updateBalance(data.balance, "win");
          statusText.textContent = "「新しく始める」でもう一度プレイできます。";
        }
      } catch (err) {
        alert(err.message);
        setCellsEnabled(Array(9).fill(""), true);
      }
    });
  });
})();
