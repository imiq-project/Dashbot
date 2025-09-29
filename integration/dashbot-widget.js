// Dashbot Widget JavaScript

// IMPORTANT: Update this URL 
const DASHBOT_API_URL = '/chat'; //we should change this to our Flask app URL

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

let isChatOpen = false;
let hasNewMessage = false;

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
async function typeWriter(element, text, speed = 25) {
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
            body: JSON.stringify({ message: message })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        hideTyping();
        setLoading(false);
        
        await addMessage(data.message, false, data.timestamp, true);
        
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
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashbot widget initialized');
    console.log('API URL:', DASHBOT_API_URL);
    
    //test if backend is reachable
    fetch(DASHBOT_API_URL.replace('/chat', '/health'))
        .then(response => {
            if (response.ok) {
                console.log('Dashbot backend is reachable');
            }
        })
        .catch(error => {
            console.warn('Dashbot backend not reachable:', error);
        });
});
