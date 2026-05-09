/**
 * 📖 БИБЛИЯ ПРОЕКТА: CONTENT.JS (v3.0 - VIRTUAL FILE SYSTEM & DOUBLE-TAP INJECTION)
 */

let myTabId = sessionStorage.getItem('vc_tab_id');
if (!myTabId) {
    myTabId = 'TAB-' + Math.random().toString(36).substring(2, 6).toUpperCase();
    sessionStorage.setItem('vc_tab_id', myTabId);
}
let myTabName = localStorage.getItem(`vc_name_${myTabId}`) || myTabId;

// Глобальный флаг для ручного продолжения работы на Flash-версии
window.ignoreLimitsSession = false;

setInterval(() => {
    fetch('http://localhost:5070/heartbeat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ tab_id: myTabId, tab_name: myTabName })
    }).catch(() => {}); 
}, 2000);

// === КОМПАКТНАЯ ПЛАШКА С ФУНКЦИЕЙ ПЕРЕТАСКИВАНИЯ (DRAG & DROP) ===
function createVibeBadge() {
    if (document.getElementById('vibe-coder-badge')) return;

    const badge = document.createElement('div');
    badge.id = 'vibe-coder-badge';
    
    badge.innerHTML = `
        <div style="display: flex; align-items: center; width: 100%;">
            <span id="vibe-drag-handle" style="margin-right: 8px; opacity: 0.5; font-size: 16px;" title="Потяните, чтобы переместить">⠿</span>
            🤖 <b>VibeCoder:</b> 
            <span id="vibe-tab-name" style="cursor:pointer; border-bottom: 1px dashed #888; margin-left: 5px; margin-right: 8px;" title="Кликните, чтобы переименовать вкладку">${myTabName}</span>
            <span id="vibe-status" style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #3c3c3c; color: #fff; font-weight: bold;">⏳ Загрузка...</span>
        </div>
    `;
    
    const savedLeft = localStorage.getItem('vc_badge_left') || '20px';
    const savedTop = localStorage.getItem('vc_badge_top') || (window.innerHeight - 60) + 'px';

    Object.assign(badge.style, {
        position: 'fixed', left: savedLeft, top: savedTop,
        backgroundColor: 'rgba(30, 30, 30, 0.85)', backdropFilter: 'blur(5px)',
        color: '#d4d4d4', padding: '8px 15px', borderRadius: '8px',
        border: '1px solid #569cd6', fontFamily: 'sans-serif', fontSize: '13px',
        zIndex: '999999', boxShadow: '0 4px 6px rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'center', userSelect: 'none', cursor: 'grab'
    });

    let isDragging = false;
    let hasMoved = false;
    let offsetX, offsetY;

    badge.onmousedown = function(e) {
        if (e.target.id === 'vibe-tab-name') return; 
        
        isDragging = true;
        hasMoved = false;
        offsetX = e.clientX - badge.getBoundingClientRect().left;
        offsetY = e.clientY - badge.getBoundingClientRect().top;
        badge.style.cursor = 'grabbing';

        document.onmousemove = function(e) {
            if (isDragging) {
                hasMoved = true;
                let newLeft = e.clientX - offsetX;
                let newTop = e.clientY - offsetY;
                
                newLeft = Math.max(0, Math.min(newLeft, window.innerWidth - badge.offsetWidth));
                newTop = Math.max(0, Math.min(newTop, window.innerHeight - badge.offsetHeight));
                
                badge.style.left = newLeft + 'px';
                badge.style.top = newTop + 'px';
            }
        };

        document.onmouseup = function() {
            isDragging = false;
            badge.style.cursor = 'grab';
            document.onmousemove = null;
            document.onmouseup = null;
            
            if (hasMoved) {
                localStorage.setItem('vc_badge_left', badge.style.left);
                localStorage.setItem('vc_badge_top', badge.style.top);
            }
        };
    };

    badge.onmouseover = () => badge.style.backgroundColor = 'rgba(14, 99, 156, 0.9)';
    badge.onmouseout = () => badge.style.backgroundColor = 'rgba(30, 30, 30, 0.85)';

    badge.querySelector('#vibe-tab-name').onclick = (e) => {
        if (hasMoved) return; 
        e.stopPropagation();
        const newName = prompt('Введите имя для этой вкладки VibeCoder:', myTabName);
        if (newName && newName.trim() !== '') {
            myTabName = newName.trim();
            localStorage.setItem(`vc_name_${myTabId}`, myTabName);
            document.getElementById('vibe-tab-name').textContent = myTabName;
        }
    };
    
    document.body.appendChild(badge);
}

