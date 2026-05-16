/**
 * src/radar.js
 * "Глаза" приложения. Следит за DOM-деревом Gemini, распознает 
 * спиннеры, скелетные загрузки и мутации текста. 
 * Управляет только флагом isGenerating в глобальном стейте.
 */

import { getState, setState } from './appState.js';

class GenerationDetector {
    constructor() {
        this.observer = null;
        this.isGenerating = false;
        this.lastMutationTime = 0;
        this.staleThreshold = 4000; // 🔥 4000мс защиты от фризов Gemini
        this._ticker = null;
        this.startupTime = Date.now(); // Фиксируем время старта детектора
        this.warmupDuration = 3000; // 🔥 3 секунды "слепой зоны" при инициализации
    }

    start() {
        this._observeLastBubble();
        
        // Тикер, который сбрасывает флаг генерации после 4 секунд тишины
        this._ticker = setInterval(() => {
            if (this.isGenerating) {
                const silence = Date.now() - this.lastMutationTime;
                if (silence > this.staleThreshold) {
                    this.isGenerating = false;
                    setState({ isGenerating: false }); // UI обновится автоматически
                }
            }
        }, 300);
    }

    _observeLastBubble() {
        if (this.observer) this.observer.disconnect();

        const container = document.querySelector(
            'response-container, .response-container, [data-response-index], chat-history, .conversation-container'
        );

        if (!container) {
            setTimeout(() => this._observeLastBubble(), 1000);
            return;
        }

        this.observer = new MutationObserver((mutations) => {
            const { fsmState } = getState();
            
            // Игнорируем мутации, пока мы сами вставляем текст
            if (fsmState === 'INJECTING') return;

            // 🔥 БЛОК ЗАЩИТЫ ОТ РАССИНХРОНА (Blind Spot)
            // Игнорируем любые мутации в первые 3 секунды после загрузки скрипта.
            // Это предотвращает ложное срабатывание на рендеринг старой истории при нажатии F5.
            if (Date.now() - this.startupTime < this.warmupDuration) {
                return;
            }

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
                setState({ isGenerating: true }); // Реактивно зажигаем индикатор
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
}

const generationDetector = new GenerationDetector();

/**
 * Ожидает готовности интерфейса Gemini и запускает детектор мутаций.
 */
export function startDetectorWhenReady() {
    const geminiReady = document.querySelector(
        'response-container, chat-history, .conversation-container, model-response'
    );
    if (geminiReady) {
        generationDetector.start();
    } else {
        setTimeout(startDetectorWhenReady, 800);
    }
}

/**
 * Бронебойная комплексная проверка состояния генерации (Мутации + Спиннеры + Пустые пузыри)
 */
export function checkIsGenerating() {
    // 1. Проверяем, видел ли мутации наш детектор
    if (generationDetector.check()) return true;

    const chatArea = document.querySelector('chat-window, .main-content, #chat-history, .conversation-container');
    if (!chatArea) return false;

    const activeResponses = chatArea.querySelectorAll('model-response, message-content');
    if (activeResponses.length > 0) {
        const last = activeResponses[activeResponses.length - 1];
        
        // Пропускаем завершенные блоки
        if (last.classList.contains('completed') || 
            last.hasAttribute('data-loading', 'false') ||
            last.closest('side-navigation-v2, mat-sidenav, .bots-list-container')) {
            return false;
        }

        // 2. Проверяем явные атрибуты загрузки Gemini
        if (last.hasAttribute('is-loading') || 
            last.getAttribute('data-loading') === 'true' || 
            last.classList.contains('is-loading')) {
            return true;
        }

        // 3. Ищем спиннеры и скелетные анимации (Thinking)
        const spinner = last.querySelector('mat-progress-spinner, .gmat-mdc-progress-spinner, mat-spinner, [class*="spinner"], [class*="loading"], [class*="Thinking"], [class*="skeleton"]');
        if (spinner) {
            const style = window.getComputedStyle(spinner);
            if (spinner.offsetWidth > 0 && spinner.offsetHeight > 0 &&
                style.display !== 'none' && style.opacity !== '0' && style.visibility !== 'hidden') {
                return true;
            }
        }
        
        // 4. ЗАЩИТА ОТ ПУСТОГО ПУЗЫРЯ (ИИ переваривает тяжелые файлы)
        if (!last.textContent.trim() && !last.querySelector('pre, code, p, span')) {
            return true; 
        }
    }
    return false;
}