/**
 * chat.js — чат с Хосе (AI-ассистент на DeepSeek).
 *
 * Хосе отображается через эмодзи 🤠 в сообщениях
 * и в нижней навигации.
 *
 * В шапке чата аватарки нет.
 */


// ============================================
// ИКОНКА ХОСЕ
// ============================================

const JOSE_ICON = "🤠";


// ============================================
// СТАРТОВЫЕ ТЕМЫ
// ============================================

const CHAT_STARTERS = [
    "Интересные факты о Мадриде 🇪🇸",
    "Самые красивые города для испаноговорящих 🏛️",
    "Как системно учить испанский? 📚",
    "Сериалы для изучения испанского 🎬",
    "Разница между ser и estar 🤔",
    "Популярные испанские выражения 💬",
];


// ============================================
// СОСТОЯНИЕ ЧАТА
// ============================================

// История диалога хранится только во время сессии.
// Не сохраняется в БД или localStorage.

let chatHistory = [];

let joseMessageCount = 0;

let chatSending = false;


// ============================================
// СОЗДАНИЕ АВАТАРКИ ХОСЕ ДЛЯ СООБЩЕНИЙ
// ============================================

function createJoseAvatar(
    extraClass = ""
) {
    const avatar =
        document.createElement("div");

    avatar.className =
        `chat-row-avatar ${extraClass}`.trim();

    avatar.textContent =
        JOSE_ICON;

    avatar.setAttribute(
        "aria-label",
        "Хосе"
    );

    return avatar;
}


// ============================================
// ИНИЦИАЛИЗАЦИЯ ИКОНКИ ВКЛАДКИ
// ============================================

function initChatAssets() {

    // ----------------------------
    // Иконка вкладки ассистента
    // ----------------------------

    const assistantTabIcon =
        document.getElementById(
            "assistantTabIcon"
        );

    if (assistantTabIcon) {

        // Если в HTML стоит <img>,
        // заменяем его на span с эмодзи.

        if (
            assistantTabIcon.tagName
                .toLowerCase()
            === "img"
        ) {
            const replacement =
                document.createElement("span");

            replacement.id =
                "assistantTabIcon";

            replacement.className =
                assistantTabIcon.className;

            replacement.textContent =
                JOSE_ICON;

            replacement.setAttribute(
                "aria-label",
                "Хосе"
            );

            assistantTabIcon.replaceWith(
                replacement
            );
        } else {
            assistantTabIcon.textContent =
                JOSE_ICON;
        }
    }
}


// ============================================
// СТАРТОВЫЕ КНОПКИ
// ============================================

function renderStarters() {
    const el =
        document.getElementById(
            "chatStarters"
        );

    if (!el) {
        return;
    }

    el.innerHTML =
        CHAT_STARTERS.map(
            (text) => `
                <button
                    class="chat-starter-btn"
                    data-text="${text.replace(
                        /"/g,
                        "&quot;"
                    )}"
                >
                    ${escapeHtml(text)}
                </button>
            `
        ).join("");

    el.querySelectorAll(
        ".chat-starter-btn"
    ).forEach(
        (btn) => {
            btn.addEventListener(
                "click",
                () => {
                    sendChatMessage(
                        btn.dataset.text
                    );
                }
            );
        }
    );
}


// ============================================
// ЗАЩИТА HTML
// ============================================

