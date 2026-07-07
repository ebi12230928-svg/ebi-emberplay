(function () {
  const wagerInput = document.getElementById("wager");
  const rowsSelect = document.getElementById("rows");
  const riskSelect = document.getElementById("risk");
  const dropBtn = document.getElementById("drop-btn");
  const resultReadout = document.getElementById("result-readout");
  const bucketRow = document.getElementById("bucket-row");

  dropBtn.addEventListener("click", async () => {
    dropBtn.disabled = true;
    resultReadout.textContent = "...";
    bucketRow.innerHTML = "";

    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        rows: parseInt(rowsSelect.value, 10),
        risk: riskSelect.value,
      };
      const data = await EmberPlay.postJSON("/games/plinko/play", payload);

      data.table.forEach((mult, i) => {
        const el = document.createElement("div");
        el.textContent = mult + "x";
        el.style.padding = "6px 8px";
        el.style.borderRadius = "6px";
        el.style.fontFamily = "var(--font-mono)";
        el.style.fontSize = "11px";
        el.style.background = i === data.bucket ? "var(--ember)" : "var(--panel)";
        el.style.color = i === data.bucket ? "#fff" : "var(--text-muted)";
        bucketRow.appendChild(el);
      });

      resultReadout.textContent = data.multiplier.toFixed(2) + "x";
      EmberPlay.flashResult(resultReadout, data.multiplier > 1, data.multiplier === 0);

      EmberPlay.updateBalance(data.balance, data.multiplier >= 1 ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      dropBtn.disabled = false;
    }
  });
})();
