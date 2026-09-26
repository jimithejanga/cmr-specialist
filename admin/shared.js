/* Shared admin helpers: token, headers, nav, whoami. */
const API = '';
function hdr(extra) {
  const h = Object.assign({'Content-Type': 'application/json'}, extra || {});
  const t = localStorage.getItem('cmr_token');
  if (t) h['Authorization'] = 'Bearer ' + t;
  return h;
}
async function login() {
  const u = document.getElementById('u').value, p = document.getElementById('p').value;
  const r = await fetch(API + '/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: u, password: p})});
  const j = await r.json();
  if (r.ok && j.token) { localStorage.setItem('cmr_token', j.token); document.getElementById('p').value = ''; }
  await whoami();
}
async function logout() {
  try { await fetch(API + '/auth/logout', {method: 'POST', headers: hdr()}); } catch (e) {}
  localStorage.removeItem('cmr_token');
  await whoami();
}
async function whoami() {
  const w = document.getElementById('who'), a = document.getElementById('adm');
  try {
    const r = await fetch(API + '/auth/me', {headers: hdr()});
    if (!r.ok) throw 0;
    const j = await r.json();
    w.textContent = 'signed in: ' + j.actor;
    a.textContent = j.is_admin ? 'ADMIN' : 'not admin';
    a.className = 'badge ' + (j.is_admin ? 'ok' : 'warn');
    return j;
  } catch (e) { w.textContent = 'anonymous'; a.textContent = 'not admin'; a.className = 'badge warn'; return null; }
}
function AdminNav(page) {
  document.querySelectorAll('nav a').forEach(x => { if (x.dataset.p === page) x.classList.add('on'); });
}
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
