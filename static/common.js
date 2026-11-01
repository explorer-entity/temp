/* Shared client helpers for every Manova page.
   1. Adds the login token to every /api/ request.
   2. Offline outbox: scores, location pings and SOS alerts that cannot be sent are queued in
      localStorage with their real timestamp and re-sent automatically when the network returns. */
(function () {
  var isCaregiverPage = location.pathname.indexOf('caregiver') !== -1;
  var TOKEN_KEY = isCaregiverPage ? 'manovaCgToken' : 'manovaToken';
  var OUTBOX_KEY = 'manovaOutbox';
  var rawFetch = window.fetch.bind(window);

  window.fetch = function (url, opts) {
    opts = opts || {};
    var isApi = typeof url === 'string' && url.indexOf('/api/') === 0;
    var token = localStorage.getItem(TOKEN_KEY);
    if (isApi && token) {
      opts.headers = Object.assign({}, opts.headers || {}, { Authorization: 'Bearer ' + token });
    }
    return rawFetch(url, opts).then(function (res) {
      if (isApi && token && res.status === 401 && url.indexOf('/api/login') !== 0) {
        window.dispatchEvent(new Event('manova-auth-expired'));
      }
      return res;
    });
  };

  function readBox() { try { return JSON.parse(localStorage.getItem(OUTBOX_KEY) || '[]'); } catch (e) { return []; } }
  function writeBox(box) { try { localStorage.setItem(OUTBOX_KEY, JSON.stringify(box.slice(-200))); } catch (e) {} }

  function enqueue(url, body) {
    var box = readBox();
    box.push({ url: url, body: body });
    var pings = box.filter(function (i) { return i.url === '/api/update_location'; });
    if (pings.length > 60) { // keep the newest 60 pings; scores and SOS alerts are never dropped
      var drop = pings.length - 60;
      box = box.filter(function (i) { return !(i.url === '/api/update_location' && drop-- > 0); });
    }
    writeBox(box);
  }

  /* POST that survives being offline. Resolves { ok, queued, status }. */
  window.manovaPost = function (url, body) {
    var stamped = Object.assign({}, body, { recorded_at: new Date().toISOString() });
    return window.fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(stamped) })
      .then(function (res) {
        if (res.status >= 500) { enqueue(url, stamped); return { ok: false, queued: true, status: res.status }; }
        return { ok: res.ok, queued: false, status: res.status }; // 4xx = rejected on purpose, do not retry
      })
      .catch(function () { enqueue(url, stamped); return { ok: false, queued: true, status: 0 }; });
  };

  var flushing = false;
  window.manovaFlush = function () {
    if (flushing || !navigator.onLine) return Promise.resolve();
    var box = readBox();
    if (!box.length) return Promise.resolve();
    flushing = true;
    var rest = [];
    return box.reduce(function (chain, item) {
      return chain.then(function () {
        if (rest.length) { rest.push(item); return; } // keep order once something fails
        return rawFetchWithAuth(item).then(function (res) { if (res.status >= 500) rest.push(item); })
          .catch(function () { rest.push(item); });
      });
    }, Promise.resolve()).then(function () { writeBox(rest); flushing = false; });
  };
  function rawFetchWithAuth(item) {
    return window.fetch(item.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(item.body) });
  }
  window.manovaOutboxSize = function () { return readBox().length; };

  window.addEventListener('online', function () { window.manovaFlush(); });
  setInterval(function () { window.manovaFlush(); }, 30000);
  window.addEventListener('load', function () { window.manovaFlush(); });
})();
