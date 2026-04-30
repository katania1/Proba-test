/**
 * 📖 БИБЛИЯ ПРОЕКТА: CONTENT.JS (v2.9.6 - CONTEXT MEMORY & RELAY)
 */

const SERVER_URL = "http://localhost:5070";
let isProcessing = false;
let lastProcessedText = "";
let currentCandidateText = "";
let stableCount = 0;
let lastServerState = "STOPPED";
let isSystemPaused = false;
let activeTaskId = null;
let isLimitReached = false;

// ==========================================
// ОБЩЕНИЕ С BACKGROUND.JS (ПРОКСИ)
// ==========================================
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

// ==========================================
// ИНТЕРФЕЙС УПРАВЛЕНИЯ И МОНИТОРИНГА
// ==========================================
function injectControlPanel() {
    if (document.getElementById('ai-community-panel')) return;

    const style = document.createElement('style');
    style.innerHTML = `
        @keyframes limit-pulse {
            0% { box-shadow: 0 0 0 0 rgba(255, 68, 68, 0.7); }
            70% { box-shadow: 0 0 0 15px rgba(255, 68, 68, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 68, 68, 0); }
        }
        .panel-limit-mode {
            animation: limit-pulse 1s infinite;
            border: 2px solid #ff4444 !important;
            background: #2a0000 !important;
        }
    `;
    document.head.appendChild(style);

    const panel = document.createElement('div');
    panel.id = 'ai-community-panel';
    panel.style.cssText = `
        position: fixed; top: 20px; right: 20px; z-index: 999999;
        background: #242526; color: #e4e6eb; padding: 12px 16px;
        border-radius: 8px; font-family: 'Segoe UI', Tahoma, sans-serif; font-size: 14px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5); display: flex; flex-direction: column; gap: 8px; 
        border: 1px solid #3e4042; min-width: 220px; transition: all 0.3s ease;
    `;
    panel.innerHTML = `
        <div style="font-weight: bold; border-bottom: 1px solid #3e4042; padding-bottom: 5px; color: #1877f2; display: flex; justify-content: space-between;">
            <span>🤖 VibeCoder</span><span style="font-size: 10px; color: #65676b;">v2.9.6</span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
            <div id="ai-community-status-dot" style="width: 12px; height: 12px; border-radius: 50%; background: #ccc; transition: 0.3s;"></div>
            <span id="ai-community-status-text" style="font-weight: bold;">Загрузка...</span>
        </div>
        <div id="ai-bridge-task" style="color: #b0b3b8; font-size: 12px; margin-top: 2px;">Нет задач</div>
    `;
    document.body.appendChild(panel);
}

function updatePanelUI(isPaused, serverDown = false) {
    const panel = document.getElementById('ai-community-panel');
    const dot = document.getElementById('ai-community-status-dot');
    const text = document.getElementById('ai-community-status-text');
    const taskText = document.getElementById('ai-bridge-task');
    if (!panel || !dot || !text || !taskText) return;

    taskText.innerText = activeTaskId ? `Задача: ${activeTaskId}` : "Нет активных задач";
    taskText.style.color = activeTaskId ? "#1877f2" : "#b0b3b8";

    if (serverDown) {
        dot.style.background = '#ff4444'; dot.style.boxShadow = '0 0 8px rgba(255,68,68,0.6)';
        text.innerText = "СЕРВЕР ОФФЛАЙН"; return;
    }

    if (isLimitReached) {
        panel.classList.add('panel-limit-mode');
        dot.style.background = '#ff4444'; dot.style.boxShadow = 'none';
        text.innerText = "🛑 ЛИМИТЫ"; text.style.color = "#ff4444";
        return;
    }

    dot.style.boxShadow = 'none'; text.style.color = "#e4e6eb";

    if (isPaused) {
        dot.style.background = '#ffaa00'; text.innerText = "ПАУЗА";
    } else {
        if (lastServerState === "RUNNING") {
            dot.style.background = '#bb86fc'; dot.style.boxShadow = '0 0 8px rgba(187,134,252,0.6)';
            text.innerText = "АКТИВНАЯ ГЕНЕРАЦИЯ";
        } else {
            dot.style.background = '#31a24c'; text.innerText = "СВОБОДЕН";
        }
    }
}

function resetChat() {
    const newChatBtn = document.querySelector('a[data-test-id="new-chat-button"], a[href^="/app"], button[aria-label*="New chat"], button[aria-label*="Новый чат"]');
    if (newChatBtn) newChatBtn.click();
    else window.location.href = "https://gemini.google.com/app";
}

// ==========================================
// ЗАЩИТА ОТ ЛИМИТОВ И КОНТРОЛЬ МОДЕЛИ
// ==========================================
async function triggerLimitReached(reason) {
    if (isLimitReached) return;
    isLimitReached = true;
    console.warn(`🛑 [VibeCoder] ЛИМИТЫ ДОСТИГНУТЫ: ${reason}`);
    updatePanelUI(isSystemPaused, false);
    
    try { 
        await fetchPostProxy(`${SERVER_URL}/api/limit_reached`, JSON.stringify({})); 
        console.log("[VibeCoder] Сервер уведомлен о лимитах. Задача возвращена в очередь.");
    } catch (e) {
        console.error("[VibeCoder] Ошибка при уведомлении сервера.", e);
    }
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
        console.log("[VibeCoder] Попытка переключиться на модель Pro/Advanced...");
        modelBtn.click(); 
        await new Promise(r => setTimeout(r, 800));
        
        const items = Array.from(document.querySelectorAll('menu-item, [role="menuitem"], li'));
        const pro = items.find(i => i.innerText.includes('Pro') || i.innerText.includes('Advanced'));
        
        if (pro) {
            if (pro.innerText.includes('Upgrade')) { 
                await triggerLimitReached("Требуется платная подписка (Upgrade)"); 
                return false; 
            }
            pro.click(); 
            await new Promise(r => setTimeout(r, 1000)); 
            return true;
        }
    }
    return true;
}

