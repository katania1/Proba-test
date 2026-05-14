/**
 * src/content.js
 * Точка входа (Оркестратор). 
 * Связывает модули воедино и управляет главным циклом checkServer.
 */

import { getState, setState } from './appState.js';
import { fetchGetProxy, fetchPostProxy, startHeartbeat, sendLog } from './network.js';
import { initUI } from './ui.js';
import { startDetectorWhenReady, checkIsGenerating } from './radar.js';
import { transition, resetFsm, getFsmElapsed } from './fsm.js';
import { checkGeminiAlerts, sendToGemini } from './gemini.js';
import { getLastModelText } from './domUtils.js';

// ==========================================================
// 1. ИНИЦИАЛИЗАЦИЯ
// ==========================================================
initUI();
startHeartbeat();

// Слушатель для принудительного захвата ответа (твоя идея с кнопкой)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "force_fetch") {
        console.log("VibeCoder: Принудительный захват ответа по команде из IDE...");
        sendLog("📥 Ручной перехват активирован. Извлекаю текст...", "#bb86fc");
        setState({ stableCount: 0, currentCandidateText: "" });
        transition('READING');
        sendResponse({ success: true });
    }
});

if (document.readyState === 'complete') {
    setTimeout(startDetectorWhenReady, 1500);
} else {
    window.addEventListener('load', () => setTimeout(startDetectorWhenReady, 1500));
}

// ==========================================================
// 2. ГЛАВНЫЙ ЦИКЛ ОРКЕСТРАТОРА
// ==========================================================
async function checkServer() {
    const state = getState();

    // 🔥 УВЕЛИЧЕННЫЙ ПРЕДОХРАНИТЕЛЬ (Failsafe)
    // Если ИИ долго "думает" над тяжелым контекстом (например, RAG), 
    // даем ему 60 секунд вместо 20, прежде чем сбросить сессию.
    if (state.fsmState !== 'IDLE' && getFsmElapsed() > 60000) {
        sendLog(`⏰ Превышено время ожидания (60с). Сброс.`, '#ff4444');
        resetFsm();
        return;
    }

    try {
        switch (state.fsmState) {
            case 'IDLE': {
                const sessionParam = state.knownServerSessionId ? `&session_id=${encodeURIComponent(state.knownServerSessionId)}` : '';
                const data = await fetchGetProxy(`${state.serverUrl}/get_task?target_id=${encodeURIComponent(state.tabId)}${sessionParam}`);
                
                let currentState = getState(); 

                if (data && data.status) {
                    if (data.server_session_id && currentState.knownServerSessionId && data.server_session_id !== currentState.knownServerSessionId) {
                        setState({ knownServerSessionId: data.server_session_id });
                        resetFsm();
                        return;
                    }

                    if (data.server_session_id && !currentState.knownServerSessionId) {
                        setState({ knownServerSessionId: data.server_session_id });
                    }

                    if (data.status === "success" && data.task) {
                        setState({ processingStartTime: Date.now() });
                        
                        if (data.task.prompt === "___RADAR_MODE___") {
                            const snapshot = getLastModelText();
                            setState({
                                activeTaskId: "manual_drag_task_" + Date.now(),
                                isProcessing: true,
                                isRadarMode: true,
                                fsmSnapshotBeforeSend: snapshot,
                                textBeforeSend: snapshot,
                                waitStartTime: Date.now()
                            });
                            transition('WAITING_BUBBLE');
                            sendLog("📡 Радар на связи! Жду вашего нажатия Enter...", "#bb86fc");
                            return;
                        } else {
                            setState({
                                activeTaskId: data.task.id,
                                isProcessing: true,
                                isRadarMode: false
                            });
                            
                            if (!transition('INJECTING')) return;
                            
                            setState({ fsmSnapshotBeforeSend: getLastModelText() });
                            await sendToGemini(data.task.prompt, data.task.images);
                            transition('WAITING_BUBBLE');
                            return;
                        }
                    }
                }

                if (checkIsGenerating()) {
                    setState({
                        processingStartTime: Date.now(),
                        activeTaskId: "manual_drag_task_" + Date.now(),
                        isProcessing: true,
                        isRadarMode: false,
                        currentCandidateText: "",
                        stableCount: 0
                    });
                    transition('READING');
                    sendLog("📡 Засечена внезапная ручная генерация! Начинаем перехват ответа...", "#bb86fc");
                    return;
                }
                break;
            }

            case 'WAITING_BUBBLE': {
                const currentText = getLastModelText();
                // Если текст изменился — значит пузырь ответа появился или начал наполняться
                if (currentText !== state.fsmSnapshotBeforeSend && currentText !== state.textBeforeSend) {
                    setState({ stableCount: 0, currentCandidateText: "" });
                    sendLog("📡 Генерация пошла! Перехватываю ответ...", "#bb86fc");
                    transition('READING');
                }
                break;
            }

            case 'READING': {
                checkGeminiAlerts().catch(() => {});

                const isGen = checkIsGenerating();
                const currentText = getLastModelText();
                const diffText = currentText.replace(/Thinking for \d+s/gi, '').trim();

                if (isGen) {
                    setState({ stableCount: 0, currentCandidateText: diffText });
                    setState({ fsmState: getState().fsmState }); 
                    return;
                }

                // ЗАЩИТА ОТ ПУСТОГО ПУЗЫРЯ (Чтение файлов)
                if (diffText === "" && getFsmElapsed() < 45000) { // Ждем до 45 сек при пустом ответе
                    setState({ stableCount: 0 });
                    setState({ fsmState: getState().fsmState }); 
                    return;
                }

                let newStableCount = state.stableCount;
                if (diffText !== state.currentCandidateText) {
                    setState({ currentCandidateText: diffText, stableCount: 0 });
                    newStableCount = 0;
                } else {
                    newStableCount++;
                    setState({ stableCount: newStableCount });
                }

                if (newStableCount >= 2 && state.activeTaskId) {
                    if (transition('POSTING')) {
                        setState({ isProcessing: true });
                        try {
                            sendLog("📤 Чтение завершено, отправляю текст в IDE...", "#31a24c");
                            await fetchPostProxy(`${state.serverUrl}/post_result`, JSON.stringify({
                                task_id: state.activeTaskId, result: currentText, source_id: state.tabId
                            }));
                        } catch (err) {
                            console.error('VibeCoder: Ошибка отправки результата:', err);
                        } finally {
                            resetFsm();
                        }
                    }
                } else {
                    setState({ fsmState: getState().fsmState }); 
                }
                break;
            }

            case 'POSTING': {
                break;
            }
        }
    } catch (e) {
        console.error("VibeCoder: Критическая ошибка в checkServer:", e);
        resetFsm();
    }
}

setInterval(checkServer, 1000);