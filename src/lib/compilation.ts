import { groupWordsIntoCues, type CaptionCue, type CaptionOptions } from './captions';
import { clipBoundsOrTime } from './transcript';
import type { Clip, Word } from './types';

/**
 * One scene of the final video: a clip's cut points in the source. A normal export has one
 * scene; a compilation plays several back to back. A time-anchored clip (no transcript)
 * maps straight through; a word clip keeps its word range so captions can be derived.
 */
export interface Scene {
  id: string;
  title: string;
  w0: number;
  w1: number;
  start: number;
  end: number;
  /** True when the clip has no transcript (t0/t1), so captions are unavailable. */
  timeless?: boolean;
}

/** Same limit as the helper's: one clip or a whole compilation. */
export const MAX_FINAL_SECONDS = 10 * 60;
/** YouTube Shorts and Instagram Reels take up to 3 minutes. */
export const SHORTS_SECONDS = 3 * 60;

export function scenesOf(words: Word[], clips: Clip[], padStart: number, padEnd: number): Scene[] {
  return clips.map((c) => {
    const timeless = c.t0 !== undefined && c.t1 !== undefined;
    const b = clipBoundsOrTime(words, c, padStart, padEnd);
    return { id: c.id, title: c.title, w0: c.w0, w1: c.w1, start: b.start, end: b.end, timeless };
  });
}

/** Where each scene starts in the final video, plus its total length as the last entry. */
export function sceneStarts(scenes: { start: number; end: number }[]): number[] {
  const out = [0];
  for (const s of scenes) out.push(out[out.length - 1] + (s.end - s.start));
  return out;
}

/** Index of the scene playing at t seconds into the final video. */
export function sceneIndexAt(starts: number[], t: number): number {
  let i = 0;
  while (i + 2 < starts.length && t >= starts[i + 1]) i++;
  return i;
}

/**
 * Captions on the final video's timeline. Each scene is grouped on its own, so a caption
 * never runs across a cut, and is cut off where its scene ends. Timeless scenes (no words)
 * contribute no captions.
 */
export function timelineCues(words: Word[], scenes: Scene[], options: CaptionOptions = {}): CaptionCue[] {
  const starts = sceneStarts(scenes);
  const out: CaptionCue[] = [];
  scenes.forEach((s, i) => {
    if (s.timeless || s.w0 > s.w1 || s.w1 >= words.length) return;
    const offset = starts[i];
    const length = s.end - s.start;
    const at = (t: number) => +(offset + Math.min(t, length)).toFixed(3);
    for (const c of groupWordsIntoCues(words.slice(s.w0, s.w1 + 1), s.start, s.end, options)) {
      const start = at(c.start);
      out.push({
        ...c,
        id: out.length + 1,
        start,
        end: Math.max(start + 0.05, at(c.end)),
        words: c.words.map((w) => ({ ...w, start: at(w.start), end: at(w.end) })),
      });
    }
  });
  return out;
}

/** Clip ids ordered as they appear in the source video. Time clips sort by their start time. */
export function inSourceOrder(ids: string[], clips: Clip[], words: Word[] = []): string[] {
  const sortKey = new Map(clips.map((c) => [c.id, c.t0 !== undefined && c.t1 !== undefined ? c.t0 : words[c.w0]?.s ?? c.w0]));
  return [...ids].sort((a, b) => (sortKey.get(a) ?? 0) - (sortKey.get(b) ?? 0));
}