createVibeBadge();
setTimeout(createVibeBadge, 1500);

function updatePanelUI(isPaused, serverDown = false) {
    const statusSpan = document.getElementById('vibe-status');
    const badge = document.getElementById('vibe-coder-badge');
    if (!statusSpan || !badge) return;

    badge.style.border = '1px solid #569cd6';

    if (serverDown) {
        statusSpan.innerHTML = '🔴 ОФФЛАЙН';
        statusSpan.style.background = '#ff4444'; statusSpan.style.color = 'white';
        return;
    }
    if (isLimitReached && !window.ignoreLimitsSession) {
        badge.style.border = '2px solid #ff4444';
        statusSpan.innerHTML = '🛑 ЛИМИТЫ';
        statusSpan.style.background = '#ff4444'; statusSpan.style.color = 'white';
        return;
    }
    if (isPaused) {
        statusSpan.innerHTML = '⏸ ПАУЗА';
        statusSpan.style.background = '#ffaa00'; statusSpan.style.color = 'black';
    } else {
        if (lastServerState === "RUNNING") {
            statusSpan.innerHTML = '⚡ ГЕНЕРАЦИЯ';
            statusSpan.style.background = '#bb86fc'; statusSpan.style.color = 'black';
        } else {
            statusSpan.innerHTML = '🟢 ГОТОВ';
            statusSpan.style.background = '#31a24c'; statusSpan.style.color = 'white';
        }
    }
}

// ==========================================

const SERVER_URL = "http://localhost:5070";
let isProcessing = false;
let lastProcessedText = "";
let currentCandidateText = "";
let stableCount = 0;
let lastServerState = "STOPPED";
let isSystemPaused = false;
let activeTaskId = null;
let isLimitReached = false;

async function fetchGetProxy(url) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({action: "proxy_get", url: url}, (response) => {
            if (chrome.runtime.lastError) return reject("Runtime Error: " + chrome.runtime.lastError.message);
            if (response && response.success) resolve(response.data);
            else reject(response ? response.error : "Background script no response");
        });
    });
}

async function fetchPostProxy(url, bodyText) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({action: "proxy_post", url: url, body: bodyText}, (response) => {
            if (chrome.runtime.lastError) return reject("Runtime Error: " + chrome.runtime.lastError.message);
            if (response && response.success) resolve(response.data);
            else reject(response ? response.error : "Background POST failed");
        });
    });
}

function resetChat() {
    const newChatBtn = document.querySelector('a[data-test-id="new-chat-button"], a[href^="/app"], button[aria-label*="New chat"], button[aria-label*="Новый чат"]');
    if (newChatBtn) newChatBtn.click();
    else window.location.href = "https://gemini.google.com/app";
}

async function triggerLimitReached(reason) {
    if (isLimitReached) return;
    console.warn(`VibeCoder: Сработал триггер лимитов. Причина: ${reason}`);
    isLimitReached = true;
    updatePanelUI(isSystemPaused, false);
    try { 
        await fetchPostProxy(`${SERVER_URL}/limit_reached`, JSON.stringify({source_id: myTabId})); 
    } catch (e) {}
}

async function checkGeminiAlerts() {
    if (window.ignoreLimitsSession) return false;

    const bodyText = (document.body.innerText || "").toLowerCase();
    if (bodyText.includes("you've reached your pro model limit") || 
        bodyText.includes("limit resets on") ||
        bodyText.includes("лимит запросов исчерпан")) {
        await triggerLimitReached("Обнаружен текст о лимитах на странице");
        return true;
    }

    const alerts = document.querySelectorAll('snack-bar, .error-message, [role="alert"], .limit-message');
    for (let el of alerts) {
        const t = (el.innerText || "").toLowerCase();
        if (t.includes("limit") || t.includes("лимит") || t.includes("upgrade")) {
            await triggerLimitReached(t); 
            return true;
        }
    }
    return false;
}

