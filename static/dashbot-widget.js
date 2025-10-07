function initDashbot(url) {

const DASHBOT_API_URL = url;

// Language translations
const translations = {
    en: {
        bubbleText: 'Ask the City',
        welcomeTitle: 'Hello! 👋',
        welcomeText: "I'm Dashbot, your smart city assistant. Ask me about parking, weather, and traffic in your city.",
        inputPlaceholder: 'Ask about city data...',
        typingText: 'Dashbot is thinking',
        exampleQuestions: [
            "What's the current temperature?",
            'Available parking spaces?',
            'Highest humidity location?',
            'Show me traffic data'
        ],
        exampleLabels: [
            '🌡️ Current temperature?',
            '🅿️ Available parking?',
            '💧 Humidity levels?',
            '🚙 Check Traffic?'
        ]
    },
    de: {
        bubbleText: 'Frag die Stadt',
        welcomeTitle: 'Hallo! 👋',
        welcomeText: 'Ich bin Dashbot, Ihr intelligenter Stadtassistent. Fragen Sie mich über Parken, Wetter und Verkehr in Ihrer Stadt.',
        inputPlaceholder: 'Fragen Sie über Stadtdaten...',
        typingText: 'Dashbot denkt nach',
        exampleQuestions: [
            'Wie ist die aktuelle Temperatur?',
            'Verfügbare Parkplätze?',
            'Standort mit höchster Luftfeuchtigkeit?',
            'Zeige mir Verkehrsdaten'
        ],
        exampleLabels: [
            '🌡️ Aktuelle Temperatur?',
            '🅿️ Verfügbare Parkplätze?',
            '💧 Luftfeuchtigkeit?',
            '🚙 Verkehr prüfen?'
        ]
    }
};

const html = `
<div class="ask-city-bubble" id="askCityBubble">
    <span class="bubble-icon">🏙️</span>
    <span id="bubbleText">Ask the City</span>
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

    <!-- Language Switcher -->
    <div class="language-switcher">
        <span class="language-switcher-label">🌐</span>
        <div class="language-toggle">
            <button class="language-option active" data-lang="en" id="langEN">English</button>
            <button class="language-option" data-lang="de" id="langDE">Deutsch</button>
        </div>
    </div>

    <div class="chat-messages" id="chatMessages">
        <div class="welcome-message">
            <h2 id="welcomeTitle">Hello! 👋</h2>
            <p id="welcomeText">I'm Dashbot, your smart city assistant. Ask me about parking, weather, and traffic in your city.</p>
            <div class="example-questions">
                <div class="example-question" id="exampleQ1">
                    🌡️ Current temperature?
                </div>
                <div class="example-question" id="exampleQ2">
                    🅿️ Available parking?
                </div>
                <div class="example-question" id="exampleQ3">
                    💧 Humidity levels?
                </div>
                <div class="example-question" id="exampleQ4">
                    🚙 Check Traffic?
                </div>
            </div>
        </div>
    </div>
    
    <div class="typing-indicator" id="typingIndicator">
        <span class="typing-dots" id="typingText">Dashbot is thinking</span>
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

document.body.insertAdjacentHTML('afterend', html)

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
const langEN = document.getElementById('langEN');
const langDE = document.getElementById('langDE');

let isChatOpen = false;
let hasNewMessage = false;
let currentLanguage = 'en';

askCityBubble.onclick = openChatFromBubble;
chatToggleBtn.onclick = toggleChat
document.getElementById('minimizeBtn').onclick = toggleChat
sendButton.onclick = sendMessage
langEN.onclick = () => switchLanguage('en');
langDE.onclick = () => switchLanguage('de');

const exampleQuestions = document.getElementsByClassName("example-question")
exampleQuestions[0].onclick = () => sendExampleQuestion(translations[currentLanguage].exampleQuestions[0])
exampleQuestions[1].onclick = () => sendExampleQuestion(translations[currentLanguage].exampleQuestions[1])
exampleQuestions[2].onclick = () => sendExampleQuestion(translations[currentLanguage].exampleQuestions[2])
exampleQuestions[3].onclick = () => sendExampleQuestion(translations[currentLanguage].exampleQuestions[3])

// Language switcher function
function switchLanguage(lang) {
    currentLanguage = lang;
    
    // Update active state
    langEN.classList.toggle('active', lang === 'en');
    langDE.classList.toggle('active', lang === 'de');
    
    // Update UI text
    document.getElementById('bubbleText').textContent = translations[lang].bubbleText;
    document.getElementById('welcomeTitle').textContent = translations[lang].welcomeTitle;
    document.getElementById('welcomeText').textContent = translations[lang].welcomeText;
    document.getElementById('messageInput').placeholder = translations[lang].inputPlaceholder;
    document.getElementById('typingText').textContent = translations[lang].typingText;
    
    // Update example questions
    document.getElementById('exampleQ1').textContent = translations[lang].exampleLabels[0];
    document.getElementById('exampleQ2').textContent = translations[lang].exampleLabels[1];
    document.getElementById('exampleQ3').textContent = translations[lang].exampleLabels[2];
    document.getElementById('exampleQ4').textContent = translations[lang].exampleLabels[3];

    console.log('Language switched to:', lang);
}

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

//format bot message with styling
function formatBotMessage(content) {
    if (!content) return content;
    
    let formatted = content;
    
    // Format parking information
    formatted = formatted.replace(
        /(\d+)\s+free\s+spaces?\s+at\s+the\s+(ParkingSpot:\w+):?\s*(\w+)?\s+location/gi, 
        function(match, spaces, spotId, name) {
            return `<div class="location-info">
                <div class="parking-spot">${spotId}${name ? ' - ' + name : ''}</div>
                <div class="free-spaces">${spaces} free spaces available</div>
            </div>`;
        }
    );

    //format follow-up questions
    formatted = formatted.replace(
        /(What would you like to learn more about\?|What else can I help with\?|Need anything else\?|Anything more\?|What else\?|Need more info\?|Want to know more\?|Anything else\?|What else would you like\?|Need more details\?|Something else\?|What else do you need\?|Anything more you need\?|Need something else\?|What else can I find for you\?|More questions\?|What else would you like to know\?|Anything else I can help with\?|Something else you want to know\?|More info\?|What else would you like\?|Need anything more\?|Something else you want\?|More info needed\?|Need more\?|What else can I get you\?|More details\?|What else can I find\?|More info needed\?|What else would you like to know about traffic\?|Is there anything more about traffic conditions you'd like to know\?|What would you like to know more about\?|Any other traffic information you need\?|What else can I help you with\?|Is there anything more about traffic you'd like to know\?|Is there anything more you need to know\?|Benötigen Sie noch etwas\?|Womit kann ich sonst helfen\?|Möchten Sie noch etwas wissen\?|Sonst noch etwas\?|Brauchen Sie mehr Informationen\?|Weitere Fragen\?|Was möchten Sie noch wissen\?|Etwas anderes\?|Brauchen Sie noch etwas\?|Was möchten Sie sonst noch wissen\?|Gibt es noch etwas über den Verkehr, das Sie wissen möchten\?|Benötigen Sie weitere Verkehrsinformationen\?|Womit kann ich Ihnen sonst helfen\?)/gi,
        '<div class="follow-up">$1</div>'
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
function addMessage(content, isUser = false, timestamp = null, useTypewriter = false, isAlert = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user' : 'bot'}`;
    
    if (!timestamp) {
        timestamp = new Date().toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }

    const messageBubble = document.createElement('div');
    messageBubble.className = isAlert ? 'message-bubble language-alert' : 'message-bubble';
    
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

    if (useTypewriter && !isUser && !isAlert) {
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

//main send message function
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;
    
    addMessage(message, true);
    messageInput.value = '';
    
    setLoading(true);
    showTyping();
    
    try {
        const response = await fetch(DASHBOT_API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                message: message,
                language: currentLanguage 
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        hideTyping();
        setLoading(false);
        
        // Check for language mismatch
        if (data.language_mismatch) {
            await addMessage(data.message, false, data.timestamp, false, true);
        } else {
            await addMessage(data.message, false, data.timestamp, true);
        }
        
    } catch (error) {
        console.error('Dashbot Error:', error);
        hideTyping();
        setLoading(false);
        
        const errorMessages = {
            en: 'Sorry, I encountered an error. Please try again.',
            de: 'Entschuldigung, ich bin auf einen Fehler gestoßen. Bitte versuchen Sie es noch einmal.'
        };
        
        let errorMessage = errorMessages[currentLanguage];
        if (error.message.includes('Failed to fetch')) {
            errorMessage = currentLanguage === 'en' 
                ? 'Cannot connect to Dashbot service. Please check if the backend is running.'
                : 'Kann keine Verbindung zum Dashbot-Dienst herstellen. Bitte prüfen Sie, ob das Backend läuft.';
        }
        
        await addMessage(errorMessage, false, null, true);
    }
    
    messageInput.focus();
}

//initialize chatbot when DOM is loaded
console.log('Dashbot widget initialized with multilingual support');
console.log('API URL:', DASHBOT_API_URL);

};
