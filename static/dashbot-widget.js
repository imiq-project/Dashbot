function initDashbot(options) {

const DASHBOT_BASE_URL = options.backendUrl.replace(/\/chat\/?$/, '');
const rootElement = options.element ? document.querySelector(options.element) : document.body;

let sessionId = null;

const html = `
<div class="ask-city-bubble" id="askCityBubble">
    <span class="bubble-icon">🏙️</span>
    <span>Ask the City</span>
</div>

<!--floating chat toggle button -->
<button class="chat-toggle-btn" id="chatToggleBtn">
    <span id="chatIcon">💬</span>
    <div class="notification-badge" id="notificationBadge" style="display: none;">!</div>
</button>

<!--floating chat container -->
<div class="floating-chat-container" id="floatingChatContainer">
    <div class="chat-header">
        <div class="chat-header-info">
            <span class="chat-header-icon">🤖</span>
            <h1>Dashbot</h1>
        </div>
        <button class="minimize-btn" id="minimizeBtn">×</button>
    </div>

    <div class="chat-messages" id="chatMessages">
        <div class="welcome-message">
            <h2>Hello! 👋</h2>
            <p>I'm Dashbot, your smart city assistant. Ask me about parking, weather, traffic, campus buildings, routes, and more.</p>
            <div class="example-questions">
                <div class="example-question">
                    🌡️ Current temperature?
                </div>
                <div class="example-question">
                    🅿️ Available parking?
                </div>
                <div class="example-question">
                    🏛️ Where is the library?
                </div>
                <div class="example-question">
                    🚙 How do I get to Uni Mensa?
                </div>
            </div>
        </div>
    </div>

    <div class="typing-indicator" id="typingIndicator">
        <span class="typing-dots">Dashbot is thinking</span>
    </div>

    <div class="chat-input-container">
        <input type="text" class="chat-input" id="messageInput" placeholder="Ask about city data..." autocomplete="off">
        <button class="send-button" id="sendButton">
            <span id="sendIcon">➤</span>
            <div class="spinner" id="loadingSpinner" style="display: none;"></div>
        </button>
    </div>
</div>
`

rootElement.insertAdjacentHTML('beforeend', html)

//get DOM elements
const chatToggleBtn = document.getElementById('chatToggleBtn');
const floatingChatContainer = document.getElementById('floatingChatContainer');
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const typingIndicator = document.getElementById('typingIndicator');
const sendIcon = document.getElementById('sendIcon');
const loadingSpinner = document.getElementById('loadingSpinner');
const chatIcon = document.getElementById('chatIcon');
const notificationBadge = document.getElementById('notificationBadge');
const askCityBubble = document.getElementById('askCityBubble');

askCityBubble.onclick = openChatFromBubble;
chatToggleBtn.onclick = toggleChat
document.getElementById('minimizeBtn').onclick = toggleChat
sendButton.onclick = sendMessage
const exampleQuestions = document.getElementsByClassName("example-question")
exampleQuestions[0].onclick = () => sendExampleQuestion('What\'s the current temperature?')
exampleQuestions[1].onclick = () => sendExampleQuestion('Available parking spaces?')
exampleQuestions[2].onclick = () => sendExampleQuestion('Where is the library?')
exampleQuestions[3].onclick = () => sendExampleQuestion('How do I get to Uni Mensa?')

let isChatOpen = false;
let hasNewMessage = false;

// Start a session when widget initializes
async function startSession() {
    try {
        const response = await fetch(DASHBOT_BASE_URL + '/session/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        sessionId = data.session_id;
        console.log('Dashbot session started:', sessionId);
    } catch (error) {
        console.error('Failed to start session:', error);
        sessionId = 'default';
    }
}

// End session when widget closes
async function endSession() {
    if (sessionId && sessionId !== 'default') {
        try {
            await fetch(DASHBOT_BASE_URL + '/session/end?session_id=' + sessionId, {
                method: 'POST'
            });
            console.log('Dashbot session ended:', sessionId);
        } catch (error) {
            console.error('Failed to end session:', error);
        }
    }
}

// Start session immediately
startSession();

// End session when page unloads
window.addEventListener('beforeunload', function() {
    if (sessionId && sessionId !== 'default') {
        navigator.sendBeacon(
            DASHBOT_BASE_URL + '/session/end?session_id=' + sessionId
        );
    }
});

//open chat from bubble click
function openChatFromBubble() {
    if (!isChatOpen) {
        toggleChat();
    }
    askCityBubble.classList.add('hidden');
}

//toggle chat visibility
function toggleChat() {
    isChatOpen = !isChatOpen;

    if (isChatOpen) {
        floatingChatContainer.classList.add('show');
        chatToggleBtn.classList.add('active');
        chatIcon.textContent = '×';
        messageInput.focus();
        hideNotification();
        askCityBubble.classList.add('hidden');
    } else {
        floatingChatContainer.classList.remove('show');
        chatToggleBtn.classList.remove('active');
        chatIcon.textContent = '💬';
        askCityBubble.classList.remove('hidden');
    }
}

//notification functions
function showNotification() {
    if (!isChatOpen) {
        notificationBadge.style.display = 'flex';
        hasNewMessage = true;
    }
}

function hideNotification() {
    notificationBadge.style.display = 'none';
    hasNewMessage = false;
}

//send message on Enter key
messageInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

//send example question
function sendExampleQuestion(question) {
    messageInput.value = question;
    sendMessage();
}

//format bot message with links and styling
function formatBotMessage(content) {
    if (!content) return content;

    let formatted = content;

    // Format parking information
    formatted = formatted.replace(
        /(\d+)\s+free\s+spaces?\s+at\s+the\s+(ParkingSpot:\w+):?\s*(\w+)?\s+location\s+\((https:[^)]+)\)/gi,
        function(match, spaces, spotId, name, url) {
            return `<div class="location-info">
                <div class="parking-spot">${spotId}${name ? ' - ' + name : ''}</div>
                <div class="free-spaces">${spaces} free spaces available</div>
                <a href="${url}" target="_blank" class="map-link">📍 View on Map</a>
            </div>`;
        }
    );

    //format follow-up questions
    formatted = formatted.replace(
        /(What would you like to learn more about\?)/gi,
        '<div class="follow-up">$1</div>'
    );

    //format remaining URLs
    formatted = formatted.replace(
        /(https:\/\/[^\s<)]+)/g,
        '<a href="$1" target="_blank" class="map-link">📍 View Location</a>'
    );

    return formatted;
}