async function ensureProMode() {
    if (window.ignoreLimitsSession) {
        console.log("VibeCoder: Игнорируем проверку Pro-режима по выбору пользователя (работаем на Flash).");
        return true; 
    }

    console.log("VibeCoder: Проверка активности Pro-режима...");
    
    const clickableElements = Array.from(document.querySelectorAll('button, [role="button"], [role="combobox"]'));
    const modelSelector = clickableElements.find(el => {
        const text = (el.innerText || el.textContent || "").trim();
        return (text === 'Fast' || text === 'Flash' || text === 'Pro' || text.includes('Advanced')) && text.length < 20;
    });

    if (!modelSelector) {
        console.warn("VibeCoder: ⚠️ Переключатель модели не найден на странице!");
        return true; 
    }

    const currentText = (modelSelector.innerText || modelSelector.textContent || "").trim();
    console.log(`VibeCoder: Текущая выбранная модель: [${currentText}]`);

    if (currentText.includes('Pro') || currentText.includes('Advanced')) {
        console.log("VibeCoder: Pro-режим уже активен.");
        return true;
    }

    console.log("VibeCoder: Обнаружена базовая модель. Пытаюсь переключить на Pro...");
    modelSelector.click();
    await new Promise(r => setTimeout(r, 800)); 

    const menuItems = Array.from(document.querySelectorAll('menu-item, [role="menuitem"], [role="option"], [role="menuitemradio"], li'));
    const proItem = menuItems.find(i => {
        const t = (i.innerText || i.textContent || "").trim();
        return t.includes('Pro') || t.includes('Advanced');
    });

    if (proItem) {
        const itemText = (proItem.innerText || proItem.textContent || "").trim();
        if (itemText.includes('Upgrade') || itemText.includes('Обновить')) {
            console.warn("VibeCoder: Опция Pro заблокирована (требуется подписка/лимит исчерпан).");
            document.body.click();
            await triggerLimitReached("Опция Pro требует обновления");
            return false;
        }
        
        console.log("VibeCoder: Кликаем по опции Pro...");
        proItem.click();
        await new Promise(r => setTimeout(r, 1000));
        return true;
    } else {
        console.error("VibeCoder: ❌ В меню не найдена модель Pro/Advanced. Лимиты исчерпаны?");
        document.body.click(); 
        await triggerLimitReached("Модель Pro недоступна в меню");
        return false;
    }
}

