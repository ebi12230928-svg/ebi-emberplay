/*
  PWA対応のためのService Worker。
  「インストール可能」の要件を満たすことが主な目的で、静的ファイル(CSS・JS・アイコン)
  だけを軽くキャッシュする(ゲームの結果やお金に関わるデータは、必ず毎回サーバーに
  問い合わせるべきなので、キャッシュの対象にしていない)。
*/
const CACHE_NAME = "emberplay-static-v2"; // バージョンを上げることで、古いキャッシュを破棄させる
const STATIC_ASSETS = [
  "/static/css/style.css",
  "/static/manifest.json",
  "/static/icons/icon-192-v2.png",
  "/static/icons/icon-512-v2.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // 静的ファイル(CSS・アイコンなど)だけをキャッシュ優先で返す。
  // それ以外(ページ本体・API・ゲーム結果など)は、常にネットワークから最新のものを取得する
  // (オフライン中にキャッシュされた古いゲーム画面や残高が表示されてしまうのを防ぐため)。
  const isStaticAsset = STATIC_ASSETS.some((path) => url.pathname === path);
  if (!isStaticAsset) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      });
    })
  );
});

// プッシュ通知を受信した時の処理(DM・お知らせなどが届いた時にサーバーから送られてくる)
self.addEventListener("push", (event) => {
  let data = { title: "EMBERPLAY", body: "新しいお知らせがあります。", url: "/" };
  try {
    if (event.data) data = event.data.json();
  } catch (err) { /* JSON以外のデータが来た場合は、既定のメッセージのままにする */ }

  event.waitUntil(
    self.registration.showNotification(data.title || "EMBERPLAY", {
      body: data.body || "",
      icon: "/static/icons/icon-192-v2.png",
      badge: "/static/icons/icon-192-v2.png",
      data: { url: data.url || "/" },
    })
  );
});

// 通知をタップした時、該当のページを開く(すでに開いているタブがあれば、それを前面に出す)
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(targetUrl) && "focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl);
    })
  );
});
