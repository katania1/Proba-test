/*
📖 БИБЛИЯ ПРОЕКТА: BACKGROUND.JS (v3.5 - UNIVERSAL PROXY)
-----------------------------------------------------------------------
1. РОЛЬ: Универсальный прокси-мост (Service Worker) между content.js (вкладка Gemini) 
   и локальным сервером Python (порт 5050).
2. ОБХОД CORS: Принимает команды proxy_get и proxy_post, выполняя запросы 
   от своего имени для обхода строгих политик безопасности (CSP) на сайте Gemini.
3. СИНХРОНИЗАЦИЯ: Устраняет проблему рассинхрона версий, обеспечивая 
   динамическую передачу любых URL и Body от контент-скрипта к серверу.
-----------------------------------------------------------------------
*/

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    
    // 1. Универсальный GET-прокси
    if (request.action === "proxy_get") {
        fetch(request.url, { method: "GET", mode: "cors" })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            })
            .then(data => sendResponse({ success: true, data: data }))
            .catch(err => sendResponse({ success: false, error: err.toString() }));
        
        return true; // Асинхронный ответ
    }
    
    // 2. Универсальный POST-прокси
    if (request.action === "proxy_post") {
        fetch(request.url, {
            method: "POST",
            mode: "cors",
            headers: { "Content-Type": "application/json" },
            body: request.body
        })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                return res.json();
            })
            .then(data => sendResponse({ success: true, data: data }))
            .catch(err => sendResponse({ success: false, error: err.toString() }));
            
        return true;
    }

});