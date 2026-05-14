/**
 * src/domUtils.js
 * Работа с DOM-деревом Gemini: очистка полей ввода, чанкированная вставка текста,
 * загрузка прикрепленных файлов и реверс-инжиниринг Markdown из ответов ИИ.
 */

import { getState, setState } from './appState.js';
import { sendLog } from './network.js';

// ==========================================================
// 1. БЕЗОПАСНАЯ ОЧИСТКА DOM
// ==========================================================
export function clearContentEditable(el) {
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
// 2. ПЛАВНЫЙ ИНЖЕКТОР (ANTI-FREEZE ДЛЯ PROSEMIRROR)
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

export async function insertLargeTextChunked(inputArea, text) {
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

    setState({ fsmState: getState().fsmState }); 
    sendLog('✅ Вставка контекста успешно завершена.', '#31a24c');
    el.focus();
}

// ==========================================================
// 3. УТИЛИТЫ ФАЙЛОВ И МАРКДАУНА
// ==========================================================
function base64ToFile(b64, mime, filename) {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    return new File([bytes], filename, { type: mime });
}

export async function uploadFiles(filesPayload, inputArea) {
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

export function getLastModelText() {
    // 🔥 ШАГ 1: Ищем строго контейнер с чистым текстом и кодом (message-content).
    // Мы БОЛЬШЕ НЕ ПОДНИМАЕМСЯ наверх, чтобы не захватить "Gemini said" и "Thoughts".
    const textNodes = Array.from(document.querySelectorAll('message-content, .markdown-main-panel, .response-text'))
        .filter(el => !el.closest('user-query, [data-message-author-role="user"]'));
    
    if (textNodes.length === 0) return "";
    
    // Берем самый последний актуальный текстовый блок
    const originalNode = textNodes[textNodes.length - 1];
    const clone = originalNode.cloneNode(true);
    
    // 🔥 ШАГ 2: Контрольная зачистка системных артефактов
    const junkSelectors = [
        'button', 
        'mat-icon', 
        '.cdk-visually-hidden', // Убирает текст для слепых
        '.visually-hidden',
        'tool-call-details',
        '.speech-button-container'
    ];
    clone.querySelectorAll(junkSelectors.join(', ')).forEach(el => el.remove());

    // 🔥 ШАГ 3: Реверс-инжиниринг Markdown (Код и языки)
    const preTags = Array.from(clone.querySelectorAll('pre'));
    const bTick = String.fromCharCode(96) + String.fromCharCode(96) + String.fromCharCode(96);
    
    preTags.forEach(pre => {
        let lang = "";
        const wrapper = pre.closest('code-block, .code-block, [data-test-id*="code-block"]') || pre;
        
        if (wrapper !== pre) {
            // Ищем заголовок языка по новому DOM-дереву (span внутри .code-block-decoration)
            const header = wrapper.querySelector('.code-block-header, .language-name, .code-block-decoration span:first-child, span:first-child');
            if (header) {
                lang = (header.innerText || header.textContent || "").trim().split(/\s+/)[0];
                if (lang.toLowerCase().includes('copy') || lang.toLowerCase().includes('копировать')) lang = "";
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