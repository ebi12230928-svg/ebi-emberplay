(function () {
  const RED_NUMBERS = new Set([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]);
  // ヨーロピアンルーレットの実際の盤面の並び順(0を基準に時計回り)
  const WHEEL_ORDER = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26];

  const wagerInput = document.getElementById("wager");
  const betTypeSelect = document.getElementById("bet-type");
  const straightField = document.getElementById("straight-field");
  const straightValue = document.getElementById("straight-value");
  const spinBtn = document.getElementById("spin-btn");
  const resultReadout = document.getElementById("result-readout");
  const wheelEl = document.getElementById("roulette-wheel");
  const ballEl = document.getElementById("roulette-ball");

  let currentWheelRotation = 0;

  function pocketColor(n) {
    if (n === 0) return "#0d8a4e";
    return RED_NUMBERS.has(n) ? "#c0392b" : "#1a1a1a";
  }

  function buildWheel() {
    const cx = 110, cy = 110, rOuter = 105, rInner = 60;
    const segAngle = 360 / WHEEL_ORDER.length;
    let svg = "";
    WHEEL_ORDER.forEach((num, i) => {
      const startAngle = i * segAngle - 90 - segAngle / 2;
      const endAngle = startAngle + segAngle;
      const toRad = (deg) => (deg * Math.PI) / 180;
      const x1 = cx + rOuter * Math.cos(toRad(startAngle));
      const y1 = cy + rOuter * Math.sin(toRad(startAngle));
      const x2 = cx + rOuter * Math.cos(toRad(endAngle));
      const y2 = cy + rOuter * Math.sin(toRad(endAngle));
      const ix1 = cx + rInner * Math.cos(toRad(endAngle));
      const iy1 = cy + rInner * Math.sin(toRad(endAngle));
      const ix2 = cx + rInner * Math.cos(toRad(startAngle));
      const iy2 = cy + rInner * Math.sin(toRad(startAngle));
      svg += `<path d="M ${x1} ${y1} A ${rOuter} ${rOuter} 0 0 1 ${x2} ${y2} L ${ix1} ${iy1} A ${rInner} ${rInner} 0 0 0 ${ix2} ${iy2} Z" fill="${pocketColor(num)}" stroke="#d4a24e" stroke-width="0.5"/>`;
      const labelAngle = startAngle + segAngle / 2;
      const lx = cx + (rOuter - 12) * Math.cos(toRad(labelAngle));
      const ly = cy + (rOuter - 12) * Math.sin(toRad(labelAngle));
      svg += `<text x="${lx}" y="${ly}" fill="#fff" font-size="7" text-anchor="middle" dominant-baseline="middle">${num}</text>`;
    });
    svg += `<circle cx="${cx}" cy="${cy}" r="${rOuter}" fill="none" stroke="#d4a24e" stroke-width="3"/>`;
    wheelEl.innerHTML = svg;
  }
  buildWheel();

  function spinWheelTo(pocket) {
    const segAngle = 360 / WHEEL_ORDER.length;
    const idx = WHEEL_ORDER.indexOf(pocket);
    // 常に増加し続ける角度に「4周分+目標の数字が針の位置に来る角度」を足していく
    // (毎回必ず前回より大きい角度にすることで、逆回転せず自然に見えるようにする)
    const base = Math.ceil(currentWheelRotation / 360) * 360;
    currentWheelRotation = base + 360 * 4 - idx * segAngle;
    wheelEl.style.transform = `rotate(${currentWheelRotation}deg)`;
    ballEl.style.transform = `rotate(${-currentWheelRotation * 1.5}deg)`;
  }

  function refreshFields() {
    straightField.style.display = betTypeSelect.value === "straight" ? "block" : "none";
  }
  betTypeSelect.addEventListener("change", refreshFields);
  refreshFields();

  spinBtn.addEventListener("click", async () => {
    spinBtn.disabled = true;
    resultReadout.textContent = "...";

    try {
      const payload = {
        wager: parseInt(wagerInput.value, 10),
        bet_type: betTypeSelect.value,
        value: betTypeSelect.value === "straight" ? parseInt(straightValue.value, 10) : null,
      };
      const data = await EmberPlay.postJSON("/games/roulette/spin", payload);

      spinWheelTo(data.pocket);
      if (window.EmberSound) window.EmberSound.playCardFlip();

      setTimeout(() => {
        const color = data.pocket === 0 ? "GREEN" : (RED_NUMBERS.has(data.pocket) ? "RED" : "BLACK");
        resultReadout.textContent = `${data.pocket} (${color})`;
        EmberPlay.flashResult(resultReadout, data.win, !data.win);
        EmberPlay.updateBalance(data.balance, data.win ? "win" : "loss");
        spinBtn.disabled = false;
      }, 4000); // ホイールが止まるタイミングに合わせて結果を表示する
    } catch (err) {
      alert(err.message);
      spinBtn.disabled = false;
    }
  });
})();
