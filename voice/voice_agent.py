"""
voice/voice_agent.py — Groq Whisper STT with Indian accent support + Browser TTS
No Anthropic dependency - completely free!
"""

import io
import os
import base64
import tempfile
from typing import Optional, Tuple
import json
import re

def transcribe_audio_groq(audio_bytes: bytes, client, filename: str = "audio.webm") -> str:
    """Transcribe audio using Groq Whisper (supports Indian accent) - FREE"""
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{filename.split('.')[-1]}", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model="whisper-large-v3-turbo",
                response_format="text",
                language="en",
                temperature=0.0,
            )
        os.unlink(tmp_path)
        return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
    except Exception as e:
        return f"[Transcription error: {e}]"


def transcribe_audio_b64(audio_b64: str, client, fmt: str = "webm") -> str:
    """Transcribe from base64-encoded audio."""
    return transcribe_audio_groq(base64.b64decode(audio_b64), client, f"recording.{fmt}")


def get_google_speech_js() -> str:
    """JavaScript for Google-like voice assistant with continuous listening."""
    return """
    <style>
    .voice-assistant {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border-radius: 20px;
        padding: 1rem;
        text-align: center;
        font-family: 'Segoe UI', sans-serif;
    }
    .mic-button {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        background: linear-gradient(135deg, #e8541e, #f97316);
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 20px rgba(232,84,30,0.4);
        transition: all 0.3s ease;
        color: white;
        font-size: 2rem;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto;
    }
    .mic-button.recording {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        animation: pulse 1.2s infinite;
        box-shadow: 0 0 20px rgba(239,68,68,0.6);
    }
    @keyframes pulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.08); }
    }
    .status-text {
        margin-top: 12px;
        font-size: 0.85rem;
        color: #94a3b8;
    }
    .status-text.active {
        color: #ef4444;
        font-weight: 600;
    }
    .transcript {
        margin-top: 12px;
        padding: 10px;
        background: rgba(255,255,255,0.1);
        border-radius: 12px;
        font-size: 0.9rem;
        color: #e2e8f0;
        min-height: 50px;
    }
    .suggestions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: center;
        margin-top: 12px;
    }
    .suggestion-chip {
        background: rgba(232,84,30,0.2);
        border: 1px solid rgba(232,84,30,0.5);
        border-radius: 20px;
        padding: 6px 14px;
        font-size: 0.75rem;
        color: #f97316;
        cursor: pointer;
        transition: all 0.2s;
    }
    .suggestion-chip:hover {
        background: rgba(232,84,30,0.4);
    }
    .wave {
        display: inline-flex;
        gap: 4px;
        align-items: center;
        justify-content: center;
        margin-left: 10px;
    }
    .wave span {
        width: 4px;
        height: 12px;
        background: #ef4444;
        border-radius: 2px;
        animation: wave 0.8s infinite ease-in-out;
    }
    .wave span:nth-child(1) { animation-delay: 0s; height: 8px; }
    .wave span:nth-child(2) { animation-delay: 0.1s; height: 16px; }
    .wave span:nth-child(3) { animation-delay: 0.2s; height: 12px; }
    .wave span:nth-child(4) { animation-delay: 0.3s; height: 20px; }
    .wave span:nth-child(5) { animation-delay: 0.4s; height: 10px; }
    @keyframes wave {
        0%, 100% { transform: scaleY(1); }
        50% { transform: scaleY(0.5); }
    }
    </style>
    
    <div class="voice-assistant">
        <button id="voiceBtn" class="mic-button" onclick="toggleVoiceAssistant()">
            🎤
        </button>
        <div id="voiceStatus" class="status-text">Click to speak</div>
        <div id="voiceTranscript" class="transcript"></div>
        <div class="suggestions">
            <div class="suggestion-chip" onclick="sendSuggestion('I bought 500g paneer and 1kg onions')">📦 Add groceries</div>
            <div class="suggestion-chip" onclick="sendSuggestion('Make me a healthy dinner recipe')">🍳 Get recipe</div>
            <div class="suggestion-chip" onclick="sendSuggestion('What can I cook with what I have?')">🥗 Pantry ideas</div>
            <div class="suggestion-chip" onclick="sendSuggestion('Plan my meals for 3 days')">📅 Meal plan</div>
            <div class="suggestion-chip" onclick="sendSuggestion('Show my daily nutrition')">📊 Nutrition</div>
        </div>
    </div>
    
    <script>
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let stream = null;
    let recognition = null;
    
    // Check for Web Speech API (Google Speech Recognition)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const useWebSpeech = !!SpeechRecognition;
    
    function toggleVoiceAssistant() {
        if (useWebSpeech) {
            toggleWebSpeech();
        } else {
            toggleLegacyRecording();
        }
    }
    
    function toggleWebSpeech() {
        if (recognition && isRecording) {
            recognition.stop();
            return;
        }
        
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-IN';  // Indian English support
        
        const btn = document.getElementById('voiceBtn');
        const status = document.getElementById('voiceStatus');
        const transcriptDiv = document.getElementById('voiceTranscript');
        
        recognition.onstart = () => {
            isRecording = true;
            btn.innerHTML = '⏹️';
            btn.classList.add('recording');
            status.innerHTML = '🎙️ Listening... <div class="wave"><span></span><span></span><span></span><span></span><span></span></div>';
            status.classList.add('active');
            transcriptDiv.innerHTML = '';
            audioChunks = [];
        };
        
        recognition.onresult = (event) => {
            let interimTranscript = '';
            let finalTranscript = '';
            
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }
            
            if (finalTranscript) {
                transcriptDiv.innerHTML = '📝 ' + finalTranscript;
                // Send to parent
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: {text: finalTranscript, isFinal: true}
                }, '*');
            } else if (interimTranscript) {
                transcriptDiv.innerHTML = '💬 ' + interimTranscript + ' <span style="opacity:0.5">(speaking...)</span>';
            }
        };
        
        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            status.innerHTML = '❌ Error: ' + event.error;
            stopRecording();
        };
        
        recognition.onend = () => {
            stopRecording();
        };
        
        recognition.start();
    }
    
    function toggleLegacyRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            return;
        }
        
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(mediaStream => {
                stream = mediaStream;
                mediaRecorder = new MediaRecorder(mediaStream);
                audioChunks = [];
                
                mediaRecorder.ondataavailable = event => {
                    if (event.data.size > 0) {
                        audioChunks.push(event.data);
                    }
                };
                
                mediaRecorder.onstop = () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        const b64 = reader.result.split(',')[1];
                        window.parent.postMessage({
                            type: 'streamlit:setComponentValue',
                            value: {audio_b64: b64, format: 'webm', isFinal: true}
                        }, '*');
                    };
                    reader.readAsDataURL(audioBlob);
                    
                    const status = document.getElementById('voiceStatus');
                    status.innerHTML = '✅ Processing...';
                    
                    if (stream) {
                        stream.getTracks().forEach(track => track.stop());
                    }
                };
                
                mediaRecorder.start();
                isRecording = true;
                
                const btn = document.getElementById('voiceBtn');
                const status = document.getElementById('voiceStatus');
                btn.innerHTML = '⏹️';
                btn.classList.add('recording');
                status.innerHTML = '🔴 Recording... <div class="wave"><span></span><span></span><span></span><span></span><span></span></div>';
                status.classList.add('active');
                
                setTimeout(() => {
                    if (mediaRecorder && isRecording) {
                        mediaRecorder.stop();
                    }
                }, 10000);
            })
            .catch(err => {
                console.error('Mic error:', err);
                document.getElementById('voiceStatus').innerHTML = '❌ Microphone access denied';
            });
    }
    
    function stopRecording() {
        isRecording = false;
        const btn = document.getElementById('voiceBtn');
        const status = document.getElementById('voiceStatus');
        btn.innerHTML = '🎤';
        btn.classList.remove('recording');
        status.innerHTML = 'Click to speak';
        status.classList.remove('active');
        if (recognition) {
            recognition = null;
        }
    }
    
    function sendSuggestion(text) {
        const transcriptDiv = document.getElementById('voiceTranscript');
        transcriptDiv.innerHTML = '📝 ' + text;
        window.parent.postMessage({
            type: 'streamlit:setComponentValue',
            value: {text: text, isFinal: true, isSuggestion: true}
        }, '*');
    }
    </script>
    """


