/**
 * src/fsm.js
 * Строгий Конечный Автомат (FSM) для управления стадиями инъекции и генерации.
 * Ничего не знает про DOM или UI. Только чистая логика переходов.
 */

// Импортируем стейт из соседнего файла в этой же папке
import { getState, setState } from './appState.js';

// Таблица разрешенных переходов (защита от петель и непредсказуемого поведения)
const TRANSITIONS = {
    IDLE:           ['INJECTING', 'WAITING_BUBBLE', 'READING'], 
    INJECTING:      ['WAITING_BUBBLE', 'IDLE'], 
    WAITING_BUBBLE: ['READING', 'IDLE'],        
    READING:        ['POSTING', 'READING', 'IDLE'],
    POSTING:        ['IDLE']
};

/**
 * Пытается перевести FSM в новое состояние.
 * Возвращает true при успехе, false при запрещенном переходе.
 */
export function transition(newState) {
    const { fsmState: currentState } = getState();
    const allowed = TRANSITIONS[currentState];

    if (!allowed?.includes(newState)) {
        console.warn(`[FSM] Запрещенный переход: ${currentState} → ${newState}. Игнорирую.`);
        return false;
    }

    console.log(`[FSM] ${currentState} → ${newState}`);
    
    // Мутируем стейт. UI автоматически обновится, так как он подпишется на fsmState!
    setState({ 
        fsmState: newState,
        fsmEnteredAt: Date.now()
    });
    
    return true;
}

/**
 * Жесткий сброс автомата (Failsafe).
 * Используется при таймаутах, перезапуске бэкенда или ручном сбросе.
 */
export function resetFsm(taskId = null) {
    console.log(`[FSM] Сброс автомата в IDLE. TaskID: ${taskId}`);
    setState({
        fsmState: 'IDLE',
        activeTaskId: taskId,
        fsmEnteredAt: Date.now(),
        fsmSnapshotBeforeSend: '',
        isProcessing: false,
        isRadarMode: false
    });
}

/**
 * Возвращает время (в мс), проведенное в текущем состоянии (для проверки таймаутов).
 */
export function getFsmElapsed() {
    return Date.now() - getState().fsmEnteredAt;
}