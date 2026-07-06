(function () {
  const wagerInput = document.getElementById("wager");
  const segmentsSelect = document.getElementById("segments");
  const riskSelect = document.getElementById("risk");
  const spinBtn = document.getElementById("spin-btn");
  const resultReadout = document.getElementById("result-readout");
  const segmentRow = document.getElementById("segment-row");

  spinBtn.addEventListener("click", async () => {
    spinBtn.disabled = true;
    resultReadout.textContent = "...";
    segmentRow.innerHTML = "";

    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        segments: parseInt(segmentsSelect.value, 10),
        risk: riskSelect.value,
      };
      const data = await EmberPlay.postJSON("/games/wheel/play", payload);

      data.table.forEach((mult, i) => {
        const el = document.createElement("div");
        el.textContent = mult + "x";
        el.style.padding = "6px 8px";
        el.style.borderRadius = "6px";
        el.style.fontFamily = "var(--font-mono)";
        el.style.fontSize = "11px";
        el.style.background = i === data.index ? "var(--ember)" : "var(--panel)";
        el.style.color = i === data.index ? "#fff" : "var(--text-muted)";
        segmentRow.appendChild(el);
      });

      resultReadout.textContent = data.multiplier.toFixed(2) + "x";
      resultReadout.className = "result-readout " + (data.multiplier > 1 ? "win" : (data.multiplier === 0 ? "loss" : ""));
      EmberPlay.updateBalance(data.balance, data.multiplier >= 1 ? "win" : "loss");
    } catch (err) {
      alert(err.message);
    } finally {
      spinBtn.disabled = false;
    }
  });
})();
