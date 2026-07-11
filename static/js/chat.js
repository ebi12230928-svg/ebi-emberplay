(function () {
  const messagesEl = document.getElementById("chat-messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const REACTIONS = window.EMBERPLAY_REACTION_EMOJIS || ["👍", "😂", "🔥", "😢", "🎉"];

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

  function renderReactionBar(messageId, reactions) {
    const bar = document.createElement("div");
    bar.style.cssText = "display:flex; gap: 4px; margin-top: 2px; flex-wrap: wrap;";
    REACTIONS.forEach((emoji) => {
      const count = (reactions && reactions[emoji]) || 0;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = count > 0 ? `${emoji} ${count}` : emoji;
      btn.style.cssText = "font-size: 11px; padding: 2px 8px; border-radius: 100px; border: 1px solid var(--panel-border); background: var(--bg-raised); color: var(--text-muted); cursor: pointer;";
      btn.addEventListener("click", async () => {
        try {
          const res = await fetch("/chat/react", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message_id: messageId, emoji }),
          });
          const data = await res.json();
          if (res.ok) {
            const newBar = renderReactionBar(messageId, data.reactions);
            bar.replaceWith(newBar);
          }
        } catch (err) {
          // 通信エラーは無視
        }
      });
      bar.appendChild(btn);
    });
    return bar;
  }

  function renderMessage(m) {
    const wrap = document.createElement("div");
    let nameColor = "var(--text)";
    let badge = "";
    if (m.is_admin) { nameColor = "var(--ember)"; badge = " <span style='font-size:10px; color:var(--ember);'>[運営]</span>"; }
    else if (m.is_vip) { nameColor = "var(--gold)"; badge = " <span style='font-size:10px; color:var(--gold);'>[VIP]</span>"; }

    const line = document.createElement("div");
    line.innerHTML = `
      <span class="mono text-muted" style="font-size:11px;">${m.time}</span>
      <span style="margin: 0 2px;">${m.avatar || "🔥"}</span>
      <strong style="color:${nameColor};">${escapeHtml(m.username)}</strong>${badge}
      <span>: ${escapeHtml(m.message)}</span>
    `;
    wrap.appendChild(line);
    wrap.appendChild(renderReactionBar(m.id, m.reactions));
    return wrap;
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
