/** Picking a usable frame for a clip thumbnail. */

export const DARK_FRAME_LUMA = 16;
/** How far to step forward when the frame at the current time is dark. */
export const THUMBNAIL_STEP_SECONDS = 0.5;
/** Most frames tried for one thumbnail, including the first. */
export const THUMBNAIL_MAX_ATTEMPTS = 6;

/**
 * Times, in seconds, to try for a thumbnail, starting where the old code looked
 * (at most one second into the clip) and stepping forward. A clip that starts
 * with a fade or a dark cut is black at that first time, so one fixed time is
 * not a frame choice, it is a gamble on the clip's first second.
 */
export function thumbnailSeekTimes(duration: number): number[] {
  if (!Number.isFinite(duration) || duration <= 0) return [0];
  const start = +Math.min(1, Math.max(0, duration / 3)).toFixed(3);
  const times = [start];
  let t = start;
  while (times.length < THUMBNAIL_MAX_ATTEMPTS) {
    t = +(t + THUMBNAIL_STEP_SECONDS).toFixed(3);
    if (t > duration - 0.05) break;
    times.push(t);
  }
  return times;
}

/**
 * Mean luminance (0-255) of RGBA pixel data, sampling every 16th pixel so a
 * full 720x1280 read stays cheap. A frame that decoded to black, or a scene
 * that is genuinely dark, reads close to 0; an ordinary frame reads far above.
 */
export function meanLuminance(data: Uint8ClampedArray): number {
  if (data.length < 4) return 0;
  const step = 16 * 4;
  let sum = 0;
  let n = 0;
  for (let i = 0; i + 3 < data.length; i += step) {
    sum += 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
    n++;
  }
  return n ? sum / n : 0;
}

export function isDarkFrame(luma: number): boolean {
  return luma < DARK_FRAME_LUMA;
}
