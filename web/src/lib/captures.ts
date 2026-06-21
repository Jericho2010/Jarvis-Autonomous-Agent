/** Extract a capture path or URL from tool output or streamed assistant text. */
export function extractCapturePath(text: string): string | null {
  if (!text?.trim()) return null;

  try {
    const parsed = JSON.parse(text);
    if (parsed?.url && typeof parsed.url === 'string') {
      return parsed.url;
    }
    if (parsed?.path && typeof parsed.path === 'string') {
      const p = parsed.path;
      return p.startsWith('/') ? p : `/v1/captures/${p.replace(/^webvision\//, '')}`;
    }
  } catch {
    // not JSON — fall through to regex
  }

  const urlMatch = text.match(/(\/v1\/captures\/[^\s"']+\.(?:png|jpg|jpeg|webp))/i);
  if (urlMatch?.[1]) return urlMatch[1];

  const webvisionMatch = text.match(/webvision\/([^\s"']+\.(?:png|jpg|jpeg|webp))/i);
  if (webvisionMatch?.[1]) return `/v1/captures/${webvisionMatch[1]}`;

  return null;
}

export async function resolveCaptureUrl(
  capturePath: string,
  getApiUrl: () => Promise<string>,
): Promise<string> {
  if (capturePath.startsWith('http')) return capturePath;
  const baseUrl = await getApiUrl();
  return `${baseUrl}${capturePath.startsWith('/') ? capturePath : `/${capturePath}`}`;
}