//typewriter effect for bot messages
async function typeWriter(element, text, speed = 1) {
    return new Promise((resolve) => {
        let i = 0;
        const cursor = document.createElement('span');
        cursor.className = 'typewriter-cursor';
        element.appendChild(cursor);

        function typeChar() {
            if (i < text.length) {
                if (text.charAt(i) === '<') {
                    const tagEnd = text.indexOf('>', i);
                    if (tagEnd !== -1) {
                        const tag = text.substring(i, tagEnd + 1);
                        element.insertAdjacentHTML('beforeend', tag);
                        i = tagEnd + 1;
                        setTimeout(typeChar, speed);
                        return;
                    }
                }

                const char = text.charAt(i);
                const textNode = document.createTextNode(char);
                element.insertBefore(textNode, cursor);
                i++;

                scrollToBottom();
                setTimeout(typeChar, speed);
            } else {
                cursor.remove();
                resolve();
            }
        }

        typeChar();
    });
}

//add message to chat
function addMessage(content, isUser = false, timestamp = null, useTypewriter = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;

    if (!timestamp) {
        timestamp = new Date().toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    const messageBubble = document.createElement('div');
    messageBubble.className = 'message-bubble';

    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = timestamp;

    messageDiv.appendChild(messageBubble);
    chatMessages.appendChild(messageDiv);

    //remove welcome message if it exists
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }

    //show notification if chat is closed
    if (!isUser && !isChatOpen) {
        showNotification();
    }

    if (useTypewriter && !isUser) {
        const formattedContent = formatBotMessage(content);
        const plainText = formattedContent.replace(/<[^>]*>/g, '');
        return typeWriter(messageBubble, plainText).then(() => {
            messageBubble.innerHTML = formattedContent;
            messageBubble.appendChild(timeDiv);
            scrollToBottom();
        });
    } else {
        const formattedContent = isUser ? content : formatBotMessage(content);
        messageBubble.innerHTML = formattedContent;
        messageBubble.appendChild(timeDiv);
        scrollToBottom();
        return Promise.resolve();
    }
}

