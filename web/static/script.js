/**
 * script.js — карточки на испанском: свайпы, переворот, словарь.
 */
 
// ============================================
// TELEGRAM WEBAPP / ID ПОЛЬЗОВАТЕЛЯ
// ============================================
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.ready(); tg.expand(); }
 
function getTelegramId() {
  if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) return tg.initDataUnsafe.user.id;
  return window.LINGOPAL_CONFIG?.devUserId || null;
}
const TELEGRAM_ID = getTelegramId();
 
// ============================================
// API-ХЕЛПЕР
// ============================================
async function api(path, options = {}) {
  const resp = await fetch(path, {
    method: options.method || 'GET',
    headers: { 'Content-Type': 'application/json',
      ...(tg?.initData ? {'X-Telegram-Init-Data': tg.initData} : {'X-Dev-User': String(TELEGRAM_ID || '')}) },
    signal: AbortSignal.timeout(60000),
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(typeof data.detail === 'string' ? data.detail :
    resp.status === 422 ? 'Проверь введённые данные' : `Ошибка ${resp.status}`);
  return data;
}
 
// ============================================
// TOAST
// ============================================
let toastTimer = null;
function showToast(text, type = '') {
  const el = document.getElementById('toast');
  el.textContent = text;
  el.className = 'toast show' + (type ? ' ' + type : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}
 
// ============================================
// ТАБЫ
// ============================================
function initTabs() {
  const buttons = document.querySelectorAll('.tab-btn[data-tab]');
  buttons.forEach(button => {
    button.onclick = () => {
      buttons.forEach(item => {
        item.classList.toggle('active', item === button);
        item.setAttribute('aria-current', item === button ? 'page' : 'false');
      });
      document.querySelectorAll('.screen').forEach(screen => screen.classList.toggle('active', screen.id === 'screen-' + button.dataset.tab));
      if (typeof closeWordPopup === 'function') closeWordPopup();
      const tab = button.dataset.tab;
      if (tab === 'dictionary') { loadDictionary(); loadReviewPacks(); loadLeitnerDueCount(); }
      if (tab === 'grammar') initGrammarScreen();
      if (tab === 'profile') initProfileScreen();
      if (tab === 'linguaplay') initLinguaPlayScreen();
      if (tab === 'cards') { loadLevelProgress(); loadPacksList(); loadQuests(); }
      window.scrollTo({top: 0});
    };
  });
}

let selectedLevel = 'A1';
let selectedType = 'word';
 
function initPickers() {
  document.querySelectorAll('#levelPicker .picker-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#levelPicker .picker-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      selectedLevel = btn.dataset.level;
      loadLevelProgress();
      loadPacksList();
    });
  });
  document.querySelectorAll('#typePicker .picker-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#typePicker .picker-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      selectedType = btn.dataset.type;
      loadLevelProgress();
      loadPacksList();
    });
  });
  document.getElementById('startDeckBtn').addEventListener('click', startDeck);
  document.getElementById('exitDeckBtn').addEventListener('click', exitDeck);
}
 
// ============================================
// КОЛОДА КАРТОЧЕК (ЗАДАЧА 2: паки по 20 карточек)
// ============================================
let currentPack = null;   // {pack_key, level, item_type, unlearned_count, session_index, session_total, session_cards}
let cardEl = null;        // текущий DOM-элемент карточки
let dragState = null;     // {startX, currentX, pointerId} во время свайпа
let deckOrigin = 'cards'; // куда вернуться при выходе — 'cards' или 'dictionary'
 
async function startDeck() {
  const button = document.getElementById('startDeckBtn');
  if (button.disabled) return;
  button.disabled = true;
  const size = parseInt(document.getElementById('packSizeSlider').value, 10);
  try {
    const data = await api('/api/packs/start', {
      method: 'POST',
      body: { telegram_id: TELEGRAM_ID, level: selectedLevel, item_type: selectedType, size },
    });
    currentPack = data.pack;
    deckOrigin = 'cards';
    enterDeck();
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    button.disabled = false;
  }
}
 
function openReviewPack(pack) {
  currentPack = pack;
  deckOrigin = 'dictionary';
  enterDeck();
}
 
function enterDeck() {
  document.getElementById('screen-cards').classList.add('active');
  document.getElementById('screen-dictionary').classList.remove('active');
  document.querySelectorAll('.tab-btn[data-tab]').forEach((b) => b.classList.remove('active'));
  document.querySelector('.tab-btn[data-tab="cards"]').classList.add('active');
 
  document.getElementById('cardsPicker').style.display = 'none';
  document.getElementById('cardsDeck').style.display = 'flex';
  renderCurrentCard();
}
 
function exitDeck() {
  if (swipeBusy) return;
  document.getElementById('cardsDeck').style.display = 'none';
  document.getElementById('cardsPicker').style.display = 'block';
  document.getElementById('deckStage').innerHTML = '';
  currentPack = null;
 
  if (deckOrigin === 'dictionary') {
    document.querySelectorAll('.tab-btn[data-tab]').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    document.querySelector('.tab-btn[data-tab="dictionary"]').classList.add('active');
    document.getElementById('screen-dictionary').classList.add('active');
    loadReviewPacks();
  } else {
    loadLevelProgress();
    loadPacksList();
  }
  loadQuests();
}
 
