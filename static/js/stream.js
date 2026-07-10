(function () {
  const SESSION_ID = window.STREAM_SESSION_ID;
  if (!SESSION_ID) return;

  const BROADCASTER_ID = window.STREAM_BROADCASTER_ID;
  const IS_BROADCASTER = window.STREAM_IS_BROADCASTER;

  const ICE_SERVERS = [{ urls: "stun:stun.l.google.com:19302" }];
  let lastSignalId = 0;

  async function sendSignal(toUserId, kind, payload) {
    await fetch("/stream/signal/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_user_id: toUserId, kind, payload }),
    });
  }

  async function pollSignals(handler) {
    try {
      const res = await fetch(`/stream/signal/poll?since_id=${lastSignalId}`);
      const data = await res.json();
      for (const sig of data.signals || []) {
        lastSignalId = Math.max(lastSignalId, sig.id);
        handler(sig);
      }
    } catch (err) {
      // 通信エラーは次回のポーリングに任せる
    }
  }

  async function heartbeat() {
    try {
      const res = await fetch("/stream/heartbeat", { method: "POST" });
      return await res.json();
    } catch (err) {
      return { active: false };
    }
  }

  // ───────── 配信者側 ─────────
  if (IS_BROADCASTER) {
    const startBtn = document.getElementById("start-share-btn");
    const localVideo = document.getElementById("local-video");
    const statusEl = document.getElementById("broadcast-status");
    const viewerCountEl = document.getElementById("viewer-count");

    let localStream = null;
    const peers = new Map(); // viewer_id -> RTCPeerConnection

    async function connectToViewer(viewerId) {
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      peers.set(viewerId, pc);

      localStream.getTracks().forEach((track) => pc.addTrack(track, localStream));

      pc.onicecandidate = (event) => {
        if (event.candidate) sendSignal(viewerId, "ice", event.candidate);
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await sendSignal(viewerId, "offer", offer);
    }

    startBtn.addEventListener("click", async () => {
      try {
        localStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
        localVideo.srcObject = localStream;
        statusEl.textContent = "配信中です。視聴者が来るとここに接続状況が表示されます。";
        startBtn.disabled = true;

        localStream.getVideoTracks()[0].addEventListener("ended", () => {
          statusEl.textContent = "画面共有が停止されました。「画面共有を開始」で再開できます。";
          startBtn.disabled = false;
        });
      } catch (err) {
        statusEl.textContent = "画面共有を開始できませんでした(許可されなかった可能性があります)。";
      }
    });

    pollSignals((sig) => {
      const pc = peers.get(sig.from_user_id);
      if (!pc) return;
      if (sig.kind === "answer") {
        pc.setRemoteDescription(new RTCSessionDescription(sig.payload)).catch(() => {});
      } else if (sig.kind === "ice") {
        pc.addIceCandidate(new RTCIceCandidate(sig.payload)).catch(() => {});
      }
    });

    setInterval(async () => {
      const data = await heartbeat();
      if (!data.active) return;

      viewerCountEl.textContent = String(data.viewer_ids.length);

      if (localStream) {
        for (const viewerId of data.viewer_ids) {
          if (!peers.has(viewerId)) {
            connectToViewer(viewerId);
          }
        }
      }
      // 離脱した視聴者の接続を片付ける
      for (const viewerId of Array.from(peers.keys())) {
        if (!data.viewer_ids.includes(viewerId)) {
          peers.get(viewerId).close();
          peers.delete(viewerId);
        }
      }

      await pollSignals((sig) => {
        const pc = peers.get(sig.from_user_id);
        if (!pc) return;
        if (sig.kind === "answer") {
          pc.setRemoteDescription(new RTCSessionDescription(sig.payload)).catch(() => {});
        } else if (sig.kind === "ice") {
          pc.addIceCandidate(new RTCIceCandidate(sig.payload)).catch(() => {});
        }
      });
    }, 3000);
  }

  // ───────── 視聴者側 ─────────
  if (!IS_BROADCASTER) {
    const watchBtn = document.getElementById("watch-btn");
    const remoteVideo = document.getElementById("remote-video");
    const statusEl = document.getElementById("watch-status");
    const viewerCountEl = document.getElementById("viewer-count");
    let pc = null;
    let watching = false;

    watchBtn.addEventListener("click", async () => {
      try {
        await fetch("/stream/join", { method: "POST" });
      } catch (err) {
        statusEl.textContent = "視聴の開始に失敗しました。";
        return;
      }

      watching = true;
      watchBtn.disabled = true;
      statusEl.textContent = "配信者からの接続を待っています...";

      pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      pc.ontrack = (event) => {
        remoteVideo.srcObject = event.streams[0];
        statusEl.textContent = "視聴中です。";
      };
      pc.onicecandidate = (event) => {
        if (event.candidate) sendSignal(BROADCASTER_ID, "ice", event.candidate);
      };
    });

    setInterval(async () => {
      if (watching) {
        await fetch("/stream/heartbeat", { method: "POST" });
      }
      const data = await heartbeat();
      if (data.active && viewerCountEl) viewerCountEl.textContent = String(data.viewer_ids.length);
    }, 4000);

    setInterval(() => {
      if (!watching || !pc) return;
      pollSignals(async (sig) => {
        if (sig.from_user_id !== BROADCASTER_ID) return;
        if (sig.kind === "offer") {
          await pc.setRemoteDescription(new RTCSessionDescription(sig.payload));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          await sendSignal(BROADCASTER_ID, "answer", answer);
        } else if (sig.kind === "ice") {
          pc.addIceCandidate(new RTCIceCandidate(sig.payload)).catch(() => {});
        }
      });
    }, 1500);
  }
})();
