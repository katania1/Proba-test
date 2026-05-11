/**
 * 📖 БИБЛИЯ ПРОЕКТА: CONTENT.JS (v4.3 - VISUAL HANDSHAKE & ANTI-THINKING)
 * Интегрирована гарантированная доставка VFS: скрипт дожидается фактической 
 * отрисовки UI-чипов файлов и разблокировки кнопки отправки в чистом чате.
 */

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

const SERVER_URL = "http://localhost:5070";
let isProcessing = false;
let currentCandidateText = "";
let stableCount = 0;
let lastServerState = "STOPPED";
let activeTaskId = null;
let isLimitReached = false;

// Пульс (Heartbeat) для поддержания связи с сервером Flask
setInterval(() => {
    fetch('http://localhost:5070/heartbeat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ tab_id: myTabId, tab_name: myTabName })
    }).catch(() => {}); 
}, 2000);

// ==========================================================
// 1. ПЛАШКА UI (Draggable Badge)
// ==========================================================
function createVibeBadge() {
    if (document.getElementById('vibe-coder-badge')) return;
    const badge = document.createElement('div');
    badge.id = 'vibe-coder-badge';
    badge.innerHTML = `
        <div style="display: flex; align-items: center; width: 100%;">
            <span id="vibe-drag-handle" style="margin-right: 8px; opacity: 0.5; font-size: 16px;">⠿</span>
            🤖 <b>VibeCoder:</b> 
            <span id="vibe-tab-name" style="cursor:pointer; border-bottom: 1px dashed #888; margin-left: 5px; margin-right: 8px;">${myTabName}</span>
            <span id="vibe-status" style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #3c3c3c; color: #fff; font-weight: bold;">⏳ Загрузка...</span>
        </div>
    `;
    Object.assign(badge.style, {
        position: 'fixed', left: '20px', top: (window.innerHeight - 60) + 'px',
        backgroundColor: 'rgba(30, 30, 30, 0.85)', backdropFilter: 'blur(5px)',
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
    document.body.appendChild(badge);
}
createVibeBadge();
setTimeout(createVibeBadge, 1500);

function updatePanelUI() {
    const statusSpan = document.getElementById('vibe-status');
    if (!statusSpan) return;
    if (isLimitReached && !window.ignoreLimitsSession) {
        statusSpan.innerText = '🛑 ЛИМИТЫ'; statusSpan.style.background = '#ff4444'; return;
    }
    if (lastServerState === "RUNNING") {
        statusSpan.innerText = '⚡ ГЕНЕРАЦИЯ'; statusSpan.style.background = '#bb86fc';
    } else {
        statusSpan.innerText = '🟢 ГОТОВ'; statusSpan.style.background = '#31a24c';
    }
}

// ==========================================================
// 2. СЕТЬ И УМНЫЙ PRO-РЕЖИМ (ANTI-THINKING SELECTOR)
// ==========================================================
async function fetchGetProxy(url) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({action: "proxy_get", url: url}, (response) => {
            if (response && response.success) resolve(response.data); else reject("Error");
        });
    });
}

async function fetchPostProxy(url, bodyText) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({action: "proxy_post", url: url, body: bodyText}, (response) => {
            if (response && response.success) resolve(response.data); else reject("Error");
        });
    });
}

function resetChat() {
    const newChatBtn = document.querySelector('a[data-test-id="new-chat-button"], a[href^="/app"], button[aria-label*="New chat" i], button[aria-label*="Новый чат" i]');
    if (newChatBtn) newChatBtn.click();
    else window.location.href = "https://gemini.google.com/app";
}

async function triggerLimitReached(reason) {
    if (isLimitReached) return;
    console.warn(`VibeCoder: Сработал триггер лимитов. Причина: ${reason}`);
    isLimitReached = true;
    updatePanelUI();
    try { await fetchPostProxy(`${SERVER_URL}/limit_reached`, JSON.stringify({source_id: myTabId})); } catch (e) {}
}

