/* The app shell is cached; data is never cached.
   The network is sometimes there and sometimes not in the arena. The cache gives exactly one thing: the page opens
   and shows the history instead of "no connection". */
/* Every shell asset must be in SHELL: with network-first, a file missing from the list never reaches the cache before the first network loss. */
const V = 'shell-29';
const SHELL = ['/', '/static/app.css', '/static/ui.css',
               '/static/isu_rank.js', '/static/text.js', '/static/coach-core.js',
               '/static/coach-today.js', '/static/coach-journal.js', '/static/coach-progress.js',
               '/static/coach-fitness.js', '/static/coach-player.js', '/static/coach-init.js',
               '/static/app-core.js', '/static/app-drill.js', '/static/app-answer.js',
               '/static/app-account.js', '/static/app-share.js', '/static/app-auth.js',
               '/static/app-team.js', '/static/app-video.js', '/static/app-live.js',
               '/static/app-upload.js', '/static/app-waiting.js', '/static/app-results.js',
               '/static/app-boot.js', '/static/app-assess.js', '/static/app-wiring.js',
               '/static/icon.svg', '/static/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  const isShell = u.pathname === '/' || u.pathname.startsWith('/static/');
  if (!isShell) return;
  e.respondWith(
    fetch(e.request)
      .then(r => { const c = r.clone(); caches.open(V).then(x => x.put(e.request, c)); return r; })
      .catch(() => caches.match(e.request).then(r => r || caches.match('/')))
  );
});
