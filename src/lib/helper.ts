import type { CaptionCue } from './captions';
import type { Box } from './preview';
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
/** Oldest helper that can prepare a preview of the final video. */
export const PREVIEW_HELPER_VERSION = '0.4.0';
/** Oldest helper that can preview and export a compilation of several scenes. */
export const COMPILATION_HELPER_VERSION = '0.5.0';
/** Oldest helper with gamer mode and the zip of a bulk export. */
export const GAMING_HELPER_VERSION = '0.6.0';

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

/** A stretch of the source video, in seconds. */
export interface Span {
  start: number;
  end: number;
}

export interface ExportParams {
  url: string;
  videoId?: string;
  title: string;
  /** One clip: its cut points. A compilation sends `segments` instead. */
  start?: number;
  end?: number;
  /** Scenes joined in this order into one video (helper 0.5.0+). */
  segments?: Span[];
  aspectRatio: '16:9' | '9:16_blur' | '9:16_crop' | '9:16_gaming';
  captionStyle: 'viral' | 'box' | 'classic' | 'neon' | 'none';
  captionPosition?: 'bottom' | 'center' | 'top';
  /** Caption cues timed from the start of the final video; the helper draws them. */
  cues?: CaptionCue[];
  /** Preview of this clip; its face path is reused so the export frames like the preview. */
  previewId?: string;
  /** Gamer mode: the gameplay and webcam areas; a null area is found automatically / centred. */
  gaming?: { face: Box | null; game: Box | null; faceTop: boolean };
}

/** Face-following path for the 9:16 crop: [seconds from clip start, left edge as a share of the width]. */
export interface CropPath {
  keys: [number, number][];
  /** Crop window width as a share of the source width. */
  width: number;
  faces: boolean;
}

export interface PreviewStatus {
  ok: boolean;
  id: string;
  status: 'pending' | 'downloading' | 'ready' | 'error';
  progress: number;
  message: string;
  error?: string | null;
  width?: number | null;
  height?: number | null;
  duration?: number | null;
  /** pending/running: still looking for faces; none: source already vertical; unavailable: no OpenCV. */
  crop_state?: 'pending' | 'running' | 'done' | 'none' | 'unavailable' | 'error' | null;
  crop_progress?: number;
  crop?: CropPath | null;
  /** Where the webcam is (gamer mode), found in the same face scan, and how steadily it was seen. */
  facecam?: { box: Box; support: number } | null;
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

/**
 * Asks the helper for a light copy of the clip, or of the scenes joined, to preview.
 * The same clip reuses its copy, and a compilation reuses the copies of its scenes.
 */
export async function startPreview(
  helperUrl: string,
  params: { url: string } & (Span | { segments: Span[] }),
): Promise<string> {
  let res: Response;
  try {
    res = await fetch(`${base(helperUrl)}/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  } catch {
    throw new Error('Tidak bisa menghubungi helper untuk menyiapkan pratinjau.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Helper error (${res.status})`);
  return data.id as string;
}

export async function checkPreviewStatus(helperUrl: string, id: string): Promise<PreviewStatus> {
  let res: Response;
  try {
    res = await fetch(`${base(helperUrl)}/preview/status?id=${encodeURIComponent(id)}`, { cache: 'no-store' });
  } catch {
    throw new Error('Helper tidak menjawab saat menyiapkan pratinjau.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Pratinjau tidak ditemukan.');
  return data as PreviewStatus;
}

/** One .zip of finished exports, in this order. */
export function exportZipUrl(helperUrl: string, jobIds: string[], name: string): string {
  return `${base(helperUrl)}/export/zip?jobs=${jobIds.map(encodeURIComponent).join(',')}&name=${encodeURIComponent(name)}`;
}

export function previewVideoUrl(helperUrl: string, id: string): string {
  return `${base(helperUrl)}/preview/video?id=${encodeURIComponent(id)}`;
}
