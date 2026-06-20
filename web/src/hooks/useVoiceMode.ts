import { useCallback, useEffect, useRef, useState } from 'react';
import {
  VoiceStatus,
  getVoiceStatus,
  setVoiceMode,
  synthesizeSpeech,
  transcribeAudio,
} from '../lib/api';

const MIN_RECORDING_MS = 1500;
const MIN_PEAK_AUDIO_LEVEL = 2;
const STT_SAMPLE_RATE = 16000;
const MIC_DEVICE_STORAGE_KEY = 'jarvis.voice.inputDeviceId';

function resamplePcm(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const outputLength = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const srcIndex = i * ratio;
    const idx = Math.floor(srcIndex);
    const frac = srcIndex - idx;
    const a = input[idx] ?? 0;
    const b = input[idx + 1] ?? a;
    output[i] = a + (b - a) * frac;
  }
  return output;
}

function floatTo16BitPCM(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

function pcm16Rms(pcm: Int16Array): number {
  if (pcm.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < pcm.length; i += 1) {
    sum += pcm[i] * pcm[i];
  }
  return Math.sqrt(sum / pcm.length);
}

function encodeWavBlob(pcm16: Int16Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample;
  const dataSize = pcm16.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < pcm16.length; i += 1) {
    view.setInt16(offset, pcm16[i], true);
    offset += 2;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

export function useVoiceMode() {
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [audioInputs, setAudioInputs] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceIdState] = useState<string>(() => {
    try {
      return window.localStorage.getItem(MIC_DEVICE_STORAGE_KEY) || '';
    } catch {
      return '';
    }
  });
  const [micMuted, setMicMuted] = useState(false);

  const selectedDeviceIdRef = useRef(selectedDeviceId);
  const voiceEnabledRef = useRef(false);
  const isRecordingRef = useRef(false);
  const isStoppingRef = useRef(false);
  const recordingStartedAtRef = useRef(0);
  const peakAudioLevelRef = useRef(0);
  const recordingTimerRef = useRef<number | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const pcmChunksRef = useRef<Float32Array[]>([]);
  const captureSampleRateRef = useRef(48000);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speechQueueRef = useRef<Promise<void>>(Promise.resolve());
  const audioContextRef = useRef<AudioContext | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const silentGainRef = useRef<GainNode | null>(null);

  useEffect(() => {
    voiceEnabledRef.current = voiceEnabled;
  }, [voiceEnabled]);

  useEffect(() => {
    selectedDeviceIdRef.current = selectedDeviceId;
  }, [selectedDeviceId]);

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const inputs = devices.filter((d) => d.kind === 'audioinput');
      setAudioInputs(inputs);
      return inputs;
    } catch {
      return [];
    }
  }, []);

  const setSelectedDeviceId = useCallback((deviceId: string) => {
    selectedDeviceIdRef.current = deviceId;
    setSelectedDeviceIdState(deviceId);
    try {
      if (deviceId) {
        window.localStorage.setItem(MIC_DEVICE_STORAGE_KEY, deviceId);
      } else {
        window.localStorage.removeItem(MIC_DEVICE_STORAGE_KEY);
      }
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    void refreshDevices();
    if (!navigator.mediaDevices) return;
    const handler = () => {
      void refreshDevices();
    };
    navigator.mediaDevices.addEventListener?.('devicechange', handler);
    return () => {
      navigator.mediaDevices.removeEventListener?.('devicechange', handler);
    };
  }, [refreshDevices]);

  const clearRecordingTimer = useCallback(() => {
    if (recordingTimerRef.current !== null) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    setRecordingSeconds(0);
    setAudioLevel(0);
    peakAudioLevelRef.current = 0;
  }, []);

  const refreshStatus = useCallback(async () => {
    const status = await getVoiceStatus();
    if (status) {
      setVoiceStatus(status);
      setVoiceEnabled(Boolean(status.enabled));
      voiceEnabledRef.current = Boolean(status.enabled);
    }
    return status;
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const toggleVoiceMode = useCallback(async (enabled?: boolean) => {
    const next = enabled ?? !voiceEnabledRef.current;
    voiceEnabledRef.current = next;
    setVoiceEnabled(next);
    await setVoiceMode(next);
    await refreshStatus();
    return next;
  }, [refreshStatus]);

  const playBlob = useCallback(async (blob: Blob) => {
    if (audioRef.current) {
      audioRef.current.pause();
      URL.revokeObjectURL(audioRef.current.src);
    }
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audioRef.current = audio;
    setIsSpeaking(true);
    await new Promise<void>((resolve, reject) => {
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setIsSpeaking(false);
        resolve();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        setIsSpeaking(false);
        reject(new Error('Audio playback failed'));
      };
      void audio.play().catch(reject);
    });
  }, []);

  const playSpeech = useCallback(async (text: string) => {
    if (!text.trim()) return;
    speechQueueRef.current = speechQueueRef.current.then(async () => {
      const blob = await synthesizeSpeech(text);
      if (blob) {
        await playBlob(blob);
      }
    });
    await speechQueueRef.current;
  }, [playBlob]);

  const cleanupRecording = useCallback(() => {
    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.onaudioprocess = null;
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    if (silentGainRef.current) {
      silentGainRef.current.disconnect();
      silentGainRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    pcmChunksRef.current = [];
    isRecordingRef.current = false;
    isStoppingRef.current = false;
    setIsRecording(false);
    clearRecordingTimer();
  }, [clearRecordingTimer]);

  const startRecording = useCallback(async () => {
    if (!voiceEnabledRef.current || isRecordingRef.current || isStoppingRef.current || isTranscribing) {
      return false;
    }
    setVoiceError(null);
    try {
      const deviceId = selectedDeviceIdRef.current;
      const audioConstraints: MediaTrackConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      };
      if (deviceId) {
        audioConstraints.deviceId = { exact: deviceId };
      }
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
      } catch (constraintErr) {
        if (deviceId) {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          });
        } else {
          throw constraintErr;
        }
      }
      mediaStreamRef.current = stream;

      // Re-enumerate now that we have permission (device labels become available).
      void refreshDevices();

      const audioTrack = stream.getAudioTracks()[0];
      if (audioTrack) {
        setMicMuted(audioTrack.muted);
        audioTrack.onmute = () => {
          setMicMuted(true);
          setVoiceError('Microphone is muted at the OS level - unmute it or pick another input.');
        };
        audioTrack.onunmute = () => {
          setMicMuted(false);
        };
        if (audioTrack.muted) {
          setVoiceError('Microphone is muted at the OS level - unmute it or pick another input.');
        }
      }

      pcmChunksRef.current = [];
      peakAudioLevelRef.current = 0;

      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }
      captureSampleRateRef.current = audioContext.sampleRate;

      const source = audioContext.createMediaStreamSource(stream);
      sourceNodeRef.current = source;
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      scriptProcessorRef.current = processor;
      processor.onaudioprocess = (event) => {
        if (!isRecordingRef.current) return;
        const channel = event.inputBuffer.getChannelData(0);
        pcmChunksRef.current.push(new Float32Array(channel));

        let sumSquares = 0;
        for (let i = 0; i < channel.length; i += 1) {
          sumSquares += channel[i] * channel[i];
        }
        const rms = Math.sqrt(sumSquares / channel.length);
        const level = Math.min(100, Math.round(rms * 500));
        setAudioLevel(level);
        if (level > peakAudioLevelRef.current) {
          peakAudioLevelRef.current = level;
        }
      };

      const silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      silentGainRef.current = silentGain;
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioContext.destination);

      recordingStartedAtRef.current = Date.now();
      isRecordingRef.current = true;
      setIsRecording(true);
      recordingTimerRef.current = window.setInterval(() => {
        const elapsed = Date.now() - recordingStartedAtRef.current;
        setRecordingSeconds(Math.max(0, Math.floor(elapsed / 1000)));
      }, 250);

      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Microphone access denied';
      setVoiceError(message);
      cleanupRecording();
      return false;
    }
  }, [cleanupRecording, isTranscribing, refreshDevices]);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (isStoppingRef.current) {
      return null;
    }
    if (!isRecordingRef.current) {
      return null;
    }

    isStoppingRef.current = true;
    isRecordingRef.current = false;
    const elapsedMs = Date.now() - recordingStartedAtRef.current;
    const peakLevel = peakAudioLevelRef.current;

    if (elapsedMs < MIN_RECORDING_MS) {
      cleanupRecording();
      setVoiceError(`Speak for at least ${MIN_RECORDING_MS / 1000} seconds, then click mic again.`);
      return null;
    }

    setIsTranscribing(true);
    try {
      const chunks = pcmChunksRef.current.slice();
      const captureRate = captureSampleRateRef.current;
      cleanupRecording();

      const totalSamples = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const merged = new Float32Array(totalSamples);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }

      const resampled = resamplePcm(merged, captureRate, STT_SAMPLE_RATE);
      const pcm16 = floatTo16BitPCM(resampled);
      const clientRms = pcm16Rms(pcm16);
      const durationS = resampled.length / STT_SAMPLE_RATE;
      const blob = encodeWavBlob(pcm16, STT_SAMPLE_RATE);

      if (peakLevel < MIN_PEAK_AUDIO_LEVEL || clientRms < 150) {
        setVoiceError(
          'No microphone signal detected. Check your input device in system settings and ensure the mic is not muted.',
        );
        return null;
      }

      if (durationS < 0.4) {
        setVoiceError('Recording was too short. Speak for at least 2 seconds.');
        return null;
      }

      const result = await transcribeAudio(blob, 'audio/wav');

      if (result.text.trim()) {
        setVoiceError(null);
        return result.text.trim();
      }

      if (result.error === 'silent_audio') {
        setVoiceError('Microphone captured silence only. Select the correct input device and speak louder.');
      } else {
        setVoiceError('Could not transcribe speech. Speak clearly for 2+ seconds near the microphone.');
      }
      return null;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Transcription failed';
      setVoiceError(message);
      cleanupRecording();
      return null;
    } finally {
      setIsTranscribing(false);
      isStoppingRef.current = false;
    }
  }, [audioLevel, cleanupRecording]);

  useEffect(() => {
    return () => {
      cleanupRecording();
      if (audioRef.current) {
        audioRef.current.pause();
        URL.revokeObjectURL(audioRef.current.src);
      }
    };
  }, [cleanupRecording]);

  const voiceLabel = voiceStatus?.voice
    ? voiceStatus.voice.split('.').slice(-2).join(' · ')
    : 'Male Butler';

  return {
    voiceEnabled,
    voiceStatus,
    voiceLabel,
    voiceError,
    isRecording,
    isTranscribing,
    isSpeaking,
    recordingSeconds,
    audioLevel,
    micMuted,
    audioInputs,
    selectedDeviceId,
    setSelectedDeviceId,
    refreshDevices,
    refreshStatus,
    toggleVoiceMode,
    speakText: useCallback(async (text: string) => {
      if (!voiceEnabledRef.current || !text.trim()) return;
      await playSpeech(text);
    }, [playSpeech]),
    playSpeech,
    startRecording,
    stopRecording,
  };
}
