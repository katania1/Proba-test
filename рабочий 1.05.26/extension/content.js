/**
 * 📖 БИБЛИЯ ПРОЕКТА: CONTENT.JS (v2.9.8 - DRAGGABLE COMPACT UI & TAB ROUTING)
 */

let myTabId = sessionStorage.getItem('vc_tab_id');
if (!myTabId) {
    myTabId = 'TAB-' + Math.random().toString(36).substring(2, 6).toUpperCase();
    sessionStorage.setItem('vc_tab_id', myTabId);
}
let myTabName = localStorage.getItem(`vc_name_${myTabId}`) || myTabId;

setInterval(() => {
    fetch('http://localhost:5070/ping', {
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
    
    // Добавили иконку перетаскивания (⠿)
    badge.innerHTML = `
        <div style="display: flex; align-items: center; width: 100%;">
            <span id="vibe-drag-handle" style="margin-right: 8px; opacity: 0.5; font-size: 16px;" title="Потяните, чтобы переместить">⠿</span>
            🤖 <b>VibeCoder:</b> 
            <span id="vibe-tab-name" style="cursor:pointer; border-bottom: 1px dashed #888; margin-left: 5px; margin-right: 8px;" title="Кликните, чтобы переименовать вкладку">${myTabName}</span>
            <span id="vibe-status" style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #3c3c3c; color: #fff; font-weight: bold;">⏳ Загрузка...</span>
        </div>
    `;
    
    // Пытаемся достать сохраненную позицию, либо ставим по умолчанию слева внизу
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

    // --- ЛОГИКА ПЕРЕТАСКИВАНИЯ ---
    let isDragging = false;
    let hasMoved = false;
    let offsetX, offsetY;

    badge.onmousedown = function(e) {
        // Если кликнули на имя для переименования - не тащим
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
                
                // Защита: не даем утащить плашку за пределы экрана
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
            
            // Если плашку таскали, сохраняем её новые координаты
            if (hasMoved) {
                localStorage.setItem('vc_badge_left', badge.style.left);
                localStorage.setItem('vc_badge_top', badge.style.top);
            }
        };
    };

    badge.onmouseover = () => badge.style.backgroundColor = 'rgba(14, 99, 156, 0.9)';
    badge.onmouseout = () => badge.style.backgroundColor = 'rgba(30, 30, 30, 0.85)';

    // Логика переименования
    badge.querySelector('#vibe-tab-name').onclick = (e) => {
        if (hasMoved) return; // Блокируем клик, если это было перетаскивание
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

// Обновление статуса
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
    if (isLimitReached) {
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
    isLimitReached = true;
    updatePanelUI(isSystemPaused, false);
    try { 
        await fetchPostProxy(`${SERVER_URL}/api/limit_reached`, JSON.stringify({source_id: myTabId})); 
    } catch (e) {}
}

async function checkGeminiAlerts() {
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
    const buttons = Array.from(document.querySelectorAll('button'));
    const modelBtn = buttons.find(b => {
        const t = b.innerText.trim();
        return (t.includes('Fast') || t.includes('Flash') || t.includes('Thinking') || t.includes('Pro') || t.includes('Advanced')) && t.length < 30;
    });
    if (modelBtn && !modelBtn.innerText.includes('Pro') && !modelBtn.innerText.includes('Advanced')) {
        modelBtn.click(); 
        await new Promise(r => setTimeout(r, 800));
        const items = Array.from(document.querySelectorAll('menu-item, [role="menuitem"], li'));
        const pro = items.find(i => i.innerText.includes('Pro') || i.innerText.includes('Advanced'));
        if (pro) {
            if (pro.innerText.includes('Upgrade')) { await triggerLimitReached("Требуется подписка"); return false; }
            pro.click(); 
            await new Promise(r => setTimeout(r, 1000)); 
            return true;
        }
    }
    return true;
}

async function checkServer() {
    if (isProcessing) return; 
    try {
        const stateRes = await fetchGetProxy(`${SERVER_URL}/api/system_state`);
        isSystemPaused = stateRes.is_paused;
        updatePanelUI(isSystemPaused, false);

        if (isLimitReached || isSystemPaused) return;
        if (await checkGeminiAlerts()) return;

        let taskUrl = `${SERVER_URL}/api/get_task?target_id=${encodeURIComponent(myTabId)}`;
        if (activeTaskId) taskUrl += `&current_task=${activeTaskId}`;
        
        const task = await fetchGetProxy(taskUrl);
        lastServerState = task.state;
        updatePanelUI(isSystemPaused, false);

        if (task.state === "RUNNING") {
            if (task.prompt) {
                activeTaskId = task.task_id;
                isProcessing = true;
                if (task.is_relay) {
                    resetChat();
                    await new Promise(r => setTimeout(r, 2000));
                }
                lastProcessedText = ""; currentCandidateText = ""; stableCount = 0;
                await sendToGemini(task.prompt);
                return;
            }

            const generatingElements = document.querySelectorAll(['button[aria-label*="Stop generating"]', 'button[aria-label*="Остановить"]', '.gmat-mdc-progress-spinner', 'mat-spinner'].join(', '));
            let isGenerating = false;
            for (let el of generatingElements) { if (el.offsetWidth > 0 || el.offsetHeight > 0) { isGenerating = true; break; } }
            if (isGenerating) { stableCount = 0; return; }

            const modelResponses = document.querySelectorAll(['message-content', '.model-response-text', '[data-message-author-role="model"]'].join(', '));
            if (modelResponses.length > 0) {
                const lastResponse = modelResponses[modelResponses.length - 1];
                let text = lastResponse.innerText || lastResponse.textContent;
                if (text && text.trim() !== "") {
                    if (text !== currentCandidateText) { currentCandidateText = text; stableCount = 0; } 
                    else if (text !== lastProcessedText) { stableCount++; }

                    if (stableCount >= 2) {
                        isProcessing = true;
                        lastProcessedText = currentCandidateText;
                        const payloadString = JSON.stringify({ task_id: activeTaskId, result: currentCandidateText, source_id: myTabId });
                        try {
                            await fetchPostProxy(`${SERVER_URL}/api/submit_result`, payloadString);
                        } catch (err) {} finally {
                            isProcessing = false; stableCount = 0; activeTaskId = null;
                        }
                    }
                }
            }
        }
    } catch (e) {
        lastServerState = "STOPPED";
        updatePanelUI(isSystemPaused, true);
    }
}

async function sendToGemini(text) {
    if (!await ensureProMode()) { isProcessing = false; return; }
    const inputArea = document.querySelector('rich-textarea > div, div[contenteditable="true"][role="textbox"], textarea#prompt-textarea');
    if (!inputArea) { isProcessing = false; return; }
    
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

        if (sendBtn) sendBtn.click();
        setTimeout(() => { isProcessing = false; stableCount = 0; }, 2000);
    }, 500);
}

setInterval(checkServer, 3000);