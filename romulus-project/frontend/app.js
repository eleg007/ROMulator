const API = '';
function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return Array.from(document.querySelectorAll(sel)); }

function fp() {
  return btoa([navigator.userAgent, navigator.language, screen.width + 'x' + screen.height, Intl.DateTimeFormat().resolvedOptions().timeZone, navigator.hardwareConcurrency || ''].join('|')).slice(0, 64);
}
const deviceFingerprint = fp();

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) throw new Error((data && (data.detail || data.message)) || `HTTP ${res.status}`);
  return data;
}

function showView(name) {
  qsa('.view').forEach(v => { v.classList.remove('active'); v.style.display = 'none'; });
  const el = document.getElementById('view-' + name);
  if (!el) return;
  el.classList.add('active');
  el.style.display = (name === 'auth') ? 'flex' : 'flex';
}

function showError(id, msg) {
  const el = qs(id);
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 4000);
}

function openModal(id) { qs('#' + id).classList.add('show'); }
function closeModal(id) { qs('#' + id).classList.remove('show'); }

// Auth tabs
qs('#tabLogin').addEventListener('click', () => {
  qs('#tabLogin').classList.add('active');
  qs('#tabSignup').classList.remove('active');
  qs('#auth-login').classList.remove('hidden');
  qs('#auth-signup').classList.add('hidden');
});
qs('#tabSignup').addEventListener('click', () => {
  qs('#tabSignup').classList.add('active');
  qs('#tabLogin').classList.remove('active');
  qs('#auth-signup').classList.remove('hidden');
  qs('#auth-login').classList.add('hidden');
});

qs('#loginBtn').addEventListener('click', async () => {
  try {
    await api('/api/auth/login', {
      method: 'POST',
      body: { username: qs('#loginUsername').value.trim(), password: qs('#loginPassword').value, device_fingerprint: deviceFingerprint },
    });
    await loadMe();
  } catch (e) { showError('#loginError', e.message); }
});

qs('#signupBtn').addEventListener('click', async () => {
  try {
    // validate PIN and get token
    const pinData = await api('/api/pin/entry', {
      method: 'POST',
      body: { pin: qs('#signupPin').value.trim(), device_fingerprint: deviceFingerprint },
    });
    await api('/api/auth/signup', {
      method: 'POST',
      body: {
        token: pinData.token,
        full_name: qs('#signupName').value.trim(),
        email: qs('#signupEmail').value.trim(),
        username: qs('#signupUsername').value.trim(),
        password: qs('#signupPassword').value,
      },
    });
    await loadMe();
  } catch (e) { showError('#signupError', e.message); }
});

async function loadMe() {
  try {
    const data = await api('/api/me');
    const user = data.user;
    if (user.status === 'Pending') { showView('pending'); return; }
    if (user.status === 'Blocked' || user.status === 'Deleted') { showView('blocked'); return; }
    qs('#userChip').innerHTML = `<strong>${user.username}</strong> · ${user.status}`;
    qs('#adminUserChip').innerHTML = `<strong>${user.username}</strong> · ${user.status}`;
    if (user.status === 'Admin' || user.status === 'Owner' || user.status === 'Test User') {
      qs('#openAdminBtn').classList.remove('hidden');
    } else {
      qs('#openAdminBtn').classList.add('hidden');
    }
    const badges = data.badges || [];
    const badgeHtml = badges.length ? badges.map(b => `<span class="tag" style="margin:2px;display:inline-block;">${b}</span>`).join('') : 'No badges yet.';
    const badgeModalList = qs('#badgesModalList');
    if (badgeModalList) badgeModalList.innerHTML = badgeHtml;
    await loadLibrary();
    showView('app');
    const msgs = data.messages || [];
    if (msgs.length) showMessage(msgs[0].content, msgs[0].id);
  } catch (e) { showView('auth'); }
}

