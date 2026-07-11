(function () {
  const pull1Btn = document.getElementById("pull1-btn");
  const pull10Btn = document.getElementById("pull10-btn");
  const revealArea = document.getElementById("reveal-area");
  const revealGrid = document.getElementById("reveal-grid");

  async function doPull(count) {
    pull1Btn.disabled = true;
    pull10Btn.disabled = true;
    revealGrid.innerHTML = "";
    revealArea.style.display = "none";

    try {
      const data = await EmberPlay.postJSON("/gacha/pull", { count });
      EmberPlay.updateBalance(data.balance, null);

      revealArea.style.display = "block";
      data.results.forEach((c, i) => {
        const card = document.createElement("div");
        card.className = `gacha-card ${c.rarity}`;
        card.style.background = `linear-gradient(160deg, ${c.colors[0]}, ${c.colors[1]})`;
        card.style.borderColor = c.colors[0];
        card.style.animationDelay = `${i * 0.08}s`;
        card.innerHTML = `
          <div class="gacha-card-icon">${c.icon}</div>
          <div style="font-weight:700; margin-top:4px;">${c.name}</div>
          <div style="opacity:0.8;">${c.rarity_label}</div>
          ${c.is_new ? '<span class="gacha-card-new">NEW</span>' : `<div style="opacity:0.7; margin-top:2px;">Lv.${c.new_count}</div>`}
        `;
        revealGrid.appendChild(card);
        if (c.rarity === "legendary" || c.rarity === "epic") {
          setTimeout(() => window.EmberSound && window.EmberSound.playBigWin(), i * 80);
        }
      });

      if (window.EmberSound) window.EmberSound.playWin();
      setTimeout(() => location.reload(), 3500);
    } catch (err) {
      alert(err.message);
      pull1Btn.disabled = false;
      pull10Btn.disabled = false;
    }
  }

  pull1Btn.addEventListener("click", () => doPull(1));
  pull10Btn.addEventListener("click", () => doPull(10));
})();
