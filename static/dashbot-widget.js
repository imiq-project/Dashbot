function initDashbot(options) {

const DASHBOT_BASE_URL = options.backendUrl.replace(/\/chat\/?$/, '');
const root = options.element ? document.querySelector(options.element) : document.body;

let sessionId = null;
let sessionToken = null;
let isChatOpen = false;
let userLocation = null;   // {lat, lon} or null
let locationEnabled = false;

//  HTML 
const html = `
<!-- Avatar Button -->
<div class="dashbot-avatar" id="dashbotAvatar">
    <div class="avatar-inner"></div>
    <div class="avatar-status-dot"></div>
    <div class="avatar-tooltip">Ask the Smart City</div>
</div>

<!-- Chat Side Panel -->
<div class="dashbot-panel" id="dashbotPanel">
    <div class="dashbot-panel-header">
        <div class="dashbot-header-left">
            <div class="dashbot-header-avatar"></div>
            <div class="dashbot-header-info">
                <h2>Dashbot</h2>
                <span class="dashbot-header-status"><span class="dot"></span> Online</span>
            </div>
        </div>
        <div class="dashbot-header-actions">
            <button class="dashbot-tts-btn tts-off" id="dashbotTtsBtn" title="Enable voice responses">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
                    <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                </svg>
            </button>
            <button class="dashbot-reset-btn" id="dashbotResetBtn" title="New chat">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21.5 2v6h-6"/><path d="M21.34 15.57a10 10 0 1 1-.57-8.38L21.5 8"/>
                </svg>
            </button>
            <button class="dashbot-close-btn" id="dashbotCloseBtn">&times;</button>
        </div>
    </div>

    <div class="dashbot-messages" id="dashbotMessages">
        <div class="dashbot-welcome" id="dashbotWelcome">
            <div class="dashbot-welcome-icon"></div>
            <h3>Hey there!</h3>
            <p>I'm your smart city assistant. Ask me about parking, weather, traffic, campus buildings, routes, and more.</p>
            <div class="dashbot-quick-actions">
                <button class="dashbot-quick-btn" data-q="What's the current temperature?">
                    <span class="q-icon">&#127777;</span> Current weather
                </button>
                <button class="dashbot-quick-btn" data-q="Available parking spaces?">
                    <span class="q-icon">&#127359;</span> Parking status
                </button>
                <button class="dashbot-quick-btn" data-q="Where is the library?">
                    <span class="q-icon">&#127963;</span> Find a building
                </button>
                <button class="dashbot-quick-btn" data-q="How do I get to Uni Mensa?">
                    <span class="q-icon">&#128587;</span> Get directions
                </button>
            </div>
        </div>
    </div>

    <div class="dashbot-typing" id="dashbotTyping">
        <div class="db-typing-wave"><span></span><span></span><span></span><span></span><span></span></div>
        <span class="dashbot-typing-text">Dashbot is thinking...</span>
    </div>

    <div class="dashbot-input-area">
        <div class="dashbot-input-wrap">
            <input type="text" class="dashbot-input" id="dashbotInput" placeholder="Ask about city data..." autocomplete="off">
            <button class="dashbot-location-btn location-off" id="dashbotLocationBtn" title="Share my location">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="4"/>
                    <line x1="12" y1="2" x2="12" y2="6"/>
                    <line x1="12" y1="18" x2="12" y2="22"/>
                    <line x1="2" y1="12" x2="6" y2="12"/>
                    <line x1="18" y1="12" x2="22" y2="12"/>
                </svg>
            </button>
            <button class="dashbot-mic-btn mic-off" id="dashbotMicBtn" title="Voice input">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                    <line x1="12" y1="19" x2="12" y2="23"/>
                    <line x1="8" y1="23" x2="16" y2="23"/>
                </svg>
            </button>
            <button class="dashbot-send-btn" id="dashbotSendBtn">
                <svg id="dashbotSendIcon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
            </button>
        </div>
    </div>
</div>
`;

root.insertAdjacentHTML('beforeend', html);

// ---- DOM refs ----
const avatar      = document.getElementById('dashbotAvatar');
const panel       = document.getElementById('dashbotPanel');
const closeBtn    = document.getElementById('dashbotCloseBtn');
const messages    = document.getElementById('dashbotMessages');
const input       = document.getElementById('dashbotInput');
const sendBtn     = document.getElementById('dashbotSendBtn');
const typing      = document.getElementById('dashbotTyping');
const resetBtn    = document.getElementById('dashbotResetBtn');
const locationBtn = document.getElementById('dashbotLocationBtn');
const micBtn      = document.getElementById('dashbotMicBtn');
const ttsBtn      = document.getElementById('dashbotTtsBtn');

// ---- Voice state ----
let ttsEnabled = false;
let currentAudio = null;
let recognition = null;
let isRecording = false;

// Quick-action buttons
document.querySelectorAll('.dashbot-quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const q = btn.getAttribute('data-q');
        if (q) { input.value = q; sendMessage(); }
    });
});