function escapeHtml(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ============================================
// ПАРСИНГ [CONSEJO]
// ============================================

function extractConsejo(raw) {
    const match =
        raw.match(
            /\[CONSEJO\]([\s\S]*?)\[\/CONSEJO\]/
        );

    if (!match) {
        return {
            text: raw.trim(),
            consejo: null,
        };
    }

    const text =
        raw.replace(
            match[0],
            ""
        ).trim();

    return {
        text,
        consejo:
            match[1].trim(),
    };
}


// ============================================
// ДОБАВЛЕНИЕ СООБЩЕНИЯ
// ============================================

function appendMessage(
    role,
    content
) {
    const messages =
        document.getElementById(
            "chatMessages"
        );

    if (!messages) {
        return;
    }

    const row =
        document.createElement(
            "div"
        );

    row.className =
        `chat-row ${
            role === "user"
                ? "user"
                : "jose"
        }`;


    // ----------------------------
    // СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ
    // ----------------------------

    if (role === "user") {
        row.innerHTML = `
            <div class="chat-bubble-wrap">
                <div class="chat-bubble">
                    ${escapeHtml(content)}
                </div>
            </div>
        `;
    }


    // ----------------------------
    // СООБЩЕНИЕ ХОСЕ
    // ----------------------------

    else {
        joseMessageCount++;

        const showAvatar =
            joseMessageCount % 2 === 1;

        const {
            text,
            consejo,
        } =
            extractConsejo(content);


        // Аватар или пустое место,
        // чтобы сообщения оставались ровными.

        const avatar =
            document.createElement(
                "div"
            );

        avatar.className =
            `chat-row-avatar ${
                showAvatar
                    ? ""
                    : "spacer"
            }`;

        avatar.textContent =
            showAvatar
                ? JOSE_ICON
                : "";


        const bubbleWrap =
            document.createElement(
                "div"
            );

        bubbleWrap.className =
            "chat-bubble-wrap";


        // Имя Хосе между сообщениями,
        // когда аватар не отображается.

        if (!showAvatar) {
            const senderName =
                document.createElement(
                    "div"
                );

            senderName.className =
                "chat-sender-name";

            senderName.textContent =
                "Хосе";

            bubbleWrap.appendChild(
                senderName
            );
        }


        // Само сообщение.

        const bubble =
            document.createElement(
                "div"
            );

        bubble.className =
            "chat-bubble";

        bubble.textContent =
            text;

        bubbleWrap.appendChild(
            bubble
        );


        // Подсказка CONSEJO.

        if (consejo) {
            const consejoBlock =
                document.createElement(
                    "div"
                );

            consejoBlock.className =
                "chat-consejo";

            consejoBlock.innerHTML = `
                <span class="icon">
                    💡
                </span>
                <span>
                    ${escapeHtml(
                        consejo
                    )}
                </span>
            `;

            bubbleWrap.appendChild(
                consejoBlock
            );
        }


        row.appendChild(
            avatar
        );

        row.appendChild(
            bubbleWrap
        );
    }


    messages.appendChild(
        row
    );

    messages.scrollTop =
        messages.scrollHeight;
}


// ============================================
// ИНДИКАТОР "ПЕЧАТАЕТ..."
// ============================================

function showTyping() {
    const messages =
        document.getElementById(
            "chatMessages"
        );

    if (!messages) {
        return;
    }


    // Не создаём второй индикатор.

    if (
        document.getElementById(
            "typingRow"
        )
    ) {
        return;
    }


    const row =
        document.createElement(
            "div"
        );

    row.className =
        "chat-row jose typing-row";

    row.id =
        "typingRow";


    // Аватар Хосе.

    const avatar =
        document.createElement(
            "div"
        );

    avatar.className =
        "chat-row-avatar";

    avatar.textContent =
        JOSE_ICON;


    // Три точки.

    const dots =
        document.createElement(
            "div"
        );

    dots.className =
        "typing-dots";

    dots.innerHTML = `
        <span></span>
        <span></span>
        <span></span>
    `;


    row.appendChild(
        avatar
    );

    row.appendChild(
        dots
    );

    messages.appendChild(
        row
    );

    messages.scrollTop =
        messages.scrollHeight;
}


function hideTyping() {
    document
        .getElementById(
            "typingRow"
        )
        ?.remove();
}


// ============================================
// ОТПРАВКА СООБЩЕНИЯ
// ============================================

async function sendChatMessage(
    text
) {
    const trimmed =
        text.trim();

    if (
        !trimmed
        || chatSending
    ) {
        return;
    }


    chatSending = true;


    const sendBtn =
        document.getElementById(
            "chatSendBtn"
        );

    const chatInput =
        document.getElementById(
            "chatInput"
        );

    const starters =
        document.getElementById(
            "chatStarters"
        );

    const status =
        document.getElementById(
            "chatHeaderStatus"
        );


    if (sendBtn) {
        sendBtn.disabled =
            true;
    }


    // Прячем стартовые кнопки
    // после первого сообщения.

    if (starters) {
        starters.style.display =
            "none";
    }


    // Добавляем сообщение пользователя.

    appendMessage(
        "user",
        trimmed
    );


    // Очищаем поле.

    if (chatInput) {
        chatInput.value =
            "";
    }


    // Меняем статус.

    if (status) {
        status.textContent =
            "печатает…";
    }


    showTyping();


    try {
        const data =
            await api(
                "/api/ask",
                {
                    method:
                        "POST",

                    body: {
                        message:
                            trimmed,

                        history:
                            chatHistory.slice(-20),

                        telegram_id:
                            TELEGRAM_ID,
                    },
                }
            );


        hideTyping();


        // Обновление прогресса.

        if (
            typeof applyProgressionResult
            === "function"
        ) {
            applyProgressionResult(
                null,
                data.streak_result
            );

            if (
                typeof handleQuestEvents
                === "function"
            ) {
                handleQuestEvents(
                    data.quest_events
                );
            }

            if (
                typeof handleUnlockedAchievements
                === "function"
            ) {
                handleUnlockedAchievements(
                    data.unlocked_achievements
                );
            }
        }


        // Небольшая задержка,
        // чтобы ответ появлялся естественно.

        await new Promise(
            (resolve) => {
                setTimeout(
                    resolve,
                    250
                );
            }
        );


        // Добавляем ответ Хосе.

        appendMessage(
            "assistant",
            data.reply
        );


        // Сохраняем историю
        // только в памяти браузера.

        chatHistory.push({
            role:
                "user",

            content:
                trimmed,
        });

        chatHistory.push({
            role:
                "assistant",

            content:
                data.reply,
        });

    } catch (e) {

        hideTyping();

        showToast(
            e.message ||
            "Не удалось отправить сообщение.",
            "error"
        );

    } finally {

        if (status) {
            status.textContent =
                "онлайн";
        }


        chatSending =
            false;


        if (sendBtn) {
            sendBtn.disabled =
                false;
        }
    }
}


// ============================================
// ИНИЦИАЛИЗАЦИЯ ЧАТА
// ============================================

function initChat() {

    // Теперь здесь инициализируется
    // только иконка нижней вкладки.

    initChatAssets();

    renderStarters();

    if (!window.LINGOPAL_CONFIG?.assistantAvailable) {
        document.getElementById('chatHeaderStatus').textContent = 'Сейчас недоступен';
        document.getElementById('chatInput').disabled = true;
        document.getElementById('chatInput').placeholder = 'Хосе вернётся чуть позже';
        document.getElementById('chatSendBtn').disabled = true;
        document.querySelectorAll('.chat-starter-btn').forEach(button => button.disabled = true);
        return;
    }


    const sendBtn =
        document.getElementById(
            "chatSendBtn"
        );

    const input =
        document.getElementById(
            "chatInput"
        );


    if (sendBtn && input) {

        sendBtn.addEventListener(
            "click",
            () => {
                sendChatMessage(
                    input.value
                );
            }
        );
    }


    if (input) {

        input.addEventListener(
            "keydown",
            (e) => {

                if (
                    e.key === "Enter"
                    && !e.shiftKey
                ) {
                    e.preventDefault();

                    sendChatMessage(
                        input.value
                    );
                }
            }
        );
    }
}
