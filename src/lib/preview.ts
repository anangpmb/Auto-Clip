import type { AspectRatio, CaptionCue } from './captions';

/** How the export places the source in the frame (mirrors the helper's render step). */
export type Layout = 'fit' | 'blur' | 'crop' | 'gaming';

/** [x, y, width, height] as shares of the source frame. */
export type Box = [number, number, number, number];

/** Gamer mode slots in the 1080x1920 frame: gameplay over two thirds, the webcam in one. */
export const GAME_ASPECT = 1080 / 1280;
export const FACE_ASPECT = 1080 / 640;
export const FULL_FRAME: Box = [0, 0, 1, 1];

export function layoutFor(aspect: AspectRatio, srcW?: number | null, srcH?: number | null): Layout {
  if (aspect === '16:9') return 'fit';
  if (aspect === '9:16_blur') return 'blur';
  if (aspect === '9:16_gaming') return 'gaming';
  // A source narrower than 9:16 cannot be cropped; the helper falls back to the blur layout.
  if (srcW && srcH && Math.round((srcH * 9) / 16) > srcW) return 'blur';
  return 'crop';
}

/** Left edge of a centred 9:16 crop, as a share of the source width. */
export function centerCropX(srcW: number, srcH: number): number {
  return Math.max(0, (1 - (srcH * 9) / 16 / srcW) / 2);
}

/**
 * Left edge of the crop window (share of the source width) at t seconds into the clip.
 * Linear between keys, like the ffmpeg expression the export renders with.
 */
export function cropXAt(keys: [number, number][], t: number): number {
  if (!keys.length) return NaN;
  let lo = 0;
  let hi = keys.length - 1;
  if (t <= keys[lo][0]) return keys[lo][1];
  if (t >= keys[hi][0]) return keys[hi][1];
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (keys[mid][0] <= t) lo = mid;
    else hi = mid;
  }
  const [ta, xa] = keys[lo];
  const [tb, xb] = keys[hi];
  return tb > ta ? xa + ((xb - xa) * (t - ta)) / (tb - ta) : xb;
}

/**
 * Index of the highlighted word in a cue at t (seconds from clip start), or -1.
 * Like the export, a word stays lit until the next one starts, so the highlight never blinks off mid-cue.
 */
export function activeWordIndex(cue: CaptionCue, t: number): number {
  let idx = -1;
  for (let i = 0; i < cue.words.length && cue.words[i].start <= t; i++) idx = i;
  return idx;
}

/**
 * A box made exactly `aspect` (width / height in pixels) around its centre and inside the
 * frame, as the helper's fit_box does before cropping. `FULL_FRAME` becomes the largest
 * centred box of that shape.
 */
export function fitBox(box: Box, srcW: number, srcH: number, aspect: number): Box {
  const [x, y, w, h] = box;
  const cx = (x + w / 2) * srcW;
  const cy = (y + h / 2) * srcH;
  let ph = Math.max(32, h * srcH);
  let pw = ph * aspect;
  if (pw > srcW) [pw, ph] = [srcW, srcW / aspect];
  if (ph > srcH) [pw, ph] = [srcH * aspect, srcH];
  const px = Math.min(Math.max(cx - pw / 2, 0), srcW - pw);
  const py = Math.min(Math.max(cy - ph / 2, 0), srcH - ph);
  return [px / srcW, py / srcH, pw / srcW, ph / srcH];
}

/** Where captions go in gamer mode: over the gameplay, as shares of the frame height. */
export function gamingCaptionArea(faceTop: boolean): { top: number; height: number } {
  return faceTop ? { top: 1 / 3, height: 2 / 3 } : { top: 0, height: 2 / 3 };
}
