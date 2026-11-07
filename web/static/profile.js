
/**
 * profile.js — вкладка "Профиль": шапка, статистика, ачивки и настройки.
 */

let profileLoaded = false; // грузим один раз за сессию, обновляем точечно после событий


// ============================================
// ШАПКА: ДАННЫЕ ИЗ TELEGRAM WEBAPP
// ============================================

function renderProfileHeaderFromTelegram() {
  const tgUser = tg && tg.initDataUnsafe ? tg.initDataUnsafe.user : null;

  const nameEl = document.getElementById('profileName');

  if (tgUser) {
    nameEl.textContent =
      [tgUser.first_name, tgUser.last_name]
        .filter(Boolean)
        .join(' ') || 'Пользователь';
  }

  // ВАЖНО: photo_url из initDataUnsafe часто отсутствует даже у пользователей
  // с аватаркой — Telegram не всегда его отдаёт.
  const avatarImg = document.getElementById('profileAvatarImg');
  const placeholder = document.getElementById('profileAvatarPlaceholder');

  if (tgUser && tgUser.photo_url) {
    avatarImg.src = tgUser.photo_url;
    avatarImg.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    avatarImg.style.display = 'none';
    placeholder.style.display = 'flex';
  }
}


// ============================================
// ИНИЦИАЛИЗАЦИЯ ЭКРАНА
// ============================================

async function initProfileScreen() {
  renderProfileHeaderFromTelegram();

  await Promise.all([
    loadProfileHeaderStats(),
    loadProfileStatsGrid(),
    loadAchievements()
  ]);

  profileLoaded = true;
}


// ============================================
// ШАПКА ПРОФИЛЯ
// ============================================

async function loadProfileHeaderStats() {
  try {
    const profile = await api(
      `/api/profile?telegram_id=${TELEGRAM_ID}`
    );

    document.getElementById('profileHeaderLevel').textContent =
      profile.level;

    document.getElementById('profileHeaderStreak').textContent =
      profile.streak_count;

  } catch (e) {
    console.warn(
      'Не удалось загрузить шапку профиля:',
      e.message
    );
  }
}


// ============================================
// СТАТИСТИКА
// ============================================

async function loadProfileStatsGrid() {
  const grid = document.getElementById('profileStatsGrid');

  try {
    const stats = await api(
      `/api/profile/stats?telegram_id=${TELEGRAM_ID}`
    );

    const profile = await api(
      `/api/profile?telegram_id=${TELEGRAM_ID}`
    );

    grid.innerHTML = `
      <div class="profile-stat-tile">
        <div class="profile-stat-value mono">
          ${stats.words_learned}
        </div>
        <div class="profile-stat-label">
          Слов выучено
        </div>
      </div>

      <div class="profile-stat-tile">
        <div class="profile-stat-value mono">
          ${stats.packs_completed}
        </div>
        <div class="profile-stat-label">
          Паков пройдено
        </div>
      </div>

      <div class="profile-stat-tile">
        <div class="profile-stat-value mono">
          ${stats.grammar_topics_completed}
        </div>
        <div class="profile-stat-label">
          Тем грамматики
        </div>
      </div>

      <div class="profile-stat-tile">
        <div class="profile-stat-value mono">
          ${profile.streak_count} ${profile.streak_tier.emoji}
        </div>
        <div class="profile-stat-label">
          Дней подряд
        </div>
      </div>
    `;

  } catch (e) {
    grid.innerHTML = '';

    console.warn(
      'Не удалось загрузить статистику:',
      e.message
    );
  }
}


// ============================================
// АЧИВКИ
// ============================================

async function loadAchievements() {
  const grid = document.getElementById('achievementsGrid');

  try {
    const data = await api(
      `/api/achievements?telegram_id=${TELEGRAM_ID}`
    );

    grid.innerHTML = data.achievements
      .map((a) => `
        <div
          class="achievement-card ${a.unlocked ? 'unlocked' : ''}"
          data-key="${a.key}"
          data-title="${a.title}"
          data-icon="${a.icon}"
        >
          <div class="achievement-icon">
            ${a.icon}
          </div>

          <div class="achievement-title">
            ${a.title}
          </div>
        </div>
      `)
      .join('');

    grid
      .querySelectorAll('.achievement-card')
      .forEach((card) => {
        card.addEventListener('click', () => {
          openAchievementModal(
            card.dataset.key,
            card.dataset.title,
            card.dataset.icon
          );
        });
      });

  } catch (e) {
    grid.innerHTML = '';

    console.warn(
      'Не удалось загрузить ачивки:',
      e.message
    );
  }
}