function updateDeckHeader() {
  document.getElementById('deckProgressLabel').textContent =
    `Было ${currentPack.total}, осталось ${currentPack.unlearned_count} невыученных`;
  document.getElementById('deckPackLabel').textContent = currentPack.is_repeat
    ? `Повторение слов`
    : `${currentPack.level} · ${currentPack.item_type === 'word' ? 'Слова' : 'Предложения'}`;
}
 
function renderDeckActions() {
  const actions = document.getElementById('deckActions');
  const exitBtn = document.getElementById('exitDeckBtn');
  const passFinished = currentPack.session_index >= currentPack.session_cards.length;
 
  if (!passFinished) {
    exitBtn.style.display = '';
    actions.innerHTML = `
      <button class="deck-action-btn dont-know" id="btnDontKnow" title="Не знаю">✕</button>
      <button class="deck-action-btn know" id="btnKnow" title="Знаю">✓</button>
    `;
    document.getElementById('btnKnow').addEventListener('click', () => swipeCurrent(true));
    document.getElementById('btnDontKnow').addEventListener('click', () => swipeCurrent(false));
    return;
  }
 
  if (currentPack.fully_learned) {
    exitBtn.style.display = '';
    actions.innerHTML = `<button class="deck-finish-btn" id="btnFinishPack">Закончить пак</button>`;
    document.getElementById('btnFinishPack').addEventListener('click', finishPack);
  } else {
    exitBtn.style.display = '';
    actions.innerHTML = `<button class="deck-continue-btn" id="btnContinuePack">Доучить слова</button>`;
    document.getElementById('btnContinuePack').addEventListener('click', continuePack);
  }
}
 
function renderCurrentCard() {
  updateDeckHeader();
  const stage = document.getElementById('deckStage');
  stage.innerHTML = '';
 
  const passFinished = currentPack.session_index >= currentPack.session_cards.length;
 
  if (passFinished) {
    if (currentPack.fully_learned) {
      stage.innerHTML = `
        <div class="deck-celebration">
          <div class="glyph">🎉</div>
          <div class="title">Пак пройден! Все слова выучены!</div>
        </div>
      `;
    } else {
      stage.innerHTML = `
        <div class="deck-celebration">
          <div class="glyph">📌</div>
          <div class="title">Проход завершён</div>
          <div class="deck-unlearned-label">Осталось <b>${currentPack.unlearned_count}</b> невыученных слов</div>
        </div>
      `;
    }
    renderDeckActions();
    return;
  }
 
  const item = currentPack.session_cards[currentPack.session_index];
  cardEl = buildCardElement(item);
  stage.appendChild(cardEl);
  renderDeckActions();
}
 
function buildCardElement(item) {
  const el = document.createElement('div');
  el.className = 'card';
 
  const backContent = item.example
    ? `<div class="card-translation">${escapeHtml(item.ru)}</div><div class="card-example">${escapeHtml(item.example)}</div>`
    : `<div class="card-translation">${escapeHtml(item.ru)}</div>`;
 
  el.innerHTML = `
    <div class="card-inner">
      <div class="card-face">
        <span class="card-level-badge">${currentPack.level}</span>
        <button class="tts-btn card-tts-btn" data-word="${escapeHtml(item.es)}" title="Прослушать">🔊</button>
        <div class="card-word">${escapeHtml(item.es)}</div>
        <div class="card-hint">Тапни, чтобы перевернуть</div>
        <div class="swipe-tint right"></div>
        <div class="swipe-tint left"></div>
      </div>
      <div class="card-face card-face-back">
        ${backContent}
      </div>
    </div>
  `;
 
  attachCardInteractions(el, item);
  el.tabIndex = 0;
  el.setAttribute('role', 'group');
  el.setAttribute('aria-label', 'Карточка. Enter — перевернуть; стрелки — не знаю или знаю.');
  el.addEventListener('keydown', event => {
    if (event.target !== el) return;
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); el.classList.toggle('flipped'); }
    if (event.key === 'ArrowRight') swipeCurrent(true);
    if (event.key === 'ArrowLeft') swipeCurrent(false);
  });
  return el;
}
 
