/*
  PWA対応のためのService Worker。
  「インストール可能」の要件を満たすことが主な目的で、静的ファイル(CSS・JS・アイコン)
  だけを軽くキャッシュする(ゲームの結果やお金に関わるデータは、必ず毎回サーバーに
  問い合わせるべきなので、キャッシュの対象にしていない)。
*/
const CACHE_NAME = "emberplay-static-v1";
const STATIC_ASSETS = [
  "/static/css/style.css",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
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
