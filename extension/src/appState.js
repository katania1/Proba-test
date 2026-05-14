/**
 * src/store/appState.js
 * Единый источник истины (State Store) для VibeCoder.
 * Реализует паттерн Pub/Sub для реактивного обновления без использования window.
 */

function generateTabId() {
    const id = 'TAB-' + Math.random().toString(36).substring(2, 6).toUpperCase();
    sessionStorage.setItem('vc_tab_id', id);
    return id;
}

const initialTabId = sessionStorage.getItem('vc_tab_id') || generateTabId();

const state = {
    // Сеть
    serverUrl: "http://localhost:5070",
    
    // Идентификация вкладки
    tabId: initialTabId,
    tabName: localStorage.getItem(`vc_name_${initialTabId}`) || initialTabId,
    knownServerSessionId: null,

    // Глобальные флаги
    ignoreLimitsSession: false,
    isLimitReached: false,
    isRadarMode: false,

    // Состояние задач и тайминги
    isProcessing: false,
    activeTaskId: null,
    processingStartTime: 0,
    
    // Чтение и перехват текста
    textBeforeSend: "",
    currentCandidateText: "",
    stableCount: 0,
    waitStartTime: 0,

    // Состояние Конечного Автомата (FSM)
    fsmState: 'IDLE',
    fsmEnteredAt: Date.now(),
    fsmSnapshotBeforeSend: ''
};

const listeners = new Map();

/**
 * Возвращает замороженную копию состояния (защита от прямых мутаций).
 */
export function getState() {
    return Object.freeze({ ...state });
}

/**
 * Обновляет состояние и уведомляет подписчиков только об измененных полях.
 */
export function setState(patch) {
    const changed = [];

    for (const [key, value] of Object.entries(patch)) {
        if (state[key] !== value) {
            state[key] = value;
            changed.push(key);
        }
    }

    for (const key of changed) {
        listeners.get(key)?.forEach(cb => cb(state[key], key));
    }
}

/**
 * Подписка на изменение конкретного ключа в store.
 * Возвращает функцию для отписки.
 */
export function subscribe(key, callback) {
    if (!listeners.has(key)) listeners.set(key, new Set());
    listeners.get(key).add(callback);
    return () => listeners.get(key).delete(callback);
}