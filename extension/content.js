/**
 * 📖 БИБЛИЯ ПРОЕКТА: CONTENT.JS (v7.1 — DYNAMIC SESSION SYNC)
 *
 * ИЗМЕНЕНИЯ v6.9 (сохранены):
 * [1] ЕДИНЫЙ ТАЙМАУТ: 120 секунд для всех режимов (защита от долгого Thinking Gemini).
 * [2] ЖЕСТКИЙ РАДАР (___RADAR_MODE___): безупречный перехват Drag-n-Drop.
 * [3] FAILSAFE СБРОС: таймер стартует только при получении задачи, исключая залипания.
 * [4] ОПТИМИЗАЦИЯ REFLOW: проверка лимитов больше не вешает браузер.
 * [5] FSM и детектор мутаций текста для устранения бесконечных циклов.
 *
 * ИСПРАВЛЕНИЯ v7.0 (сохранены):
 * [FIX-A] GenerationDetector.start() вызывается только после готовности UI.
 * [FIX-B] Рекурсивный поиск контейнера ответов без захвата document.body.
 * [FIX-C] Фильтрация мутаций строго по зоне ответа и игнорирование фазы INJECTING.
 * [FIX-D] Удалена устаревшая проверка скрытых кнопок "Stop".
 *
 * ИСПРАВЛЕНИЯ v7.1:
 * [FIX-E] Внедрена синхронизация с server_session_id бэкенда. При обнаружении
 * перезапуска Python-сервера (смена session_id) расширение мгновенно
 * сбрасывает локальный FSM в IDLE, гася вечную загрузку/генерацию на плашке.
 */

// ==========================================================
// ИНИЦИАЛИЗАЦИЯ ИДЕНТИФИКАТОРА ВКЛАДКИ
// ==========================================================
let myTabId = sessionStorage.getItem('vc_tab_id');
if (!myTabId) {
    myTabId = 'TAB-' + Math.random().toString(36).substring(2, 6).toUpperCase();
    sessionStorage.setItem('vc_tab_id', myTabId);
}
let myTabName = localStorage.getItem(`vc_name_${myTabId}`) || myTabId;

window.ignoreLimitsSession = false;
window.textBeforeSend = "";
window.waitingForNewBubble = false;
window.waitStartTime = 0;
window.isRadarMode = false;
window.processingStartTime = 0;

const SERVER_URL = "http://localhost:5070";
let isProcessing = false;
let currentCandidateText = "";
let stableCount = 0;
let activeTaskId = null;
let isLimitReached = false;

// Глобальное хранилище идентификатора серверной сессии
let knownServerSessionId = null;

