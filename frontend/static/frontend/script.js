// frontend/static/frontend/script.js

document.addEventListener("DOMContentLoaded", () => {

    let recorder;
    let audioChunks = [];
    let reminderSeenIds = new Set();

    // Tokens
    let tokenAccess = localStorage.getItem("jwt_access");
    let tokenRefresh = localStorage.getItem("jwt_refresh");

    const recordBtn = document.getElementById("recordBtn");
    const status = document.getElementById("status");
    const transcriptEl = document.getElementById("transcript");
    const responseEl = document.getElementById("response");

    const loginBtn = document.getElementById("loginBtn");
    const usernameInput = document.getElementById("username");
    const passwordInput = document.getElementById("password");
    const loginStatus = document.getElementById("loginStatus");

    // Wake-word state
    const WAKE_WORD = "luna";
    let wakeRecognition;
    let wakeDetectionActive = false;

    // ------------------- LOGIN -------------------
    if (loginBtn) {
        loginBtn.onclick = async () => {
            const username = usernameInput.value;
            const password = passwordInput.value;

            const response = await fetch("/api/token/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (data.access && data.refresh) {
                tokenAccess = data.access;
                tokenRefresh = data.refresh;

                localStorage.setItem("jwt_access", tokenAccess);
                localStorage.setItem("jwt_refresh", tokenRefresh);

                loginStatus.innerText = "Login successful";
                status.innerText = `Logged in. Say "${WAKE_WORD}" to start listening.`;
            } else {
                loginStatus.innerText = "Login failed";
            }
        };
    }

    // ------------------- FETCH WITH JWT -------------------
    async function fetchWithAuth(url, options = {}) {
        if (!tokenAccess) throw new Error("Login required");
        options.headers = options.headers || {};
        options.headers["Authorization"] = "Bearer " + tokenAccess;

        let response = await fetch(url, options);

        if (response.status === 401) {
            if (!tokenRefresh) throw new Error("Login required");

            const refreshResp = await fetch("/api/token/refresh/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh: tokenRefresh })
            });
            const refreshData = await refreshResp.json();
            if (!refreshData.access) throw new Error("Session expired. Please login again.");

            tokenAccess = refreshData.access;
            localStorage.setItem("jwt_access", tokenAccess);

            options.headers["Authorization"] = "Bearer " + tokenAccess;
            response = await fetch(url, options);
        }

        return response;
    }

    async function processVoiceBlob(blob) {
        const formData = new FormData();
        formData.append("audio_file", blob, "voice.wav");

        const response = await fetchWithAuth("/api/assistant/voice/", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        transcriptEl.innerText = data.transcript || "";
        responseEl.innerText = data.response || "";

        if (data && data.response) {
            speak(data.response);
        }
    }

    // ------------------- RECORD VOICE -------------------
    if (recordBtn) {
        recordBtn.onclick = async () => {
            if (!tokenAccess) {
                alert("Please login first");
                return;
            }

            if (recordBtn.classList.contains("recording")) {
                recorder.stop();
                recordBtn.classList.remove("recording");
                status.innerText = "Processing...";
                return;
            }

            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            recorder = new MediaRecorder(stream);

            recorder.start();
            recordBtn.classList.add("recording");
            status.innerText = "Listening...";

            recorder.ondataavailable = (e) => {
                audioChunks.push(e.data);
            };

            recorder.onstop = async () => {
                const blob = new Blob(audioChunks, { type: "audio/wav" });
                audioChunks = [];

                try {
                    await processVoiceBlob(blob);
                    status.innerText = `Say "${WAKE_WORD}" or click microphone to speak again.`;
                } catch (error) {
                    status.innerText = "Server error or unauthorized";
                    console.error(error);
                }
            };
        };
    }

    // ------------------- WAKE WORD: "Luna" -------------------
    async function recordSingleCommand(seconds = 5) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const wakeRecorder = new MediaRecorder(stream);
        const chunks = [];

        return new Promise((resolve) => {
            wakeRecorder.ondataavailable = (event) => chunks.push(event.data);
            wakeRecorder.onstop = () => {
                stream.getTracks().forEach((track) => track.stop());
                resolve(new Blob(chunks, { type: "audio/wav" }));
            };

            wakeRecorder.start();
            setTimeout(() => wakeRecorder.stop(), seconds * 1000);
        });
    }

    function initWakeWordListener() {
        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!Recognition) {
            status.innerText = "Wake word is not supported in this browser. Use the microphone button.";
            return;
        }

        wakeRecognition = new Recognition();
        wakeRecognition.continuous = true;
        wakeRecognition.interimResults = false;
        wakeRecognition.lang = "en-US";

        wakeRecognition.onresult = async (event) => {
            const result = event.results[event.results.length - 1];
            const transcript = (result[0].transcript || "").trim().toLowerCase();

            if (!transcript.startsWith(WAKE_WORD)) return;
            if (!tokenAccess) {
                status.innerText = "Wake word detected, but please login first.";
                return;
            }

            status.innerText = "Wake word detected. Listening for your command...";

            try {
                const commandBlob = await recordSingleCommand(6);
                status.innerText = "Processing wake-word command...";
                await processVoiceBlob(commandBlob);
                status.innerText = `Done. Say "${WAKE_WORD}" for the next command.`;
            } catch (error) {
                status.innerText = "Could not process wake-word command.";
                console.error(error);
            }
        };

        wakeRecognition.onerror = (event) => {
            console.error("Wake word error:", event.error);
            status.innerText = "Wake-word listener had an issue, restarting...";
        };

        wakeRecognition.onend = () => {
            if (wakeDetectionActive) wakeRecognition.start();
        };

        wakeDetectionActive = true;
        wakeRecognition.start();
    }

    // ------------------- CHECK REMINDERS -------------------
    async function checkReminders() {
        if (!tokenAccess) return;
        try {
            const response = await fetchWithAuth("/api/reminders/due/");
            if (!response.ok) throw new Error(`Reminder poll failed: ${response.status}`);

            const reminders = await response.json();
            reminders.forEach((reminder) => {
                if (reminderSeenIds.has(reminder.id)) return;
                reminderSeenIds.add(reminder.id);
                alert(`Reminder: ${reminder.task} at ${reminder.date_time}`);

                const speech = new SpeechSynthesisUtterance(reminder.task);
                speech.rate = 1;
                speech.pitch = 1;
                speechSynthesis.speak(speech);
            });
        } catch (err) {
            console.error("Error checking reminders:", err);
        }
    }

    // ------------------- TEXT TO SPEECH -------------------
    function speak(text) {
        if (!text || typeof text !== "string") return;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1;
        utterance.pitch = 1;

        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    }

    // ------------------- INITIALIZATION -------------------
    initWakeWordListener();
    checkReminders();
    setInterval(checkReminders, 15000);
});