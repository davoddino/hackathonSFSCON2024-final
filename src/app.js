import { Conversation } from '@11labs/client';

let conversation = null;
let conversationTimeout = null;
let gameActive = false;
let imageElement = document.getElementById('videoStream');

async function requestMicrophonePermission() {
    try {
        await navigator.mediaDevices.getUserMedia({ audio: true });
        return true;
    } catch (error) {
        console.error('Microphone permission denied:', error);
        return false;
    }
}

async function getSignedUrl() {
    try {
        const response = await fetch('/api/signed-url');
        if (!response.ok) throw new Error('Failed to get signed URL');
        const data = await response.json();
        return data.signedUrl;
    } catch (error) {
        console.error('Error getting signed URL:', error);
        throw error;
    }
}

async function getAgentId() {
    const response = await fetch('/api/getAgentId');
    const { agentId } = await response.json();
    return agentId;
}

function updateStatus(isConnected) {
    const statusElement = document.getElementById('connectionStatus');
    statusElement.textContent = isConnected ? 'Connected' : 'Disconnected';
    statusElement.classList.toggle('connected', isConnected);
}

function updateSpeakingStatus(mode) {
    const statusElement = document.getElementById('speakingStatus');
    const isSpeaking = mode.mode === 'speaking';
    statusElement.textContent = isSpeaking ? 'Agent Speaking' : 'Agent Silent';
    statusElement.classList.toggle('speaking', isSpeaking);
    console.log('Speaking status updated:', { mode, isSpeaking });
}

async function startConversation() {
    if (conversation !== null) {
        console.log("Una conversazione è già attiva.");
        return;
    }

    try {
        const hasPermission = await requestMicrophonePermission();
        if (!hasPermission) {
            alert('Microphone permission is required for the conversation.');
            return;
        }

        const signedUrl = await getSignedUrl();

        conversation = await Conversation.startSession({
            signedUrl: signedUrl,
            onConnect: () => {
                console.log('Connected');
                updateStatus(true);
            },
            onDisconnect: () => {
                console.log('Disconnected');
                updateStatus(false);
                updateSpeakingStatus({ mode: 'listening' });
                conversation = null;
            },
            onError: (error) => {
                console.error('Conversation error:', error);
                alert('An error occurred during the conversation.');
                conversation = null;
            },
            onModeChange: (mode) => {
                console.log('Mode changed:', mode);
                updateSpeakingStatus(mode);
            }
        });
    } catch (error) {
        console.error('Error starting conversation:', error);
        alert('Failed to start conversation. Please try again.');
        conversation = null;
    }
}

async function endConversation() {
    if (conversation) {
        await conversation.endSession();
        conversation = null;
    }
}

window.addEventListener('error', function(event) {
    console.error('Global error:', event.error);
});

const socket = new WebSocket("ws://localhost:6789");

// Accetta dati binari come ArrayBuffer
socket.binaryType = 'arraybuffer';

socket.onopen = () => {
    console.log("Connesso al server WebSocket");
};

socket.onmessage = async (event) => {
    if (typeof event.data === 'string') {
        console.log(`Stato: ${event.data}`);

        clearTimeout(conversationTimeout);

        if (event.data === "Game Started") {
            console.log("Gioco avviato");
            gameActive = true;
            document.getElementById("videoContainer").style.display = "block";
            document.getElementById("birkengymSeller").style.display = "none";
            document.getElementById("personImage").style.display = "none";

            if (conversation) {
                await endConversation();
            }
        } else if (event.data === "Congratulations") {
            console.log("Congratulazioni!");
            // Mostra la scritta "Congratulazioni!" nell'HTML
            const congratsElement = document.getElementById("congratulationsMessage");
            congratsElement.style.display = "block";
            // Mantieni lo stream video per 4 secondi
            setTimeout(() => {
                congratsElement.style.display = "none";
                gameActive = false;
                document.getElementById("videoContainer").style.display = "none";
                document.getElementById("personImage").style.display = "block";
            }, 4000); // Mostra per 4 secondi
        } else if (event.data === "Person detected but arms not raised") {
            console.log("Person detected but arms not raised");
            gameActive = false;
            document.getElementById("birkengymSeller").style.display = "block";
            document.getElementById("videoContainer").style.display = "none";
            document.getElementById("personImage").style.display = "none";

            if (!conversation) {
                
                conversationTimeout = setTimeout(startConversation, 3000);
            }
        } else {
            gameActive = false;
            document.getElementById("personImage").style.display = "block";
            document.getElementById("birkengymSeller").style.display = "none";
            document.getElementById("videoContainer").style.display = "none";

            if (conversation) {
                await endConversation();
            }
        }
    } else {
        // Riceve i dati binari (frame video)
        if (gameActive) {
            const blob = new Blob([event.data], { type: 'image/jpeg' });
            const url = URL.createObjectURL(blob);
            imageElement.src = url;
            // Rilascia l'URL oggetto dopo che l'immagine è stata caricata
            imageElement.onload = () => {
                URL.revokeObjectURL(url);
            };
        }
    }
};

socket.onclose = () => {
    console.log("Connessione chiusa");
};