function base64ToFile(base64Data, mimeType, filename) {
    const byteCharacters = atob(base64Data);
    const byteArrays = [];
    for (let offset = 0; offset < byteCharacters.length; offset += 512) {
        const slice = byteCharacters.slice(offset, offset + 512);
        const byteNumbers = new Array(slice.length);
        for (let i = 0; i < slice.length; i++) {
            byteNumbers[i] = slice.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        byteArrays.push(byteArray);
    }
    const blob = new Blob(byteArrays, { type: mimeType });
    return new File([blob], filename, { type: mimeType });
}

function extractGeminiText(element) {
    let clone = element.cloneNode(true);
    
    let container = document.createElement('div');
    Object.assign(container.style, {
        position: 'absolute', left: '-9999px', top: '0', opacity: '0', display: 'block', width: '800px'
    });
    container.appendChild(clone);
    document.body.appendChild(container);

    // 1. Убираем мусор
    clone.querySelectorAll('button, .copy-button, [aria-label*="Copy"]').forEach(btn => btn.remove());

    // 2. ЧИНИМ БЛОКИ КОДА
    let pres = clone.querySelectorAll('pre');
    pres.forEach(pre => {
        let code = pre.innerText || pre.textContent;
        let lang = 'python';
        
        let wrapper = pre.closest('.code-block, code-block, [class*="code"]');
        if (wrapper) {
            let header = wrapper.querySelector('.language-name, .code-block-language');
            if (header && header.innerText) {
                lang = header.innerText.trim().split('\n')[0].replace(/[^a-zA-Z0-9+#-]/g, '').toLowerCase();
            }
        }

        let mdCodeBlock = document.createElement('div');
        mdCodeBlock.innerText = `\n\n\`\`\`${lang || 'python'}\n${code}\n\`\`\`\n\n`;
        
        if (wrapper && wrapper.parentNode) {
            wrapper.replaceWith(mdCodeBlock);
        } else if (pre.parentNode) {
            pre.replaceWith(mdCodeBlock);
        }
    });

    // 3. ВОССТАНАВЛИВАЕМ СПИСКИ
    clone.querySelectorAll('li').forEach(li => {
        if (li.parentNode && li.parentNode.tagName === 'OL') {
            let idx = Array.from(li.parentNode.children).indexOf(li) + 1;
            li.textContent = `${idx}. ${li.textContent}`;
        } else {
            li.textContent = `- ${li.textContent}`;
        }
    });

    let result = clone.innerText || clone.textContent;
    document.body.removeChild(container);
    
    return result.replace(/\n{3,}/g, '\n\n').trim();
}

async function checkServer() {
    if (isProcessing) return; 
    try {
        let taskUrl = `${SERVER_URL}/get_task?target_id=${encodeURIComponent(myTabId)}`;
        const data = await fetchGetProxy(taskUrl);
        
        if (data.status === "paused") {
            isSystemPaused = true;
            updatePanelUI(true, false);
            return; 
        } else {
            if (isSystemPaused && isLimitReached) {
                console.log("VibeCoder: Пауза снята сервером! Пользователь решил продолжить на Flash.");
                window.ignoreLimitsSession = true;
                isLimitReached = false;
            }
            isSystemPaused = false;
        }

        if (!window.ignoreLimitsSession) {
            if (await checkGeminiAlerts()) return; 
        }

        if (data.status === "success" && data.task) {
            const task = data.task;
            activeTaskId = task.id;
            isProcessing = true;
            lastServerState = "RUNNING";
            updatePanelUI(false, false);

            if (task.is_relay) {
                resetChat();
                await new Promise(r => setTimeout(r, 2000));
            }
            
            lastProcessedText = ""; currentCandidateText = ""; stableCount = 0;
            await sendToGemini(task.prompt, task.images);
            return;
        }

        if (isLimitReached) {
            updatePanelUI(false, false);
            return;
        }

        const generatingElements = document.querySelectorAll(['button[aria-label*="Stop generating"]', 'button[aria-label*="Остановить"]', '.gmat-mdc-progress-spinner', 'mat-spinner'].join(', '));
        let isGenerating = false;
        for (let el of generatingElements) { if (el.offsetWidth > 0 || el.offsetHeight > 0) { isGenerating = true; break; } }
        
        if (isGenerating) { 
            lastServerState = "RUNNING";
            updatePanelUI(false, false);
            stableCount = 0; 
            return; 
        }

        const modelResponses = document.querySelectorAll(['message-content', '.model-response-text', '[data-message-author-role="model"]'].join(', '));
        if (modelResponses.length > 0) {
            const lastResponse = modelResponses[modelResponses.length - 1];
            let text = extractGeminiText(lastResponse);
            
            if (text && text.trim() !== "") {
                if (text !== currentCandidateText) { currentCandidateText = text; stableCount = 0; } 
                else if (text !== lastProcessedText) { stableCount++; }

                if (stableCount >= 2) {
                    isProcessing = true;
                    lastProcessedText = currentCandidateText;
                    lastServerState = "STOPPED";
                    updatePanelUI(false, false);
                    
                    const payloadString = JSON.stringify({ task_id: activeTaskId, result: currentCandidateText, source_id: myTabId });
                    try {
                        await fetchPostProxy(`${SERVER_URL}/post_result`, payloadString);
                    } catch (err) {} finally {
                        isProcessing = false; stableCount = 0; activeTaskId = null;
                    }
                }
            }
        } else {
             lastServerState = "STOPPED";
             updatePanelUI(false, false);
        }
    } catch (e) {
        lastServerState = "STOPPED";
        updatePanelUI(isSystemPaused, true);
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

    if (filesPayload && filesPayload.length > 0) {
        try {
            const files = filesPayload.map(fileObj => base64ToFile(fileObj.data, fileObj.mime, fileObj.name));
            const dt = new DataTransfer();
            files.forEach(f => dt.items.add(f));
            
            // ХАК 1: Нативная инъекция через React setter
            const fileInput = document.querySelector('input[type="file"]');
            if (fileInput) {
                console.log("VibeCoder: Найдена кнопка загрузки. Выполняю React-инъекцию...");
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'files').set;
                nativeSetter.call(fileInput, dt.files);
                fileInput.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                // ХАК 2: Эмуляция физического броска файлов
                console.log("VibeCoder: Использую Drag & Drop инъекцию...");
                const dropEvent = new DragEvent('drop', {
                    bubbles: true, cancelable: true, dataTransfer: dt
                });
                inputArea.dispatchEvent(dropEvent);
            }
            
            console.log("VibeCoder: Файлы отправлены в интерфейс. Жду старта загрузки...");
            await new Promise(r => setTimeout(r, 1500)); // Первичная задержка для старта анимации
            
            // --- НОВАЯ УМНАЯ ЗАДЕРЖКА ---
            let retries = 0;
            let isUploading = false;
            
            while (retries < 40) { // Максимум 20 секунд ожидания
                await new Promise(r => setTimeout(r, 500));
                
                // Проверяем наличие лоадеров
                const spinners = document.querySelectorAll('mat-progress-spinner, .gmat-mdc-progress-spinner, [aria-label="Loading"], .uploader-progress, [role="progressbar"]');
                
                // Проверяем состояние кнопки отправки
                const sendBtnForCheck = document.querySelector('button[aria-label*="Send"], button[aria-label*="Отправить"], [data-testid="send-button"], .send-button');
                const isBtnDisabled = sendBtnForCheck && (sendBtnForCheck.disabled || sendBtnForCheck.getAttribute('aria-disabled') === 'true');
                
                if (spinners.length > 0) {
                    isUploading = true;
                } else if (isUploading && spinners.length === 0 && !isBtnDisabled) {
                    console.log("VibeCoder: Загрузка файлов успешно завершена, кнопка разблокирована.");
                    break;
                } else if (retries > 6 && spinners.length === 0 && !isBtnDisabled) {
                    // Если спиннеров нет вообще, но кнопка активна - файл залетел мгновенно
                    console.log("VibeCoder: Файлы загружены мгновенно.");
                    break;
                }
                retries++;
            }
            // -----------------------------
            
        } catch (err) {
            console.error("VibeCoder: Критическая ошибка при инъекции файлов:", err);
        }
    }

    inputArea.focus();
    document.execCommand('insertText', false, text);
    inputArea.dispatchEvent(new Event('input', { bubbles: true }));
    inputArea.dispatchEvent(new Event('change', { bubbles: true }));
    
    setTimeout(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const sendBtn = buttons.find(b => {
            const combined = ((b.getAttribute('aria-label') || '') + " " + (b.innerText || '')).toLowerCase();
            return (combined.includes('send') || combined.includes('отправить')) && !combined.includes('feedback') && !combined.includes('отзыв');
        }) || document.querySelector('[data-testid="send-button"], .send-button');

        if (sendBtn && !sendBtn.disabled) {
            console.log("VibeCoder: Нажатие кнопки Отправить.");
            sendBtn.click();
        } else {
            console.warn("VibeCoder: Кнопка Отправить всё еще заблокирована перед кликом!");
        }
        setTimeout(() => { isProcessing = false; stableCount = 0; }, 2000);
    }, 800); // Чуть увеличен финальный таймаут перед кликом для надежности
}

setInterval(checkServer, 3000);