#Terminal 1
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# .\venv\Scripts\Activate.ps1
# streamlit run app.py

#Terminal 2
# node server_local.js


import streamlit as st
import requests
import whisper
import soundfile as sf
import numpy as np
import tempfile
import os
import ssl

# --- Page Setup ---
st.set_page_config(
    page_title="SmartHealthChat",
    page_icon="🩺",
    layout="centered"
)

st.title("🩺 SmartHealthChat")
st.caption("Your friendly AI health information assistant")

# --- Session State Management ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hi! I'm SmartHealthChat. How are you feeling today?"}
    ]
if "last_audio" not in st.session_state:
    st.session_state.last_audio = None
if "whisper_model" not in st.session_state:
    with st.spinner("Loading voice model (first time only)..."):
        # Bypass SSL cert verification for model download (handles self-signed certs)
        _orig_ctx = ssl._create_default_https_context
        ssl._create_default_https_context = ssl._create_unverified_context
        try:
            st.session_state.whisper_model = whisper.load_model("base")
        finally:
            ssl._create_default_https_context = _orig_ctx

# --- SIDEBAR: Settings ---
with st.sidebar:
    st.header("⚙️ Settings")
    st.info("Select language for Voice Input & Output.")
    voice_lang = st.selectbox(
        "Language:",
        options=["en-IN", "hi-IN", "ta-IN", "te-IN", "mr-IN", "bn-IN", "gu-IN", "kn-IN", "ml-IN"],
        format_func=lambda x: {
            "en-IN": "English",
            "hi-IN": "Hindi (हिंदी)",
            "ta-IN": "Tamil (தமிழ்)",
            "te-IN": "Telugu (తెలుగు)",
            "mr-IN": "Marathi (मराठी)",
            "bn-IN": "Bengali (বাংলা)",
            "gu-IN": "Gujarati (ગુજરાતી)",
            "kn-IN": "Kannada (ಕನ್ನಡ)",
            "ml-IN": "Malayalam (മലയാളം)"
        }.get(x, x)
    )

# --- FUNCTION: Handle Chat (Text or Voice) ---
def handle_chat(user_input):
    # 1. Add user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 2. Get bot response from server
    api_url = "http://localhost:3000/ask"
    answer = "Sorry, I couldn't connect."

    try:
        response = requests.get(api_url, params={"q": user_input, "lang": voice_lang})
        if response.status_code == 200:
            answer = response.json().get("answer", "No answer found.")
        else:
            answer = f"Sorry, error: {response.status_code}"
    except requests.exceptions.RequestException:
        answer = "I'm sorry, I can't reach my brain right now."

    # 3. Save assistant message
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer
    })

# --- DISPLAY CHAT HISTORY ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- VOICE INPUT ---
st.write("---")
audio_value = st.audio_input("🎤 Tap to Speak")

# --- WHISPER LANGUAGE MAP ---
# Maps the app's BCP-47 locale codes to Whisper's language identifiers
WHISPER_LANG_MAP = {
    "en-IN": "en", "hi-IN": "hi", "ta-IN": "ta",
    "te-IN": "te", "mr-IN": "mr", "bn-IN": "bn",
    "gu-IN": "gu", "kn-IN": "kn", "ml-IN": "ml"
}

# --- PROCESS VOICE INPUT (100% LOCAL via Whisper) ---
if audio_value and audio_value != st.session_state.last_audio:
    st.session_state.last_audio = audio_value
    try:
        with st.spinner("Transcribing audio locally..."):
            # Write audio bytes to a temp WAV file that Whisper can read
            audio_bytes = audio_value.read()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            try:
                whisper_lang = WHISPER_LANG_MAP.get(voice_lang, "en")
                result = st.session_state.whisper_model.transcribe(
                    tmp_path,
                    language=whisper_lang,
                    fp16=False  # fp16=False avoids warnings on CPU/Apple Silicon
                )
                transcribed_text = result["text"].strip()
            finally:
                os.unlink(tmp_path)

        if transcribed_text:
            handle_chat(transcribed_text)
            st.rerun()
        else:
            st.warning("Could not detect any speech. Please try again.")
    except Exception as e:
        st.error(f"Voice error: {e}")

# --- TEXT INPUT ---
if prompt := st.chat_input("Type your health concern here..."):
    handle_chat(prompt)
    st.rerun()