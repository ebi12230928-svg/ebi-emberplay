/*
  カジノのリアリティを高めるための、本物のトランプに近いカード描画コンポーネント。
  "A♠" "10♦" のような文字列(ランク+スート記号)を渡すと、白地に角の数字・中央の大きなスート
  マークを持つ、実際のトランプのようなカード要素を作って返す。
  裏向きのカード(相手の伏せ札など)も再現できる。
*/
window.CardVisuals = (function () {
  const RED_SUITS = ["♥", "♦"];

  function parseCardLabel(label) {
    const suit = label.slice(-1);
    const rank = label.slice(0, -1);
    return { rank, suit };
  }

  function renderPlayingCard(label, options) {
    options = options || {};
    const el = document.createElement("div");
    el.className = "playing-card" + (options.small ? " playing-card-small" : "");

    if (label === "??" || label === "?" || label === "back") {
      el.classList.add("playing-card-back");
      return el;
    }

    const { rank, suit } = parseCardLabel(label);
    const isRed = RED_SUITS.includes(suit);
    if (isRed) el.classList.add("playing-card-red");

    el.innerHTML = `
      <span class="pc-corner pc-corner-top">${rank}<br>${suit}</span>
      <span class="pc-center">${suit}</span>
      <span class="pc-corner pc-corner-bottom">${rank}<br>${suit}</span>
    `;
    return el;
  }

  function renderHand(container, labels, options) {
    container.innerHTML = "";
    container.classList.add("playing-card-row");
    labels.forEach((label, i) => {
      const card = renderPlayingCard(label, options);
      card.style.animationDelay = (i * 0.08) + "s";
      card.classList.add("playing-card-deal-in");
      container.appendChild(card);
      if (window.EmberSound) {
        setTimeout(() => window.EmberSound.playCardFlip(), i * 80);
      }
    });
  }

  return { renderPlayingCard, renderHand, parseCardLabel };
})();
