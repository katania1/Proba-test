/**
 * src/ui.js
 * Управление пользовательским интерфейсом (плашка VibeBadge).
 * Полностью реактивный компонент: обновляется сам при изменении appState.
 */

import { getState, setState, subscribe } from './appState.js';

/**
 * Создает и добавляет плашку на экран (с поддержкой перетаскивания)
 */
export function createVibeBadge() {
    if (document.getElementById('vibe-coder-badge')) return;
    
    const { tabName } = getState();
    const badge = document.createElement('div');
    badge.id = 'vibe-coder-badge';
    badge.innerHTML = `
        <div style="display:flex;align-items:center;width:100%;">
            <span id="vibe-drag-handle" style="margin-right:8px;opacity:0.5;font-size:16px;">⠿</span>
            🤖 <b>VibeCoder:</b>
            <span id="vibe-tab-name" style="cursor:pointer;border-bottom:1px dashed #888;margin-left:5px;margin-right:8px;">${tabName}</span>
            <span id="vibe-status" style="font-size:11px;padding:2px 6px;border-radius:4px;background:#3c3c3c;color:#fff;font-weight:bold;">⏳ Загрузка...</span>
        </div>
    `;
    
    Object.assign(badge.style, {
        position: 'fixed', left: '20px', top: (window.innerHeight - 60) + 'px',
        backgroundColor: 'rgba(30,30,30,0.85)', backdropFilter: 'blur(5px)',
        color: '#d4d4d4', padding: '8px 15px', borderRadius: '8px',
        border: '1px solid #569cd6', zIndex: '999999', cursor: 'grab', userSelect: 'none'
    });

    // Логика Drag & Drop для плашки
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

    // Переименование вкладки
    badge.addEventListener('click', (e) => {
        if (e.target.id !== 'vibe-tab-name') return;
        const currentName = getState().tabName;
        const newName = prompt('Имя вкладки:', currentName);
        if (newName && newName.trim()) {
            const finalName = newName.trim();
            localStorage.setItem(`vc_name_${getState().tabId}`, finalName);
            setState({ tabName: finalName });
            e.target.innerText = finalName;
        }
    });

    document.body.appendChild(badge);
}

/**
 * Отрисовка текущего статуса на плашке
 */
export function updatePanelUI() {
    const statusSpan = document.getElementById('vibe-status');
    if (!statusSpan) return;
    
    const { fsmState, isLimitReached, ignoreLimitsSession, isGenerating } = getState();

    // Защита от зависания плашки на "Вставка"
    if (fsmState === 'INJECTING' && statusSpan.innerText.includes('Вставка')) return;
    
    // Проверка лимитов
    if (isLimitReached && !ignoreLimitsSession) {
        statusSpan.innerText = '🛑 ЛИМИТЫ'; 
        statusSpan.style.background = '#ff4444'; 
        return;
    }
    
    // Отрисовка состояний FSM
    switch (fsmState) {
        case 'IDLE':
            statusSpan.innerText = '🟢 ГОТОВ'; 
            statusSpan.style.background = '#31a24c';
            break;
        case 'INJECTING':
            statusSpan.innerText = '⚡ ВСТАВКА...'; 
            statusSpan.style.background = '#bb86fc';
            break;
        case 'WAITING_BUBBLE':
            statusSpan.innerText = '⏳ ОЖИДАНИЕ'; 
            statusSpan.style.background = '#e6a822';
            break;
        case 'READING':
            statusSpan.innerText = isGenerating ? '⚡ ГЕНЕРАЦИЯ' : '🔍 ЧТЕНИЕ...';
            statusSpan.style.background = '#bb86fc';
            break;
        case 'POSTING':
            statusSpan.innerText = '📤 ОТПРАВКА'; 
            statusSpan.style.background = '#31a24c';
            break;
    }
}

/**
 * Инициализация интерфейса и подписка на реактивные обновления
 */
/**
 * Инициализация интерфейса и подписка на реактивные обновления
 */
export function initUI() {
    createVibeBadge();
    
    setTimeout(() => {
        createVibeBadge();
        updatePanelUI(); // Обновляем, если плашка создалась со второго раза
    }, 1500);

    // Подписка на реактивные обновления (сработают при изменениях)
    subscribe('fsmState', updatePanelUI);
    subscribe('isLimitReached', updatePanelUI);
    subscribe('isGenerating', updatePanelUI);

    // 🔥 ПЕРВИЧНЫЙ ПИНОК: принудительно рисуем начальное состояние (IDLE)
    updatePanelUI(); 
}