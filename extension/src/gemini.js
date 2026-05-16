/**
 * src/gemini.js
 * Специфичная логика для сайта Gemini: проверка лимитов,
 * принудительное включение Pro-модели и программное нажатие кнопок отправки.
 */

import { getState, setState } from './appState.js';
import { resetFsm } from './fsm.js';
import { fetchPostProxy, sendLog } from './network.js';
import { insertLargeTextChunked, uploadFiles, getLastModelText } from './domUtils.js';

// ==========================================================
// 1. УПРАВЛЕНИЕ ЧАТОМ И ЛИМИТАМИ
// ==========================================================

export function resetChat() {
    const newChatBtn = document.querySelector(
        'a[data-test-id="new-chat-button"], a[href^="/app"], button[aria-label*="New chat" i], button[aria-label*="Новый чат" i]'
    );
    if (newChatBtn) newChatBtn.click();
    else window.location.href = "https://gemini.google.com/app";
}

export async function triggerLimitReached(reason) {
    const { isLimitReached, tabId, serverUrl } = getState();
    if (isLimitReached) return;
    
    console.warn(`VibeCoder: Лимит. Причина: ${reason}`);
    
    // Реактивно меняем статус (плашка покраснеет сама)
    setState({ isLimitReached: true }); 
    
    fetchPostProxy(`${serverUrl}/limit_reached`, JSON.stringify({ source_id: tabId }))
        .catch(() => {});
}

export async function checkGeminiAlerts() {
    const { ignoreLimitsSession } = getState();
    if (ignoreLimitsSession) return false;
    
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

export async function ensureProMode() {
    const { ignoreLimitsSession } = getState();
    if (ignoreLimitsSession) return true;

    const modelSelector = document.querySelector(
        '[data-test-id="bard-mode-menu-button"], button.input-area-switch'
    );
    if (!modelSelector) return true;

    const currentText = (modelSelector.innerText || modelSelector.textContent || "").toLowerCase().trim();
    
    // Anti-Thinking Selector (выбираем Pro, но без принудительного Thinking)
    if ((currentText.includes('pro') || currentText.includes('advanced')) && !currentText.includes('thinking')) {
        return true;
    }

    modelSelector.click();
    
    // Динамическое ожидание отрисовки элементов меню в оверлее (до 2.5 секунд)
    let overlay = null;
    let menuItems = [];
    let attempts = 0;
    while (attempts < 16) {
        await new Promise(r => setTimeout(r, 150));
        overlay = document.querySelector('.cdk-overlay-container') || document.body;
        menuItems = Array.from(overlay.querySelectorAll(
            '[role="menuitem"], [role="option"], [role="menuitemradio"], button.mat-mdc-menu-item, .mat-mdc-menu-item, button[mat-menu-item], [data-test-id*="mode"], [data-test-id*="model"]'
        ));
        if (menuItems.length > 0) break;
        attempts++;
    }

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
                    if (!overlayEl.querySelector('[role="menuitem"], button.mat-mdc-menu-item')) {
                        observer.disconnect(); resolve();
                    }
                });
                observer.observe(overlayEl, { childList: true, subtree: true });
                setTimeout(() => { observer.disconnect(); resolve(); }, 1000);
            });
        }
        return true;
    }

    // Ликвидация тихого сбоя: закрываем меню, отправляем предупреждение и блокируем отправку не туда
    document.body.click();
    sendLog('Не удалось найти переключатель на Pro/Advanced модель в меню.', '#ffaa00');
    return false;
}

// ==========================================================
// 2. ГЛАВНАЯ ФУНКЦИЯ ОТПРАВКИ
// ==========================================================

export async function sendToGemini(text, filesPayload = []) {
    if (!await ensureProMode()) {
        resetFsm();
        return;
    }

    const inputArea = document.querySelector(
        'rich-textarea > div, div[contenteditable="true"][role="textbox"], textarea#prompt-textarea'
    );
    
    if (!inputArea) { 
        resetFsm(); 
        return; 
    }

    if (filesPayload && filesPayload.length > 0) {
        await uploadFiles(filesPayload, inputArea);
    }

    await insertLargeTextChunked(inputArea, text);

    const fieldSnapshot = (inputArea.innerText || inputArea.value || '').substring(0, 200);
    if (!fieldSnapshot.trim()) {
        sendLog('Поле ввода пустое перед отправкой. Задача не выполнена.', '#ff4444');
        resetFsm();
        return;
    }

    // Сохраняем слепок текста ПЕРЕД генерацией, чтобы детектор понял, когда пойдет новый ответ
    setState({
        textBeforeSend: getLastModelText(),
        waitStartTime: Date.now()
    });

    const sendStart = Date.now();
    let sent = false;

    // Агрессивный поиск кнопки "Отправить" в течение 5 секунд
    while (Date.now() - sendStart < 5000) {
        const sendBtn = Array.from(document.querySelectorAll('button')).find(b => {
            const label = ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '')).toLowerCase();
            return (label.includes('send') || label.includes('отправить')) && !label.includes('feedback');
        }) || document.querySelector('[data-testid="send-button"], .send-button');

        if (sendBtn && !sendBtn.disabled && sendBtn.getAttribute('aria-disabled') !== 'true') {
            sendBtn.click();
            sent = true;
            break;
        }
        await new Promise(r => setTimeout(r, 150));
    }

    if (!sent) {
        const fallback = document.querySelector(
            '[data-testid="send-button"], .send-button, button[aria-label*="send" i], button[aria-label*="отправить" i]'
        );
        if (fallback) fallback.click();
        else {
            sendLog('Кнопка Send не найдена!', '#ff4444');
            resetFsm();
        }
    }
}