async function checkGeminiAlerts() {
    if (window.ignoreLimitsSession) return false;
    const bodyText = (document.body.innerText || "").toLowerCase();
    if (bodyText.includes("you've reached your pro model limit") || bodyText.includes("limit resets on") || bodyText.includes("лимит запросов исчерпан")) {
        await triggerLimitReached("Обнаружен текст о лимитах на странице"); return true;
    }
    const alerts = document.querySelectorAll('snack-bar, .error-message, [role="alert"], .limit-message');
    for (let el of alerts) {
        const t = (el.innerText || "").toLowerCase();
        if (t.includes("limit") || t.includes("лимит") || t.includes("upgrade")) {
            await triggerLimitReached(t); return true;
        }
    }
    return false;
}

async function ensureProMode() {
    if (window.ignoreLimitsSession) return true; 

    console.log("VibeCoder: Проверка активности Pro-режима...");
    const modelSelector = document.querySelector('[data-test-id="bard-mode-menu-button"], button.input-area-switch');

    if (!modelSelector) {
        console.log("VibeCoder: Кнопка переключения моделей не найдена на странице.");
        return true; 
    }

    const currentText = (modelSelector.innerText || modelSelector.textContent || "").toLowerCase().trim();
    console.log(`VibeCoder: Текущая модель на кнопке: [${currentText}]`);

    // Проверяем, что активна Pro/Advanced, но НЕТ приписки Thinking
    const isProActive = currentText.includes('pro') || currentText.includes('advanced');
    const isThinkingActive = currentText.includes('thinking');

    if (isProActive && !isThinkingActive) {
        console.log("VibeCoder: Pro-режим уже активен и это не Thinking.");
        return true;
    }

    console.log("VibeCoder: Включена не та модель. Открываю меню выбора...");
    modelSelector.click();
    await new Promise(r => setTimeout(r, 800)); 

    const overlay = document.querySelector('.cdk-overlay-container') || document.body;
    const menuItems = Array.from(overlay.querySelectorAll('[role="menuitem"], [role="option"], [role="menuitemradio"], button.mat-mdc-menu-item'));

    // Ищем модель, где есть Pro/Advanced, но строго НЕТ слова Thinking
    const proItem = menuItems.find(i => {
        const t = (i.innerText || i.textContent || "").toLowerCase();
        return (t.includes('pro') || t.includes('advanced')) && !t.includes('thinking');
    });

    if (proItem) {
        const itemText = (proItem.innerText || proItem.textContent || "").toLowerCase();
        if (itemText.includes('upgrade') || itemText.includes('обновить') || proItem.disabled || proItem.getAttribute('aria-disabled') === 'true') {
            console.warn("VibeCoder: ⚠️ Опция Pro заблокирована (нужна подписка или исчерпаны лимиты).");
            document.body.click(); 
            await triggerLimitReached("Опция Pro заблокирована/требует обновления");
            return false;
        }
        
        console.log("VibeCoder: Кликаю по опции Pro/Advanced (без Thinking)...");
        proItem.click();
        await new Promise(r => setTimeout(r, 1200)); 
        return true;
    } else {
        console.warn("VibeCoder: ❌ В меню не найдена чистая модель Pro/Advanced без Thinking!");
        document.body.click(); 
        return true; 
    }
}

function base64ToFile(b64, mime, filename) {
    const byteChars = atob(b64);
    const byteArrays = [];
    for (let i = 0; i < byteChars.length; i += 512) {
        const slice = byteChars.slice(i, i + 512);
        const byteNums = new Array(slice.length);
        for (let j = 0; j < slice.length; j++) byteNums[j] = slice.charCodeAt(j);
        byteArrays.push(new Uint8Array(byteNums));
    }
    return new File([new Blob(byteArrays, { type: mime })], filename, { type: mime });
}

// ==========================================================
// 3. ПРЯМОЕ ЧТЕНИЕ ТЕКСТА
// ==========================================================
function getLastModelText() {
    const elements = Array.from(document.querySelectorAll('message-content'));
    const validContents = elements.filter(el => !el.closest('user-query, [data-message-author-role="user"]'));
    
    if (validContents.length > 0) {
        const el = validContents[validContents.length - 1];
        let text = el.innerText || el.textContent;
        return text ? text.replace(/\u00A0/g, ' ').replace(/\u200B/g, '').trim() : "";
    }
    return "";
}

