import { useCallback, useEffect, useRef, useState } from 'react';
import {
  VoiceStatus,
  getVoiceStatus,
  setVoiceMode,
  synthesizeSpeech,
  transcribeAudio,
} from '../lib/api';

export function useVoiceMode() {
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speechQueueRef = useRef<Promise<void>>(Promise.resolve());

  const refreshStatus = useCallback(async () => {
    const status = await getVoiceStatus();
    if (status) {
      setVoiceStatus(status);
      setVoiceEnabled(Boolean(status.enabled));
    }
    return status;
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const toggleVoiceMode = useCallback(async (enabled?: boolean) => {
    const next = enabled ?? !voiceEnabled;
    await setVoiceMode(next);
    setVoiceEnabled(next);
    await refreshStatus();
    return next;
  }, [voiceEnabled, refreshStatus]);

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

  const speakText = useCallback(async (text: string) => {
    if (!voiceEnabled || !text.trim()) return;
    speechQueueRef.current = speechQueueRef.current.then(async () => {
      const blob = await synthesizeSpeech(text);
      if (blob) {
        await playBlob(blob);
      }
    });
    await speechQueueRef.current;
  }, [voiceEnabled, playBlob]);

  const stopRecordingStream = useCallback(() => {
    mediaRecorderRef.current = null;
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  const startRecording = useCallback(async () => {
    if (!voiceEnabled || isRecording || isTranscribing) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaStreamRef.current = stream;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    mediaRecorderRef.current = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };
    recorder.start();
    setIsRecording(true);
  }, [voiceEnabled, isRecording, isTranscribing]);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (!mediaRecorderRef.current || !isRecording) return null;

    const recorder = mediaRecorderRef.current;
    const transcriptPromise = new Promise<string | null>((resolve) => {
      recorder.onstop = async () => {
        stopRecordingStream();
        setIsRecording(false);
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        chunksRef.current = [];
        if (blob.size === 0) {
          resolve(null);
          return;
        }
        setIsTranscribing(true);
        try {
          const text = await transcribeAudio(blob);
          resolve(text);
        } finally {
          setIsTranscribing(false);
        }
      };
    });

    recorder.stop();
    return transcriptPromise;
  }, [isRecording, stopRecordingStream]);

  useEffect(() => {
    return () => {
      stopRecordingStream();
      if (audioRef.current) {
        audioRef.current.pause();
        URL.revokeObjectURL(audioRef.current.src);
      }
    };
  }, [stopRecordingStream]);

  const voiceLabel = voiceStatus?.voice
    ? voiceStatus.voice.split('.').slice(-2).join(' · ')
    : 'Male Butler';

  return {
    voiceEnabled,
    voiceStatus,
    voiceLabel,
    isRecording,
    isTranscribing,
    isSpeaking,
    refreshStatus,
    toggleVoiceMode,
    speakText,
    startRecording,
    stopRecording,
  };
}
