// DOM Elements
const chatContainer = document.getElementById('chatContainer');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const fileInput = document.getElementById('fileInput');
const fileLabel = document.getElementById('fileLabel');
const statusDot = document.getElementById('statusDot');
const toastEl = document.getElementById('toast');
const toastMsg = document.getElementById('toastMsg');

// State
let isProcessing = false;

// Helpers
function showToast(msg, type = 'info') {
    toastMsg.textContent = msg;
    toastEl.className = `toast show ${type}`;
    setTimeout(() => {
        toastEl.classList.remove('show');
    }, 3000);
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function setProcessing(processing) {
    isProcessing = processing;
    sendBtn.disabled = processing;
    messageInput.disabled = processing;
    statusDot.classList.toggle('active', processing);

    if (processing) {
        sendBtn.innerHTML = '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
    } else {
        sendBtn.innerHTML = `
            <span>Send</span>
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
            </svg>
        `;
        messageInput.focus();
    }
}

function appendMessage(text, type, sources = []) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${type}`;

    let contentHtml = text;

    // Improved Markdown rendering with marked.js
    if (typeof marked !== 'undefined') {
        contentHtml = marked.parse(text);
    } else {
        // Fallback if marked.js fails to load
        contentHtml = contentHtml
            .replace(/\n\n/g, '<br><br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    }

    let sourceHtml = '';
    if (sources && sources.length > 0) {
        const unique = [...new Set(sources.map(s => s.source))];
        sourceHtml = `<div class="citation">📚 ${unique.join(', ')}</div>`;
    }

    msgDiv.innerHTML = `
        <div class="bubble">
            ${contentHtml}
            ${sourceHtml}
        </div>
    `;

    chatContainer.appendChild(msgDiv);
    scrollToBottom();
}

// API Interactions
async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;

    // UI Update
    messageInput.value = '';
    appendMessage(text, 'user');
    setProcessing(true);

    // Add temp thinking bubble
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'message bot typing';
    thinkingDiv.innerHTML = `
        <div class="bubble">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>`;
    chatContainer.appendChild(thinkingDiv);
    scrollToBottom();

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        const data = await res.json();

        // Remove thinking bubble
        chatContainer.removeChild(thinkingDiv);

        if (data.error) {
            appendMessage(`⚠️ Error: ${data.error}`, 'bot');
        } else {
            appendMessage(data.reply, 'bot', data.sources);
        }
    } catch (e) {
        chatContainer.removeChild(thinkingDiv);
        appendMessage(`⚠️ Network Error: ${e.message}`, 'bot');
    } finally {
        setProcessing(false);
    }
}

async function uploadFile(file) {
    const fd = new FormData();
    fd.append('file', file);

    fileLabel.textContent = 'Uploading...';

    try {
        const res = await fetch('/upload', { method: 'POST', body: fd });
        const data = await res.json();

        if (data.ok) {
            showToast(`Indexed ${data.filename}`, 'success');
            appendMessage(`✅ Successfully indexed **${data.filename}** (${data.chunks_added} chunks). Ready to chat!`, 'bot');
        } else {
            showToast(`Upload failed: ${data.error}`, 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    } finally {
        fileLabel.innerHTML = `
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>
            <span>Upload Document</span>
        `;
        fileInput.value = ''; // Reset
    }
}

async function resetDocs() {
    if (!confirm('Are you sure you want to clear all indexed documents?')) return;
    try {
        await fetch('/reset_docs', { method: 'POST' });
        showToast('All documents cleared', 'success');
        appendMessage('🗑️ RAG Index cleared. Please upload new documents.', 'bot');
    } catch (e) {
        showToast('Failed to reset', 'error');
    }
}

async function clearHistory() {
    if (!confirm('Clear conversation history?')) return;
    try {
        await fetch('/clear_history', { method: 'POST' });
        chatContainer.innerHTML = ''; // efficient clear
        appendMessage('🧹 Conversation history cleared.', 'bot');
    } catch (e) {
        showToast('Failed to clear history', 'error');
    }
}

// Event Listeners
sendBtn.addEventListener('click', sendMessage);

messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-resize textarea
messageInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
    if (this.value === '') this.style.height = 'auto';
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files[0]) uploadFile(e.target.files[0]);
});

// Expose functions for buttons
window.resetDocs = resetDocs;
window.clearHistory = clearHistory;

// Initial greeting
if (chatContainer.children.length === 0) {
    appendMessage("👋 Hi! I'm your RAG assistant. Upload a PDF/DOCX to get started.", 'bot');
}