function showMessage(content, id) {
  const modal = qs('#msgModal');
  qs('#msgContent').textContent = DOMPurify.sanitize(content, { ALLOWED_TAGS: [] });
  modal.classList.add('show');
  let count = 5;
  const countdown = qs('#msgCountdown');
  countdown.textContent = count;
  const timer = setInterval(() => {
    count -= 1; countdown.textContent = count;
    if (count <= 0) {
      clearInterval(timer);
      modal.classList.remove('show');
      if (id) api('/api/messages/' + id + '/displayed', { method: 'POST' }).catch(() => {});
    }
  }, 1000);
  modal.onclick = (e) => { if (e.target === modal && count > 0) e.stopPropagation(); };
}

qs('#pendingLogout').addEventListener('click', logout);
qs('#blockedLogout').addEventListener('click', logout);
qs('#appLogout').addEventListener('click', logout);
async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (e) {}
  showView('auth');
}

// Sidebar collapse
const sidebar = qs('#sidebar');
const sidebarState = localStorage.getItem('sidebarCollapsed') === '1';
if (sidebarState) sidebar.classList.add('collapsed');
qs('#sidebarToggle').addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
  localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed') ? '1' : '0');
});

let selectedItemId = null;
let libraryItems = [];

qs('#badgesOpenBtn').addEventListener('click', () => openModal('badgesModal'));
qs('#badgesCloseBtn').addEventListener('click', () => closeModal('badgesModal'));

async function loadLibrary() {
  try {
    const data = await api('/api/library');
    libraryItems = data.items || [];
    const list = qs('#libraryList');
    list.innerHTML = '';
    libraryItems.forEach(item => {
      const div = document.createElement('div');
      div.className = 'game-item';
      div.innerHTML = `<div class="g-icon">${item.system === 'SWF' ? '⚡' : '🎮'}</div><div class="g-info"><div class="g-name">${item.title}</div><div class="g-meta">${item.system} · ${item.visibility} · ♥${item.upvotes}</div></div>`;
      div.addEventListener('click', () => play(item));
      list.appendChild(div);
    });
  } catch (e) { console.error(e); }
}

// Upload modal
qs('#uploadIconBtn').addEventListener('click', () => openModal('uploadModal'));
qs('#uploadCloseBtn').addEventListener('click', () => closeModal('uploadModal'));
qs('#uploadBtn').addEventListener('click', async () => {
  const title = qs('#uploadTitle').value.trim();
  const system = qs('#uploadSystem').value;
  const file = qs('#uploadFile').files[0];
  if (!title || !file) { alert('Title and file required'); return; }
  const fd = new FormData();
  fd.append('title', title);
  fd.append('system', system);
  fd.append('file', file);
  try {
    await fetch('/api/library/upload', { method: 'POST', credentials: 'include', body: fd });
    qs('#uploadTitle').value = '';
    qs('#uploadFile').value = '';
    closeModal('uploadModal');
    await loadLibrary();
  } catch (e) { alert(e.message); }
});

function play(item) {
  selectedItemId = item.id;
  qs('#nowPlaying').textContent = item.title;
  const container = qs('#emulatorWrap');
  container.innerHTML = '';
  qs('#voteBtn').onclick = async () => {
    try { await api('/api/library/' + item.id + '/vote', { method: 'POST' }); await loadLibrary(); } catch (e) { alert(e.message); }
  };
  if (item.system === 'SWF') {
    try {
      const ruffle = window.RufflePlayer.newest();
      const player = ruffle.createPlayer();
      player.style.width = '100%';
      player.style.height = '100%';
      container.appendChild(player);
      player.load({ url: `/api/library/${item.id}/download` });
    } catch (e) {
      container.innerHTML = '<div style="color:var(--muted);padding:20px;">Ruffle failed to load.</div>';
    }
  } else {
    const gameDiv = document.createElement('div');
    gameDiv.id = 'game';
    gameDiv.style.width = '100%';
    gameDiv.style.height = '100%';
    container.appendChild(gameDiv);
    window.EJS_player = '#game';
    window.EJS_gameUrl = `/api/library/${item.id}/download`;
    window.EJS_core = 'nes';
    const loader = document.createElement('script');
    loader.src = 'https://cdn.emulatorjs.org/latest/data/loader.js';
    document.body.appendChild(loader);
  }
  api('/api/activity/start', { method: 'POST', body: { game_id: item.id, system: item.system } }).catch(() => {});
}

