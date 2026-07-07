(function () {
  const messagesEl = document.getElementById("chat-messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");

  let lastId = 0;
  let atBottom = true;

  messagesEl.addEventListener("scroll", () => {
    atBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 40;
  });

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderMessage(m) {
    const el = document.createElement("div");
    let nameColor = "var(--text)";
    let badge = "";
    if (m.is_admin) { nameColor = "var(--ember)"; badge = " <span style='font-size:10px; color:var(--ember);'>[運営]</span>"; }
    else if (m.is_vip) { nameColor = "var(--gold)"; badge = " <span style='font-size:10px; color:var(--gold);'>[VIP]</span>"; }

    el.innerHTML = `
      <span class="mono text-muted" style="font-size:11px;">${m.time}</span>
      <strong style="color:${nameColor};">${escapeHtml(m.username)}</strong>${badge}
      <span>: ${escapeHtml(m.message)}</span>
    `;
    return el;
  }

  async function poll() {
    try {
      const res = await fetch(`/chat/messages?since_id=${lastId}`);
      const data = await res.json();
      if (data.messages && data.messages.length > 0) {
        data.messages.forEach((m) => {
          messagesEl.appendChild(renderMessage(m));
          lastId = Math.max(lastId, m.id);
        });
        if (atBottom) {
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }
      }
    } catch (err) {
      // 通信エラーは無視して次回のポーリングに任せる
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    try {
      const res = await fetch("/chat/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.error || "送信に失敗しました。");
      }
    } catch (err) {
      alert("送信に失敗しました。");
    }
  });

  poll();
  setInterval(poll, 2500);
})();
