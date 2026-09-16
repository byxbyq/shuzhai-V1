// ============================================================
// 书斋 Service Worker
// 缓存策略：
//   - 静态资源（CSS/JS/favicon）：cache-first（缓存优先）
//   - API 请求（/api/）：network-only（纯网络直通，不缓存）
//   - HTML 页面：stale-while-revalidate（先返回缓存，后台更新）
// ============================================================

// 缓存版本号（更新此版本号可触发新缓存与旧缓存清理）
const CACHE_VERSION = 'shuzhai-v8';

// 各类缓存名称
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const PAGE_CACHE = `${CACHE_VERSION}-pages`;

// 所有缓存名称集合，便于 activate 时统一管理
const ALL_CACHES = [STATIC_CACHE, PAGE_CACHE];

// 安装时需要预缓存的核心资源
const PRECACHE_URLS = [
  '/',
  '/css/style.css',
  '/css/reader.css',
  '/js/api.js',
  '/js/app.js',
  '/js/state.js',
  '/js/reader.js',
  '/favicon.ico'
];

// ============================================================
// 安装阶段：预缓存核心资源
// ============================================================
self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(STATIC_CACHE);
      // 逐个预缓存，避免单个资源失败导致整个安装失败
      await Promise.all(
        PRECACHE_URLS.map(async (url) => {
          try {
            await cache.add(url);
          } catch (err) {
            console.warn(`[SW] 预缓存失败：${url}`, err);
          }
        })
      );
      // 安装完成后立即激活，跳过等待
      await self.skipWaiting();
    })()
  );
});

// ============================================================
// 激活阶段：清理旧版本缓存
// ============================================================
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      // 清理不属于当前版本的所有缓存
      await Promise.all(
        cacheNames.map((cacheName) => {
          if (!ALL_CACHES.includes(cacheName)) {
            console.log(`[SW] 清理旧缓存：${cacheName}`);
            return caches.delete(cacheName);
          }
          return undefined;
        })
      );
      // 立即接管所有客户端
      await self.clients.claim();
    })()
  );
});

// ============================================================
// 判断请求类型
// ============================================================

// 是否为静态资源（CSS / JS / favicon 等）
function isStaticAsset(request) {
  const url = new URL(request.url);
  return (
    request.destination === 'style' ||
    request.destination === 'script' ||
    url.pathname.match(/\.(css|js|ico|png|jpg|jpeg|gif|svg|woff|woff2|ttf|eot)$/i)
  );
}

// 是否为 API 请求
function isApiRequest(request) {
  const url = new URL(request.url);
  return url.pathname.startsWith('/api/');
}

// 是否为 HTML 页面导航请求
function isHtmlPage(request) {
  return request.mode === 'navigate' || request.destination === 'document';
}

// ============================================================
// 缓存策略实现
// ============================================================

// cache-first：缓存优先，缓存未命中时回退到网络，并把结果写入缓存
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }
  const networkResponse = await fetch(request);
  // 仅缓存成功的 GET 请求结果
  if (networkResponse && networkResponse.ok && request.method === 'GET') {
    cache.put(request, networkResponse.clone());
  }
  return networkResponse;
}

// network-first：网络优先，失败时降级到缓存
async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const networkResponse = await fetch(request);
    // 仅缓存成功的 GET 请求结果
    if (networkResponse && networkResponse.ok && request.method === 'GET') {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    // 网络失败，尝试从缓存读取
    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    throw err;
  }
}

// stale-while-revalidate：立即返回缓存，同时后台更新缓存
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);

  // 后台发起网络请求更新缓存
  const fetchPromise = fetch(request)
    .then((networkResponse) => {
      // 仅缓存成功的 GET 请求结果
      if (networkResponse && networkResponse.ok && request.method === 'GET') {
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    })
    .catch((err) => {
      // 网络请求失败时静默处理，缓存可能已有内容
      console.warn(`[SW] 后台更新缓存失败：${request.url}`, err);
      return null;
    });

  // 若缓存命中则立即返回，否则等待网络请求
  return cachedResponse || fetchPromise;
}

// ============================================================
// 请求拦截与分发
// ============================================================
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // 仅处理 GET 请求，其余请求直接放行
  if (request.method !== 'GET') {
    return;
  }

  // 跳过非 http/https 协议的请求（如 chrome-extension、data 等）
  if (!request.url.startsWith('http')) {
    return;
  }

  let responsePromise;

  if (isApiRequest(request)) {
    // API 请求：纯网络直通，不缓存
    responsePromise = fetch(request);
  } else if (isHtmlPage(request)) {
    // HTML 页面：stale-while-revalidate（先返回缓存，后台更新）
    responsePromise = staleWhileRevalidate(request, PAGE_CACHE);
  } else if (isStaticAsset(request)) {
    // 静态资源：cache-first（缓存优先，JS/CSS 带版本号控制更新）
    responsePromise = cacheFirst(request, STATIC_CACHE);
  } else {
    // 其他资源：默认使用 network-first（保证可用性）
    responsePromise = networkFirst(request, STATIC_CACHE);
  }

  event.respondWith(responsePromise);
});
