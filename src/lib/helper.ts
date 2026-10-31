import type { Track, VideoInfo, Word, WordTiming } from './types';

export interface HelperHealth {
  ok: boolean;
  error?: string;
  origin?: string;
  version?: string;
  yt_dlp?: string | null;
  ffmpeg?: boolean;
  js_runtime?: string | null;
}

export interface CaptionsResult {
  video: VideoInfo;
  tracks: Track[];
  track: string;
  wordTiming: WordTiming;
  words: Word[];
}

const base = (url: string) => url.trim().replace(/\/+$/, '');

/** Null when the helper is not reachable. */
export async function checkHelper(helperUrl: string): Promise<HelperHealth | null> {
  try {
    const res = await fetch(`${base(helperUrl)}/health`, { signal: AbortSignal.timeout(2500), cache: 'no-store' });
    return (await res.json()) as HelperHealth;
  } catch {
    return null;
  }
}

export async function fetchCaptions(helperUrl: string, url: string, track?: string, signal?: AbortSignal): Promise<CaptionsResult> {
  let res: Response;
  try {
    res = await fetch(`${base(helperUrl)}/captions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, track }),
      signal,
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new Error('Tidak bisa menghubungi helper. Pastikan helper sedang berjalan.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Helper error (${res.status})`);
  return {
    video: data.video,
    tracks: data.tracks,
    track: data.track,
    wordTiming: data.word_timing,
    words: (data.words as [number, number, string][]).map(([s, e, t]) => ({ s, e, t })),
  };
}
