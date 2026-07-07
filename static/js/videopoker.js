(function () {
  const wagerInput = document.getElementById("wager");
  const dealBtn = document.getElementById("deal-btn");
  const drawBtn = document.getElementById("draw-btn");
  const handEl = document.getElementById("hand");
  const resultReadout = document.getElementById("result-readout");

  let holds = [false, false, false, false, false];

  function renderHand(cards, clickable) {
    handEl.innerHTML = "";
    cards.forEach((label, i) => {
      const el = document.createElement("div");
      el.className = "mine-tile";
      el.style.width = "64px";
      el.style.fontSize = "22px";
      el.textContent = label;
      if (holds[i]) el.classList.add("revealed");
      if (clickable) {
        el.addEventListener("click", () => {
          holds[i] = !holds[i];
          el.classList.toggle("revealed");
        });
      }
      handEl.appendChild(el);
    });
  }

  dealBtn.addEventListener("click", async () => {
    try {
      holds = [false, false, false, false, false];
      const data = await EmberPlay.postJSON("/games/videopoker/deal", { wager: parseInt(wagerInput.value, 10) });
      renderHand(data.hand, true);
      resultReadout.textContent = "";
      EmberPlay.flashResult(resultReadout, false, false);
      EmberPlay.updateBalance(data.balance, "loss");
      dealBtn.disabled = true;
      wagerInput.disabled = true;
      drawBtn.disabled = false;
    } catch (err) {
      alert(err.message);
    }
  });

  drawBtn.addEventListener("click", async () => {
    try {
      const data = await EmberPlay.postJSON("/games/videopoker/draw", { holds });
      renderHand(data.hand, false);
      resultReadout.textContent = `${data.hand_type} ・ ${data.multiplier}x`;
      EmberPlay.flashResult(resultReadout, data.multiplier > 0, data.multiplier <= 0);
      EmberPlay.updateBalance(data.balance, data.multiplier > 0 ? "win" : "loss");
      dealBtn.disabled = false;
      wagerInput.disabled = false;
      drawBtn.disabled = true;
    } catch (err) {
      alert(err.message);
    }
  });
})();