def render_voice_input_ui(client) -> Optional[str]:
    """Streamlit voice input UI with Google-like voice assistant."""
    import streamlit as st
    import streamlit.components.v1 as components

    st.markdown("""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                border-radius: 16px; padding: 2px; margin-bottom: 16px;">
        <div style="background: #0f172a; border-radius: 14px; padding: 16px;">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
                <span style="font-size: 28px;">🎙️</span>
                <div>
                    <div style="font-weight: 700; color: #f97316;">Voice Assistant</div>
                    <div style="font-size: 12px; color: #94a3b8;">Speak naturally - supports Indian English</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # File upload alternative
    audio_file = st.file_uploader(
        "Or upload audio file", 
        type=["wav", "mp3", "m4a", "ogg", "webm", "flac"],
        key="voice_upload", 
        label_visibility="collapsed"
    )
    
    if audio_file:
        with st.spinner("🔊 Transcribing with Whisper..."):
            text = transcribe_audio_groq(audio_file.read(), client, audio_file.name)
        if not text.startswith("["):
            st.success(f"📝 Heard: *{text}*")
            return text
        else:
            st.error(text)
    
    # Voice assistant component
    result = components.html(get_google_speech_js(), height=200)
    
    if result and isinstance(result, dict):
        if "text" in result and result.get("isFinal"):
            return result["text"]
        if "audio_b64" in result:
            with st.spinner("🔊 Transcribing with Whisper..."):
                text = transcribe_audio_b64(result["audio_b64"], client)
            if not text.startswith("["):
                return text
    
    return None