function checkIsGenerating() {
    const stopBtn = document.querySelector('button[aria-label*="stop gen" i], button[aria-label*="останови" i]');
    if (stopBtn && stopBtn.offsetWidth > 0) return true;
    
    const activeResponses = document.querySelectorAll('model-response');
    if (activeResponses.length > 0) {
        const lastResponse = activeResponses[activeResponses.length - 1];
        const spinner = lastResponse.querySelector('mat-progress-spinner, .gmat-mdc-progress-spinner, mat-spinner');
        if (spinner) {
            const style = window.getComputedStyle(spinner);
            if (spinner.offsetWidth > 0 && spinner.offsetHeight > 0 && style.display !== 'none' && style.opacity !== '0' && style.visibility !== 'hidden') { 
                return true;
            }
        }
    }
    return false;
}

// ==========================================================
// 4. ОРКЕСТРАТОР И ИНЪЕКЦИЯ (ГАРАНТИРОВАННАЯ ДОСТАВКА)
// ==========================================================
async function checkServer() {
    if (isProcessing) return; 
    try {
        const data = await fetchGetProxy(`${SERVER_URL}/get_task?target_id=${encodeURIComponent(myTabId)}`);
        
        if (data.status === "success" && data.task) {
            console.log("VibeCoder: 📥 ПОЛУЧЕНА НОВАЯ ЗАДАЧА!");
            activeTaskId = data.task.id;
            isProcessing = true;
            lastServerState = "RUNNING";
            updatePanelUI();
            currentCandidateText = "";
            stableCount = 0;
            await sendToGemini(data.task.prompt, data.task.images);
            return;
        }

        if (!activeTaskId) {
            lastServerState = "STOPPED"; updatePanelUI(); return;
        }

        let currentText = getLastModelText();

        if (window.waitingForNewBubble) {
            if (currentText !== window.textBeforeSend || (Date.now() - window.waitStartTime > 15000)) {
                window.waitingForNewBubble = false;
                stableCount = 0;
            } else {
                lastServerState = "RUNNING"; updatePanelUI(); return;
            }
        }

        let isGenerating = checkIsGenerating();
        if (isGenerating) { 
            stableCount = 0;
            lastServerState = "RUNNING"; updatePanelUI(); return; 
        }

        if (currentText && currentText.trim() !== "") {
            let diffText = currentText.replace(/Thinking for \d+s/gi, '').trim();

            if (diffText !== currentCandidateText) {
                currentCandidateText = diffText;
                stableCount = 0;
            } else {
                stableCount++;
            }

            if (stableCount >= 2 && activeTaskId) {
                isProcessing = true;
                lastServerState = "STOPPED"; updatePanelUI();
                
                const payloadString = JSON.stringify({ task_id: activeTaskId, result: currentText, source_id: myTabId });
                try {
                    await fetchPostProxy(`${SERVER_URL}/post_result`, payloadString);
                    console.log("VibeCoder: ✅ УСПЕХ! Ответ принят сервером.");
                } catch (err) {} finally {
                    isProcessing = false; activeTaskId = null;
                }
            } else {
                lastServerState = "RUNNING"; updatePanelUI();
            }
        } else {
            lastServerState = "RUNNING"; updatePanelUI();
        }
    } catch (e) {
        lastServerState = "STOPPED"; updatePanelUI();
    }
}