// Admin
qs('#openAdminBtn').addEventListener('click', () => { showView('admin'); loadAdmin(); });
qs('#adminBackBtn').addEventListener('click', () => showView('app'));

let selectedAdminUserId = null;
async function loadAdmin() {
  try {
    const data = await api('/api/users');
    const users = data.users || [];
    const filter = (window._adminFilter || 'all');
    const filtered = filter === 'all' ? users : users.filter(u => u.status === filter);
    const body = qs('#adminUsers');
    body.innerHTML = '';
    filtered.forEach(u => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><div class="u-name">${u.username}</div><div class="u-email">${u.email}</div></td><td><span class="tag t-${u.status.toLowerCase().replace(/ /g,'-')}">${u.status}</span></td><td><div class="act-cell"><button class="btn btn-ghost btn-xs edit-btn" data-id="${u.id}" data-name="${u.username}" data-status="${u.status}">Edit</button></div></td>`;
      body.appendChild(tr);
    });
    qsa('.edit-btn').forEach(btn => btn.addEventListener('click', () => openAdminUserModal(btn.dataset.id, btn.dataset.name, btn.dataset.status)));
    const ndata = await api('/api/notifications');
    qs('#adminNotifications').innerHTML = (ndata.notifications || []).map(n => `<div>${n.created_at} · ${n.message}</div>`).join('') || 'No notifications.';
  } catch (e) { console.error(e); }
}

qsa('.filter-btn').forEach(btn => btn.addEventListener('click', () => {
  qsa('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  window._adminFilter = btn.dataset.filter;
  loadAdmin();
}));

function openAdminUserModal(id, name, status) {
  selectedAdminUserId = id;
  qs('#adminModalTitle').textContent = 'Edit ' + name;
  qs('#adminModalSub').textContent = 'User ID: ' + id;
  qs('#adminStatusSelect').value = status;
  qs('#adminUserModal').classList.add('show');
}
qs('#adminCloseModal').addEventListener('click', () => qs('#adminUserModal').classList.remove('show'));
qs('#adminSaveStatus').addEventListener('click', async () => {
  if (!selectedAdminUserId) return;
  try {
    await api('/api/admin/users/' + selectedAdminUserId + '/status', { method: 'POST', body: { status: qs('#adminStatusSelect').value } });
    qs('#adminUserModal').classList.remove('show');
    await loadAdmin();
  } catch (e) { alert(e.message); }
});
qs('#adminSendMsg').addEventListener('click', async () => {
  if (!selectedAdminUserId) return;
  const content = qs('#adminMsgText').value.trim();
  if (!content) return;
  try { await api('/api/admin/users/' + selectedAdminUserId + '/message', { method: 'POST', body: { content } }); qs('#adminMsgText').value = ''; alert('Message sent'); } catch (e) { alert(e.message); }
});
qs('#adminAddBadge').addEventListener('click', async () => {
  if (!selectedAdminUserId) return;
  const badge = qs('#adminBadgeText').value.trim();
  if (!badge) return;
  try { await api('/api/admin/users/' + selectedAdminUserId + '/badges', { method: 'POST', body: { badge } }); qs('#adminBadgeText').value = ''; alert('Badge added'); } catch (e) { alert(e.message); }
});

// Code modal
qs('#genCodeOpenBtn').addEventListener('click', () => openModal('codeModal'));
qs('#codeCloseBtn').addEventListener('click', () => closeModal('codeModal'));
qs('#genCodeBtn').addEventListener('click', async () => {
  const name = qs('#codeName').value.trim();
  if (!name) { alert('Holder name required'); return; }
  try {
    const data = await api('/api/admin/codes', { method: 'POST', body: { holder_name: name } });
    qs('#codeResult').textContent = `Code ${data.code} generated for ${data.holder_name}`;
    qs('#codeName').value = '';
  } catch (e) { alert(e.message); }
});

loadMe();