// ---- Session ----
async function startSession() {
    try {
        const res = await fetch(DASHBOT_BASE_URL + '/session/start', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        sessionId = data.session_id;
        sessionToken = data.session_token;
    } catch (e) {
        sessionId = 'default';
    }
}

startSession();

window.addEventListener('beforeunload', () => {
    if (sessionId && sessionId !== 'default' && sessionToken) {
        fetch(DASHBOT_BASE_URL + '/session/' + encodeURIComponent(sessionId) + '/end', {
            method: 'POST',
            headers: { 'X-Session-Token': sessionToken },
            keepalive: true,
        });
    }
});

// ---- Open / Close ----
function openChat() {
    isChatOpen = true;
    panel.classList.add('open');
    avatar.classList.add('hidden');
    input.focus();
}

function closeChat() {
    isChatOpen = false;
    panel.classList.remove('open');
    avatar.classList.remove('hidden');
}

// Save welcome HTML so we can restore it on reset
const welcomeHTML = document.getElementById('dashbotWelcome').outerHTML;

async function resetChat() {
    ttsStopAll();
    // Clear backend history
    if (sessionId) {
        try {
            await fetch(DASHBOT_BASE_URL + '/chat/reset', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(sessionToken ? { 'X-Session-Token': sessionToken } : {})
                },
                body: JSON.stringify({ session_id: sessionId })
            });
        } catch (_) {}
    }
    // Clear UI messages and restore welcome
    messages.innerHTML = welcomeHTML;
    // Re-bind quick action buttons
    messages.querySelectorAll('.dashbot-quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const q = btn.getAttribute('data-q');
            if (q) { input.value = q; sendMessage(); }
        });
    });
    hideTyping();
    setLoading(false);
}

avatar.addEventListener('click', openChat);
closeBtn.addEventListener('click', closeChat);
resetBtn.addEventListener('click', resetChat);

// ---- Location ----
function updateLocationButton(state) {
    locationBtn.classList.remove('location-off', 'location-loading', 'location-on', 'location-error');
    locationBtn.classList.add('location-' + state);
}

function showLocationToast(msg) {
    var toast = document.createElement('div');
    toast.className = 'dashbot-location-toast';
    toast.textContent = msg;
    messages.appendChild(toast);
    scrollToBottom();
    setTimeout(function() {
        toast.style.opacity = '0';
        setTimeout(function() { toast.remove(); }, 300);
    }, 2000);
}

