/*
  全ページで動くDM新着通知。フレンドからDMが届くと、上部バーに「誰から・なんて書いてあったか」を表示し、
  効果音を鳴らす。バーをタップするとその人とのDM画面に飛ぶ。
*/
(function () {
  const bar = document.getElementById("dm-notify-bar");
  if (!bar) return;

  let lastId = parseInt(sessionStorage.getItem("emberplay_dm_last_id") || "0", 10);
  let hideTimer = null;

  function showNotification(msg) {
    bar.textContent = `✉️ ${msg.from_username}: ${msg.message}`;
    bar.style.display = "block";
    bar.onclick = () => { window.location.href = `/dm/${msg.from_user_id}`; };

    if (window.EmberSound) window.EmberSound.playNotify();

    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { bar.style.display = "none"; }, 6000);
  }

  async function poll() {
    try {
      const res = await fetch(`/dm/global-poll?after_id=${lastId}`);
      if (!res.ok) return;
      const data = await res.json();

      if (data.new_messages && data.new_messages.length) {
        const onThatConversation = window.location.pathname === `/dm/${data.new_messages[data.new_messages.length - 1].from_user_id}`;
        if (!onThatConversation) {
          showNotification(data.new_messages[data.new_messages.length - 1]);
        }
      }
      if (data.latest_id) {
        lastId = data.latest_id;
        sessionStorage.setItem("emberplay_dm_last_id", String(lastId));
      }
    } catch (err) {
      // 次回のポーリングに任せる
    }
  }

  poll();
  setInterval(poll, 4000);
})();
