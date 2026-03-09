let recorder;
let audioChunks = [];

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

// ------------------- LOGIN -------------------
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
    } else {
        loginStatus.innerText = "Login failed";
    }
};

// ------------------- FETCH WITH JWT -------------------
async function fetchWithAuth(url, options = {}) {
    let token = tokenAccess;
    options.headers = options.headers || {};
    options.headers["Authorization"] = "Bearer " + token;

    let response = await fetch(url, options);

    if (response.status === 401) {
        // try refresh token
        if (!tokenRefresh) throw new Error("Login required");

        const refreshResp = await fetch("/api/token/refresh/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh: tokenRefresh })
        });
        const refreshData = await refreshResp.json();
        tokenAccess = refreshData.access;
        localStorage.setItem("jwt_access", tokenAccess);

        // retry original request
        options.headers["Authorization"] = "Bearer " + tokenAccess;
        response = await fetch(url, options);
    }

    return response;
}

// ------------------- RECORD VOICE -------------------
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

    recorder.ondataavailable = e => {
        audioChunks.push(e.data);
    };

    recorder.onstop = async () => {
        const blob = new Blob(audioChunks, { type: "audio/wav" });
        audioChunks = [];

        const formData = new FormData();
        formData.append("audio_file", blob, "voice.wav");

        try {
            const response = await fetchWithAuth("/api/assistant/voice/", {
                method: "POST",
                body: formData
            });

            const data = await response.json();
            console.log(data);

            transcriptEl.innerText = data.transcript;
            responseEl.innerText = data.response;
            status.innerText = "Click microphone to speak";

            speak(data.response);
        } catch (error) {
            status.innerText = "Server error or unauthorized";
            console.error(error);
        }
    };
};

// ------------------- TEXT TO SPEECH -------------------
function speak(text) {
    const speech = new SpeechSynthesisUtterance(text);
    speech.rate = 1;
    speech.pitch = 1;
    speechSynthesis.speak(text);
}