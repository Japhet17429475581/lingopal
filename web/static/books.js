/**
 * books.js — LinguaPlay: список книг + постраничная читалка (как Apple Books).
 *
 * Пагинация делается измерением реального DOM: контент бьётся на "юниты"
 * (слово-спан или кусок текста между словами), юниты жадно набиваются в
 * скрытый измеритель, пока не превысят доступную высоту — тогда страница
 * закрывается, следующий юнит уходит на новую. Это не эвристика по
 * символам, а честное измерение отрисованной высоты — точнее, но требует
 * реального браузера (в песочнице без layout-движка не проверить).
 */
 
let bookLevelFilter = 'A1';
let currentBook = null;
let dictionaryWordSet = new Set(); // испанские слова, уже добавленные в словарь — для подсветки
let bookPages = [];
let currentPageIndex = 0;
let touchStartX = null;
let resizeDebounceTimer = null;
 
// ============================================
// СПИСОК КНИГ
// ============================================
function initLinguaPlayHandlers() {
  document.querySelectorAll('#bookLevelFilter .picker-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#bookLevelFilter .picker-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      bookLevelFilter = btn.dataset.level;
      loadBooksList();
    });
  });
 
  document.getElementById('bookReaderBack').addEventListener('click', exitBookReader);
  document.getElementById('wordPopupCloseBtn').addEventListener('click', closeWordPopup);
  document.getElementById('selectionTranslateBtn').addEventListener('click', translateSelection);
  document.addEventListener('selectionchange', handleTextSelection);
  document.getElementById('bookPrevPage').onclick = prevPage;
  document.getElementById('bookNextPage').onclick = nextPage;
}
 
async function initLinguaPlayScreen() {
  await loadBooksList();
}
 