async function sendToGemini(text, filesPayload = []) {
    if (!await ensureProMode()) { 
        isProcessing = false; 
        return; 
    }
    
    const inputArea = document.querySelector('rich-textarea > div, div[contenteditable="true"][role="textbox"], textarea#prompt-textarea');
    if (!inputArea) { isProcessing = false; return; }
    
    inputArea.focus();

    // --- ЭТАП 1: ВБРОС И ВИЗУАЛЬНЫЙ HANDSHAKE ФАЙЛОВ ---
    if (filesPayload && filesPayload.length > 0) {
        try {
            const files = filesPayload.map(fileObj => base64ToFile(fileObj.data, fileObj.mime, fileObj.name));
            const dt = new DataTransfer();
            files.forEach(f => dt.items.add(f));
            
            const addBtns = document.querySelectorAll('button[aria-label*="upload" i], button[aria-label*="загруз" i], button[aria-label*="attach" i], button[aria-label*="прикреп" i]');
            if (addBtns.length > 0) { addBtns[0].click(); await new Promise(r => setTimeout(r, 400)); }
            
            let fileInputs = document.querySelectorAll('input[type="file"]');
            if (fileInputs.length > 0) {
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'files').set;
                fileInputs.forEach(fi => { try { nativeSetter.call(fi, dt.files); fi.dispatchEvent(new Event('change', { bubbles: true })); } catch(e) {} });
            } else {
                const dropEvent = new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt });
                inputArea.dispatchEvent(dropEvent);
            }
            
            // 🛡️ ИНТЕЛЛЕКТУАЛЬНОЕ ОЖИДАНИЕ МОНТИРОВАНИЯ (VISUAL HANDSHAKE)
            console.log(`VibeCoder: Ожидание полной отрисовки ${filesPayload.length} вложений в DOM...`);
            const startMountWait = Date.now();
            let isFullyMounted = false;
            
            while (Date.now() - startMountWait < 12000) {
                const formContainer = inputArea.closest('form, .input-area, rich-textarea, [role="region"]') || document.body;
                
                // Ищем отрендеренные чипы/иконки вложений
                const renderedChips = formContainer.querySelectorAll('file-attachment-chip, attachment-chip, preview-chip, .file-preview, [data-test-id*="attachment"], [aria-label*="remove file" i], [aria-label*="удалить файл" i]');
                
                // Проверяем текстовое присутствие имен файлов в контейнере
                let foundNamesCount = 0;
                const containerText = (formContainer.innerText || "").toLowerCase();
                filesPayload.forEach(f => {
                    if (containerText.includes(f.name.toLowerCase())) foundNamesCount++;
                });

                if (renderedChips.length >= filesPayload.length || foundNamesCount >= filesPayload.length) {
                    console.log("VibeCoder: ✅ Визуальный Handshake успешен! Вложения зафиксированы интерфейсом.");
                    isFullyMounted = true;
                    await new Promise(r => setTimeout(r, 600)); // Короткая пауза для завершения внутренних анимаций React
                    break;
                }
                await new Promise(r => setTimeout(r, 400));
            }
            
            if (!isFullyMounted) {
                console.warn("VibeCoder: ⚠️ Истекло время ожидания иконок файлов. Переходим к отправке по таймеру.");
            }
        } catch (err) {
            console.error("VibeCoder: Ошибка при инъекции файлов:", err);
        }
    }

    // --- ЭТАП 2: ВСТАВКА ТЕКСТА ПРОМПТА ---
    inputArea.focus();
    document.execCommand('insertText', false, text);
    inputArea.dispatchEvent(new Event('input', { bubbles: true }));
    inputArea.dispatchEvent(new Event('change', { bubbles: true }));
    
    // --- ЭТАП 3: ОЖИДАНИЕ РАЗБЛОКИРОВКИ И КЛИК ОТПРАВКИ ---
    window.textBeforeSend = getLastModelText();
    window.waitingForNewBubble = true;
    window.waitStartTime = Date.now();

    console.log("VibeCoder: Ожидание активации кнопки 'Отправить'...");
    const startSendWait = Date.now();
    let isSentSuccessfully = false;

    while (Date.now() - startSendWait < 8000) {
        const buttons = Array.from(document.querySelectorAll('button'));
        const sendBtn = buttons.find(b => {
            const combined = ((b.getAttribute('aria-label') || '') + " " + (b.innerText || '')).toLowerCase();
            return (combined.includes('send') || combined.includes('отправить')) && !combined.includes('feedback');
        }) || document.querySelector('[data-testid="send-button"], .send-button');

        // Проверяем, что кнопка существует и не заблокирована
        if (sendBtn && !sendBtn.disabled && sendBtn.getAttribute('aria-disabled') !== 'true') {
            console.log("VibeCoder: 🚀 Кнопка активна. Выполняем отправку!");
            sendBtn.click();
            isSentSuccessfully = true;
            break;
        }
        await new Promise(r => setTimeout(r, 300));
    }

    if (!isSentSuccessfully) {
        console.warn("VibeCoder: ⚠️ Кнопка отправки не разблокировалась. Принудительный резервный клик.");
        const fallbackBtn = document.querySelector('[data-testid="send-button"], .send-button, button[aria-label*="send" i], button[aria-label*="отправить" i]');
        if (fallbackBtn) fallbackBtn.click();
    }

    // Освобождаем статус обработки с запасом времени
    setTimeout(() => { isProcessing = false; }, 3500);
}

// Запуск основного цикла проверки задач
setInterval(checkServer, 3000);