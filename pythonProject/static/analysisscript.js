const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("upload-btn");
const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const themeToggle = document.getElementById("theme-toggle");
const theme = document.body;

// 📂 + Butonuna Tıklanınca Dosya Yükleme Aç
uploadBtn.addEventListener("click", function () {
    fileInput.click();
});

// 📂 Dosya Yüklendiğinde Sohbet Alanına Göster ve Backend'e Gönder
fileInput.addEventListener("change", function () {
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        displayUploadedFile(file);
        uploadFileToServer(file);
    }
});

// 📩 Kullanıcı Mesajını Gönderme
sendBtn.addEventListener("click", function () {
    sendUserMessage();
});

// ↩️ Kullanıcı Enter'a Basınca Mesaj Gönderme
userInput.addEventListener("keypress", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendUserMessage();
    }
});

// 📩 Kullanıcı Mesaj Gönderme Fonksiyonu
function sendUserMessage() {
    const userText = userInput.value.trim();
    if (userText !== "") {
        addMessage(userText, "user-message");
        userInput.value = "";
        setTimeout(() => addMessage("🤖 Rapor inceleniyor...", "bot-message"), 500);
    }
}

// 📝 Mesaj Eklemek için
function addMessage(text, className) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${className}`;
    messageDiv.innerText = text;
    chatBox.appendChild(messageDiv);

    // Scroll işlemini biraz geciktirerek en son mesaja kaydır
    setTimeout(() => {
        chatBox.scrollTop = chatBox.scrollHeight;
    }, 10); // 10ms gecikme
}

// 📂 Dosya Yükleme Mesajını Gösterme
function displayUploadedFile(file) {
    const fileName = file.name;

    // ⚠️ PDF değilse uyarı ver
    if (!fileName.endsWith(".pdf")) {
        addMessage("⚠️ Yalnızca PDF dosyaları yüklenebilir!", "bot-message");
        return;
    }

    const fileDiv = document.createElement("div");
    fileDiv.className = "message bot-message";

    // 📄 PDF Simgesi ve Dosya Adı
    const fileIcon = document.createElement("i");
    fileIcon.className = "fas fa-file-pdf";
    fileIcon.style.color = "red";
    fileIcon.style.marginRight = "8px";

    const fileLink = document.createElement("a");
    fileLink.href = URL.createObjectURL(file);
    fileLink.target = "_blank";
    fileLink.innerText = fileName;
    fileLink.style.color = "cyan";

    fileDiv.appendChild(fileIcon);
    fileDiv.appendChild(fileLink);

    chatBox.appendChild(fileDiv);

    // Scroll işlemini biraz geciktirerek en son mesaja kaydır
    setTimeout(() => {
        chatBox.scrollTop = chatBox.scrollHeight;
    }, 10); // 10ms gecikme
}

// 📤 Dosyayı Backend'e Gönderme
function uploadFileToServer(file) {
    const formData = new FormData();
    formData.append("file", file);

    fetch("/upload", {
        method: "POST",
        body: formData
    })
    .then(response => response.json()) // Text yerine JSON olarak işleme
    .then(data => {
        // JSON objesi içindeki message alanını düzgün şekilde göster
        if (data && data.message) {
            addMessage(`✅ ${data.message}`, "bot-message");
        } else {
            addMessage(`✅ ${JSON.stringify(data)}`, "bot-message");
        }
    })
    .catch(error => {
        console.error("Hata:", error);
        addMessage("❌ Dosya yükleme başarısız!", "bot-message");
    });
}

// 🌙 Dark Mode - Light Mode Geçişi
themeToggle.addEventListener("click", function () {
    theme.classList.toggle("dark-mode");
    theme.classList.toggle("light-mode");
    themeToggle.textContent = theme.classList.contains("dark-mode") ? "☀️ Light Mode" : "🌙 Dark Mode";
});