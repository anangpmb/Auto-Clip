import type { CaptionCue } from './captions';
import type { Track, VideoInfo, Word, WordTiming } from './types';

export interface HelperHealth {
  ok: boolean;
  error?: string;
  origin?: string;
  version?: string;
  yt_dlp?: string | null;
  ffmpeg?: boolean;
  /** OpenCV is installed, so 9:16 crops follow faces. */
  face_detect?: boolean;
  /** Pillow is installed, so captions can be burned in. */
  captions?: boolean;
  js_runtime?: string | null;
}

/** Oldest helper whose /export understands `cues` and face tracking. */
export const EXPORT_HELPER_VERSION = '0.3.0';

/** True when version a is older than b (dotted numbers). */
export function versionBefore(a: string | undefined, b: string): boolean {
  const pa = (a ?? '0').split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d < 0;
  }
  return false;
}

export interface CaptionsResult {
  video: VideoInfo;
  tracks: Track[];
  track: string;
  wordTiming: WordTiming;
  words: Word[];
}

export interface ExportParams {
  url: string;
  videoId?: string;
  title: string;
  start: number;
  end: number;
  aspectRatio: '16:9' | '9:16_blur' | '9:16_crop';
  captionStyle: 'viral' | 'box' | 'classic' | 'neon' | 'none';
  captionPosition?: 'bottom' | 'center' | 'top';
  /** Caption cues with word timings relative to the clip start; the helper draws them. */
  cues?: CaptionCue[];
}

export interface ExportStatus {
  ok: boolean;
  jobId: string;
  status: 'pending' | 'downloading' | 'analyzing' | 'rendering' | 'done' | 'error';
  progress: number;
  message: string;
  filename?: string;
  error?: string;
  /** Things the helper did differently, e.g. a centre crop because no face was found. */
  notes?: string[];
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

/**
 * Starts a video export job on the helper.
 */
export async function startExport(helperUrl: string, params: ExportParams): Promise<{ jobId: string }> {
  let res: Response;
  try {
    res = await fetch(`${base(helperUrl)}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  } catch {
    throw new Error('Tidak bisa menghubungi helper untuk merender video.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Helper error (${res.status})`);
  return { jobId: data.jobId };
}

/**
 * Polls the current status of an export job.
 */
export async function checkExportStatus(helperUrl: string, jobId: string): Promise<ExportStatus> {
  let res: Response;
  try {
    res = await fetch(`${base(helperUrl)}/export/status?jobId=${encodeURIComponent(jobId)}`, {
      cache: 'no-store',
    });
  } catch {
    throw new Error('Gagal memeriksa status proses ekspor.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Status tidak ditemukan.');
  return data as ExportStatus;
}

/**
 * Gets the direct download link for an exported video.
 */
export function getExportDownloadUrl(helperUrl: string, jobId: string): string {
  return `${base(helperUrl)}/export/download?jobId=${encodeURIComponent(jobId)}`;
}
