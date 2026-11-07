/** Grammar roadmap, readable lessons and server-graded practice. */
let grammarUserLevel = null;
let grammarActiveLevel = 'A1';
let grammarBlockCache = [];
let grammarCurrentBlock = null;
let grammarQuestions = [];
let grammarQuestionIndex = 0;
let grammarAttemptId = null;
let grammarBusy = false;
let grammarAnswered = false;
let grammarPicked = [];
let grammarLoadVersion = 0;

function showWelcomeScreen(isNew) {
  if (isNew) document.getElementById('welcome-screen').style.display = 'flex';
}
function initWelcomeScreen() {
  document.getElementById('start-app-btn').onclick = () => {
    document.getElementById('welcome-screen').style.display = 'none';
  };
}
function hideAllGrammarSubscreens() {
  ['grammarOnboarding', 'grammarRoadmap', 'grammarTheory', 'grammarTest'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });
}
function setGrammarSwitcherActive(level) {
  document.querySelectorAll('.grammar-switcher-btn').forEach(button => {
    button.classList.toggle('active', button.dataset.level === level);
    button.setAttribute('aria-pressed', button.dataset.level === level);
  });
}
async function initGrammarScreen() {
  if (grammarAttemptId && !grammarCurrentBlock?.finished) return;
  try {
    const profile = await api(`/api/profile?telegram_id=${TELEGRAM_ID}`);
    grammarUserLevel = profile.grammar_level;
    hideAllGrammarSubscreens();
    if (!grammarUserLevel) {
      document.getElementById('grammarOnboarding').style.display = 'block';
    } else {
      grammarActiveLevel = grammarUserLevel;
      document.getElementById('grammarRoadmap').style.display = 'block';
      setGrammarSwitcherActive(grammarActiveLevel);
      await loadGrammarBlocks(grammarActiveLevel);
    }
  } catch (error) { showToast(error.message, 'error'); }
}
function showGrammarRoadmap() {
  grammarAttemptId = null;
  hideAllGrammarSubscreens();
  document.getElementById('grammarRoadmap').style.display = 'block';
  loadGrammarBlocks(grammarActiveLevel);
}
function initGrammarHandlers() {
  document.querySelectorAll('.grammar-level-card').forEach(button => {
    button.onclick = async () => {
      button.disabled = true;
      try {
        await api('/api/user/set-grammar-level', {method: 'POST', body: {telegram_id: TELEGRAM_ID, level: button.dataset.level}});
        grammarUserLevel = grammarActiveLevel = button.dataset.level;
        setGrammarSwitcherActive(grammarActiveLevel);
        showGrammarRoadmap();
      } catch (error) { showToast(error.message, 'error'); }
      finally { button.disabled = false; }
    };
  });
  document.querySelectorAll('.grammar-switcher-btn').forEach(button => {
    button.onclick = async () => {
      if (grammarBusy) return;
      grammarBusy = true;
      try {
        await api('/api/user/set-grammar-level', {method: 'POST', body: {telegram_id: TELEGRAM_ID, level: button.dataset.level}});
        grammarUserLevel = grammarActiveLevel = button.dataset.level;
        setGrammarSwitcherActive(grammarActiveLevel);
        await loadGrammarBlocks(grammarActiveLevel);
      } catch (error) { showToast(error.message, 'error'); }
      finally { grammarBusy = false; }
    };
  });
  document.getElementById('grammarTheoryBack').onclick = showGrammarRoadmap;
  document.getElementById('grammarStartTestBtn').onclick = startGrammarTest;
  document.getElementById('grammarTestExitBtn').onclick = () => {
    if (grammarBusy) return;
    grammarAttemptId = null;
    hideAllGrammarSubscreens();
    document.getElementById('grammarTheory').style.display = 'block';
  };
}
const GRAMMAR_LEVEL_META = {
  A1: ['Первые слова. Первые фразы.', 'Местоимения, базовые глаголы и простые вопросы.'],
  A2: ['Больше свободы в разговоре.', 'Прошлое, планы и истории из повседневной жизни.'],
  B1: ['От фраз к живому разговору.', 'Желания, мнения и связи между идеями.'],
  B2: ['Выражай именно то, что думаешь.', 'Сложные условия, оттенки смысла и точная речь.'],
};
async function loadGrammarBlocks(level) {
  const version = ++grammarLoadVersion;
  const list = document.getElementById('grammarTopicsList');
  document.getElementById('grammarRoadmapTitle').textContent = GRAMMAR_LEVEL_META[level][0];
  document.getElementById('grammarRoadmapSubtitle').textContent = GRAMMAR_LEVEL_META[level][1];
  list.innerHTML = '<div class="empty-state">Загружаем твой путь…</div>';
  try {
    const data = await api(`/api/grammar/blocks?telegram_id=${TELEGRAM_ID}&level=${level}`);
    if (version !== grammarLoadVersion) return;
    grammarBlockCache = data.blocks;
    const completed = data.blocks.filter(block => block.is_completed).length;
    document.getElementById('grammarSummary').innerHTML = `<span><b>${completed}</b> из ${data.blocks.length} тем пройдено</span><span>Уровень ${level}</span>`;
    document.getElementById('grammarLevelFill').style.width = `${data.blocks.length ? completed / data.blocks.length * 100 : 0}%`;
    list.innerHTML = data.blocks.map((block, index) => `
      <button class="grammar-topic ${block.status}" data-block-id="${escapeHtml(block.id)}" ${block.status === 'locked' ? 'disabled' : ''}>
        <span class="grammar-topic-number">${block.is_completed ? '✓' : String(index + 1).padStart(2, '0')}</span>
        <span class="grammar-topic-copy"><span class="grammar-topic-meta">${block.status === 'current' ? 'СЛЕДУЮЩИЙ ШАГ' : block.is_completed ? 'ПРОЙДЕНО' : 'ВПЕРЕДИ'} · 3 УРОКА</span>
        <strong>${escapeHtml(block.title)}</strong><span>${escapeHtml(block.description)}</span>
        <small>${block.best_score ? `Лучший результат ${block.best_score}% · ` : ''}6 упражнений · ${block.exp_reward} XP за прохождение</small></span>
        <span class="grammar-topic-arrow">${block.status === 'locked' ? '⌑' : '↗'}</span>
      </button>`).join('');
    list.querySelectorAll('[data-block-id]').forEach(button => {
      button.onclick = () => openGrammarBlock(button.dataset.blockId);
    });
  } catch (error) {
    if (version !== grammarLoadVersion) return;
    list.innerHTML = '<div class="empty-state">Не удалось загрузить темы. <button class="text-button" id="retryGrammar">Попробовать ещё раз</button></div>';
    document.getElementById('retryGrammar').onclick = () => loadGrammarBlocks(level);
    showToast(error.message, 'error');
  }
}
async function openGrammarBlock(blockId) {
  try {
    const data = await api(`/api/grammar/blocks/${encodeURIComponent(blockId)}`);
    grammarCurrentBlock = data.block;
    grammarAttemptId = null;
    document.getElementById('grammarTheoryTitle').textContent = data.block.title;
    document.getElementById('grammarTheoryText').innerHTML = data.block.lessons.map((lesson, index) => `
      <article class="grammar-lesson"><span class="eyebrow">УРОК 0${index + 1}</span><h3>${escapeHtml(lesson.title)}</h3>
      <p>${escapeHtml(lesson.theory).replace(/\n/g, '<br>')}</p></article>`).join('') +
      `<div class="grammar-final-note">6 упражнений по теме · Для прохождения нужно ${data.block.pass_percent}% верных ответов. Ошибки разберём вместе.</div>`;
    hideAllGrammarSubscreens();
    document.getElementById('grammarTheory').style.display = 'block';
    document.getElementById('grammarTheoryBack').focus();
    window.scrollTo({top: 0, behavior: 'smooth'});
  } catch (error) { showToast(error.message, 'error'); }
}
async function startGrammarTest() {
  if (grammarBusy || !grammarCurrentBlock) return;
  grammarBusy = true;
  const button = document.getElementById('grammarStartTestBtn');
  button.disabled = true;
  try {
    const data = await api(`/api/grammar/blocks/${grammarCurrentBlock.id}/start`, {method: 'POST', body: {telegram_id: TELEGRAM_ID}});
    grammarAttemptId = data.attempt_id;
    grammarQuestions = data.questions;
    grammarQuestionIndex = 0;
    grammarCurrentBlock.finished = false;
    hideAllGrammarSubscreens();
    document.getElementById('grammarTest').style.display = 'flex';
    renderGrammarQuestion();
  } catch (error) { showToast(error.message, 'error'); }
  finally { grammarBusy = false; button.disabled = false; }
}
function renderGrammarQuestion() {
  grammarAnswered = false;
  grammarPicked = [];
  const question = grammarQuestions[grammarQuestionIndex];
  const kind = question.question_type;
  document.getElementById('grammarTestProgress').textContent = `${grammarQuestionIndex + 1} / ${grammarQuestions.length}`;
  document.getElementById('grammarTestFill').style.width = `${grammarQuestionIndex / grammarQuestions.length * 100}%`;
  const options = kind === 'boolean' ? ['Верно', 'Неверно'] : kind === 'constructor' ? question.payload.words : question.payload.options;
  const stage = document.getElementById('grammarQuestionStage');
  stage.innerHTML = `<div class="grammar-question-card"><span class="eyebrow">${kind === 'constructor' ? 'СОБЕРИ ФРАЗУ' : kind === 'boolean' ? 'ПРОВЕРЬ УТВЕРЖДЕНИЕ' : 'ВЫБЕРИ ОТВЕТ'}</span>
    <h2 class="grammar-question-text">${escapeHtml(question.payload.question)}</h2>
    ${kind === 'constructor' ? '<div class="constructor-answer" id="constructorAssembled" aria-label="Собранная фраза"></div><p class="constructor-hint">Нажми на слово в ответе, чтобы вернуть его обратно.</p>' : ''}
    <div id="grammarOptions" class="${kind === 'constructor' ? 'word-bank' : 'answer-options'}">${options.map((option, index) => `<button class="grammar-option-btn" data-option-index="${index}">${kind === 'choice' ? `<span class="option-letter">${String.fromCharCode(65 + index)}</span>` : ''}${escapeHtml(option)}</button>`).join('')}</div>
    <div id="grammarFeedback" aria-live="polite"></div>
    ${kind === 'constructor' ? '<button class="start-btn" id="checkConstructor" disabled>Проверить ответ</button>' : ''}</div>`;
  stage.querySelectorAll('[data-option-index]').forEach(button => {
    button.onclick = () => {
      if (grammarBusy || grammarAnswered) return;
      const index = Number(button.dataset.optionIndex);
      if (kind === 'constructor') {
        grammarPicked.push(index);
        renderConstructorAnswer();
      } else {
        submitGrammarAnswer(kind === 'boolean' ? index === 0 : options[index], button);
      }
    };
  });
  if (kind === 'constructor') document.getElementById('checkConstructor').onclick = () => submitGrammarAnswer(grammarPicked.map(index => options[index]));
}
function renderConstructorAnswer() {
  const words = grammarQuestions[grammarQuestionIndex].payload.words;
  document.querySelectorAll('[data-option-index]').forEach(button => button.disabled = grammarPicked.includes(Number(button.dataset.optionIndex)));
  const assembled = document.getElementById('constructorAssembled');
  assembled.replaceChildren();
  grammarPicked.forEach((index, position) => {
    const button = document.createElement('button');
    button.className = 'word-chip';
    button.textContent = words[index];
    button.onclick = () => {
      if (grammarBusy || grammarAnswered) return;
      grammarPicked.splice(position, 1);
      renderConstructorAnswer();
    };
    assembled.appendChild(button);
  });
  document.getElementById('checkConstructor').disabled = grammarPicked.length !== words.length;
}
async function submitGrammarAnswer(answer, selected) {
  if (grammarBusy || grammarAnswered) return;
  grammarBusy = true;
  const question = grammarQuestions[grammarQuestionIndex];
  const stage = document.getElementById('grammarQuestionStage');
  const buttons = [...stage.querySelectorAll('button')];
  const disabled = buttons.map(button => button.disabled);
  buttons.forEach(button => button.disabled = true);
  try {
    const receipt = await api('/api/grammar/answer', {method: 'POST', body: {telegram_id: TELEGRAM_ID,
      attempt_id: grammarAttemptId, question_id: question.id, answer}});
    grammarAnswered = true;
    if (selected) selected.classList.add(receipt.correct ? 'correct' : 'incorrect');
    const correctText = Array.isArray(receipt.correct_answer) ? receipt.correct_answer.join(' ') : typeof receipt.correct_answer === 'boolean' ? (receipt.correct_answer ? 'Верно' : 'Неверно') : receipt.correct_answer;
    document.getElementById('grammarFeedback').innerHTML = `<div class="grammar-feedback ${receipt.correct ? 'is-correct' : 'is-incorrect'}"><strong>${receipt.correct ? '¡Muy bien! Всё верно' : 'Разберёмся вместе'}</strong>${!receipt.correct ? `<p>Правильный ответ: <b>${escapeHtml(correctText)}</b></p>` : ''}<p>${escapeHtml(receipt.explanation)}</p></div>`;
    const next = document.createElement('button');
    next.className = 'start-btn';
    next.textContent = grammarQuestionIndex + 1 === grammarQuestions.length ? 'Посмотреть результат →' : 'Следующий вопрос →';
    next.onclick = async () => {
      if (grammarBusy) return;
      if (grammarQuestionIndex + 1 < grammarQuestions.length) {
        grammarQuestionIndex++;
        renderGrammarQuestion();
      } else {
        next.disabled = true;
        await finishGrammarBlock();
        next.disabled = false;
      }
    };
    stage.appendChild(next);
    next.focus();
  } catch (error) {
    buttons.forEach((button, index) => button.disabled = disabled[index]);
    showToast(error.message, 'error');
  } finally { grammarBusy = false; }
}
async function finishGrammarBlock() {
  grammarBusy = true;
  try {
    const data = await api(`/api/grammar/blocks/${grammarCurrentBlock.id}/complete`, {method: 'POST', body: {telegram_id: TELEGRAM_ID, attempt_id: grammarAttemptId}});
    if (!data.replayed) {
      applyProgressionResult(data.exp_result, data.streak_result);
      handleUnlockedAchievements(data.unlocked_achievements || []);
      handleQuestEvents(data.quest_events || []);
    }
    grammarCurrentBlock.finished = true;
    grammarAttemptId = null;
    document.getElementById('grammarTestFill').style.width = '100%';
    const stage = document.getElementById('grammarQuestionStage');
    stage.innerHTML = `<div class="grammar-result-card"><span class="result-icon">${data.passed ? '✦' : '↻'}</span><span class="eyebrow">${data.passed ? 'ТЕМА ПРОЙДЕНА' : 'ЕЩЁ НЕМНОГО ПРАКТИКИ'}</span><h2>${data.passed ? '¡Excelente!' : 'Ошибки помогают учиться'}</h2><p>${data.correct_answers} из ${data.total_questions} верно · ${data.score}%</p><span class="result-xp">+${data.replayed ? 0 : data.exp_result.awarded} XP</span><p>${data.passed ? 'Можно переходить к следующей теме.' : `Для прохождения нужно ${data.pass_percent}%. Повтори правило и попробуй снова.`}</p></div>
      ${data.mistakes.length ? `<div class="mistakes-list"><h3>Что стоит повторить</h3>${data.mistakes.map(mistake => `<article><p>${escapeHtml(grammarQuestions.find(question => question.id === mistake.question_id)?.payload.question || '')}</p><span>${escapeHtml(mistake.explanation)}</span></article>`).join('')}</div>` : ''}
      <button class="start-btn" id="grammarResultContinue">${data.passed ? 'Вернуться к темам →' : 'Попробовать ещё раз'}</button><button class="text-button" id="grammarResultTheory">Повторить теорию</button>`;
    document.getElementById('grammarResultContinue').onclick = data.passed ? showGrammarRoadmap : startGrammarTest;
    document.getElementById('grammarResultTheory').onclick = () => {
      hideAllGrammarSubscreens();
      document.getElementById('grammarTheory').style.display = 'block';
    };
    loadProfile();
  } catch (error) { showToast(error.message, 'error'); }
  finally { grammarBusy = false; }
}