// Пульс (Heartbeat) для поддержания связи с сервером Flask
setInterval(() => {
    fetch(`${SERVER_URL}/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tab_id: myTabId, tab_name: myTabName })
    })
    .then(resp => resp.json())
    .then(data => {
        if (data && data.server_session_id) {
            // Фоновое обновление известной сессии
            if (!knownServerSessionId) {
                knownServerSessionId = data.server_session_id;
            }
        }
    })
    .catch(() => {});
}, 2000);

// ==========================================================
// 0. СЕТЕВЫЕ ПРОКСИ-ФУНКЦИИ И ЛОГИРОВАНИЕ
// ==========================================================
function fetchGetProxy(url) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: "proxy_get", url }, (response) => {
            if (response && response.success) resolve(response.data);
            else reject("proxy_get error");
        });
    });
}

function fetchPostProxy(url, bodyText) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: "proxy_post", url, body: bodyText }, (response) => {
            if (response && response.success) resolve(response.data);
            else reject("proxy_post error");
        });
    });
}

function sendLog(message, color = "#aaaaaa") {
    fetchPostProxy(`${SERVER_URL}/log`, JSON.stringify({
        source_id: myTabId, message, color
    })).catch(() => {});
}

// ==========================================================
// 1. БЕЗОПАСНАЯ РАБОТА С DOM (ОЧИСТКА БЕЗ СИНЕГО ЭКРАНА)
// ==========================================================
function clearContentEditable(el) {
    if (!el) return;
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
        el.value = '';
        el.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
        el.focus();
        try {
            const range = document.createRange();
            range.selectNodeContents(el);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            document.execCommand('delete', false, null);
        } catch (e) {
            el.innerHTML = '<p><br></p>';
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

// ==========================================================
// 2. ПЛАВНЫЙ ИНЖЕКТОР (ДЛЯ ТЯЖЕЛЫХ ПАКЕТОВ > 4 КБ)
// ==========================================================
class TurboTextInjector {
    constructor(options = {}) {
        this.currentChunkSize = options.currentChunkSize || 3500; 
        this.onProgress = options.onProgress || (() => {});
    }

    async inject(element, text) {
        const chunks = this._splitIntoChunks(text, this.currentChunkSize);
        let injected = 0;

        for (let i = 0; i < chunks.length; i++) {
            await this._yieldThread();
            document.execCommand('insertText', false, chunks[i]);
            element.dispatchEvent(new Event('input', { bubbles: true }));
            injected += chunks[i].length;
            this.onProgress(injected / text.length);
        }
    }

    _splitIntoChunks(text, chunkSize) {
        const chunks = [];
        let i = 0;
        while (i < text.length) {
            let end = Math.min(i + chunkSize, text.length);
            if (end < text.length) {
                const boundary = Math.max(
                    text.lastIndexOf('\n', end),
                    text.lastIndexOf(' ', end)
                );
                if (boundary > i + 300) end = boundary + 1;
            }
            chunks.push(text.slice(i, end));
            i = end;
        }
        return chunks;
    }

    _yieldThread() {
        return new Promise(resolve => setTimeout(resolve, 0));
    }
}

// ==========================================================
// 3. ГЛАВНАЯ ФУНКЦИЯ ВСТАВКИ (ПРЯМОЙ ОПТИМИЗИРОВАННЫЙ ПОТОК)
// ==========================================================
async function insertLargeTextChunked(inputArea, text) {
    console.log(`VibeCoder: Подготовка промпта (${text.length} символов)...`);

    const selector = 'rich-textarea > div, div[contenteditable="true"][role="textbox"], textarea#prompt-textarea';
    const el = document.querySelector(selector) || inputArea;

    if (!el) {
        console.error('VibeCoder: Поле ввода не найдено!');
        return;
    }

    el.focus();
    await new Promise(r => requestAnimationFrame(r));
    clearContentEditable(el);
    await new Promise(r => requestAnimationFrame(r));

    const statusSpan = document.getElementById('vibe-status');

    if (text.length <= 4000) {
        console.log('VibeCoder: Объем <= 4КБ. Прямой инжект...');
        document.execCommand('insertText', false, text);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        await new Promise(r => setTimeout(r, 50));

        sendLog('⚡ Промпт загружен мгновенно (Fast-Track).', '#bb86fc');
        el.focus();
        return;
    }

    console.log('VibeCoder: Объем > 4КБ. Запуск анти-фриз инжектора...');
    sendLog('⚡ Загрузка объемного контекста безопасными блоками...', '#bb86fc');

    const injector = new TurboTextInjector({
        currentChunkSize: 3500,
        onProgress: (pct) => {
            if (statusSpan && !statusSpan.innerText.includes('ГЕНЕРАЦИЯ')) {
                statusSpan.innerText = `⚡ Вставка ${Math.round(pct * 100)}%`;
                statusSpan.style.background = '#bb86fc';
            }
        }
    });
    await injector.inject(el, text);

    if (statusSpan) updatePanelUI();
    sendLog('✅ Вставка контекста успешно завершена.', '#31a24c');
    el.focus();
}

// ==========================================================
// 3.5. ДЕТЕКТОР ГЕНЕРАЦИИ И КОНЕЧНЫЙ АВТОМАТ (FSM)
// ==========================================================
class GenerationDetector {
    constructor() {
        this.observer = null;
        this.isGenerating = false;
        this.lastMutationTime = 0;
        this.staleThreshold = 4000; // 🔥 ИЗМЕНЕНО: Увеличено с 1500 до 4000 для тяжелых diff-файлов
        this._ticker = null;
    }

    start() {
        this._observeLastBubble();
        this._ticker = setInterval(() => {
            if (this.isGenerating) {
                const silence = Date.now() - this.lastMutationTime;
                if (silence > this.staleThreshold) {
                    this.isGenerating = false;
                    updatePanelUI();
                }
            }
        }, 300);
    }

    _observeLastBubble() {
        if (this.observer) this.observer.disconnect();

        // Поиск контейнера ответов без захвата глобального body
        const container = document.querySelector(
            'response-container, .response-container, [data-response-index], chat-history, .conversation-container'
        );

        if (!container) {
            console.warn('VibeCoder: Контейнер ответов Gemini не найден, повторная попытка через 1с...');
            setTimeout(() => this._observeLastBubble(), 1000);
            return;
        }

        console.log('VibeCoder: GenerationDetector подключён к', container.tagName || container.className);

        this.observer = new MutationObserver((mutations) => {
            if (typeof FSM !== 'undefined' && FSM.state === 'INJECTING') return;

            const hasTextChange = mutations.some(m => {
                if (m.type === 'attributes') return false;

                const inResponseZone = m.target.closest?.(
                    'message-content, model-response, .response-text, ms-chat-message'
                );
                if (!inResponseZone) return false;

                if (m.target.nodeType === Node.ELEMENT_NODE) {
                    const style = window.getComputedStyle(m.target);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    if (m.target.offsetWidth === 0 && m.target.offsetHeight === 0) return false;
                }

                if (m.type === 'childList' && m.addedNodes.length > 0) {
                    return Array.from(m.addedNodes).some(node =>
                        node.nodeType === Node.TEXT_NODE ||
                        (node.nodeType === Node.ELEMENT_NODE &&
                         node.closest('message-content, model-response, .response-text'))
                    );
                }

                return m.type === 'characterData';
            });

            if (hasTextChange) {
                this.isGenerating = true;
                this.lastMutationTime = Date.now();
                updatePanelUI();
            }
        });

        this.observer.observe(container, {
            childList: true,
            subtree: true,
            characterData: true,
            characterDataOldValue: false
        });
    }

    check() {
        return this.isGenerating;
    }

    destroy() {
        if (this.observer) this.observer.disconnect();
        if (this._ticker) clearInterval(this._ticker);
    }
}

const generationDetector = new GenerationDetector();

function startDetectorWhenReady() {
    const geminiReady = document.querySelector(
        'response-container, chat-history, .conversation-container, model-response'
    );
    if (geminiReady) {
        console.log('VibeCoder: Gemini UI готов, запускаю GenerationDetector.');
        generationDetector.start();
    } else {
        setTimeout(startDetectorWhenReady, 800);
    }
}

if (document.readyState === 'complete') {
    setTimeout(startDetectorWhenReady, 1500);
} else {
    window.addEventListener('load', () => setTimeout(startDetectorWhenReady, 1500));
}

// Конечный автомат для строгого контроля состояний и предотвращения петель
const FSM = {
    IDLE: 'IDLE',               
    INJECTING: 'INJECTING',     
    WAITING_BUBBLE: 'WAITING_BUBBLE', 
    READING: 'READING',         
    POSTING: 'POSTING',         

    _state: 'IDLE',
    _taskId: null,
    _enteredAt: Date.now(),
    _snapshotBeforeSend: '',

    get state() { return this._state; },

    transition(newState) {
        const allowed = {
            IDLE:           ['INJECTING', 'WAITING_BUBBLE', 'READING'], 
            INJECTING:      ['WAITING_BUBBLE', 'IDLE'], 
            WAITING_BUBBLE: ['READING', 'IDLE'],        
            READING:        ['POSTING', 'READING', 'IDLE'],
            POSTING:        ['IDLE'],
        };
        if (!allowed[this._state]?.includes(newState)) {
            console.warn(`FSM: Запрещённый переход ${this._state} → ${newState}, игнорирую.`);
            return false;
        }
        console.log(`FSM: ${this._state} → ${newState}`);
        this._state = newState;
        this._enteredAt = Date.now();
        updatePanelUI();
        return true;
    },

    elapsed() { return Date.now() - this._enteredAt; },

    reset(taskId = null) {
        this._state = 'IDLE';
        this._taskId = taskId;
        this._enteredAt = Date.now();
        this._snapshotBeforeSend = '';
        updatePanelUI();
    }
};

// ==========================================================
// 4. ПЛАШКА UI (Draggable Badge)
// ==========================================================
function createVibeBadge() {
    if (document.getElementById('vibe-coder-badge')) return;
    const badge = document.createElement('div');
    badge.id = 'vibe-coder-badge';
    badge.innerHTML = `
        <div style="display:flex;align-items:center;width:100%;">
            <span id="vibe-drag-handle" style="margin-right:8px;opacity:0.5;font-size:16px;">⠿</span>
            🤖 <b>VibeCoder:</b>
            <span id="vibe-tab-name" style="cursor:pointer;border-bottom:1px dashed #888;margin-left:5px;margin-right:8px;">${myTabName}</span>
            <span id="vibe-status" style="font-size:11px;padding:2px 6px;border-radius:4px;background:#3c3c3c;color:#fff;font-weight:bold;">⏳ Загрузка...</span>
        </div>
    `;
    Object.assign(badge.style, {
        position: 'fixed', left: '20px', top: (window.innerHeight - 60) + 'px',
        backgroundColor: 'rgba(30,30,30,0.85)', backdropFilter: 'blur(5px)',
        color: '#d4d4d4', padding: '8px 15px', borderRadius: '8px',
        border: '1px solid #569cd6', zIndex: '999999', cursor: 'grab', userSelect: 'none'
    });

    let isDragging = false, offsetX, offsetY;
    badge.onmousedown = (e) => {
        if (e.target.id === 'vibe-tab-name') return;
        isDragging = true;
        offsetX = e.clientX - badge.getBoundingClientRect().left;
        offsetY = e.clientY - badge.getBoundingClientRect().top;
        document.onmousemove = (ev) => {
            if (isDragging) {
                badge.style.left = (ev.clientX - offsetX) + 'px';
                badge.style.top = (ev.clientY - offsetY) + 'px';
            }
        };
        document.onmouseup = () => { isDragging = false; document.onmousemove = null; };
    };

    document.getElementById && badge.addEventListener('click', (e) => {
        if (e.target.id !== 'vibe-tab-name') return;
        const newName = prompt('Имя вкладки:', myTabName);
        if (newName && newName.trim()) {
            myTabName = newName.trim();
            localStorage.setItem(`vc_name_${myTabId}`, myTabName);
            e.target.innerText = myTabName;
        }
    });

    document.body.appendChild(badge);
}
createVibeBadge();
setTimeout(createVibeBadge, 1500);

function updatePanelUI() {
    const statusSpan = document.getElementById('vibe-status');
    if (!statusSpan) return;
    if (statusSpan.innerText.includes('Вставка')) return;
    if (isLimitReached && !window.ignoreLimitsSession) {
        statusSpan.innerText = '🛑 ЛИМИТЫ'; statusSpan.style.background = '#ff4444'; return;
    }
    
    switch (FSM.state) {
        case 'IDLE':
            statusSpan.innerText = '🟢 ГОТОВ'; statusSpan.style.background = '#31a24c';
            break;
        case 'INJECTING':
            statusSpan.innerText = '⚡ ВСТАВКА...'; statusSpan.style.background = '#bb86fc';
            break;
        case 'WAITING_BUBBLE':
            statusSpan.innerText = '⏳ ОЖИДАНИЕ'; statusSpan.style.background = '#e6a822';
            break;
        case 'READING':
            statusSpan.innerText = generationDetector.check() ? '⚡ ГЕНЕРАЦИЯ' : '🔍 ЧТЕНИЕ...';
            statusSpan.style.background = '#bb86fc';
            break;
        case 'POSTING':
            statusSpan.innerText = '📤 ОТПРАВКА'; statusSpan.style.background = '#31a24c';
            break;
    }
}

// ==========================================================
// 5. PRO-РЕЖИМ И ПРОВЕРКА ЛИМИТОВ
// ==========================================================
function resetChat() {
    const newChatBtn = document.querySelector(
        'a[data-test-id="new-chat-button"], a[href^="/app"], button[aria-label*="New chat" i], button[aria-label*="Новый чат" i]'
    );
    if (newChatBtn) newChatBtn.click();
    else window.location.href = "https://gemini.google.com/app";
}

async function triggerLimitReached(reason) {
    if (isLimitReached) return;
    console.warn(`VibeCoder: Лимит. Причина: ${reason}`);
    isLimitReached = true;
    updatePanelUI();
    fetchPostProxy(`${SERVER_URL}/limit_reached`, JSON.stringify({ source_id: myTabId })).catch(() => {});
}

async function checkGeminiAlerts() {
    if (window.ignoreLimitsSession) return false;
    
    const alertZone = document.querySelector('snack-bar-container, .toast-container, [role="alert"], .error-message, .limit-message');
    const bodyText = (alertZone && alertZone.innerText ? alertZone.innerText : "").toLowerCase();
    
    if (bodyText.includes("you've reached your pro model limit") ||
        bodyText.includes("limit resets on") ||
        bodyText.includes("лимит запросов исчерпан") ||
        bodyText.includes("upgrade")) {
        await triggerLimitReached(bodyText); 
        return true;
    }
    return false;
}

async function ensureProMode() {
    if (window.ignoreLimitsSession) return true;

    const modelSelector = document.querySelector(
        '[data-test-id="bard-mode-menu-button"], button.input-area-switch'
    );
    if (!modelSelector) return true;

    const currentText = (modelSelector.innerText || modelSelector.textContent || "").toLowerCase().trim();
    if ((currentText.includes('pro') || currentText.includes('advanced')) && !currentText.includes('thinking')) {
        return true;
    }

    modelSelector.click();
    await new Promise(r => setTimeout(r, 400));

    const overlay = document.querySelector('.cdk-overlay-container') || document.body;
    const menuItems = Array.from(overlay.querySelectorAll(
        '[role="menuitem"], [role="option"], [role="menuitemradio"], button.mat-mdc-menu-item'
    ));

    const proItem = menuItems.find(i => {
        const t = (i.innerText || i.textContent || "").toLowerCase();
        return (t.includes('pro') || t.includes('advanced')) && !t.includes('thinking');
    });

    if (proItem) {
        const itemText = (proItem.innerText || proItem.textContent || "").toLowerCase();
        if (itemText.includes('upgrade') || itemText.includes('обновить') ||
            proItem.disabled || proItem.getAttribute('aria-disabled') === 'true') {
            document.body.click();
            await triggerLimitReached("Pro заблокирован/требует обновления");
            return false;
        }
        proItem.click();

        const overlayEl = document.querySelector('.cdk-overlay-container');
        if (overlayEl) {
            await new Promise(resolve => {
                const observer = new MutationObserver(() => {
                    if (!document.querySelector('[role="menuitem"]')) {
                        observer.disconnect(); resolve();
                    }
                });
                observer.observe(overlayEl, { childList: true, subtree: true });
                setTimeout(() => { observer.disconnect(); resolve(); }, 1000);
            });
        }
        return true;
    }

    document.body.click();
    return true;
}

// ==========================================================
// 6. УТИЛИТЫ И РЕВЕРС-ИНЖИНИРИНГ МАРКДАУНА
// ==========================================================
function base64ToFile(b64, mime, filename) {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    return new File([bytes], filename, { type: mime });
}

function getLastModelText() {
    const elements = Array.from(document.querySelectorAll('message-content'));
    const validContents = elements.filter(el =>
        !el.closest('user-query, [data-message-author-role="user"]')
    );
    
    if (validContents.length === 0) return "";
    
    const originalNode = validContents[validContents.length - 1];
    const clone = originalNode.cloneNode(true);
    
    const preTags = Array.from(clone.querySelectorAll('pre'));
    const bTick = String.fromCharCode(96) + String.fromCharCode(96) + String.fromCharCode(96);
    
    preTags.forEach(pre => {
        let lang = "";
        const wrapper = pre.closest('code-block, .code-block, [data-test-id*="code-block"]') || pre;
        
        if (wrapper !== pre) {
            const header = wrapper.querySelector('.code-block-header, .language-name, [data-test-id*="language"], span:first-child');
            if (header) {
                lang = (header.innerText || header.textContent || "").trim().split(/\s+/)[0];
                if (lang.toLowerCase().includes('copy')) lang = "";
            }
        }
        
        const codeTag = pre.querySelector('code');
        if (!lang && codeTag && codeTag.className) {
            const match = codeTag.className.match(/language-(\w+)/);
            if (match) lang = match[1];
        }
        
        const sourceCode = (pre.innerText || pre.textContent || "").trimEnd();
        const mdFormattedNode = document.createTextNode(`\n\n${bTick}${lang.toLowerCase()}\n${sourceCode}\n${bTick}\n\n`);
        wrapper.replaceWith(mdFormattedNode);
    });
    
    clone.querySelectorAll('br').forEach(br => br.replaceWith(document.createTextNode('\n')));
    
    clone.querySelectorAll('p, h1, h2, h3, h4, h5, h6').forEach(el => {
        el.appendChild(document.createTextNode('\n\n'));
    });
    
    clone.querySelectorAll('li').forEach(el => {
        el.insertBefore(document.createTextNode('\n* '), el.firstChild);
        el.appendChild(document.createTextNode('\n'));
    });
    
    clone.querySelectorAll('div').forEach(el => {
        el.appendChild(document.createTextNode('\n'));
    });

    let textTextText = clone.textContent || "";
    textTextText = textTextText.replace(/\u00A0/g, ' ').replace(/\u200B/g, '');
    textTextText = textTextText.replace(/\n\s*\n\s*\n/g, '\n\n'); 
    
    return textTextText.trim();
}

function checkIsGenerating() {
    if (generationDetector.check()) return true;

    // Ограничиваем поиск спиннеров строго активной зоной текущего чата
    const chatArea = document.querySelector('chat-window, .main-content, #chat-history');
    if (!chatArea) return false;

    const activeResponses = chatArea.querySelectorAll('model-response');
    if (activeResponses.length > 0) {
        const last = activeResponses[activeResponses.length - 1];
        
        // Игнорируем завершенные блоки и элементы из левой панели навигации
        if (last.classList.contains('completed') || 
            last.hasAttribute('data-loading', 'false') ||
            last.closest('side-navigation-v2, mat-sidenav, .bots-list-container')) {
            return false;
        }

        const spinner = last.querySelector('mat-progress-spinner, .gmat-mdc-progress-spinner, mat-spinner');
        if (spinner) {
            const style = window.getComputedStyle(spinner);
            if (spinner.offsetWidth > 0 && spinner.offsetHeight > 0 &&
                style.display !== 'none' && style.opacity !== '0' && style.visibility !== 'hidden') {
                return true;
            }
        }
    }
    return false;
}

// ==========================================================
// 7. ЗАГРУЗКА ФАЙЛОВ
// ==========================================================
async function uploadFiles(filesPayload, inputArea) {
    if (!filesPayload || filesPayload.length === 0) return;

    try {
        const files = filesPayload.map(f => base64ToFile(f.data, f.mime, f.name));
        const dt = new DataTransfer();
        files.forEach(f => dt.items.add(f));

        const addBtns = document.querySelectorAll(
            'button[aria-label*="upload" i], button[aria-label*="загруз" i], button[aria-label*="attach" i], button[aria-label*="прикреп" i]'
        );
        if (addBtns.length > 0) {
            addBtns[0].click();
            await new Promise(r => setTimeout(r, 400));
        }

        const fileInputs = document.querySelectorAll('input[type="file"]');
        if (fileInputs.length > 0) {
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'files').set;
            fileInputs.forEach(fi => {
                try {
                    nativeSetter.call(fi, dt.files);
                    fi.dispatchEvent(new Event('change', { bubbles: true }));
                } catch (e) {}
            });
        } else {
            inputArea.dispatchEvent(new DragEvent('drop', {
                bubbles: true, cancelable: true, dataTransfer: dt
            }));
        }

        const start = Date.now();
        while (Date.now() - start < 3000) {
            const container = inputArea.closest('form, .input-area, rich-textarea, [role="region"]') || document.body;
            const chips = container.querySelectorAll(
                'file-attachment-chip, attachment-chip, preview-chip, .file-preview, [data-test-id*="attachment"]'
            );
            if (chips.length >= filesPayload.length) {
                const spinners = container.querySelectorAll('mat-progress-spinner, .gmat-mdc-progress-spinner, [role="progressbar"]');
                let uploading = false;
                spinners.forEach(s => {
                    if (s.offsetWidth > 0 && window.getComputedStyle(s).display !== 'none') uploading = true;
                });
                if (!uploading) { await new Promise(r => setTimeout(r, 400)); break; }
            }
            await new Promise(r => setTimeout(r, 300));
        }
    } catch (err) {
        console.warn('VibeCoder: Ошибка загрузки файлов:', err);
    }
}

// ==========================================================
// 8. ОТПРАВКА В GEMINI
// ==========================================================
async function sendToGemini(text, filesPayload = []) {
    if (!await ensureProMode()) {
        FSM.reset();
        isProcessing = false;
        return;
    }

    const inputArea = document.querySelector(
        'rich-textarea > div, div[contenteditable="true"][role="textbox"], textarea#prompt-textarea'
    );
    if (!inputArea) { 
        FSM.reset();
        isProcessing = false; 
        return; 
    }

    if (filesPayload && filesPayload.length > 0) {
        await uploadFiles(filesPayload, inputArea);
    }

    await insertLargeTextChunked(inputArea, text);

    const fieldSnapshot = (inputArea.innerText || inputArea.value || '').substring(0, 200);
    console.log(`VibeCoder: Содержимое поля перед Send:\n"${fieldSnapshot}"`);
    if (!fieldSnapshot.trim()) {
        console.error('VibeCoder: ⚠️ ПОЛЕ ПУСТОЕ! Отправка прервана.');
        sendLog('❌ Поле ввода пустое перед отправкой. Задача не выполнена.', '#ff4444');
        FSM.reset();
        isProcessing = false;
        activeTaskId = null;
        return;
    }

    window.textBeforeSend = getLastModelText();
    window.waitingForNewBubble = true;
    window.waitStartTime = Date.now();

    const sendStart = Date.now();
    let sent = false;

    while (Date.now() - sendStart < 5000) {
        const sendBtn = Array.from(document.querySelectorAll('button')).find(b => {
            const label = ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).toLowerCase();
            return (label.includes('send') || label.includes('отправить')) && !label.includes('feedback');
        }) || document.querySelector('[data-testid="send-button"], .send-button');

        if (sendBtn && !sendBtn.disabled && sendBtn.getAttribute('aria-disabled') !== 'true') {
            sendBtn.click();
            sent = true;
            console.log('VibeCoder: ✅ Send нажат.');
            break;
        }
        await new Promise(r => setTimeout(r, 150));
    }

    if (!sent) {
        const fallback = document.querySelector(
            '[data-testid="send-button"], .send-button, button[aria-label*="send" i], button[aria-label*="отправить" i]'
        );
        if (fallback) {
            fallback.click();
            console.log('VibeCoder: Send через fallback.');
        } else {
            console.error('VibeCoder: Кнопка Send не найдена!');
            sendLog('❌ Кнопка Send не найдена!', '#ff4444');
            window.waitingForNewBubble = false;
            FSM.reset();
            isProcessing = false;
            activeTaskId = null;
        }
    }
}

// ==========================================================
// 9. ГЛАВНЫЙ ОРКЕСТРАТОР С ЖЕСТКИМ РАДАРОМ И ЗАЩИТОЙ (FSM)
// ==========================================================
async function checkServer() {
    // Глобальный Failsafe предохранитель
    if (FSM.state !== 'IDLE' && FSM.elapsed() > 90000) {
        console.error(`FSM: Таймаут в состоянии ${FSM.state}. Принудительный сброс.`);
        sendLog(`⏰ Таймаут ${FSM.state}. Сброс.`, '#ff4444');
        FSM.reset();
        isProcessing = false;
        activeTaskId = null;
        window.isRadarMode = false;
        return;
    }

    try {
        switch (FSM.state) {

            case 'IDLE': {
                // Добавляем передачу текущей известной сессии в параметры запроса
                const sessionParam = knownServerSessionId ? `&session_id=${encodeURIComponent(knownServerSessionId)}` : '';
                const data = await fetchGetProxy(`${SERVER_URL}/get_task?target_id=${encodeURIComponent(myTabId)}${sessionParam}`);
                
                if (data && data.status) {
                    // [FIX-E] Проверка консистентности сессии: если бэкенд отдал новый session_id,
                    // значит Python-сервер был перезапущен. Сбрасываем все активные процессы.
                    if (data.server_session_id && knownServerSessionId && data.server_session_id !== knownServerSessionId) {
                        console.warn(`VibeCoder: Обнаружен перезапуск бэкенда (смена сессии: ${knownServerSessionId} -> ${data.server_session_id}). Сброс автомата.`);
                        knownServerSessionId = data.server_session_id;
                        FSM.reset();
                        isProcessing = false;
                        activeTaskId = null;
                        window.isRadarMode = false;
                        return;
                    }

                    // Первичная фиксация сессии
                    if (data.server_session_id && !knownServerSessionId) {
                        knownServerSessionId = data.server_session_id;
                    }

                    if (data.status === "success" && data.task) {
                        window.processingStartTime = Date.now();
                        
                        if (data.task.prompt === "___RADAR_MODE___") {
                            FSM._taskId = "manual_drag_task_" + Date.now();
                            activeTaskId = FSM._taskId;
                            isProcessing = true;
                            window.isRadarMode = true;
                            FSM._snapshotBeforeSend = getLastModelText();
                            window.textBeforeSend = FSM._snapshotBeforeSend;
                            window.waitingForNewBubble = true;
                            window.waitStartTime = Date.now();
                            FSM.transition('WAITING_BUBBLE');
                            sendLog("📡 Радар на связи! Жду вашего нажатия Enter...", "#bb86fc");
                            return;
                        } else {
                            FSM._taskId = data.task.id;
                            activeTaskId = FSM._taskId;
                            isProcessing = true;
                            window.isRadarMode = false;
                            if (!FSM.transition('INJECTING')) return;
                            
                            FSM._snapshotBeforeSend = getLastModelText();
                            await sendToGemini(data.task.prompt, data.task.images);
                            FSM.transition('WAITING_BUBBLE');
                            return;
                        }
                    }
                }

                if (checkIsGenerating()) {
                    window.processingStartTime = Date.now();
                    FSM._taskId = "manual_drag_task_" + Date.now();
                    activeTaskId = FSM._taskId;
                    isProcessing = true;
                    window.isRadarMode = false;
                    currentCandidateText = "";
                    stableCount = 0;
                    FSM.transition('READING');
                    sendLog("📡 Засечена внезапная ручная генерация! Начинаем перехват ответа...", "#bb86fc");
                    return;
                }
                break;
            }

            case 'WAITING_BUBBLE': {
                if (FSM.elapsed() > 120000) {
                    sendLog("⏳ Таймаут ожидания ответа (2 мин). Перехват отменен.", "#ffaa00");
                    FSM.reset();
                    isProcessing = false;
                    activeTaskId = null;
                    window.isRadarMode = false;
                    return;
                }
                
                const currentText = getLastModelText();
                if (currentText !== FSM._snapshotBeforeSend) {
                    window.waitingForNewBubble = false;
                    stableCount = 0;
                    currentCandidateText = "";
                    sendLog("📡 Генерация пошла! Перехватываю ответ...", "#bb86fc");
                    FSM.transition('READING');
                }
                break;
            }

            case 'READING': {
                if (FSM.elapsed() > 120000) {
                    sendLog("⚠️ Чтение затянулось или зависло. Сброс.", "#ffaa00");
                    FSM.reset();
                    isProcessing = false;
                    activeTaskId = null;
                    window.isRadarMode = false;
                    return;
                }

                checkGeminiAlerts().catch(() => {});

                const isGen = checkIsGenerating();
                const currentText = getLastModelText();
                const diffText = currentText.replace(/Thinking for \d+s/gi, '').trim();

                if (isGen) {
                    stableCount = 0;
                    currentCandidateText = diffText;
                    updatePanelUI();
                    return;
                }

                if (diffText !== currentCandidateText) {
                    currentCandidateText = diffText;
                    stableCount = 0;
                } else {
                    stableCount++;
                }

                if (stableCount >= 2 && activeTaskId) {
                    if (FSM.transition('POSTING')) {
                        isProcessing = true;
                        try {
                            sendLog("📤 Чтение завершено, отправляю текст в IDE...", "#31a24c");
                            await fetchPostProxy(`${SERVER_URL}/post_result`, JSON.stringify({
                                task_id: activeTaskId, result: currentText, source_id: myTabId
                            }));
                        } catch (err) {
                            console.error('VibeCoder: Ошибка отправки результата:', err);
                        } finally {
                            isProcessing = false;
                            activeTaskId = null;
                            window.isRadarMode = false;
                            FSM.reset();
                        }
                    }
                } else {
                    updatePanelUI();
                }
                break;
            }

            case 'POSTING': {
                break;
            }
        }
    } catch (e) {
        console.error("VibeCoder: Критическая ошибка в checkServer:", e);
        isProcessing = false;
        window.isRadarMode = false;
        activeTaskId = null;
        FSM.reset();
    }
}

setInterval(checkServer, 1000);