import os
from typing import List, Set

NIM_SPEECH_GRPC_URI = os.environ.get("NIM_SPEECH_GRPC_URI", "grpc.nvcf.nvidia.com:443")
NIM_TTS_FUNCTION_ID = os.environ.get(
    "NIM_TTS_FUNCTION_ID", "877104f7-e885-42b9-8de8-f6e4c6303969"
)
NIM_ASR_FUNCTION_ID = os.environ.get(
    "NIM_ASR_FUNCTION_ID", "bb0837de-8c7b-481f-9ec8-ef5663e9c1fa"
)

# NVIDIA Magpie offers no British (EN-GB) voices - only EN-US for English. "Ray" is the
# deepest/most measured EN-US male, which - combined with a lowered playback rate (see
# JARVIS_VOICE_RATE_SCALE) - best approximates an older, distinguished butler. Override with
# JARVIS_BUTLER_VOICE to audition others (e.g. Magpie-Multilingual.EN-US.Leo.Calm).
BUTLER_VOICE = os.environ.get(
    "JARVIS_BUTLER_VOICE", "Magpie-Multilingual.EN-US.Ray.Calm"
)
BUTLER_VOICE_FALLBACKS: List[str] = [
    "Magpie-Multilingual.EN-US.Ray.Calm",
    "Magpie-Multilingual.EN-US.Ray",
    "Magpie-Multilingual.EN-US.Jason.Calm",
    "Magpie-Multilingual.EN-US.Jason",
    "Magpie-Multilingual.EN-US.Leo.Calm",
    "Magpie-Multilingual.EN-US.Leo",
]
BUTLER_LANGUAGE = os.environ.get("JARVIS_BUTLER_LANGUAGE", "en-US")
MALE_SPEAKERS: Set[str] = {"Jason", "Leo", "Ray", "Pascal", "Diego", "John Van Stan"}
FEMALE_SPEAKERS: Set[str] = {"Sofia", "Aria", "Isabela", "Mia", "Louise"}

# Playback rate multiplier applied to synthesized speech. Values < 1.0 lower the pitch and
# slow the cadence for an older, more gravelly/measured delivery. Magpie rejects SSML prosody,
# so this is applied via the output WAV sample-rate header. Clamped to a sane range.
try:
    VOICE_RATE_SCALE = float(os.environ.get("JARVIS_VOICE_RATE_SCALE", "0.92"))
except ValueError:
    VOICE_RATE_SCALE = 0.92
VOICE_RATE_SCALE = max(0.75, min(1.25, VOICE_RATE_SCALE))

VOICE_MODE_PREF_KEY = "voice_mode_enabled"
TTS_SAMPLE_RATE_HZ = 22050
ASR_SAMPLE_RATE_HZ = 16000
MAX_TTS_CHARS = 4000