/**
 * Общая точка для любого ответа бэкенда с полем unlocked_achievements —
 * показывает уведомление и обновляет сетку ачивок,
 * если экран профиля уже открыт.
 */
function handleUnlockedAchievements(unlocked) {
  if (!unlocked || !unlocked.length) return;

  unlocked.forEach((item, i) => {
    setTimeout(() => {
      showLevelUpAnimation(
        item.icon,
        `Ачивка: ${item.title}!`
      );

      if (item.exp_result) {
        applyProgressionResult(
          item.exp_result,
          null
        );
      }

    }, i * 2200);
  });

  if (profileLoaded) {
    setTimeout(
      loadAchievements,
      unlocked.length * 2200 + 300
    );
  }
}


// ============================================
// НАСТРОЙКИ
// ============================================

function initProfileSettings() {
  const toggle =
    document.getElementById('isPublicToggle');

  toggle.addEventListener(
    'change',
    async () => {
      try {
        await api(
          '/api/user/settings',
          {
            method: 'POST',
            body: {
              telegram_id: TELEGRAM_ID,
              is_public: toggle.checked
            }
          }
        );

        showToast(
          toggle.checked
            ? 'Профиль публичный'
            : 'Профиль скрыт',
          'success'
        );

      } catch (e) {
        // Откатываем визуально,
        // если сохранить настройку не удалось
        toggle.checked = !toggle.checked;

        showToast(
          e.message,
          'error'
        );
      }
    }
  );
}


// ============================================
// ИНИЦИАЛИЗАЦИЯ ВКЛАДКИ ПРОФИЛЯ
// ============================================

function initProfileTab() {
  initProfileSettings();
  initThemePicker();
  initAchievementModal();
}


// ============================================
// ПЕРЕКЛЮЧАТЕЛЬ ТЕМЫ
// ============================================

function initThemePicker() {
  const saved =
    localStorage.getItem('lingopal-theme')
    || 'madrid';

  updateThemeSwatches(saved);

  document
    .querySelectorAll('.theme-swatch')
    .forEach((btn) => {

      btn.addEventListener(
        'click',
        () => {
          const theme = btn.dataset.theme;

          if (theme === 'madrid') {
            document.documentElement
              .removeAttribute('data-app-theme');

          } else {
            document.documentElement
              .setAttribute(
                'data-app-theme',
                theme
              );
          }

          localStorage.setItem(
            'lingopal-theme',
            theme
          );

          updateThemeSwatches(theme);
        }
      );
    });
}


function updateThemeSwatches(activeTheme) {
  document
    .querySelectorAll('.theme-swatch')
    .forEach((btn) => {
      btn.classList.toggle(
        'active',
        btn.dataset.theme === activeTheme
      );
    });
}


// ============================================
// ПОПАП ПРОГРЕССА ПО АЧИВКЕ
// ============================================

async function openAchievementModal(
  key,
  title,
  icon
) {
  const overlay =
    document.getElementById(
      'achievementModalOverlay'
    );

  document.getElementById(
    'achievementModalIcon'
  ).textContent = icon;

  document.getElementById(
    'achievementModalTitle'
  ).textContent = title;

  document.getElementById(
    'achievementModalProgressText'
  ).textContent = 'Загрузка…';

  document.getElementById(
    'achievementModalHint'
  ).textContent = '';

  document.getElementById(
    'achievementModalBarFill'
  ).style.width = '0%';

  overlay.classList.add('open');

  try {
    const data = await api(
      `/api/achievements/${key}/progress?telegram_id=${TELEGRAM_ID}`
    );

    document.getElementById(
      'achievementModalProgressText'
    ).textContent =
      `${data.current} / ${data.target}`;

    document.getElementById(
      'achievementModalHint'
    ).textContent =
      data.hint;

    const pct = data.target
      ? Math.min(
          100,
          (data.current / data.target) * 100
        )
      : 0;

    document.getElementById(
      'achievementModalBarFill'
    ).style.width = `${pct}%`;

  } catch (e) {
    document.getElementById(
      'achievementModalProgressText'
    ).textContent = '—';

    document.getElementById(
      'achievementModalHint'
    ).textContent =
      `Ошибка: ${e.message}`;
  }
}


function initAchievementModal() {
  document
    .getElementById('achievementModalClose')
    .addEventListener(
      'click',
      () => {
        document
          .getElementById(
            'achievementModalOverlay'
          )
          .classList.remove('open');
      }
    );

  document
    .getElementById(
      'achievementModalOverlay'
    )
    .addEventListener(
      'click',
      (e) => {
        if (
          e.target.id ===
          'achievementModalOverlay'
        ) {
          e.target
            .classList
            .remove('open');
        }
      }
    );
}

