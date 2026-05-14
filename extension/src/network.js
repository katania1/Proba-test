/**
 * src/network.js
 * Сетевой слой. Отвечает за проксирование запросов через background.js
 * (для обхода CORS) и поддержание пульса (heartbeat) с локальным сервером.
 */

import { getState, setState } from './appState.js';

/**
 * GET-запрос через Service Worker (background.js)
 */
export function fetchGetProxy(url) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: "proxy_get", url }, (response) => {
            if (response && response.success) resolve(response.data);
            else reject("proxy_get error");
        });
    });
}

/**
 * POST-запрос через Service Worker (background.js)
 */
export function fetchPostProxy(url, bodyText) {
    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: "proxy_post", url, body: bodyText }, (response) => {
            if (response && response.success) resolve(response.data);
            else reject("proxy_post error");
        });
    });
}

/**
 * Отправка логов в системный чат IDE
 */
export function sendLog(message, color = "#aaaaaa") {
    const { serverUrl, tabId } = getState();
    fetchPostProxy(`${serverUrl}/log`, JSON.stringify({
        source_id: tabId, message, color
    })).catch(() => {});
}

/**
 * Запуск фонового пульса (Heartbeat).
 * Сообщает IDE, что вкладка жива, и синхронизирует ID серверной сессии.
 */
export function startHeartbeat() {
    setInterval(() => {
        const { serverUrl, tabId, tabName, knownServerSessionId } = getState();
        
        fetch(`${serverUrl}/heartbeat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tab_id: tabId, tab_name: tabName })
        })
        .then(resp => resp.json())
        .then(data => {
            if (data && data.server_session_id) {
                // Если мы еще не знаем сессию бэкенда — запоминаем её
                if (!knownServerSessionId) {
                    setState({ knownServerSessionId: data.server_session_id });
                }
            }
        })
        .catch(() => {
            // Игнорируем ошибки сети (сервер IDE может быть выключен)
        });
    }, 2000);
}