function attachCardInteractions(el, item) {
  let moved = false;
 
  const ttsBtn = el.querySelector('.card-tts-btn');
  ttsBtn.addEventListener('click', (e) => {
    e.stopPropagation(); // иначе клик по 🔊 ещё и перевернёт карточку
    playTTS(item.es, ttsBtn);
  });
 
  el.addEventListener('click', () => {
    if (moved) { moved = false; return; }
    el.classList.toggle('flipped');
  });
 
  el.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;
    dragState = { startX: e.clientX, currentX: e.clientX, pointerId: e.pointerId };
    el.setPointerCapture(e.pointerId);
    el.classList.add('dragging');
    moved = false;
  });
 
  el.addEventListener('pointermove', (e) => {
    if (!dragState || dragState.pointerId !== e.pointerId) return;
    dragState.currentX = e.clientX;
    const dx = dragState.currentX - dragState.startX;
    if (Math.abs(dx) > 6) moved = true;
 
    const rotate = dx / 18;
    el.style.transform = `translateX(${dx}px) rotate(${rotate}deg)`;
 
    const rightTint = el.querySelector('.swipe-tint.right');
    const leftTint = el.querySelector('.swipe-tint.left');
    const intensity = Math.min(Math.abs(dx) / 120, 1);
    if (dx > 0) { rightTint.style.opacity = intensity; leftTint.style.opacity = 0; }
    else { leftTint.style.opacity = intensity; rightTint.style.opacity = 0; }
  });
 
  const endDrag = (e) => {
    if (!dragState || dragState.pointerId !== e.pointerId) return;
    const dx = dragState.currentX - dragState.startX;
    el.classList.remove('dragging');
    dragState = null;
 
    const SWIPE_THRESHOLD = 110;
    if (dx > SWIPE_THRESHOLD) {
      swipeCurrent(true);
    } else if (dx < -SWIPE_THRESHOLD) {
      swipeCurrent(false);
    } else {
      el.style.transform = '';
      el.querySelectorAll('.swipe-tint').forEach((t) => (t.style.opacity = 0));
    }
  };
 
  el.addEventListener('pointerup', endDrag);
  el.addEventListener('pointercancel', endDrag);
}
 
let swipeBusy = false;
async function swipeCurrent(knows) {
  if (!cardEl || !currentPack || swipeBusy) return;
  swipeBusy = true;
  const item = currentPack.session_cards[currentPack.session_index];
  cardEl.classList.add(knows ? 'flying-right' : 'flying-left');
  cardEl.style.transform = '';
 
  try {
    const data = await api(`/api/packs/${currentPack.pack_key}/swipe`, {
      method: 'POST',
      body: { telegram_id: TELEGRAM_ID, word_id: item.id, knows },
    });
    currentPack = data.pack;
    applyProgressionResult(currentPack.exp_result, currentPack.streak_result);
    handleQuestEvents(currentPack.quest_events);
    handleUnlockedAchievements(currentPack.unlocked_achievements);
  } catch (e) {
    showToast(e.message, 'error');
    cardEl.classList.remove('flying-right', 'flying-left');
    swipeBusy = false;
    return;
  }
 
  setTimeout(() => { swipeBusy = false; if (currentPack) renderCurrentCard(); }, 380);
}
 
async function continuePack() {
  try {
    const data = await api(`/api/packs/${currentPack.pack_key}/continue`, {
      method: 'POST', body: { telegram_id: TELEGRAM_ID },
    });
    currentPack = data.pack;
    renderCurrentCard();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
async function finishPack() {
  try {
    const data = await api(`/api/packs/${currentPack.pack_key}/finish`, {
      method: 'POST', body: { telegram_id: TELEGRAM_ID },
    });
    applyProgressionResult(data.exp_result, data.streak_result);
    handleUnlockedAchievements(data.unlocked_achievements);
  } catch (e) {
    showToast(e.message, 'error');
  }
  exitDeck();
}
 
function initDeckButtons() {
  document.getElementById('packSizeSlider').addEventListener('input', (e) => {
    document.getElementById('packSizeValue').textContent = e.target.value;
  });
}
 
// ============================================
// ПРОГРЕСС ПО УРОВНЮ И СПИСОК ПАКОВ (ЗАДАЧИ 4, 5)
// ============================================
async function loadLevelProgress() {
  if (!TELEGRAM_ID) return;
  try {
    const data = await api(`/api/progress?telegram_id=${TELEGRAM_ID}&level=${selectedLevel}&item_type=${selectedType}`);
    const el = document.getElementById('levelProgress');
    const pct = data.total ? Math.round((data.learned / data.total) * 100) : 0;
    el.innerHTML = `
      <div class="level-progress-label">Выучено ${data.learned} слов из ${data.total} в уровне ${selectedLevel}</div>
      <div class="level-progress-bar"><div class="level-progress-fill" style="width:${pct}%;"></div></div>
    `;
  } catch (e) {
    console.warn('Не удалось загрузить прогресс уровня:', e.message);
  }
}
 
async function loadPacksList() {
  if (!TELEGRAM_ID) return;
  try {
    const data = await api(`/api/packs?telegram_id=${TELEGRAM_ID}&level=${selectedLevel}`);
    const el = document.getElementById('packsList');
    const packs = data.packs.filter((p) => p.item_type === selectedType);
    if (!packs.length) { el.innerHTML = ''; return; }
 
    el.innerHTML = packs.map((p) => `
      <div class="pack-row">
        <div>
          <div class="pack-row-info">${escapeHtml(p.level)} · ${p.item_type === 'word' ? 'Слова' : 'Предложения'}</div>
          <div class="pack-row-sub">Было ${p.total}, осталось ${p.unlearned_count} невыученных</div>
        </div>
        <div class="pack-row-actions">
          <button class="pack-row-btn" data-resume="${p.pack_key}">Продолжить</button>
          <button class="pack-row-btn danger" data-delete="${p.pack_key}">Удалить</button>
        </div>
      </div>
    `).join('');
 
    el.querySelectorAll('[data-resume]').forEach((btn) => {
      btn.addEventListener('click', () => startDeck()); // start_pack сам вернёт этот же незавершённый пак
    });
    el.querySelectorAll('[data-delete]').forEach((btn) => {
      btn.addEventListener('click', () => deletePack(btn.dataset.delete));
    });
  } catch (e) {
    console.warn('Не удалось загрузить список паков:', e.message);
  }
}
 
async function deletePack(packKey) {
  try {
    await api(`/api/packs/${packKey}?telegram_id=${TELEGRAM_ID}`, { method: 'DELETE' });
    showToast('Пак удалён', 'success');
    loadPacksList();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
 
// ============================================
// СЛОВАРЬ С ФИЛЬТРАМИ (ЗАДАЧА 6)
// ============================================
// ============================================
// СЛОВАРЬ: ЧЕКБОКСЫ ПО БУКВАМ, ПОВТОРЕНИЕ, "СПРОСИТЬ ХОСЕ"
// ============================================
let dictLevelFilter = '';
let dictLetterFilter = '';
let dictSearchQuery = '';
let selectedWordIds = new Set();
let dictEntriesCache = [];
 
function initAlphaStrip() {
  const letters = 'abcdefghijklmnopqrstuvwxyz'.split('');
  const el = document.getElementById('alphaStrip');
  el.innerHTML = `<button class="alpha-btn active" data-letter="">*</button>` +
    letters.map((l) => `<button class="alpha-btn" data-letter="${l}">${l.toUpperCase()}</button>`).join('');
 
  el.querySelectorAll('.alpha-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      el.querySelectorAll('.alpha-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      dictLetterFilter = btn.dataset.letter;
      loadDictionary();
    });
  });
}
 
function initDictLevelFilter() {
  const el = document.getElementById('dictLevelFilter');
  el.querySelectorAll('.dict-filter-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      el.querySelectorAll('.dict-filter-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      dictLevelFilter = btn.dataset.level;
      loadDictionary();
    });
  });
}
 
