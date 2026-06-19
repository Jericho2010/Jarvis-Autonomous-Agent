import os
from typing import List, Set

NIM_SPEECH_GRPC_URI = os.environ.get("NIM_SPEECH_GRPC_URI", "grpc.nvcf.nvidia.com:443")
NIM_TTS_FUNCTION_ID = os.environ.get(
    "NIM_TTS_FUNCTION_ID", "877104f7-e885-42b9-8de8-f6e4c6303969"
)
NIM_ASR_FUNCTION_ID = os.environ.get(
    "NIM_ASR_FUNCTION_ID", "bb0837de-8c7b-481f-9ec8-ef5663e9c1fa"
)

BUTLER_VOICE = os.environ.get(
    "JARVIS_BUTLER_VOICE", "Magpie-Multilingual.EN-US.Jason.Calm"
)
BUTLER_VOICE_FALLBACKS: List[str] = [
    "Magpie-Multilingual.EN-US.Jason.Calm",
    "Magpie-Multilingual.EN-US.Jason",
    "Magpie-Multilingual.EN-US.Leo.Calm",
    "Magpie-Multilingual.EN-US.Leo",
    "Magpie-Multilingual.EN-US.John Van Stan",
]
BUTLER_LANGUAGE = os.environ.get("JARVIS_BUTLER_LANGUAGE", "en-US")
MALE_SPEAKERS: Set[str] = {"Jason", "Leo", "John Van Stan"}
FEMALE_SPEAKERS: Set[str] = {"Sofia", "Aria"}

VOICE_MODE_PREF_KEY = "voice_mode_enabled"
TTS_SAMPLE_RATE_HZ = 22050
ASR_SAMPLE_RATE_HZ = 16000
MAX_TTS_CHARS = 4000

VOICE_MODE_SYSTEM_APPEND = """
# VOICE MODE (ACTIVE)
The platform speaks your replies automatically via NVIDIA TTS (male English butler voice) after each turn.
- Write normal plain-English replies only.
- When asked to say something aloud, put the words in your text response.
- Do NOT use espeak, festival, say, aplay, paplay, or any shell/audio command to produce speech.
- Do NOT use execute_bash to speak. Never invoke TTS yourself — the system handles audio.
"""