//add message from streaming tokens (no typewriter, tokens arrive in real-time)
function addStreamingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';

    const messageBubble = document.createElement('div');
    messageBubble.className = 'message-bubble';

    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = new Date().toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });

    messageDiv.appendChild(messageBubble);
    chatMessages.appendChild(messageDiv);

    //remove welcome message if it exists
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }

    return { messageBubble, timeDiv };
}

//scroll to bottom of chat
function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

//show/hide typing indicator
function showTyping() {
    typingIndicator.style.display = 'block';
    scrollToBottom();
}

function hideTyping() {
    typingIndicator.style.display = 'none';
}

//set loading state for send button
function setLoading(loading) {
    sendButton.disabled = loading;
    if (loading) {
        sendIcon.style.display = 'none';
        loadingSpinner.style.display = 'block';
    } else {
        sendIcon.style.display = 'block';
        loadingSpinner.style.display = 'none';
    }
}

//main send message function — uses SSE streaming
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage(message, true);
    messageInput.value = '';

    setLoading(true);
    showTyping();

    try {
        const response = await fetch(DASHBOT_BASE_URL + '/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                session_id: sessionId || 'default',
                stream: true,
                conversational: true
            })
        });

        if (!response.ok) {
            throw new Error('HTTP error! status: ' + response.status);
        }

        hideTyping();

        const { messageBubble, timeDiv } = addStreamingMessage();
        let fullText = '';

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // keep incomplete line in buffer

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;

                try {
                    const event = JSON.parse(jsonStr);

                    if (event.type === 'token') {
                        fullText += event.content;
                        messageBubble.innerHTML = formatBotMessage(fullText);
                        scrollToBottom();
                    } else if (event.type === 'done') {
                        // finalize
                        messageBubble.innerHTML = formatBotMessage(fullText);
                        messageBubble.appendChild(timeDiv);
                        scrollToBottom();
                    } else if (event.type === 'error') {
                        fullText += ' [Error: ' + event.content + ']';
                        messageBubble.innerHTML = formatBotMessage(fullText);
                        messageBubble.appendChild(timeDiv);
                        scrollToBottom();
                    }
                    // map_data, sensor_data, dialogue_info — silently ignored in widget
                } catch (e) {
                    // skip malformed JSON
                }
            }
        }

        // If no text came through streaming, show fallback
        if (!fullText) {
            messageBubble.textContent = 'Sorry, I could not generate a response. Please try again.';
            messageBubble.appendChild(timeDiv);
        }

        if (!isChatOpen) {
            showNotification();
        }

        setLoading(false);

    } catch (error) {
        console.error('Dashbot Error:', error);
        hideTyping();
        setLoading(false);

        let errorMessage = 'Sorry, I encountered an error. Please try again.';
        if (error.message.includes('Failed to fetch')) {
            errorMessage = 'Cannot connect to Dashbot service. Please check if the backend is running.';
        }

        await addMessage(errorMessage, false, null, true);
    }

    messageInput.focus();
}

//initialize chatbot when DOM is loaded
console.log('Dashbot widget initialized');
console.log('Base URL:', DASHBOT_BASE_URL);

};