async function loadBooksList() {
  const list = document.getElementById('booksList');
  list.innerHTML = `<div class="empty-state">Загружаем истории…</div>`;
  try {
    const data = await api(`/api/books?telegram_id=${TELEGRAM_ID}&level=${bookLevelFilter}`);
    if (!data.books.length) {
      list.innerHTML = `<div class="empty-state"><div class="glyph">📭</div>Историй на этом уровне пока нет.</div>`;
      return;
    }
    list.innerHTML = data.books.map((b) => `
      <button class="book-card ${b.is_completed ? 'completed' : ''}" data-book-id="${b.id}">
        <div class="book-icon">📖</div>
        <div class="book-info">
          <div class="book-title">${escapeHtml(b.title)}</div>
          <div class="book-author">${escapeHtml(b.author || 'LingoPal')}</div>
          ${b.progress_ratio > 0 ? `<div class="book-progress-bar"><div class="book-progress-fill" style="width:${b.progress_ratio * 100}%;"></div></div>` : ''}
        </div>
        <div class="book-status">${b.is_completed ? '✅' : ''}</div>
      </button>
    `).join('');
 
    list.querySelectorAll('.book-card').forEach((card) => {
      card.addEventListener('click', () => openBook(parseInt(card.dataset.bookId, 10)));
    });
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
// ============================================
// ТОКЕНИЗАЦИЯ ТЕКСТА
// ============================================
function escapeHtmlText(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
 
/**
 * Разбивает текст книги на "юниты" — либо кликабельный span слова,
 * либо кусок сырого текста между словами (пробелы/пунктуация,
 * HTML-экранированный). Порядок юнитов = порядок чтения.
 */
function tokenizeToUnits(content) {
  const wordRegex = /([a-zA-ZáéíóúÁÉÍÓÚñÑüÜ]+)/g;
  const units = [];
  let lastIndex = 0;
  let match;
 
  while ((match = wordRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      units.push(escapeHtmlText(content.slice(lastIndex, match.index)));
    }
    const word = match[0];
    const isKnown = dictionaryWordSet.has(word.toLowerCase());
    units.push(`<span class="reader-word ${isKnown ? 'in-dictionary' : ''}" data-word="${word}">${word}</span>`);
    lastIndex = wordRegex.lastIndex;
  }
  if (lastIndex < content.length) {
    units.push(escapeHtmlText(content.slice(lastIndex)));
  }
  return units;
}
 
/**
 * Жадная упаковка юнитов в страницы по реальной высоте измерителя.
 * measurer — скрытый DOM-элемент с той же шириной/шрифтом, что и
 * видимая читалка (см. createMeasurer). Возвращает массив HTML-строк,
 * по одной на страницу.
 */
function paginateUnits(units, measurer, availableHeight) {
  const pages = [];
  let buffer = [];
 
  for (let i = 0; i < units.length; i++) {
    buffer.push(units[i]);
    measurer.innerHTML = buffer.join('');
 
    if (measurer.scrollHeight > availableHeight && buffer.length > 1) {
      buffer.pop(); // этот юнит не влез — уносим на следующую страницу
      pages.push(buffer.join(''));
      buffer = [units[i]];
    }
  }
  if (buffer.length) pages.push(buffer.join(''));
 
  return pages.length ? pages : [''];
}
 
function createMeasurer(referenceEl) {
  let measurer = document.getElementById('bookPageMeasurer');
  if (!measurer) {
    measurer = document.createElement('div');
    measurer.id = 'bookPageMeasurer';
    measurer.className = 'reader-text';
    measurer.style.position = 'absolute';
    measurer.style.visibility = 'hidden';
    measurer.style.pointerEvents = 'none';
    measurer.style.top = '-9999px';
    measurer.style.left = '-9999px';
    measurer.style.height = 'auto';
    measurer.style.overflow = 'visible';
    document.body.appendChild(measurer);
  }
  const rect = referenceEl.getBoundingClientRect();
  measurer.style.width = `${rect.width}px`;
  return measurer;
}
 
// ============================================
// ЧТЕНИЕ КНИГИ (ПОСТРАНИЧНО)
// ============================================
async function openBook(bookId) {
  try {
    const [bookData, dictData] = await Promise.all([
      api(`/api/books/${bookId}?telegram_id=${TELEGRAM_ID}`),
      api(`/api/dictionary?telegram_id=${TELEGRAM_ID}`),
    ]);
    currentBook = bookData.book;
    dictionaryWordSet = new Set(dictData.entries.map((e) => e.es.toLowerCase()));
 
    document.getElementById('bookReaderTitle').textContent = currentBook.title;
    document.getElementById('booksListView').style.display = 'none';
    document.getElementById('bookReaderView').style.display = 'flex';
 
    // Контейнер должен успеть получить реальные размеры ПОСЛЕ того как
    // стал видимым — при display:none его высота равна нулю.
    requestAnimationFrame(() => {
      paginateAndRender(currentBook.content, currentBook.progress_ratio);
    });
 
    initReaderNavigation();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
 
function paginateAndRender(content, progressRatio) {
  const readerEl = document.getElementById('bookReaderText');
  const measurer = createMeasurer(readerEl);
  const availableHeight = Math.max(200, readerEl.clientHeight);
 
  const units = tokenizeToUnits(content);
  bookPages = paginateUnits(units, measurer, availableHeight);
 
  currentPageIndex = bookPages.length > 1 ? Math.round(progressRatio * (bookPages.length - 1)) : 0;
  currentPageIndex = Math.max(0, Math.min(bookPages.length - 1, currentPageIndex));
 
  renderPage(currentPageIndex);
}
 
function renderPage(index) {
  const readerEl = document.getElementById('bookReaderText');
  readerEl.innerHTML = bookPages[index];
 
  readerEl.querySelectorAll('.reader-word').forEach((span) => {
    span.addEventListener('click', (e) => {
      e.stopPropagation();
      openWordPopupFor(span.dataset.word, false);
    });
  });
 
  document.getElementById('bookPageCounter').textContent =
    `${index + 1} / ${bookPages.length}`;
 
  const ratio = bookPages.length > 1 ? index / (bookPages.length - 1) : 1;
  document.getElementById('bookPrevPage').disabled = index === 0;
  document.getElementById('bookNextPage').textContent = index === bookPages.length - 1 ? 'Прочитано ✓' : 'Дальше →';
}
 
function goToPage(newIndex) {
  if (newIndex < 0 || newIndex >= bookPages.length || newIndex === currentPageIndex) return;
  const direction = newIndex > currentPageIndex ? 'next' : 'prev';
  currentPageIndex = newIndex;
 
  const readerEl = document.getElementById('bookReaderText');
  readerEl.classList.add(direction === 'next' ? 'page-slide-out-next' : 'page-slide-out-prev');
 
  setTimeout(() => {
    renderPage(currentPageIndex);
    saveBookProgress(bookPages.length > 1 ? currentPageIndex / (bookPages.length - 1) : 0);
    readerEl.classList.remove('page-slide-out-next', 'page-slide-out-prev');
    readerEl.classList.add(direction === 'next' ? 'page-slide-in-next' : 'page-slide-in-prev');
    setTimeout(() => readerEl.classList.remove('page-slide-in-next', 'page-slide-in-prev'), 220);
  }, 160);
}
 
function nextPage() { if (currentPageIndex === bookPages.length - 1) { saveBookProgress(1); showToast('История прочитана. ¡Muy bien!', 'success'); } else goToPage(currentPageIndex + 1); }
function prevPage() { goToPage(currentPageIndex - 1); }
 
function initReaderNavigation() {
  const readerEl = document.getElementById('bookReaderText');
  if (readerEl.dataset.navBound) return; // не навешиваем слушатели повторно при переоткрытии книги
  readerEl.dataset.navBound = '1';
 
  readerEl.addEventListener('touchstart', (e) => {
    touchStartX = e.touches[0].clientX;
  });
 
  readerEl.addEventListener('touchend', (e) => {
    if (touchStartX === null) return;
    const dx = e.changedTouches[0].clientX - touchStartX;
    touchStartX = null;
    if (Math.abs(dx) < 50) return; // короткий тап — листает клик-обработчик ниже, не свайп
    e.preventDefault(); // гасим синтетический click после свайпа, иначе перелистнёт дважды
    if (dx < 0) nextPage(); else prevPage();
  });
 
  // Тап по краям экрана — как в Apple Books/Readest: левая четверть назад,
  // правая четверть вперёд, середина — ничего (не мешает выделению текста).
  readerEl.addEventListener('click', (e) => {
    if (e.target.classList.contains('reader-word')) return; // клик по слову — не листаем
    const rect = readerEl.getBoundingClientRect();
    const relX = e.clientX - rect.left;
    if (relX < rect.width * 0.25) prevPage();
    else if (relX > rect.width * 0.75) nextPage();
  });
 
  window.addEventListener('resize', () => {
    clearTimeout(resizeDebounceTimer);
    resizeDebounceTimer = setTimeout(() => {
      if (!currentBook || document.getElementById('bookReaderView').style.display === 'none') return;
      const ratio = bookPages.length > 1 ? currentPageIndex / (bookPages.length - 1) : 0;
      paginateAndRender(currentBook.content, ratio);
    }, 300);
  });
}
 
function exitBookReader() {
  document.getElementById('bookReaderView').style.display = 'none';
  document.getElementById('booksListView').style.display = 'block';
  closeWordPopup();
  currentBook = null;
  bookPages = [];
  loadBooksList();
}
 
async function saveBookProgress(ratio) {
  if (!currentBook) return;
  try {
    await api(`/api/books/${currentBook.id}/progress`, {
      method: 'POST', body: { telegram_id: TELEGRAM_ID, progress_ratio: ratio },
    });
  } catch (e) {
    console.warn('Не удалось сохранить прогресс чтения:', e.message);
  }
}
 
// ============================================
// ВЫДЕЛЕНИЕ ТЕКСТА → "ПЕРЕВЕСТИ ВЫДЕЛЕННОЕ"
// ============================================
function handleTextSelection() {
  const btn = document.getElementById('selectionTranslateBtn');
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount) return;
  const text = selection.toString().trim();
  const reader = document.getElementById('bookReaderText');
 
  if (!text || text.split(/\s+/).length < 2 || !reader || !reader.contains(selection.anchorNode)) {
    btn.style.display = 'none';
    return;
  }
 
  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  btn.style.top = `${window.scrollY + rect.top - 42}px`;
  btn.style.left = `${Math.max(10, rect.left)}px`;
  btn.style.display = 'block';
  btn.dataset.selectedText = text;
}
 
function translateSelection() {
  const btn = document.getElementById('selectionTranslateBtn');
  const text = btn.dataset.selectedText;
  btn.style.display = 'none';
  if (text) openWordPopupFor(text, true);
}
 
// ============================================
// ПОПАП ПЕРЕВОДА
// ============================================
let popupCurrentWordId = null;
let popupVersion = 0;
 
async function openWordPopupFor(text, isPhrase) {
  const version = ++popupVersion;
  const popup = document.getElementById('wordPopup');
  const loader = document.getElementById('wordPopupLoader');
  const translationEl = document.getElementById('wordPopupTranslation');
  const actions = document.getElementById('wordPopupActions');
  const addBtn = document.getElementById('wordPopupAddBtn');
 
  document.getElementById('wordPopupOriginal').textContent = text;
  loader.style.display = 'flex';
  translationEl.style.display = 'none';
  actions.style.display = 'none';
  popup.style.display = 'block';
  popupCurrentWordId = null;
 
  try {
    const data = await api('/api/translate', {
      method: 'POST',
      body: { telegram_id: TELEGRAM_ID, text, book_level: currentBook ? currentBook.level : 'A1' },
    });
 
    if (version !== popupVersion) return;
    loader.style.display = 'none';
    translationEl.textContent = data.translation;
    translationEl.style.display = 'block';
    actions.style.display = 'flex';
    addBtn.style.display = '';
 
    if (data.word_id) {
      popupCurrentWordId = data.word_id;
      const alreadyKnown = dictionaryWordSet.has(text.toLowerCase());
      addBtn.disabled = alreadyKnown;
      addBtn.textContent = alreadyKnown ? 'Уже в словаре' : '+ В словарь';
    } else {
      addBtn.style.display = 'none'; // фразы в словарь не добавляем
    }
  } catch (e) {
    if (version !== popupVersion) return;
    loader.style.display = 'none';
    translationEl.textContent = e.message;
    translationEl.style.display = 'block';
    actions.style.display = 'flex';
    addBtn.style.display = 'none';
  }
}
 
function closeWordPopup() {
  popupVersion++;
  document.getElementById('wordPopup').style.display = 'none';
  document.getElementById('wordPopupAddBtn').style.display = '';
}
 
function initWordPopupAddButton() {
  document.getElementById('wordPopupAddBtn').addEventListener('click', async () => {
    if (!popupCurrentWordId) return;
    try {
      const data = await api('/api/dictionary', { method: 'POST', body: { telegram_id: TELEGRAM_ID, word_id: popupCurrentWordId } });
      if (data.added) {
        showToast('Добавлено в словарь', 'success');
        const word = document.getElementById('wordPopupOriginal').textContent;
        dictionaryWordSet.add(word.toLowerCase());
        document.querySelectorAll('.reader-word').forEach(el => { if (el.dataset.word.toLowerCase() === word.toLowerCase()) el.classList.add('in-dictionary'); });
      }
      const addBtn = document.getElementById('wordPopupAddBtn');
      addBtn.disabled = true;
      addBtn.textContent = 'Уже в словаре';
    } catch (e) {
      showToast(e.message, 'error');
    }
  });
}