// ==========================================
// ГЛАВНЫЙ ЦИКЛ ОПРОСА
// ==========================================
async function checkServer() {
    if (isProcessing) return; 

    injectControlPanel();
    
    try {
        const stateRes = await fetchGetProxy(`${SERVER_URL}/api/system_state`);
        isSystemPaused = stateRes.is_paused;
        updatePanelUI(isSystemPaused, false);

        if (isLimitReached || isSystemPaused) return;
        if (await checkGeminiAlerts()) return;

        const taskUrl = `${SERVER_URL}/api/get_task` + (activeTaskId ? `?current_task=${activeTaskId}` : "");
        const task = await fetchGetProxy(taskUrl);
        
        lastServerState = task.state;
        updatePanelUI(isSystemPaused, false);

        if (task.state === "RUNNING") {
            
            if (task.prompt) {
                console.log(`[VibeCoder] 📥 Получена задача: ${task.task_id}`);
                activeTaskId = task.task_id;
                isProcessing = true;
                
                // --- ЛОГИКА ЭСТАФЕТЫ ---
                if (task.is_relay) {
                    console.log("[VibeCoder] 🔄 Запрос эстафеты! Открываем новый чат...");
                    resetChat();
                    await new Promise(r => setTimeout(r, 2000)); // Ждем загрузки нового чата
                }
                
                lastProcessedText = "";
                currentCandidateText = "";
                stableCount = 0;
                
                await sendToGemini(task.prompt);
                return;
            }

            const generatingElements = document.querySelectorAll([
                'button[aria-label*="Stop generating"]',
                'button[aria-label*="Остановить"]',
                'button[aria-label*="Stop response"]',
                'button[aria-label*="Отменить"]',
                '.gmat-mdc-progress-spinner',
                'mat-spinner', 
                'button[class*="stop-button"]'
            ].join(', '));

            let isGenerating = false;
            for (let el of generatingElements) {
                if (el.offsetWidth > 0 || el.offsetHeight > 0) {
                    isGenerating = true;
                    break;
                }
            }

            if (isGenerating) {
                console.log("⏳ Gemini работает... ждем.");
                stableCount = 0;
                return;
            }

            const modelResponses = document.querySelectorAll([
                'message-content', 
                '.model-response-text', 
                '[data-test-id="model-response"]', 
                '.agent-turn',
                '[data-message-author-role="model"]',
                '.markdown'
            ].join(', '));
            
            if (modelResponses.length > 0) {
                const lastResponse = modelResponses[modelResponses.length - 1];
                let text = lastResponse.innerText || lastResponse.textContent;
                
                if (text && text.trim() !== "") {
                    if (text !== currentCandidateText) {
                        currentCandidateText = text;
                        stableCount = 0;
                        console.log("📝 Текст обновляется...");
                    } else if (text !== lastProcessedText) {
                        stableCount++;
                        console.log(`⏱ Стабилизация: ${stableCount}/2`);
                    }

                    if (stableCount >= 2) {
                        console.log("📦 Текст стабилен! Отправка на сервер...");
                        isProcessing = true;
                        lastProcessedText = currentCandidateText;
                        
                        const payloadString = JSON.stringify({
                            task_id: activeTaskId,
                            result: currentCandidateText
                        });
                        
                        try {
                            await fetchPostProxy(`${SERVER_URL}/api/submit_result`, payloadString);
                            console.log("✅ Успешно отправлено!");
                        } catch (err) {
                            console.error("❌ Сервер отклонил ответ. Сбрасываем мост:", err);
                        } finally {
                            isProcessing = false;
                            stableCount = 0;
                            activeTaskId = null;
                            // ВОТ ЗДЕСЬ УДАЛЕН СБРОС ЧАТА (resetChat)
                        }
                    }
                }
            }
        }
    } catch (e) {
        if (lastServerState === "RUNNING") console.error("❌ Ошибка связи:", e);
        lastServerState = "STOPPED";
        updatePanelUI(isSystemPaused, true);
    }
}

async function sendToGemini(text) {
    if (!await ensureProMode()) { 
        isProcessing = false; 
        return; 
    }

    const inputArea = document.querySelector('rich-textarea > div, div[contenteditable="true"][role="textbox"], textarea#prompt-textarea');
    if (!inputArea) { 
        console.error("❌ Не найдено поле ввода Gemini!");
        isProcessing = false; 
        return; 
    }
    
    inputArea.focus();
    document.execCommand('insertText', false, text);
    
    inputArea.dispatchEvent(new Event('input', { bubbles: true }));
    inputArea.dispatchEvent(new Event('change', { bubbles: true }));
    
    setTimeout(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const sendBtn = buttons.find(b => {
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            const textContent = (b.innerText || '').toLowerCase();
            const combined = aria + " " + textContent;
            
            const isSend = combined.includes('send message') || combined.includes('отправить сообщение') || aria === 'send' || aria === 'отправить';
            const isNotFeedback = !combined.includes('feedback') && !combined.includes('отзыв');
            
            return isSend && isNotFeedback;
        }) || document.querySelector('[data-testid="send-button"], .send-button');

        if (sendBtn) {
            sendBtn.click();
            console.log("🚀 Промпт отправлен в Gemini!");
        } else {
            console.error("❌ Не найдена кнопка отправки!");
        }
        
        setTimeout(() => { 
            isProcessing = false; 
            stableCount = 0;
        }, 2000);
    }, 500);
}

console.log("🤖 VibeCoder Bridge v2.9.6 загружен!");
setInterval(checkServer, 3000);