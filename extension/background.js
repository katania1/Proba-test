/*
📖 БИБЛИЯ ПРОЕКТА: BACKGROUND.JS (v3.6 - BIG DATA PROXY)
-----------------------------------------------------------------------
1. РОЛЬ: Универсальный прокси-мост (Service Worker) между content.js (вкладка Gemini) 
   и локальным сервером Python (порт 5070).
2. ОБХОД CORS: Принимает команды proxy_get и proxy_post, выполняя запросы 
   от своего имени для обхода строгих политик безопасности (CSP) на сайте Gemini.
3. ПОДДЕРЖКА БОЛЬШИХ ДАННЫХ: Оптимизировано для передачи объемных Base64 
   строк (файлов кода, RAG-контекста и картинок) без обрезки payload'а.
-----------------------------------------------------------------------
*/

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    
    // 1. Универсальный GET-прокси (Получение задач от оркестратора)
    if (request.action === "proxy_get") {
        fetch(request.url, { 
            method: "GET", 
            mode: "cors",
            cache: "no-store"
        })
        .then(res => {
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            return res.json();
        })
        .then(data => sendResponse({ success: true, data: data }))
        .catch(err => sendResponse({ success: false, error: err.toString() }));
        
        return true; // Указывает Chrome, что sendResponse будет вызван асинхронно
    }
    
    // 2. Универсальный POST-прокси (Отправка ответов ИИ на сервер VibeCoder)
    if (request.action === "proxy_post") {
        fetch(request.url, {
            method: "POST",
            mode: "cors",
            headers: { 
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            body: request.body
        })
        .then(res => {
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            return res.json();
        })
        .then(data => sendResponse({ success: true, data: data }))
        .catch(err => sendResponse({ success: false, error: err.toString() }));

        return true; // Указывает Chrome, что sendResponse будет вызван асинхронно
    }
});