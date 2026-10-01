/* Registry console shared helpers. Registry API is same-origin (this console
   is served by the registry service); sign-in goes to the agent on :8080 of
   the same host (portable across pilot laptop and VM). */
const API = '';
const AGENT = location.protocol + '//' + location.hostname + ':8080';
function hdr(extra) {
  const h = Object.assign({'Content-Type': 'application/json'}, extra || {});
  const t = localStorage.getItem('cmr_token');
  if (t) h['Authorization'] = 'Bearer ' + t;
  return h;
}
async function login() {
  const u = document.getElementById('u').value, p = document.getElementById('p').value;
  const r = await fetch(AGENT + '/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: u, password: p})});
  const j = await r.json();
  if (r.ok && j.token) { localStorage.setItem('cmr_token', j.token); document.getElementById('p').value = ''; }
  await whoami();
}
async function logout() {
  try { await fetch(AGENT + '/auth/logout', {method: 'POST', headers: hdr()}); } catch (e) {}
  localStorage.removeItem('cmr_token');
  await whoami();
}
async function whoami() {
  const w = document.getElementById('who');
  try {
    const r = await fetch(AGENT + '/auth/me', {headers: hdr()});
    if (!r.ok) throw 0;
    const j = await r.json();
    w.textContent = 'signed in: ' + j.actor + (j.is_admin ? ' (admin)' : '');
    return j;
  } catch (e) { w.textContent = 'anonymous'; return null; }
}
function Shell(page) {
  const shell = document.getElementById('shell');
  if (shell) shell.innerHTML =
    '<header><div><h1>Registry <small>mock CMR database</small></h1></div>' +
    '<nav><a href="/console/" data-p="index">Tables</a>' +
    '<a href="/console/links.html" data-p="links">Links</a>' +
    '<a href="/console/feed.html" data-p="feed">Feed</a></nav></header>';
  document.querySelectorAll('nav a').forEach(x => { if (x.dataset.p === page) x.classList.add('on'); });
}
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
async function api(path, opts) {
  const r = await fetch(API + path, opts);
  let j = null;
  try { j = await r.json(); } catch (e) {}
  if (r.status === 401) { document.getElementById('who').textContent = 'session expired - sign in again'; }
  return {ok: r.ok, status: r.status, body: j};
}
function kv(obj) {
  return '<table class="kv">' + Object.keys(obj || {}).map(k =>
    '<tr><th>' + esc(k) + '</th><td>' + esc(obj[k]) + '</td></tr>').join('') + '</table>';
}