function toggleLocation() {
    if (locationEnabled) {
        userLocation = null;
        locationEnabled = false;
        updateLocationButton('off');
        showLocationToast('Location disabled');
        return;
    }
    if (!navigator.geolocation) {
        updateLocationButton('error');
        showLocationToast('Geolocation not supported');
        setTimeout(function() { updateLocationButton('off'); }, 3000);
        return;
    }
    updateLocationButton('loading');
    navigator.geolocation.getCurrentPosition(
        function(pos) {
            userLocation = { lat: pos.coords.latitude, lon: pos.coords.longitude };
            locationEnabled = true;
            updateLocationButton('on');
            showLocationToast('Location enabled');
        },
        function(err) {
            var msg = 'Location error';
            if (err.code === 1) msg = 'Location permission denied';
            else if (err.code === 2) msg = 'Location unavailable';
            else if (err.code === 3) msg = 'Location request timed out';
            updateLocationButton('error');
            showLocationToast(msg);
            setTimeout(function() { updateLocationButton('off'); }, 3000);
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}

locationBtn.addEventListener('click', toggleLocation);

// ---- Microphone (STT via Web Speech API) ----
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function updateMicButton(state) {
    micBtn.classList.remove('mic-off', 'mic-on', 'mic-error');
    micBtn.classList.add('mic-' + state);
}

function toggleMic() {
    if (!SpeechRecognition) {
        showLocationToast('Voice input not supported in this browser');
        return;
    }

    if (isRecording && recognition) {
        recognition.abort();
        isRecording = false;
        updateMicButton('off');
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {
        isRecording = true;
        updateMicButton('on');
    };

    recognition.onresult = function(event) {
        var transcript = event.results[0][0].transcript;
        if (transcript.trim()) {
            input.value = transcript;
            sendMessage();
        }
    };

    recognition.onerror = function(event) {
        isRecording = false;
        if (event.error === 'not-allowed') {
            showLocationToast('Microphone permission denied');
        } else if (event.error === 'no-speech') {
            showLocationToast('No speech detected');
        } else {
            showLocationToast('Voice error: ' + event.error);
        }
        updateMicButton('error');
        setTimeout(function() { updateMicButton('off'); }, 2000);
    };

    recognition.onend = function() {
        isRecording = false;
        updateMicButton('off');
    };

    recognition.start();
}

micBtn.addEventListener('click', toggleMic);

// ---- TTS (ElevenLabs via /tts endpoint) ----
function toggleTts() {
    ttsEnabled = !ttsEnabled;
    ttsBtn.classList.remove('tts-off', 'tts-on');
    ttsBtn.classList.add(ttsEnabled ? 'tts-on' : 'tts-off');
    ttsBtn.title = ttsEnabled ? 'Disable voice responses' : 'Enable voice responses';
    showLocationToast(ttsEnabled ? 'Voice responses enabled' : 'Voice responses disabled');
    if (!ttsEnabled && currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }
}

ttsBtn.addEventListener('click', toggleTts);

function stripForTts(text) {
    if (!text) return '';
    // Remove HTML tags, markdown, and excessive whitespace
    var clean = text
        .replace(/<[^>]+>/g, '')
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/#{1,6}\s*/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    // Truncate to ~1000 chars for TTS (avoid very long audio)
    if (clean.length > 1000) {
        clean = clean.substring(0, 1000) + '...';
    }
    return clean;
}

// TTS audio queue - plays chunks back-to-back
var ttsQueue = [];
var ttsPlaying = false;

function ttsPlayNext() {
    if (ttsQueue.length === 0) {
        ttsPlaying = false;
        currentAudio = null;
        document.querySelectorAll('.dashbot-speak-btn.playing').forEach(function(b) {
            b.classList.remove('playing');
        });
        return;
    }
    ttsPlaying = true;
    var url = ttsQueue.shift();
    var audio = new Audio(url);
    currentAudio = audio;
    audio.onended = function() {
        URL.revokeObjectURL(url);
        ttsPlayNext();
    };
    audio.onerror = function() {
        URL.revokeObjectURL(url);
        ttsPlayNext();
    };
    audio.play();
}

function ttsStopAll() {
    ttsQueue = [];
    ttsPlaying = false;
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }
    window.speechSynthesis.cancel();
}

function speakBrowserTts(text) {
    ttsStopAll();
    var utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'en-US';
    utter.rate = 1.0;
    utter.onend = function() {
        currentAudio = null;
        document.querySelectorAll('.dashbot-speak-btn.playing').forEach(function(b) {
            b.classList.remove('playing');
        });
    };
    currentAudio = { pause: function() { window.speechSynthesis.cancel(); } };
    window.speechSynthesis.speak(utter);
}

async function fetchTtsChunk(text) {
    var clean = stripForTts(text);
    if (!clean) return;
    try {
        var res = await fetch(DASHBOT_BASE_URL + '/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: clean })
        });
        if (!res.ok) {
            console.warn('ElevenLabs TTS failed (' + res.status + ')');
            return null;
        }
        var blob = await res.blob();
        return URL.createObjectURL(blob);
    } catch (err) {
        console.warn('TTS fetch error:', err);
        return null;
    }
}

async function enqueueTtsChunk(text) {
    var url = await fetchTtsChunk(text);
    if (!url) return;
    ttsQueue.push(url);
    if (!ttsPlaying) ttsPlayNext();
}

async function speakText(text) {
    ttsStopAll();
    var clean = stripForTts(text);
    if (!clean) return;
    await enqueueTtsChunk(clean);
}

// ---- Helpers ----
function scrollToBottom() { messages.scrollTop = messages.scrollHeight; }

var thinkingPhrases = [
    '\uD83C\uDF10 Scanning the city...',
    '\uD83D\uDEE3\uFE0F Checking road conditions...',
    '\uD83D\uDCCF Calculating distances...',
    '\uD83D\uDCE1 Reading sensor data...',
    '\uD83C\uDFDB\uFE0F Looking over campus buildings...',
    '\uD83D\uDE97 Analyzing traffic flow...',
    '\uD83C\uDD7F\uFE0F Checking parking availability...',
    '\u26C5 Fetching weather updates...',
    '\uD83D\uDE8B Mapping transit routes...',
    '\u2699\uFE0F Querying smart city systems...',
    '\uD83E\uDDE0 Processing your request...',
    '\uD83D\uDCF6 Connecting to FIWARE sensors...',
    '\uD83D\uDE8A Checking tram schedules...',
    '\u2693 Surveying the Science Harbor...',
    '\uD83D\uDDFA\uFE0F Exploring the map...',
    '\uD83C\uDF21\uFE0F Reading temperatures...',
];
var typingTextEl = typing.querySelector('.dashbot-typing-text');
var typingInterval = null;

function showTyping() {
    typing.classList.add('show');
    var idx = Math.floor(Math.random() * thinkingPhrases.length);
    typingTextEl.textContent = thinkingPhrases[idx];
    typingInterval = setInterval(function() {
        idx = (idx + 1) % thinkingPhrases.length;
        typingTextEl.style.opacity = '0';
        setTimeout(function() {
            typingTextEl.textContent = thinkingPhrases[idx];
            typingTextEl.style.opacity = '1';
        }, 200);
    }, 2000);
    scrollToBottom();
}

function hideTyping() {
    typing.classList.remove('show');
    if (typingInterval) { clearInterval(typingInterval); typingInterval = null; }
}

function setLoading(on) {
    // Busy state just dims the (disabled) send button — no spinner. The
    // "Checking…" typing indicator already shows the assistant is working.
    sendBtn.disabled = on;
}

// Light formatter for streaming — only safe inline transforms, no structure detection
function formatStreaming(content) {
    if (!content) return content;
    var f = content;
    // URLs
    f = f.replace(/(https:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" class="map-link">View Location</a>');
    // Bold markdown
    f = f.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Newlines → <br>
    f = f.replace(/\n/g, '<br>');
    return f;
}

function formatBotMessage(content) {
    if (!content) return content;

    // --- Inline transformations (URLs, bold, italic) ---
    var f = content;
    f = f.replace(/(https:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener" class="map-link">$1</a>');
    f = f.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // italic: match single * but not ** (already handled)
    f = f.replace(/(^|[\s(])\*(?!\*)([^*\n]+?)\*(?!\*)/g, '$1<em>$2</em>');

    // --- Block parsing: paragraphs, bullet lists, numbered lists ---
    var rawLines = f.split('\n');
    var blocks = [];
    var current = null;

    function flush() {
        if (current && current.lines.length) blocks.push(current);
        current = null;
    }

    for (var i = 0; i < rawLines.length; i++) {
        var line = rawLines[i].trim();
        if (!line) { flush(); continue; }

        var mBullet = /^[-•]\s+(.*)$/.exec(line);
        var mNum = /^\d+\.\s+(.*)$/.exec(line);

        if (mBullet) {
            if (!current || current.type !== 'ul') { flush(); current = { type: 'ul', lines: [] }; }
            current.lines.push(mBullet[1]);
        } else if (mNum) {
            if (!current || current.type !== 'ol') { flush(); current = { type: 'ol', lines: [] }; }
            current.lines.push(mNum[1]);
        } else {
            if (!current || current.type !== 'p') { flush(); current = { type: 'p', lines: [] }; }
            current.lines.push(line);
        }
    }
    flush();

    // --- Inline highlights for times, distances, temperatures ---
    function highlight(text) {
        text = text.replace(/\b(\d+\.?\d*)\s*(minutes?|min|hours?|hrs?)\b/gi, '<span class="db-pill db-pill-time">$1 $2</span>');
        text = text.replace(/\b(\d+\.?\d*)\s*(meters?|m|km|kilometres?|kilometers?)\b(?!\w)/gi, '<span class="db-pill db-pill-dist">$1 $2</span>');
        text = text.replace(/\b(-?\d+\.?\d*)\s*°\s*(C|F)\b/gi, '<span class="db-pill db-pill-temp">$1°$2</span>');
        return text;
    }

    // --- Render ---
    var html = '';
    for (var b = 0; b < blocks.length; b++) {
        var blk = blocks[b];
        if (blk.type === 'ul') {
            html += '<ul class="db-list">';
            for (var j = 0; j < blk.lines.length; j++) html += '<li>' + highlight(blk.lines[j]) + '</li>';
            html += '</ul>';
        } else if (blk.type === 'ol') {
            html += '<ol class="db-list">';
            for (var j = 0; j < blk.lines.length; j++) html += '<li>' + highlight(blk.lines[j]) + '</li>';
            html += '</ol>';
        } else {
            html += '<p class="db-para">' + blk.lines.map(highlight).join(' ') + '</p>';
        }
    }

    return html || content;
}

function now() {
    return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

// ---- Messages ----
function createSpeakButton(text) {
    var btn = document.createElement('button');
    btn.className = 'dashbot-speak-btn';
    btn.title = 'Play voice';
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>';
    btn.addEventListener('click', function() {
        // Reset other playing buttons
        document.querySelectorAll('.dashbot-speak-btn.playing').forEach(function(b) { b.classList.remove('playing'); });
        btn.classList.add('playing');
        speakText(text);
    });
    return btn;
}

function addMessage(content, isUser) {
    const div = document.createElement('div');
    div.className = 'dashbot-msg ' + (isUser ? 'user' : 'bot with-avatar');

    const bubble = document.createElement('div');
    bubble.className = 'dashbot-bubble';
    bubble.innerHTML = isUser ? content : formatBotMessage(content);

    const time = document.createElement('div');
    time.className = 'dashbot-msg-time';
    time.textContent = now();

    if (!isUser) {
        var speakRow = document.createElement('div');
        speakRow.className = 'dashbot-msg-footer';
        speakRow.appendChild(time);
        speakRow.appendChild(createSpeakButton(content));
        bubble.appendChild(speakRow);
    } else {
        bubble.appendChild(time);
    }

    if (!isUser) {
        var botAvatar = document.createElement('div');
        botAvatar.className = 'db-bot-avatar';
        div.appendChild(botAvatar);
    }
    div.appendChild(bubble);
    messages.appendChild(div);

    // remove welcome
    const w = document.getElementById('dashbotWelcome');
    if (w) w.remove();

    scrollToBottom();
}

function addStreamingMessage() {
    const div = document.createElement('div');
    div.className = 'dashbot-msg bot with-avatar';

    const botAvatar = document.createElement('div');
    botAvatar.className = 'db-bot-avatar';

    const bubble = document.createElement('div');
    bubble.className = 'dashbot-bubble';

    const textContainer = document.createElement('div');
    textContainer.className = 'db-bubble-text';

    const cardsContainer = document.createElement('div');
    cardsContainer.className = 'db-cards';

    // Text first, cards below — cards are appended after response finishes.
    bubble.appendChild(textContainer);
    bubble.appendChild(cardsContainer);

    const time = document.createElement('div');
    time.className = 'dashbot-msg-time';
    time.textContent = now();

    div.appendChild(botAvatar);
    div.appendChild(bubble);
    messages.appendChild(div);

    const w = document.getElementById('dashbotWelcome');
    if (w) w.remove();

    // Return textContainer as `bubble` so existing innerHTML assignments target the
    // text area only — the cards container above them is preserved.
    // `outerBubble` exposes the outer .dashbot-bubble for class toggles (e.g. is-streaming).
    return { bubble: textContainer, time, cardsContainer, outerBubble: bubble };
}

// ---- Info card rendering ----
function dbEscape(s) {
    if (s === null || s === undefined) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function dbFmtDist(m) {
    if (m == null) return '';
    if (m < 1000) return Math.round(m) + ' m';
    return (m / 1000).toFixed(1) + ' km';
}

function dbFmtDur(s) {
    if (s == null) return '';
    if (s < 60) return Math.round(s) + ' s';
    const min = Math.round(s / 60);
    if (min < 60) return min + ' min';
    const h = Math.floor(min / 60);
    const mm = min % 60;
    return h + 'h ' + (mm ? mm + 'm' : '');
}

function renderTransitCard(card) {
    const segments = card.segments || [];
    const transfers = card.total_transfers || 0;

    // Metric strip
    const metrics = [];
    metrics.push('<span class="db-metric"><span class="db-metric-val">' + (card.total_stops || 0) + '</span><span class="db-metric-unit">stops</span></span>');
    if (transfers > 0) {
        metrics.push('<span class="db-metric db-metric-warn"><span class="db-metric-val">' + transfers + '</span><span class="db-metric-unit">transfer' + (transfers > 1 ? 's' : '') + '</span></span>');
    } else {
        metrics.push('<span class="db-metric db-metric-ok"><span class="db-metric-val">Direct</span></span>');
    }
    if (card.origin_walk_m) {
        metrics.push('<span class="db-metric"><span class="db-metric-val">' + dbFmtDist(card.origin_walk_m) + '</span><span class="db-metric-unit">walk start</span></span>');
    }
    if (card.destination_walk_m) {
        metrics.push('<span class="db-metric"><span class="db-metric-val">' + dbFmtDist(card.destination_walk_m) + '</span><span class="db-metric-unit">walk end</span></span>');
    }

    // Timeline
    const rows = [];
    // Origin
    const originName = (segments[0] && segments[0].from) || card.origin_stop || card.origin || '';
    rows.push(
        '<div class="db-tl-item db-tl-start">' +
            '<div class="db-tl-marker"><div class="db-tl-dot"></div></div>' +
            '<div class="db-tl-body">' +
                '<div class="db-tl-name">' + dbEscape(originName) + '</div>' +
                '<div class="db-tl-sub">Start</div>' +
            '</div>' +
        '</div>'
    );

    segments.forEach(function(s, i) {
        const isBus = /bus/i.test(s.line || '');
        const icon = isBus ? '\uD83D\uDE8C' : '\uD83D\uDE8B';
        const badgeClass = isBus ? 'db-tl-badge db-line-bus' : 'db-tl-badge';
        const intermediate = (s.stops || []).slice(1, -1); // exclude from/to
        const stopsList = intermediate.length
            ? '<details class="db-tl-stops">' +
                '<summary>' + intermediate.length + ' stop' + (intermediate.length > 1 ? 's' : '') + ' along the way</summary>' +
                '<ol>' + intermediate.map(function(st) { return '<li>' + dbEscape(st) + '</li>'; }).join('') + '</ol>' +
              '</details>'
            : '';
        rows.push(
            '<div class="db-tl-item db-tl-segment">' +
                '<div class="db-tl-marker"><div class="db-tl-connector"></div></div>' +
                '<div class="db-tl-body">' +
                    '<span class="' + badgeClass + '">' + icon + ' ' + dbEscape(s.line || '') + '</span>' +
                    (s.direction ? '<div class="db-tl-dir"><span class="db-tl-dir-arrow">\u2192</span>' + dbEscape(s.direction) + (s.num_stops ? ' \u00B7 ride ' + s.num_stops + ' stops' : '') + '</div>' : '') +
                    stopsList +
                '</div>' +
            '</div>'
        );

        // Transfer marker between segments (intermediate stop is also the next from)
        if (i < segments.length - 1) {
            rows.push(
                '<div class="db-tl-item db-tl-transfer">' +
                    '<div class="db-tl-marker"><div class="db-tl-dot"></div></div>' +
                    '<div class="db-tl-body">' +
                        '<div class="db-tl-name">' + dbEscape(s.to || '') + '</div>' +
                        '<div class="db-tl-sub">Transfer</div>' +
                    '</div>' +
                '</div>'
            );
        }
    });

    // Destination
    const destName = (segments.length && segments[segments.length - 1].to) || card.destination_stop || card.destination || '';
    rows.push(
        '<div class="db-tl-item db-tl-end">' +
            '<div class="db-tl-marker"><div class="db-tl-dot db-tl-dot-end"></div></div>' +
            '<div class="db-tl-body">' +
                '<div class="db-tl-name">' + dbEscape(destName) + '</div>' +
                '<div class="db-tl-sub">Arrive</div>' +
            '</div>' +
        '</div>'
    );

    return '<div class="db-card db-card-transit">' +
        '<div class="db-card-head">' +
            '<div class="db-card-title">' +
                '<span class="db-card-icon">\uD83D\uDE8F</span>' +
                '<span>' + dbEscape(card.origin || '') + ' \u2192 ' + dbEscape(card.destination || '') + '</span>' +
            '</div>' +
        '</div>' +
        '<div class="db-metrics">' + metrics.join('') + '</div>' +
        '<div class="db-timeline">' + rows.join('') + '</div>' +
    '</div>';
}

function renderRouteCard(card) {
    const icons = { walking: '\uD83D\uDEB6', cycling: '\uD83D\uDEB4', driving: '\uD83D\uDE97' };
    const modeLabel = (card.mode || '').charAt(0).toUpperCase() + (card.mode || '').slice(1);
    const dirs = (card.directions || []).slice(0, 8).map(function(d) {
        const text = typeof d === 'string' ? d : (d.instruction || d.text || d.message || '');
        return text ? '<li>' + dbEscape(text) + '</li>' : '';
    }).filter(Boolean).join('');

    const metrics = [];
    if (card.distance_m != null) {
        metrics.push('<span class="db-metric"><span class="db-metric-val">' + dbFmtDist(card.distance_m) + '</span></span>');
    }
    if (card.duration_s != null) {
        metrics.push('<span class="db-metric"><span class="db-metric-val">' + dbFmtDur(card.duration_s) + '</span></span>');
    }
    if (card.traffic_delay_s) {
        metrics.push('<span class="db-metric db-metric-warn"><span class="db-metric-val">+' + dbFmtDur(card.traffic_delay_s) + '</span><span class="db-metric-unit">traffic</span></span>');
    }

    return '<div class="db-card db-card-route db-route-' + dbEscape(card.mode || '') + '">' +
        '<div class="db-card-head">' +
            '<div class="db-card-title">' +
                '<span class="db-card-icon">' + (icons[card.mode] || '\uD83D\uDDFA\uFE0F') + '</span>' +
                '<span>' + modeLabel + ' route</span>' +
            '</div>' +
        '</div>' +
        (metrics.length ? '<div class="db-metrics">' + metrics.join('') + '</div>' : '') +
        (dirs ? '<details class="db-route-directions"><summary>Turn-by-turn directions</summary><ol>' + dirs + '</ol></details>' : '') +
    '</div>';
}

// ---- Map overlay ----
// Draws on the HOST page's Leaflet map (the IMIQ dashboard's `map`). No-ops
// gracefully when the page has no Leaflet map (e.g. Dashbot's standalone chat
// page), so the widget stays self-contained and infra-free.
let dashbotMapOverlay = null;   // place markers
let routePolyline = null;       // the single route line currently on the map
let defaultRouteDrawn = false;  // has the default (walking) route been auto-shown this answer?

function getLeafletMap() {
    // The dashboard declares a page-global `const map` (classic script) + global `L`.
    try { if (typeof map !== 'undefined' && window.L && map instanceof L.Map) return map; } catch (e) {}
    try { if (window.map && window.L && window.map instanceof L.Map) return window.map; } catch (e) {}
    return null;
}

function getMapOverlay(m) {
    if (!dashbotMapOverlay) { dashbotMapOverlay = L.layerGroup().addTo(m); }
    return dashbotMapOverlay;
}

function clearMapOverlay() {
    try { if (dashbotMapOverlay) dashbotMapOverlay.clearLayers(); } catch (e) {}
    const m = getLeafletMap();
    try { if (m && routePolyline) m.removeLayer(routePolyline); } catch (e) {}
    routePolyline = null;
    defaultRouteDrawn = false;
}

const DB_ROUTE_COLORS = { walking: '#2e7d32', cycling: '#1565c0', driving: '#7b1fa2' };

function drawOnMap(card) {
    // Place pins only — routes are handled by drawRoute/selectRoute so the map
    // never shows more than ONE route line at a time.
    const m = getLeafletMap();
    if (!m || !window.L || !card) return;
    if (card.type !== 'place' || card.lat == null || card.lon == null) return;
    try {
        const overlay = getMapOverlay(m);
        const marker = L.marker([card.lat, card.lon]);
        if (card.name) marker.bindPopup(String(card.name));
        overlay.addLayer(marker);
        // Single pin → center + open popup; multiple → frame them all.
        if (overlay.getLayers().length <= 1) {
            m.setView([card.lat, card.lon], Math.max(m.getZoom(), 16));
            marker.openPopup();
        } else {
            try { m.fitBounds(overlay.getBounds(), { padding: [40, 40], maxZoom: 17 }); } catch (e) {}
        }
    } catch (e) {
        console.warn('Dashbot: map draw failed', e);
    }
}

// Always exactly ONE route line. Drawing a mode replaces the previous line.
function drawRoute(mode, coords) {
    const m = getLeafletMap();
    if (!m || !window.L || !Array.isArray(coords) || coords.length < 2) return;
    try { if (routePolyline) m.removeLayer(routePolyline); } catch (e) {}
    routePolyline = L.polyline(coords, {
        color: DB_ROUTE_COLORS[mode] || '#7a003f', weight: 5, opacity: 0.9,
    }).addTo(m);
    try {
        const layers = [routePolyline].concat(dashbotMapOverlay ? dashbotMapOverlay.getLayers() : []);
        m.fitBounds(L.featureGroup(layers).getBounds(), { padding: [40, 40], maxZoom: 17 });
    } catch (e) {}
}

// Draw the chosen mode's line and highlight its card among its siblings.
function selectRoute(el, mode, coords) {
    drawRoute(mode, coords);
    try {
        const group = el.closest('.db-cards') || el.parentElement;
        if (group) {
            group.querySelectorAll('.db-card-route').forEach(function (c) {
                if (c === el) {
                    c.style.outline = '2px solid ' + (DB_ROUTE_COLORS[mode] || '#7a003f');
                    c.style.outlineOffset = '1px';
                } else {
                    c.style.outline = 'none';
                }
            });
        }
    } catch (e) {}
}

function renderPlaceCard(card) {
    return '<div class="db-card db-card-place">' +
        '<div class="db-card-head">' +
            '<div class="db-card-title">' +
                '<span class="db-card-icon">📍</span>' +
                '<span>' + dbEscape(card.name || 'Location') + '</span>' +
            '</div>' +
        '</div>' +
        '<div class="db-tl-sub">Shown on the map</div>' +
    '</div>';
}

function renderCard(container, card) {
    if (!container || !card || !card.type) return;
    // Draw the geo overlay on the host Leaflet map (dashboard) when present.
    drawOnMap(card);
    let html = '';
    switch (card.type) {
        case 'transit_route': html = renderTransitCard(card); break;
        case 'route': html = renderRouteCard(card); break;
        case 'place': html = renderPlaceCard(card); break;
        default: return;
    }
    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    const el = wrap.firstElementChild;
    if (el) {
        el.classList.add('db-card-enter');
        const isRoute = (card.type === 'route' && Array.isArray(card.geometry) && card.geometry.length > 1);
        if (isRoute) {
            el.setAttribute('data-mode', card.mode);
            el.style.cursor = 'pointer';
            el.title = 'Show this route on the map';
            el.addEventListener('click', function () { selectRoute(el, card.mode, card.geometry); });
        }
        container.appendChild(el);
        // Show ONE route by default (walking — route cards arrive walking-first).
        if (isRoute && !defaultRouteDrawn) {
            selectRoute(el, card.mode, card.geometry);
            defaultRouteDrawn = true;
        }
        requestAnimationFrame(function() { el.classList.add('db-card-shown'); });
    }
}

// ---- Send ----
input.addEventListener('keypress', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
sendBtn.addEventListener('click', sendMessage);

async function sendMessage() {
    const msg = input.value.trim();
    if (!msg) return;

    if (!isChatOpen) openChat();

    addMessage(msg, true);
    clearMapOverlay();   // wipe the previous answer's pins/routes from the map
    input.value = '';
    setLoading(true);
    showTyping();

    try {
        const res = await fetch(DASHBOT_BASE_URL + '/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(sessionToken ? { 'X-Session-Token': sessionToken } : {})
            },
            body: JSON.stringify({
                message: msg,
                session_id: sessionId || 'default',
                stream: true,
                conversational: true,
                user_location: userLocation
            })
        });

        if (!res.ok) throw new Error('HTTP ' + res.status);

        // JSON (non-streaming) fast path for the LangGraph backend
        const ctype = res.headers.get('content-type') || '';
        if (ctype.includes('application/json')) {
            const data = await res.json();
            hideTyping();
            const s = addStreamingMessage();
            s.outerBubble.classList.add('is-streaming');
            const fullText = data.text || 'Sorry, I could not generate a response.';
            s.bubble.innerHTML = formatBotMessage(fullText);
            const footer = document.createElement('div');
            footer.className = 'dashbot-msg-footer';
            footer.appendChild(s.time);
            footer.appendChild(createSpeakButton(fullText));
            s.bubble.appendChild(footer);
            s.outerBubble.classList.remove('is-streaming');
            scrollToBottom();
            setLoading(false);
            return;
        }

        var bubble = null;
        var outerBubble = null;
        var time = null;
        var cardsContainer = null;
        let fullText = '';
        var firstToken = true;
        var ttsSentIndex = 0;
        var pendingCards = [];

        function ensureBubble() {
            if (!firstToken) return;
            hideTyping();
            var s = addStreamingMessage();
            bubble = s.bubble;
            outerBubble = s.outerBubble;
            time = s.time;
            cardsContainer = s.cardsContainer;
            outerBubble.classList.add('is-streaming');
            firstToken = false;
        }

        function flushCards() {
            for (var i = 0; i < pendingCards.length; i++) {
                renderCard(cardsContainer, pendingCards[i]);
            }
            pendingCards.length = 0;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const json = line.slice(6).trim();
                if (!json) continue;
                try {
                    const ev = JSON.parse(json);
                    if (ev.type === 'card') {
                        // Buffer until text finishes — cards render below the message
                        pendingCards.push(ev.card);
                    } else if (ev.type === 'token') {
                        ensureBubble();
                        fullText += ev.content;
                        bubble.innerHTML = formatStreaming(fullText);
                        scrollToBottom();
                        // Stream TTS: send each paragraph as it completes
                        if (ttsEnabled) {
                            var unsent = fullText.slice(ttsSentIndex);
                            var paraBreak = unsent.indexOf('\n\n');
                            if (paraBreak > 0) {
                                var chunk = unsent.slice(0, paraBreak).trim();
                                if (chunk) enqueueTtsChunk(chunk);
                                ttsSentIndex += paraBreak + 2;
                            }
                        }
                    } else if (ev.type === 'done') {
                        ensureBubble();
                        if (bubble) {
                            bubble.innerHTML = formatBotMessage(fullText);
                            var footer = document.createElement('div');
                            footer.className = 'dashbot-msg-footer';
                            footer.appendChild(time);
                            footer.appendChild(createSpeakButton(fullText));
                            bubble.appendChild(footer);
                        }
                        // Now reveal any cards below the finalized text
                        flushCards();
                        if (outerBubble) {
                            outerBubble.classList.remove('is-streaming');
                        }
                        scrollToBottom();
                        // Send remaining unsent text to TTS
                        if (ttsEnabled && fullText) {
                            var remaining = fullText.slice(ttsSentIndex).trim();
                            if (remaining) enqueueTtsChunk(remaining);
                        }
                    } else if (ev.type === 'error') {
                        ensureBubble();
                        fullText += ' [Error: ' + ev.content + ']';
                        if (bubble) {
                            bubble.innerHTML = formatBotMessage(fullText);
                            bubble.appendChild(time);
                        }
                        if (outerBubble) outerBubble.classList.remove('is-streaming');
                        scrollToBottom();
                    }
                } catch (_) {}
            }
        }

        hideTyping();
        if (!fullText) {
            if (!bubble) {
                var sf = addStreamingMessage();
                bubble = sf.bubble; time = sf.time;
                cardsContainer = sf.cardsContainer;
                outerBubble = sf.outerBubble;
            }
            bubble.textContent = 'Sorry, I could not generate a response.';
            bubble.appendChild(time);
            if (outerBubble) outerBubble.classList.remove('is-streaming');
        }
        // Safety net: if `done` never fired but we have pending cards, reveal them.
        if (pendingCards.length && cardsContainer) {
            flushCards();
        }

        setLoading(false);

    } catch (err) {
        console.error('Dashbot Error:', err);
        hideTyping();
        setLoading(false);
        addMessage(
            err.message.includes('Failed to fetch')
                ? 'Cannot connect to Dashbot. Is the backend running?'
                : 'Sorry, something went wrong. Please try again.',
            false
        );
    }

    input.focus();
}

console.log('Dashbot widget initialized — base URL:', DASHBOT_BASE_URL);

}

