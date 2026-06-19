export interface Session {
  session_id: string;
  started_at: number;
  title?: string;
  agent_id?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: number;
  tool_name?: string;
  reasoning?: string;
}

export interface SubagentStatus {
  name: string;
  activity: 'working' | 'awaiting' | 'done' | 'failed' | 'idle';
  lastMessage?: string;
  nestedLevel: number;
}

let activePort: number | null = null;
const START_PORT = 8008;
const MAX_SCAN = 8;

export async function discoverPort(): Promise<number> {
  if (activePort !== null) return activePort;

  // If the Web UI is served directly from J.A.R.V.I.S., use that port
  if (window.location.port && window.location.port !== '5173') {
    const portNum = parseInt(window.location.port, 10);
    if (!isNaN(portNum)) {
      activePort = portNum;
      return activePort;
    }
  }

  // First check if a port is specified in query parameters
  const params = new URLSearchParams(window.location.search);
  const queryPort = params.get('port');
  if (queryPort) {
    const portNum = parseInt(queryPort, 10);
    if (!isNaN(portNum)) {
      try {
        const res = await fetch(`http://127.0.0.1:${portNum}/health`);
        const data = await res.json();
        if (data.service === 'jarvis') {
          activePort = portNum;
          return activePort;
        }
      } catch (e) {
        // Fall back to scanning
      }
    }
  }

  // Scan ports sequentially
  for (let offset = 0; offset < MAX_SCAN; offset++) {
    const port = START_PORT + offset;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 800);
      
      const res = await fetch(`http://127.0.0.1:${port}/health`, {
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      
      if (res.ok) {
        const data = await res.json();
        if (data.service === 'jarvis') {
          activePort = port;
          console.log(`[J.A.R.V.I.S. HUD] Discovered active API server on port ${port}`);
          return activePort;
        }
      }
    } catch (e) {
      // Port closed or not jarvis
    }
  }

  // Fallback to default port
  console.warn(`[J.A.R.V.I.S. HUD] No active API server found, using default port ${START_PORT}`);
  activePort = START_PORT;
  return START_PORT;
}

export async function getApiUrl(): Promise<string> {
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost.localdomain') {
    if (window.location.port !== '5173' && window.location.port !== '') {
      return `${window.location.protocol}//${window.location.host}`;
    }
  }
  const port = await discoverPort();
  return `http://127.0.0.1:${port}`;
}

export async function listSessions(): Promise<Session[]> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/sessions`);
    if (!res.ok) throw new Error('Failed to fetch sessions');
    return await res.json();
  } catch (e) {
    console.error(e);
    return [];
  }
}

export async function createSession(): Promise<string> {
  const baseUrl = await getApiUrl();
  const res = await fetch(`${baseUrl}/v1/sessions`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to create session');
  const data = await res.json();
  return data.session_id;
}

export async function sendChatMessage(
  sessionId: string, 
  message: string, 
  files?: { id: string, filename: string, bytes: number }[]
): Promise<boolean> {
  const baseUrl = await getApiUrl();
  const res = await fetch(`${baseUrl}/v1/sessions/${sessionId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message, client_id: 'web', files })
  });
  return res.ok;
}

export async function uploadSessionFile(
  sessionId: string, 
  file: File
): Promise<{ id: string, filename: string, bytes: number }> {
  const baseUrl = await getApiUrl();
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${baseUrl}/v1/sessions/${sessionId}/files`, {
    method: 'POST',
    body: formData
  });
  if (!res.ok) throw new Error('Failed to upload file');
  return await res.json();
}

export async function switchSessionAgent(sessionId: string, agentId: string): Promise<boolean> {
  const baseUrl = await getApiUrl();
  const res = await fetch(`${baseUrl}/v1/sessions/${sessionId}/switch-agent`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ agent_id: agentId })
  });
  return res.ok;
}

export interface VoiceStatus {
  enabled: boolean;
  voice: string | null;
  language: string | null;
  gender: string | null;
  persona_warning?: string | null;
  tts_available: boolean;
  stt_available: boolean;
  error?: string | null;
}

export async function getVoiceStatus(): Promise<VoiceStatus | null> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/voice/status`);
    if (!res.ok) throw new Error('Failed to fetch voice status');
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function setVoiceMode(enabled: boolean): Promise<{ enabled: boolean } | null> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/voice/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || 'Failed to update voice mode');
    }
    return await res.json();
  } catch (e) {
    console.error(e);
    throw e;
  }
}

export async function synthesizeSpeech(text: string): Promise<Blob | null> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error('Failed to synthesize speech');
    return await res.blob();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function transcribeAudio(blob: Blob, mimeType = 'audio/webm'): Promise<string | null> {
  try {
    const baseUrl = await getApiUrl();
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');
    const res = await fetch(`${baseUrl}/v1/voice/stt`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error('Failed to transcribe audio');
    const data = await res.json();
    return data.text || '';
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function getSessionStream(
  sessionId: string, 
  onEvent: (event: string, data: any) => void
): Promise<EventSource> {
  const baseUrl = await getApiUrl();
  const eventSource = new EventSource(`${baseUrl}/v1/sessions/${sessionId}/stream?client_id=web`);
  
  const eventTypes = [
    'text_chunk', 
    'reasoning_chunk', 
    'tool_call_start', 
    'tool_call_complete', 
    'turn_complete', 
    'user_message',
    'agent_changed',
    'title_changed',
    'voice_ready'
  ];
  
  eventTypes.forEach(type => {
    eventSource.addEventListener(type, (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent(type, data);
      } catch (err) {
        console.error(`Failed to parse event ${type}:`, err);
      }
    });
  });
  
  return eventSource;
}

export interface SubagentDetail {
  name: string;
  model: string;
  instructions: string;
  tools: { name: string; description: string }[];
}

export async function getSessionHistory(sessionId: string): Promise<ChatMessage[]> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/sessions/${sessionId}/history`);
    if (!res.ok) throw new Error('Failed to fetch session history');
    return await res.json();
  } catch (e) {
    console.error(e);
    return [];
  }
}

export async function getSubagentDetails(name: string): Promise<SubagentDetail | null> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/subagents/${name}`);
    if (!res.ok) throw new Error('Failed to fetch subagent details');
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function getSessionDetail(sessionId: string): Promise<any> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/sessions/${sessionId}`);
    if (!res.ok) throw new Error('Failed to fetch session details');
    return await res.json();
  } catch (e) {
    console.error(e);
    return null;
  }
}

export async function getSessionModel(sessionId: string): Promise<string> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/sessions/${sessionId}`);
    if (!res.ok) throw new Error('Failed to fetch session details');
    const data = await res.json();
    return data.model || 'house-party';
  } catch (e) {
    console.error(e);
    return 'house-party';
  }
}

export async function setSessionModel(sessionId: string, model: string): Promise<boolean> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/sessions/${sessionId}/model`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ model })
    });
    return res.ok;
  } catch (e) {
    console.error(e);
    return false;
  }
}

export async function getAvailableModels(): Promise<string[]> {
  try {
    const baseUrl = await getApiUrl();
    const res = await fetch(`${baseUrl}/v1/models`);
    if (!res.ok) throw new Error('Failed to fetch models');
    const data = await res.json();
    return data.models || [];
  } catch (e) {
    console.error(e);
    return [];
  }
}
