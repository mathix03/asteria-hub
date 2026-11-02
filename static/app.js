'use strict';
const $ = id => document.getElementById(id);
const state = {page: 1, pages: 1, favorites: false, played: false, token: '', status: null, request: 0, controller: null};
let toastTimer, searchTimer;
function toast(message, error = false) {
  $('toast').textContent = message;
  $('toast').className = error ? 'error' : '';
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 8000 : 4000);
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type': 'application/json', 'X-Asteria-Token': state.token, ...options.headers}});
  let data;
  try { data = await response.json(); } catch { throw new Error('Réponse du serveur illisible.'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Vérifie les informations saisies.');
  return data;
}
function size(bytes) {
  const units = ['o', 'Ko', 'Mo', 'Go', 'To'];
  let index = 0;
  while (bytes >= 1024 && index < units.length - 1) { bytes /= 1024; index++; }
  return `${new Intl.NumberFormat('fr', {maximumFractionDigits: index ? 1 : 0}).format(bytes)} ${units[index]}`;
}
function updateStatus(data) {
  state.status = data;
  $('gameCount').textContent = data.count;
  $('navCount').textContent = data.count;
  $('totalSize').textContent = size(data.total_size);
  $('emulatorStatus').textContent = data.emulator_ready ? '● Prêt à jouer' : 'À configurer';
  $('emulatorStatus').classList.toggle('ready', data.emulator_ready);
  $('configureBtn').textContent = data.settings.rom_directories.length ? '＋ Gérer les dossiers' : '＋ Configurer ma bibliothèque';
  $('warnings').textContent = data.warnings.join('\n');
  $('warnings').hidden = !data.warnings.length;
}
function openSettings() {
  if (!state.status) { toast('Connexion au serveur en cours. Réessaie dans un instant.', true); return; }
  $('emulator').value = state.status.settings.emulator_path;
  $('directories').value = state.status.settings.rom_directories.join('\n');
  $('settingsError').hidden = true;
  $('settingsDialog').showModal();
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function card(game) {
  const node = element('article', 'card');
  const art = element('div', 'art');
  const hue = parseInt(game.id.slice(0, 4), 16) % 360;
  art.style.setProperty('--hue', hue);
  art.append(element('span', 'initial', game.title.slice(0, 2).toLocaleUpperCase('fr')), element('span', 'format-tag', game.format));
  if (game.has_cover) {
    const cover = document.createElement('img');
    cover.className = 'cover'; cover.alt = ''; cover.loading = 'lazy';
    cover.src = `/api/games/${game.id}/cover`;
    cover.addEventListener('error', () => cover.remove());
    art.prepend(cover);
  }
  const favorite = element('button', 'favorite', game.favorite ? '★' : '☆');
  favorite.setAttribute('aria-label', `${game.favorite ? 'Retirer des' : 'Ajouter aux'} favoris : ${game.title}`);
  favorite.setAttribute('aria-pressed', String(game.favorite));
  favorite.addEventListener('click', async () => {
    favorite.disabled = true;
    try { await api(`/api/games/${game.id}/favorite`, {method: 'POST', body: JSON.stringify({enabled: !game.favorite})}); await loadGames(); }
    catch (error) { toast(error.message, true); favorite.disabled = false; }
  });
  art.append(favorite);
  const body = element('div', 'card-body');
  const title = element('h3', '', game.title);
  title.title = game.title;
  let meta = size(game.size);
  if (game.count) meta += ` · ${game.count} lancement${game.count > 1 ? 's' : ''}`;
  body.append(title, element('p', 'metadata', meta));
  const play = element('button', 'play', '▶  Lancer le jeu');
  play.setAttribute('aria-label', `Lancer ${game.title}`);
  play.addEventListener('click', async () => {
    play.disabled = true;
    try { await api(`/api/games/${game.id}/launch`, {method: 'POST'}); toast('Commande de lancement envoyée à l’émulateur.'); await loadGames(); }
    catch (error) { toast(error.message, true); }
    finally { play.disabled = false; }
  });
  body.append(play); node.append(art, body); return node;
}
function emptyState(error) {
  const node = element('div', 'empty');
  const configured = state.status?.settings.rom_directories.length;
  node.append(element('span', 'symbol', error ? '!' : '✳'), element('h3', '', error ? 'Connexion interrompue' : configured ? 'Aucun jeu dans cette vue' : 'Votre prochaine aventure commence ici'));
  node.append(element('p', '', error || (configured ? 'Essayez une autre recherche, modifiez vos filtres ou analysez à nouveau vos dossiers.' : 'Ajoutez un dossier de jeux et votre émulateur. Asteria organise vos fichiers, sans téléchargement ni compte.')));
  const action = element('button', 'primary', error ? 'Réessayer' : 'Configurer les dossiers');
  action.addEventListener('click', error ? initialize : openSettings);
  node.append(action); return node;
}
async function loadGames() {
  const request = ++state.request;
  state.controller?.abort();
  state.controller = new AbortController();
  $('games').setAttribute('aria-busy', 'true');
  const params = new URLSearchParams({q: $('search').value, favorites: state.favorites, played: state.played, format: $('format').value, sort: $('sort').value, page: state.page});
  try {
    const data = await api(`/api/games?${params}`, {signal: state.controller.signal});
    if (request !== state.request) return;
    state.page = data.page; state.pages = data.pages;
    $('resultCount').textContent = `${data.total} jeu${data.total > 1 ? 'x' : ''} · bibliothèque locale`;
    $('games').replaceChildren(...(data.games.length ? data.games.map(card) : [emptyState()]));
    $('pageLabel').textContent = `${state.page} / ${state.pages}`;
    $('previous').disabled = state.page <= 1;
    $('next').disabled = state.page >= state.pages;
  } catch (error) {
    if (error.name === 'AbortError' || request !== state.request) return;
    $('games').replaceChildren(emptyState(error.message));
    $('resultCount').textContent = 'Chargement impossible';
    $('previous').disabled = $('next').disabled = true;
  } finally { if (request === state.request) $('games').setAttribute('aria-busy', 'false'); }
}
async function initialize() {
  try { state.token = (await api('/api/session')).token; updateStatus(await api('/api/status')); await loadGames(); }
  catch (error) { $('games').replaceChildren(emptyState(error.message)); $('games').setAttribute('aria-busy', 'false'); $('resultCount').textContent = 'Serveur indisponible'; toast(error.message, true); }
}
$('settingsBtn').addEventListener('click', openSettings);
$('configureBtn').addEventListener('click', openSettings);
for (const id of ['closeSettings', 'cancelSettings']) $(id).addEventListener('click', () => $('settingsDialog').close());
$('settingsForm').addEventListener('submit', async event => {
  event.preventDefault(); $('saveSettings').disabled = true; $('settingsError').hidden = true;
  try {
    const data = await api('/api/settings', {method: 'POST', body: JSON.stringify({emulator_path: $('emulator').value.trim(), rom_directories: $('directories').value.split('\n').map(p => p.trim()).filter(Boolean)})});
    updateStatus(data); state.page = 1; $('settingsDialog').close(); await loadGames(); toast('Configuration enregistrée. Bibliothèque actualisée.');
  } catch (error) { $('settingsError').textContent = error.message; $('settingsError').hidden = false; }
  finally { $('saveSettings').disabled = false; }
});
$('scanBtn').addEventListener('click', async () => {
  $('scanBtn').disabled = true; $('scanBtn').textContent = 'Analyse en cours…';
  try { updateStatus(await api('/api/scan', {method: 'POST'})); await loadGames(); toast('Analyse terminée.'); }
  catch (error) { toast(error.message, true); }
  finally { $('scanBtn').disabled = false; $('scanBtn').textContent = '↻ Analyser les dossiers'; }
});
$('search').addEventListener('input', () => { clearTimeout(searchTimer); state.controller?.abort(); state.request++; searchTimer = setTimeout(() => { state.page = 1; loadGames(); }, 180); });
for (const id of ['format', 'sort']) $(id).addEventListener('change', () => { state.page = 1; loadGames(); });
for (const id of ['allTab', 'favoritesTab', 'recentTab']) $(id).addEventListener('click', () => {
  for (const tab of ['allTab', 'favoritesTab', 'recentTab']) { $(tab).classList.toggle('active', tab === id); $(tab).setAttribute('aria-pressed', String(tab === id)); }
  state.favorites = id === 'favoritesTab'; state.played = id === 'recentTab'; $('sort').value = id === 'recentTab' ? 'recent' : 'title';
  $('viewTitle').textContent = id === 'favoritesTab' ? 'Mes favoris' : id === 'recentTab' ? 'Derniers lancements' : 'Ma bibliothèque';
  state.page = 1; loadGames();
});
$('previous').addEventListener('click', () => { if (state.page > 1) { state.page--; loadGames(); } });
$('next').addEventListener('click', () => { if (state.page < state.pages) { state.page++; loadGames(); } });
$('exportBtn').addEventListener('click', () => { const link = document.createElement('a'); link.href = '/api/export'; link.download = 'asteria-library.json'; link.click(); });
document.addEventListener('keydown', event => {
  if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) && !$('settingsDialog').open) { event.preventDefault(); $('search').focus(); }
});
initialize();
