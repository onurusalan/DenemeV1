const chatBox = document.getElementById("chat-box");
const answerInput = document.getElementById("answer-input");
const sendBtn = document.getElementById("send-btn");
const themeToggle = document.getElementById("theme-toggle");
const resetChatBtn = document.getElementById("reset-chat");
const downloadPdfBtn = document.getElementById("download-pdf");
const theme = document.body;

let lastAskedQuestion = "";
let currentQuestionType = "text";
let currentOptions = [];

// ✅ Sohbeti Yükle
function loadConversation() {
    fetch("/get_conversation")
        .then(response => response.json())
        .then(data => {
            chatBox.innerHTML = "";
            let lastQuestion = "";
            data.forEach(item => {
                if (item.question !== lastQuestion) {
                    console.log("Önceki Konuşmadan Gelen Soru:", item.question); // Debugging Log
                    addMessage(item.question, "bot-message");
                }
                addMessage(item.answer, "user-message");
                lastQuestion = item.question; // Son soruyu kaydet
            });

            // 🔹 Eğer önceki sohbet yoksa, yeni soru iste
            if (data.length === 0) {
                console.log("Önceki sohbet yok, yeni soru isteniyor.");
                askNextQuestion();
            }
        });
}

// ✅ Yeni Soru İste
function askNextQuestion() {
    fetch("/get_question")
        .then(response => response.json())
        .then(data => {
            console.log("Yeni Soru İstendi:", data.question); // Debugging Log

            if (data.question && data.question !== lastAskedQuestion) {
                renderQuestion(data);
                lastAskedQuestion = data.question; // 🔹 Son soruyu güncelle
            } else {
                console.log("Aynı soru tekrar gelmedi:", data.question);
            }
        });
}

// Soruya göre input render et
function renderQuestion(data) {
    addMessage(data.question, "bot-message");
    currentQuestionType = data.type;
    currentOptions = data.options || [];
    clearInputArea();

    if (data.type === "text") {
        answerInput.style.display = "block";
        sendBtn.style.display = "inline-block";
        answerInput.value = "";
        answerInput.focus();
    } else if (data.type === "radio") {
        renderOptions(currentOptions, false);
    } else if (data.type === "checkbox") {
        renderOptions(currentOptions, true);
    } else if (data.type === "dsm-yesno") {
        renderDSMYesNo(currentOptions);
    }
}

function clearInputArea() {
    answerInput.style.display = "none";
    sendBtn.style.display = "none";
    // Eski seçenek butonlarını temizle
    const old = document.getElementById("options-area");
    if (old) old.remove();
}

function renderOptions(options, isCheckbox) {
    clearInputArea();
    const optionsDiv = document.createElement("div");
    optionsDiv.id = "options-area";
    optionsDiv.style.marginTop = "16px";
    optionsDiv.style.display = "flex";
    optionsDiv.style.flexWrap = "wrap";
    optionsDiv.style.gap = "10px";
    let selected = [];
    options.forEach(option => {
        const btn = document.createElement("button");
        btn.innerText = option;
        btn.className = "btn option-btn";
        btn.onclick = () => {
            if (isCheckbox) {
                if (selected.includes(option)) {
                    selected = selected.filter(o => o !== option);
                    btn.classList.remove("selected");
                } else {
                    selected.push(option);
                    btn.classList.add("selected");
                }
            } else {
                sendAnswer(option);
            }
        };
        optionsDiv.appendChild(btn);
    });
    if (isCheckbox) {
        const submitBtn = document.createElement("button");
        submitBtn.innerText = "Gönder";
        submitBtn.className = "btn btn-primary";
        submitBtn.onclick = () => {
            if (selected.length > 0) sendAnswer(selected.join(", "));
        };
        optionsDiv.appendChild(submitBtn);
    }
    chatBox.appendChild(optionsDiv);
}

function renderDSMYesNo(options) {
    clearInputArea();
    const dsmDiv = document.createElement("div");
    dsmDiv.id = "options-area";
    dsmDiv.style.marginTop = "16px";
    dsmDiv.style.display = "flex";
    dsmDiv.style.flexDirection = "column";
    dsmDiv.style.gap = "10px";
    let answers = [];
    options.forEach(option => {
        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.alignItems = "center";
        row.style.gap = "10px";
        const label = document.createElement("span");
        label.innerText = option;
        row.appendChild(label);
        ["Evet", "Hayır"].forEach(val => {
            const btn = document.createElement("button");
            btn.innerText = val;
            btn.className = "btn option-btn";
            btn.onclick = () => {
                answers.push(`${option}: ${val}`);
                row.style.opacity = 0.5;
                row.querySelectorAll("button").forEach(b => b.disabled = true);
                if (answers.length === options.length) {
                    sendAnswer(answers.join(", "));
                }
            };
            row.appendChild(btn);
        });
        dsmDiv.appendChild(row);
    });
    chatBox.appendChild(dsmDiv);
}

function sendAnswer(answer) {
    addMessage(answer, "user-message");
    fetch("/submit_answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer: answer })
    }).then(() => {
        askNextQuestion();
    });
    clearInputArea();
}

// ✅ Mesaj Ekle
function addMessage(text, className) {
    let messageDiv = document.createElement("div");
    messageDiv.className = `message ${className} fade-in`;
    messageDiv.innerText = text;
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ✅ Mesaj Gönderme
sendBtn.addEventListener("click", () => {
    let answer = answerInput.value.trim();
    if (answer !== "") {
        sendAnswer(answer);
        answerInput.value = "";
    }
});

// ✅ Enter Tuşu ile Gönderme
answerInput.addEventListener("keypress", function (event) {
    if (event.key === "Enter") {
        sendBtn.click();
    }
});

// ✅ Sohbeti Sıfırla
resetChatBtn.addEventListener("click", function () {
    fetch("/reset_chat", { method: "POST" }).then(() => location.reload());
});

// ✅ PDF İndir
downloadPdfBtn.addEventListener("click", function () {
    fetch("/download_pdf", { method: "GET" })
        .then(response => response.blob())
        .then(blob => {
            const link = document.createElement("a");
            link.href = window.URL.createObjectURL(blob);
            link.download = "sohbet.pdf";
            link.click();
        });
});

// ✅ Dark/Light Mode
themeToggle.addEventListener("click", function () {
    if (theme.classList.contains("dark-mode")) {
        theme.classList.remove("dark-mode");
        theme.classList.add("light-mode");
        themeToggle.textContent = "🌙 Dark Mode";
    } else {
        theme.classList.remove("light-mode");
        theme.classList.add("dark-mode");
        themeToggle.textContent = "☀️ Light Mode";
    }
});

// ✅ Sayfa Yüklendiğinde
window.onload = function () {
    loadConversation(); // 🔹 Sadece geçmiş konuşmaları yükle
};