async function loadDictionary() {
  if (!TELEGRAM_ID) return;
  try {
    const params = new URLSearchParams({ telegram_id: TELEGRAM_ID });
    if (dictLevelFilter) params.set('level', dictLevelFilter);
    if (dictLetterFilter) params.set('letter', dictLetterFilter);
    if (dictSearchQuery) params.set('search', dictSearchQuery);
 
    const data = await api(`/api/dictionary?${params.toString()}`);
    dictEntriesCache = data.entries;
    selectedWordIds.clear();
    updateSelectionBar();
    renderDictionary(dictEntriesCache);
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
function groupByLetter(entries) {
  const groups = {};
  entries.forEach((e) => {
    const letter = (e.es[0] || '#').toUpperCase();
    groups[letter] = groups[letter] || [];
    groups[letter].push(e);
  });
  return Object.keys(groups).sort().reduce((acc, k) => { acc[k] = groups[k]; return acc; }, {});
}
 
function renderDictionary(entries) {
  const list = document.getElementById('dictList');
  const empty = document.getElementById('dictEmpty');
 
  if (!entries.length) {
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
 
  const groups = groupByLetter(entries);
 
  list.innerHTML = Object.entries(groups).map(([letter, items]) => `
    <div class="dict-letter-group">
      <div class="dict-letter-header">
        <div class="dict-letter-title">${escapeHtml(letter)} · ${items.length}</div>
        <button class="dict-letter-select-btn" data-select-letter="${escapeHtml(letter)}">Выбрать все на букву ${escapeHtml(letter)}</button>
      </div>
      ${items.map((item) => `
        <div class="dict-item" data-word-id="${item.word_id}">
          <button class="dict-checkbox" data-checkbox="${item.word_id}" aria-label="Выбрать слово" aria-pressed="${selectedWordIds.has(item.word_id)}">${selectedWordIds.has(item.word_id) ? '✓' : ''}</button>
          <div class="dict-item-text">
            <div class="dict-item-es">${escapeHtml(item.es)}</div>
            <div class="dict-item-ru">${escapeHtml(item.ru)}</div>
          </div>
          <button class="tts-btn dict-tts-btn" data-word="${escapeHtml(item.es)}" title="Прослушать">🔊</button>
          <button class="dict-menu-btn" aria-label="Подробнее о слове" data-menu="${item.word_id}" data-es="${escapeHtml(item.es)}" data-ru="${escapeHtml(item.ru)}">⋮</button>
        </div>
      `).join('')}
    </div>
  `).join('');
 
  // Обновляем класс .selected на всех строках
  list.querySelectorAll('.dict-item').forEach((row) => {
    row.classList.toggle('selected', selectedWordIds.has(parseInt(row.dataset.wordId, 10)));
  });
 
  list.querySelectorAll('[data-checkbox]').forEach((box) => {
    box.addEventListener('click', () => toggleWordSelection(parseInt(box.dataset.checkbox, 10)));
  });
  list.querySelectorAll('[data-select-letter]').forEach((btn) => {
    btn.addEventListener('click', () => selectAllByLetter(btn.dataset.selectLetter, groups[btn.dataset.selectLetter]));
  });
  list.querySelectorAll('[data-menu]').forEach((btn) => {
    btn.addEventListener('click', (e) => openWordMenu(e, parseInt(btn.dataset.menu, 10), btn.dataset.es, btn.dataset.ru));
  });
  list.querySelectorAll('.dict-tts-btn').forEach((btn) => {
    btn.addEventListener('click', () => playTTS(btn.dataset.word, btn));
  });
}
 
function toggleWordSelection(wordId) {
  if (selectedWordIds.has(wordId)) selectedWordIds.delete(wordId);
  else selectedWordIds.add(wordId);
 
  const row = document.querySelector(`.dict-item[data-word-id="${wordId}"]`);
  const box = document.querySelector(`[data-checkbox="${wordId}"]`);
  if (row) row.classList.toggle('selected', selectedWordIds.has(wordId));
  if (box) {
    box.classList.add('checked');
    box.textContent = selectedWordIds.has(wordId) ? '✓' : '';
    setTimeout(() => box.classList.remove('checked'), 200); // короткая анимация "пульса"
  }
  updateSelectionBar();
}
 
function selectAllByLetter(letter, items) {
  const allSelected = items.every((item) => selectedWordIds.has(item.word_id));
  items.forEach((item) => {
    if (allSelected) selectedWordIds.delete(item.word_id);
    else selectedWordIds.add(item.word_id);
  });
  renderDictionary(dictEntriesCache);
  updateSelectionBar();
}
 
function updateSelectionBar() {
  const bar = document.getElementById('selectionBar');
  const count = document.getElementById('selectionCount');
  if (selectedWordIds.size > 0) {
    bar.style.display = 'flex';
    count.textContent = `${selectedWordIds.size} выбрано`;
  } else {
    bar.style.display = 'none';
  }
}
 
function initReviewSelection() {
  document.getElementById('reviewSelectedBtn').addEventListener('click', async () => {
    if (!selectedWordIds.size) return;
    try {
      const data = await api('/api/review/create', {
        method: 'POST',
        body: { telegram_id: TELEGRAM_ID, word_ids: Array.from(selectedWordIds) },
      });
      selectedWordIds.clear();
      updateSelectionBar();
      renderDictionary(dictEntriesCache);
      showToast('Пак повторения создан ✓', 'success');
      loadReviewPacks();
    } catch (e) {
      showToast(e.message, 'error');
    }
  });
}
 
// ============================================
// ПАКИ ПОВТОРЕНИЯ (в разделе "Словарь")
// ============================================
async function loadReviewPacks() {
  if (!TELEGRAM_ID) return;
  try {
    const data = await api(`/api/review/packs?telegram_id=${TELEGRAM_ID}`);
    const el = document.getElementById('reviewPacksList');
    if (!data.packs.length) { el.innerHTML = ''; return; }
 
    el.innerHTML = data.packs.map((p) => `
      <div class="review-pack-row">
        <div>
          <div class="review-pack-info">🔄 ${p.pack_key}</div>
          <div class="review-pack-sub">Было ${p.total}, осталось ${p.unlearned_count} невыученных</div>
        </div>
        <div class="review-pack-actions">
          <button class="review-pack-btn" data-open-review="${p.pack_key}">Учить</button>
          <button class="review-pack-btn danger" data-delete-review="${p.pack_key}">Удалить</button>
        </div>
      </div>
    `).join('');
 
    el.querySelectorAll('[data-open-review]').forEach((btn) => {
      const pack = data.packs.find((p) => p.pack_key === btn.dataset.openReview);
      btn.addEventListener('click', () => openReviewPack(pack));
    });
    el.querySelectorAll('[data-delete-review]').forEach((btn) => {
      btn.addEventListener('click', () => deleteReviewPack(btn.dataset.deleteReview));
    });
  } catch (e) {
    console.warn('Не удалось загрузить паки повторения:', e.message);
  }
}
 
async function deleteReviewPack(packKey) {
  try {
    await api(`/api/packs/${packKey}?telegram_id=${TELEGRAM_ID}`, { method: 'DELETE' });
    showToast('Пак повторения удалён', 'success');
    loadReviewPacks();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
// ============================================
// "⋮" МЕНЮ И МОДАЛКА "СПРОСИТЬ ХОСЕ"
// ============================================
function openWordMenu(event, wordId, es, ru) {
  event.stopPropagation();
  const menu = document.getElementById('wordMenu');
  const rect = event.target.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 6}px`;
  menu.style.left = `${Math.min(rect.left, window.innerWidth - 200)}px`;
  menu.classList.add('open');
 
  const askBtn = document.getElementById('wordMenuAsk');
  askBtn.onclick = () => {
    menu.classList.remove('open');
    openContextModal(es, ru);
  };
}
 
document.addEventListener('click', (e) => {
  const menu = document.getElementById('wordMenu');
  if (menu.classList.contains('open') && !menu.contains(e.target)) {
    menu.classList.remove('open');
  }
});
 
async function openContextModal(es, ru) {
  const overlay = document.getElementById('contextModalOverlay');
  const loader = document.getElementById('contextLoader');
  const body = document.getElementById('contextBody');
 
  document.getElementById('contextModalWord').textContent = es;
  loader.style.display = 'flex';
  body.style.display = 'none';
  overlay.classList.add('open');
 
  try {
    const data = await api('/api/ask-context', { method: 'POST', body: { word: es, translation: ru } });
    document.getElementById('contextText').textContent = data.context || 'Хосе не смог придумать объяснение 🤷';
    document.getElementById('contextExamples').innerHTML = (data.examples || [])
      .map((ex) => `<div class="context-example-item">${ex}</div>`).join('');
    loader.style.display = 'none';
    body.style.display = 'block';
  } catch (e) {
    loader.style.display = 'none';
    body.style.display = 'block';
    document.getElementById('contextText').textContent = `Ошибка: ${e.message}`;
    document.getElementById('contextExamples').innerHTML = '';
  }
}
 
function initContextModal() {
  document.getElementById('contextModalClose').addEventListener('click', () => {
    document.getElementById('contextModalOverlay').classList.remove('open');
  });
  document.getElementById('contextModalOverlay').addEventListener('click', (e) => {
    if (e.target.id === 'contextModalOverlay') e.target.classList.remove('open');
  });
}
 
 
let dictSearchTimer = null;
function initDictSearch() {
  document.getElementById('dictSearch').addEventListener('input', (e) => {
    dictSearchQuery = e.target.value.trim();
    clearTimeout(dictSearchTimer);
    dictSearchTimer = setTimeout(loadDictionary, 300); // debounce, чтобы не долбить API на каждый символ
  });
}
 
// ============================================
// СТАРТ
// ============================================
async function bootstrap() {
  document.getElementById('grammarShortcut').onclick = () => document.querySelector('[data-tab="grammar"]').click();
  const updateConnection = () => { document.getElementById('connectionBanner').hidden = navigator.onLine; };
  window.addEventListener('online', updateConnection);
  window.addEventListener('offline', updateConnection);
  updateConnection();
  document.getElementById('profileBarFlag').addEventListener('click', () => {
    document.querySelector('.tab-btn[data-tab="profile"]').click();
  });
 
  initTabs();
  initPickers();
  initDeckButtons();
  initDictSearch();
  initDictLevelFilter();
  initAlphaStrip();
  initReviewSelection();
  initLeitnerHandlers();
  initContextModal();
  initChat();
  initWelcomeScreen();
  initGrammarHandlers();
  initProfileTab();
  initLinguaPlayHandlers();
  initWordPopupAddButton();
 
  if (!TELEGRAM_ID) {
    showToast('Открой приложение через Telegram-бота', 'error');
    return;
  }
 
  try {
    const data = await api('/api/register', { method: 'POST', body: { telegram_id: TELEGRAM_ID } });
    showWelcomeScreen(data.user.is_new);
    loadLevelProgress();
    loadPacksList();
    loadReviewPacks();
    loadProfile();
    loadQuests();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
document.addEventListener('DOMContentLoaded', bootstrap);
 
// ============================================
// ПРОФИЛЬ: УРОВЕНЬ, EXP, СТРИК
// ============================================
async function loadProfile() {
  if (!TELEGRAM_ID) return;
  try {
    const data = await api(`/api/profile?telegram_id=${TELEGRAM_ID}`);
    renderProfile(data);
  } catch (e) {
    console.warn('Не удалось загрузить профиль:', e.message);
  }
}
 
function renderProfile(profile) {
  document.getElementById('profileLevelBadge').textContent = profile.level;
  document.getElementById('profileExpLabel').textContent = `${profile.exp}/${profile.exp_needed}`;
  const pct = profile.exp_needed ? Math.min(100, (profile.exp / profile.exp_needed) * 100) : 0;
  document.getElementById('profileExpFill').style.width = `${pct}%`;
 
  document.getElementById('profileStreakCount').textContent = profile.streak_count;
  document.getElementById('profileStreak').classList.toggle('active', profile.is_active_today);
  document.getElementById('profileStreak').title =
    `${profile.streak_tier.label} · бонус к EXP +${profile.streak_tier.bonus_pct}%` +
    (profile.is_active_today ? ' · сегодня уже позанимался' : ' · сегодня ещё не занимался');
}
 
/**
 * Единая точка для любого ответа бэкенда с exp_result/streak_result —
 * обновляет шапку профиля и запускает анимацию, если поднялся уровень
 * или сменился огненный уровень стрика.
 */
function applyProgressionResult(expResult, streakResult) {
  if (!expResult && !streakResult) return;
 
  if (expResult) {
    document.getElementById('profileLevelBadge').textContent = expResult.level;
    document.getElementById('profileExpLabel').textContent = `${expResult.exp}/${expResult.exp_needed}`;
    const pct = expResult.exp_needed ? Math.min(100, (expResult.exp / expResult.exp_needed) * 100) : 0;
    document.getElementById('profileExpFill').style.width = `${pct}%`;
  }
  if (streakResult) {
    document.getElementById('profileStreakCount').textContent = streakResult.streak_count;
    document.getElementById('profileStreak').classList.add('active'); // раз стрик обновился — сегодня уже позанимался
  }
 
  if (expResult && expResult.leveled_up) {
    showLevelUpAnimation('🎉', `Уровень ${expResult.level}!`);
  } else if (streakResult && streakResult.tier_changed) {
    showLevelUpAnimation(streakResult.tier.emoji, `${streakResult.tier.label}!`);
  }
}
 
let levelUpTimer = null;
function showLevelUpAnimation(glyph, title) {
  const overlay = document.getElementById('levelUpOverlay');
  document.getElementById('levelUpGlyph').textContent = glyph;
  document.getElementById('levelUpTitle').textContent = title;
  overlay.classList.add('show');
  if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
 
  clearTimeout(levelUpTimer);
  levelUpTimer = setTimeout(() => overlay.classList.remove('show'), 1800);
}
 
// ============================================
// TTS — ОЗВУЧКА ИСПАНСКИХ СЛОВ
// ============================================
const ttsCache = new Map(); // word -> url, чтобы не дёргать /api/tts повторно в рамках сессии
let ttsAudioEl = null;
 
async function playTTS(word, btnEl) {
  if (!word || btnEl.classList.contains('loading')) return;
  btnEl.classList.add('loading');
 
  try {
    let url = ttsCache.get(word);
    if (!url) {
      const data = await api(`/api/tts?word=${encodeURIComponent(word)}`);
      url = data.url;
      ttsCache.set(word, url);
    }
 
    if (!ttsAudioEl) ttsAudioEl = new Audio();
    ttsAudioEl.src = url;
    await ttsAudioEl.play();
  } catch (e) {
    showToast('Не удалось озвучить: ' + e.message, 'error');
  } finally {
    btnEl.classList.remove('loading');
  }
}
 
// ============================================
// ЕЖЕДНЕВНЫЕ КВЕСТЫ
// ============================================
async function loadQuests() {
  if (!TELEGRAM_ID) return;
  try {
    const data = await api(`/api/quests?telegram_id=${TELEGRAM_ID}`);
    renderQuests(data.quests);
  } catch (e) {
    console.warn('Не удалось загрузить квесты:', e.message);
  }
}
 
function renderQuests(quests) {
  const el = document.getElementById('questsList');
  el.innerHTML = quests.map((q) => `
    <div class="quest-row ${q.completed ? 'done' : ''}">
      <div class="quest-check">${q.completed ? '✓' : ''}</div>
      <div class="quest-info">
        <div class="quest-title">${q.title} (${q.current}/${q.target})</div>
        <div class="quest-bar"><div class="quest-bar-fill" style="width:${(q.current / q.target) * 100}%;"></div></div>
      </div>
      <div class="quest-reward mono">+${q.exp}</div>
    </div>
  `).join('');
}
 
/**
 * Общая точка для любого ответа бэкенда с полем quest_events —
 * обновляет список квестов и показывает анимацию за каждое выполненное.
 */
function handleQuestEvents(questEvents) {
  if (!questEvents || !questEvents.length) return;
  loadQuests();
  questEvents.forEach((event, i) => {
    setTimeout(() => {
      showLevelUpAnimation('🎯', `Квест выполнен: ${event.title}!`);
      if (event.exp_result) applyProgressionResult(event.exp_result, null);
    }, i * 2000); // показываем анимации по очереди, если выполнено сразу несколько
  });
}
 
// ============================================
// ЛЕЙТНЕР: КНОПКА ПОВТОРЕНИЯ + СЕССИЯ
// ============================================
let leitnerWords = [];
let leitnerIndex = 0;
let leitnerCorrectCount = 0;
let leitnerSessionId = null;
let leitnerBusy = false;
let leitnerTotalCount = 0;
 
async function loadLeitnerDueCount() {
  if (!TELEGRAM_ID) return;
  try {
    const data = await api(`/api/review/due-count?telegram_id=${TELEGRAM_ID}`);
    const btn = document.getElementById('leitnerReviewBtn');
    const countEl = document.getElementById('leitnerDueCount');
    if (countEl) countEl.textContent = data.count;
    btn.disabled = data.count === 0;
    if (data.count === 0) {
      btn.innerHTML = 'Сейчас нет слов к повторению. Возвращайся позже.';
    } else {
      btn.innerHTML = `Повторить слова 🔥 <span id="leitnerDueCount">${data.count}</span>`;
    }
  } catch (e) {
    console.warn('Не удалось загрузить счётчик повторения:', e.message);
  }
}
 
function initLeitnerHandlers() {
  document.getElementById('leitnerReviewBtn').addEventListener('click', startLeitnerSession);
  document.getElementById('leitnerExitBtn').addEventListener('click', exitLeitnerSession);
}
 
async function startLeitnerSession() {
  try {
    const data = await api('/api/review/start', {method: 'POST', body: {telegram_id: TELEGRAM_ID}});
    leitnerSessionId = data.session_id;
    leitnerTotalCount = data.total_count;
    if (!data.session_id) {
      showToast('Слов для повторения пока нет', 'error');
      return;
    }
    leitnerWords = data.words;
    leitnerIndex = 0;
    leitnerCorrectCount = 0;
 
    document.getElementById('dictionaryMainView').style.display = 'none';
    document.getElementById('leitnerSessionView').style.display = 'flex';
    renderLeitnerCard();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
function exitLeitnerSession() {
  document.getElementById('leitnerSessionView').style.display = 'none';
  document.getElementById('dictionaryMainView').style.display = 'block';
  loadLeitnerDueCount();
  loadDictionary();
}
 
function updateLeitnerProgress() {
  document.getElementById('leitnerProgressLabel').textContent = `${leitnerIndex} / ${leitnerWords.length}`;
}
 
function renderLeitnerCard() {
  updateLeitnerProgress();
  const stage = document.getElementById('leitnerStage');
 
  if (leitnerIndex >= leitnerWords.length) {
    finishLeitnerSession();
    return;
  }
 
  const word = leitnerWords[leitnerIndex];
  stage.innerHTML = `
    <div class="leitner-card">
      <div class="leitner-word">${escapeHtml(word.es)}</div>
      <div class="leitner-translation" id="leitnerTranslation" style="display:none;">${escapeHtml(word.ru)}${word.example ? '<br><span style="font-size:12px; color:var(--text-muted);">' + escapeHtml(word.example) + '</span>' : ''}</div>
      <button class="leitner-reveal-btn" id="leitnerRevealBtn">Показать перевод</button>
      <div class="leitner-answer-row" id="leitnerAnswerRow" style="display:none;">
        <button class="leitner-answer-btn dont-know" id="leitnerDontKnowBtn">✕ Не знаю</button>
        <button class="leitner-answer-btn know" id="leitnerKnowBtn">✓ Знаю</button>
      </div>
    </div>
  `;
 
  document.getElementById('leitnerRevealBtn').addEventListener('click', () => {
    document.getElementById('leitnerTranslation').style.display = 'block';
    document.getElementById('leitnerRevealBtn').style.display = 'none';
    document.getElementById('leitnerAnswerRow').style.display = 'flex';
  });
  document.getElementById('leitnerKnowBtn').addEventListener('click', () => submitLeitnerAnswer(true));
  document.getElementById('leitnerDontKnowBtn').addEventListener('click', () => submitLeitnerAnswer(false));
}
 
async function submitLeitnerAnswer(correct) {
  if (leitnerBusy) return;
  leitnerBusy = true;
  const word = leitnerWords[leitnerIndex];
 
  try {
    await api('/api/review/answer', {
      method: 'POST', body: { telegram_id: TELEGRAM_ID, session_id: leitnerSessionId, word_id: word.word_id, correct },
    });
    if (correct) leitnerCorrectCount++;
    leitnerIndex++;
    renderLeitnerCard();
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    leitnerBusy = false;
  }
}
 
async function finishLeitnerSession() {
  const stage = document.getElementById('leitnerStage');
  let expAwarded = 0;
 
  try {
    const data = await api('/api/review/finish-session', {
      method: 'POST', body: { telegram_id: TELEGRAM_ID, session_id: leitnerSessionId },
    });
    if (data.exp_result) {
      expAwarded = data.replayed ? 0 : data.exp_result.awarded;
      if (!data.replayed) applyProgressionResult(data.exp_result, data.streak_result);
    }
  } catch (e) {
    stage.innerHTML = '<div class="empty-state">Не удалось сохранить результат.<button class="text-button" id="retryReviewFinish">Попробовать ещё раз</button></div>';
    document.getElementById('retryReviewFinish').onclick = finishLeitnerSession;
    showToast(e.message, 'error');
    return;
  }
 
  stage.innerHTML = `
    <div class="leitner-summary">
      <div class="glyph">🎉</div>
      <div class="leitner-summary-title">Вы повторили ${leitnerTotalCount} слов!</div>
      <div class="leitner-summary-exp">+${expAwarded} EXP</div>
      <div class="deck-actions" style="justify-content:center; gap:10px;">
        <button class="leitner-answer-btn know" id="leitnerAnotherBtn" style="flex:none; padding:12px 24px;">Ещё порцию</button>
        <button class="leitner-answer-btn" style="flex:none; padding:12px 24px; background:var(--surface-2); color:var(--text);" id="leitnerDoneBtn">Готово</button>
      </div>
    </div>
  `;
 
  document.getElementById('leitnerAnotherBtn').addEventListener('click', startLeitnerSession);
  document.getElementById('leitnerDoneBtn').addEventListener('click', exitLeitnerSession);
}
