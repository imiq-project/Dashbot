function initDashbot(options) {

const DASHBOT_BASE_URL = options.backendUrl.replace(/\/chat\/?$/, '');
const root = options.element ? document.querySelector(options.element) : document.body;

let sessionId = null;
let isChatOpen = false;
let userLocation = null;   // {lat, lon} or null
let locationEnabled = false;

// ---- Inject HTML ----
const html = `
<!-- Avatar Button -->
<div class="dashbot-avatar" id="dashbotAvatar">
    <div class="avatar-glow"></div>
    <div class="avatar-inner">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
            <rect x="2" y="6" width="20" height="12" rx="3" stroke="white" stroke-width="1.5"/>
            <circle cx="8.5" cy="12" r="2" fill="white"/>
            <circle cx="15.5" cy="12" r="2" fill="white"/>
            <path d="M9 16.5C9 16.5 10.5 18 12 18C13.5 18 15 16.5 15 16.5" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
            <line x1="4" y1="6" x2="6" y2="2" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
            <line x1="20" y1="6" x2="18" y2="2" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
    </div>
    <div class="avatar-status-dot"></div>
    <div class="avatar-tooltip">Ask the Smart City</div>
</div>

<!-- Chat Side Panel -->
<div class="dashbot-panel" id="dashbotPanel">
    <div class="dashbot-panel-header">
        <div class="dashbot-header-left">
            <div class="dashbot-header-avatar">
                <svg viewBox="0 0 24 24" fill="none">
                    <rect x="2" y="6" width="20" height="12" rx="3" stroke="white" stroke-width="1.5"/>
                    <circle cx="8.5" cy="12" r="2" fill="white"/>
                    <circle cx="15.5" cy="12" r="2" fill="white"/>
                    <path d="M9 16.5C9 16.5 10.5 18 12 18C13.5 18 15 16.5 15 16.5" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </div>
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
            <div class="dashbot-welcome-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                    <rect x="2" y="6" width="20" height="12" rx="3" stroke="#7a003f" stroke-width="1.5"/>
                    <circle cx="8.5" cy="12" r="2" fill="#7a003f"/>
                    <circle cx="15.5" cy="12" r="2" fill="#7a003f"/>
                    <path d="M9 16.5C9 16.5 10.5 18 12 18C13.5 18 15 16.5 15 16.5" stroke="#7a003f" stroke-width="1.5" stroke-linecap="round"/>
                    <line x1="4" y1="6" x2="6" y2="2" stroke="#7a003f" stroke-width="1.5" stroke-linecap="round"/>
                    <line x1="20" y1="6" x2="18" y2="2" stroke="#7a003f" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </div>
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
        <div class="dashbot-typing-dots"><span></span><span></span><span></span></div>
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
                <div class="dashbot-send-spinner" id="dashbotSpinner" style="display:none;"></div>
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
const sendIcon    = document.getElementById('dashbotSendIcon');
const spinner     = document.getElementById('dashbotSpinner');
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
    } catch (e) {
        sessionId = 'default';
    }
}

startSession();

window.addEventListener('beforeunload', () => {
    if (sessionId && sessionId !== 'default') {
        navigator.sendBeacon(DASHBOT_BASE_URL + '/session/end?session_id=' + sessionId);
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
            await fetch(DASHBOT_BASE_URL + '/chat/reset?session_id=' + sessionId, { method: 'POST' });
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
    sendBtn.disabled = on;
    sendIcon.style.display = on ? 'none' : 'block';
    spinner.style.display  = on ? 'block' : 'none';
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
    var f = content;

    // =============================================
    // 1. Pre-processing: structured parking data & URLs
    // =============================================
    f = f.replace(
        /(\d+)\s+free\s+spaces?\s+at\s+the\s+(ParkingSpot:\w+):?\s*(\w+)?\s+location\s+\((https:[^)]+)\)/gi,
        function(m, spaces, spotId, name, url) {
            return '<div class="db-info-card"><div class="parking-spot">' + spotId +
                (name ? ' - ' + name : '') + '</div><div class="free-spaces">' + spaces +
                ' free spaces</div><a href="' + url + '" target="_blank" class="map-link">View on Map</a></div>';
        }
    );
    f = f.replace(/(https:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" class="map-link">View Location</a>');

    // =============================================
    // 2. Markdown: **bold** → <strong>
    // =============================================
    f = f.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // =============================================
    // 3. Line-based content parsing (multi-pass)
    // =============================================

    // Step A: Split into lines — sentence boundaries, route transitions, bullets
    var rawLines = f.split('\n');
    var lines = [];
    for (var ri = 0; ri < rawLines.length; ri++) {
        var raw = rawLines[ri].trim();
        if (!raw) continue;
        var isList = /^\s*(-\s+|\d+\.\s+)/.test(raw);

        if (isList) {
            lines.push(raw);
        } else if (/\s+-\s+\S/.test(raw) && !/^.{0,30}:/.test(raw)) {
            // Inline bullets — split them
            var bparts = raw.replace(/\s+(-\s+\S)/g, '\n$1').split('\n');
            for (var bi = 0; bi < bparts.length; bi++) {
                var bp = bparts[bi].trim();
                if (bp) lines.push(bp);
            }
        } else if (raw.length > 80) {
            // Split long prose at: sentence boundaries, ", then", "From there"
            var expanded = raw
                .replace(/([.!?])\s+(?=[A-Z])/g, '$1\n')
                .replace(/,\s*then\s+/gi, ',\n')
                .replace(/\.\s*From there,?\s*/gi, '.\nFrom there, ');
            var parts = expanded.split('\n');
            for (var pi = 0; pi < parts.length; pi++) {
                var p = parts[pi].trim();
                if (!p) continue;
                // Further split intro lines: "To get to X, take Tram..." → intro + step
                if (/^To\s+(?:get|reach|go|travel|head)/i.test(p) && p.length > 60) {
                    var verbMatch = p.match(/,\s*(take|walk|board|catch|hop)\s/i);
                    if (verbMatch) {
                        var idx = p.indexOf(verbMatch[0]);
                        var intro = p.substring(0, idx + 1).trim();
                        var step = p.substring(idx + 2).trim();
                        if (intro) lines.push(intro);
                        if (step) lines.push(step);
                        continue;
                    }
                }
                lines.push(p);
            }
        } else {
            lines.push(raw);
        }
    }

    // Step B: classify each line
    var routeVerbs = /^(take\s|walk\s|transfer\s|ride\s|board\s|catch\s|hop\s|then\s+(?:take|walk|transfer|ride|board)|from there)/i;
    var lineTypes = [];
    for (var li = 0; li < lines.length; li++) {
        var line = lines[li].trim();
        if (!line) continue;
        if (/^-\s+/.test(line)) {
            lineTypes.push({ type: 'bullet', text: line.replace(/^-\s+/, '') });
        } else if (/^\d+\.\s+/.test(line)) {
            lineTypes.push({ type: 'numbered', text: line.replace(/^\d+\.\s+/, '') });
        } else if (/:\s*$/.test(line) && line.length < 80) {
            lineTypes.push({ type: 'header-candidate', text: line });
        } else if (routeVerbs.test(line)) {
            // Capitalize first letter for display
            var display = line.charAt(0).toUpperCase() + line.slice(1);
            lineTypes.push({ type: 'route-step', text: display });
        } else {
            lineTypes.push({ type: 'text', text: line });
        }
    }

    // Step C: promote header candidates that precede list items or are short labels
    for (var li = 0; li < lineTypes.length; li++) {
        if (lineTypes[li].type === 'header-candidate') {
            var next = li + 1 < lineTypes.length ? lineTypes[li + 1] : null;
            var followedByList = next && (next.type === 'bullet' || next.type === 'numbered' || next.type === 'route-step');
            var isShortLabel = lineTypes[li].text.length < 50;
            if (followedByList || isShortLabel) {
                lineTypes[li].type = 'header';
            } else {
                lineTypes[li].type = 'text';
            }
        }
    }

    // Step D: render HTML
    var body = '';
    var stepCounter = 0;
    var inSteps = false;

    for (var li = 0; li < lineTypes.length; li++) {
        var item = lineTypes[li];

        if (item.type === 'header') {
            if (inSteps) { body += '</div>'; inSteps = false; }
            stepCounter = 0;
            body += '<div class="db-section-header">' + item.text + '</div>';
        } else if (item.type === 'bullet' || item.type === 'numbered' || item.type === 'route-step') {
            if (!inSteps) { body += '<div class="db-steps-container">'; inSteps = true; }
            stepCounter++;
            body += '<div class="db-step"><span class="db-step-num">' + stepCounter + '</span><span class="db-step-text">' + item.text + '</span></div>';
        } else {
            if (inSteps) { body += '</div>'; inSteps = false; stepCounter = 0; }
            body += '<p class="db-para">' + item.text + '</p>';
        }
    }
    if (inSteps) body += '</div>';

    // =============================================
    // 5. Inline highlights (applied to everything)
    // =============================================
    function applyHighlights(text) {
        // Times
        text = text.replace(/\b(\d+)\s*(minutes?|min|hours?|hrs?)\b/gi, '<span class="db-time">$1 $2</span>');
        // Distances
        text = text.replace(/\b(\d+\.?\d*)\s*(meters?|km|kilometres?|kilometers?)\b/gi, '<span class="db-distance">$1 $2</span>');
        // Parking spots
        text = text.replace(/\b(\d+)\s+(free\s+)?spots?\b/gi, '<span class="db-parking-highlight">$&</span>');
        text = text.replace(/\bparking\s+available\b/gi, '<span class="db-parking-highlight">parking available</span>');
        // Temperatures
        text = text.replace(/\b(-?\d+\.?\d*)\s*°?\s*(°C|°F|degrees?\s*(?:C|F|Celsius|Fahrenheit)?)\b/gi, '<span class="db-temp">$1 $2</span>');
        // Air quality
        text = text.replace(/\b(\d+)\s+(air\s+quality\s+sensors?)\b/gi, '<span class="db-air">$1 $2</span>');
        text = text.replace(/\b(PM2\.?5|PM10|NO2|O3|air\s+quality)\b/gi, '<span class="db-air">$&</span>');
        // Sensor counts
        text = text.replace(/\b(\d+)\s+((?:weather|parking)\s+sensors?|sensors?)\b/gi, '<span class="db-count">$1 $2</span>');
        // Total travel time
        text = text.replace(/(Total\s+(?:travel\s+)?time\s*(?:is|:)?\s*(?:around|about)?\s*)/gi, '<span class="db-total-label">$1</span>');
        // "Alternatively"
        text = text.replace(/\b(Alternatively,?\s*)/gi, '<span class="db-alt-label">$1</span>');
        // Follow-up questions
        text = text.replace(/(What would you like.*?\?)/gi, '<span class="db-follow-up">$1</span>');
        return text;
    }

    body = applyHighlights(body);

    // =============================================
    // 5. Return assembled HTML
    // =============================================
    return body || content;
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
    div.className = 'dashbot-msg ' + (isUser ? 'user' : 'bot');

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

    div.appendChild(bubble);
    messages.appendChild(div);

    // remove welcome
    const w = document.getElementById('dashbotWelcome');
    if (w) w.remove();

    scrollToBottom();
}

function addStreamingMessage() {
    const div = document.createElement('div');
    div.className = 'dashbot-msg bot';

    const bubble = document.createElement('div');
    bubble.className = 'dashbot-bubble';

    const time = document.createElement('div');
    time.className = 'dashbot-msg-time';
    time.textContent = now();

    div.appendChild(bubble);
    messages.appendChild(div);

    const w = document.getElementById('dashbotWelcome');
    if (w) w.remove();

    return { bubble, time };
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
    input.value = '';
    setLoading(true);
    showTyping();

    try {
        const res = await fetch(DASHBOT_BASE_URL + '/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: msg,
                session_id: sessionId || 'default',
                stream: true,
                conversational: true,
                user_location: userLocation
            })
        });

        if (!res.ok) throw new Error('HTTP ' + res.status);

        // Don't hide typing yet — wait for first token
        var bubble = null;
        var time = null;
        let fullText = '';
        var firstToken = true;
        var ttsSentIndex = 0; // tracks how much text we've already sent to TTS

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
                    if (ev.type === 'token') {
                        if (firstToken) {
                            hideTyping();
                            var streaming = addStreamingMessage();
                            bubble = streaming.bubble;
                            time = streaming.time;
                            firstToken = false;
                        }
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
                        if (firstToken) {
                            hideTyping();
                            var s = addStreamingMessage();
                            bubble = s.bubble; time = s.time;
                            firstToken = false;
                        }
                        if (bubble) {
                            bubble.innerHTML = formatBotMessage(fullText);
                            var footer = document.createElement('div');
                            footer.className = 'dashbot-msg-footer';
                            footer.appendChild(time);
                            footer.appendChild(createSpeakButton(fullText));
                            bubble.appendChild(footer);
                        }
                        scrollToBottom();
                        // Send remaining unsent text to TTS
                        if (ttsEnabled && fullText) {
                            var remaining = fullText.slice(ttsSentIndex).trim();
                            if (remaining) enqueueTtsChunk(remaining);
                        }
                    } else if (ev.type === 'error') {
                        if (firstToken) {
                            hideTyping();
                            var se = addStreamingMessage();
                            bubble = se.bubble; time = se.time;
                            firstToken = false;
                        }
                        fullText += ' [Error: ' + ev.content + ']';
                        if (bubble) {
                            bubble.innerHTML = formatBotMessage(fullText);
                            bubble.appendChild(time);
                        }
                        scrollToBottom();
                    }
                } catch (_) {}
            }
        }

        // Fallback if no tokens came at all
        hideTyping();
        if (!fullText) {
            if (!bubble) {
                var sf = addStreamingMessage();
                bubble = sf.bubble; time = sf.time;
            }
            bubble.textContent = 'Sorry, I could not generate a response.';
            bubble.appendChild(time);
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
