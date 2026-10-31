import type { Clip, Unit, Word } from './types';

const SENTENCE_END = /[.!?…。！？]["'”’)\]]*$/;
/** Silence (s) that ends a unit once it has a few words. */
const PAUSE_BREAK = 0.7;
/** Silence (s) that always ends a unit. */
const LONG_PAUSE = 1.2;
/** Units longer than this break at the next small pause. */
const SOFT_MAX_SEC = 12;
const HARD_MAX_WORDS = 40;

export function joinWords(words: Word[], w0: number, w1: number): string {
  const out: string[] = [];
  for (let i = Math.max(0, w0); i <= Math.min(w1, words.length - 1); i++) out.push(words[i].t);
  return out.join(' ');
}

/**
 * Split words into sentence-like units. YouTube auto captions usually have no
 * punctuation, so pauses between words do most of the work.
 */
export function buildUnits(words: Word[]): Unit[] {
  const units: Unit[] = [];
  let w0 = 0;
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    const next = words[i + 1];
    const count = i - w0 + 1;
    const gap = next ? next.s - w.e : Infinity;
    const span = w.e - words[w0].s;
    const brk =
      !next ||
      gap >= LONG_PAUSE ||
      (SENTENCE_END.test(w.t) && count >= 2) ||
      (gap >= PAUSE_BREAK && count >= 3) ||
      (span >= SOFT_MAX_SEC && gap >= 0.25) ||
      count >= HARD_MAX_WORDS;
    if (brk) {
      units.push({ id: units.length, w0, w1: i, s: words[w0].s, e: w.e, text: joinWords(words, w0, i) });
      w0 = i + 1;
    }
  }
  return units;
}

/** Index of the last word that starts at or before t, or -1. */
export function wordIndexAt(words: Word[], t: number): number {
  let lo = 0;
  let hi = words.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].s <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}

/** Index of the unit containing word wi. */
export function unitIndexOfWord(units: Unit[], wi: number): number {
  let lo = 0;
  let hi = units.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const u = units[mid];
    if (wi < u.w0) hi = mid - 1;
    else if (wi > u.w1) lo = mid + 1;
    else return mid;
  }
  return Math.max(0, Math.min(units.length - 1, lo));
}

/**
 * Word index in [lo, hi] whose boundary is nearest to t. A start boundary is a
 * word's start; an end boundary is its end. With snap, only sentence (unit)
 * boundaries are candidates.
 */
export function nearestBoundary(
  words: Word[],
  units: Unit[],
  t: number,
  lo: number,
  hi: number,
  which: 'start' | 'end',
  snap: boolean,
): number {
  let best = -1;
  let bestD = Infinity;
  if (snap) {
    for (const u of units) {
      const wi = which === 'start' ? u.w0 : u.w1;
      if (wi < lo || wi > hi) continue;
      const d = Math.abs((which === 'start' ? u.s : u.e) - t);
      if (d < bestD) {
        bestD = d;
        best = wi;
      }
    }
    if (best >= 0) return best;
  }
  for (let i = Math.max(0, lo); i <= Math.min(hi, words.length - 1); i++) {
    const d = Math.abs((which === 'start' ? words[i].s : words[i].e) - t);
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/**
 * Move a clip boundary by one sentence. For the start, dir -1 adds the previous
 * sentence and +1 drops the first one. For the end, +1 adds the next sentence
 * and -1 drops the last one. A boundary in mid-sentence first moves to that
 * sentence's edge.
 */
export function sentenceStep(units: Unit[], which: 'start' | 'end', wi: number, dir: -1 | 1): number {
  const u = unitIndexOfWord(units, wi);
  const unit = units[u];
  if (which === 'start') {
    if (dir < 0) return wi === unit.w0 && u > 0 ? units[u - 1].w0 : unit.w0;
    return u + 1 < units.length ? units[u + 1].w0 : wi;
  }
  if (dir > 0) return wi === unit.w1 && u + 1 < units.length ? units[u + 1].w1 : unit.w1;
  return u > 0 ? units[u - 1].w1 : wi;
}

/**
 * Cut points for a clip in seconds. Padding gives the first and last word
 * some air but never reaches into the neighbouring words.
 */
export function clipBounds(words: Word[], w0: number, w1: number, padStart: number, padEnd: number) {
  const first = words[w0];
  const last = words[w1];
  const prev = words[w0 - 1];
  const next = words[w1 + 1];
  let start = first.s - padStart;
  if (prev) start = Math.max(start, Math.min(prev.e, first.s));
  let end = last.e + padEnd;
  if (next) end = Math.min(end, Math.max(next.s - 0.05, last.e));
  return { start: Math.max(0, start), end };
}

export type DurationStatus = 'ok' | 'short' | 'long';

export function durationStatus(d: number, minSec: number, maxSec: number): DurationStatus {
  if (d < minSec) return 'short';
  if (d > maxSec) return 'long';
  return 'ok';
}

/** Units [s, e] adjusted to fit [minSec, maxSec], growing the end first. */
export function fitDuration(units: Unit[], s: number, e: number, minSec: number, maxSec: number): [number, number] {
  const dur = (a: number, b: number) => units[b].e - units[a].s;
  while (dur(s, e) < minSec && e + 1 < units.length && dur(s, e + 1) <= maxSec) e++;
  while (dur(s, e) < minSec && s > 0 && dur(s - 1, e) <= maxSec) s--;
  while (dur(s, e) > maxSec && e > s) e--;
  return [s, e];
}

/** Last unit index so that units [u, result] last about targetSec. */
export function unitsSpanFrom(units: Unit[], u: number, targetSec: number): number {
  let e = u;
  while (e + 1 < units.length && units[e].e - units[u].s < targetSec) e++;
  return e;
}

/** Re-anchor a clip on a different word list (e.g. after switching caption track). */
export function remapClip(oldWords: Word[], newWords: Word[], newUnits: Unit[], clip: Clip): Clip {
  const last = newWords.length - 1;
  const map = (wi: number | null, which: 'start' | 'end') => {
    if (wi === null) return null;
    const w = oldWords[Math.min(wi, oldWords.length - 1)];
    return nearestBoundary(newWords, newUnits, which === 'start' ? w.s : w.e, 0, last, which, false);
  };
  const w0 = map(clip.w0, 'start') ?? 0;
  const w1 = Math.max(w0, map(clip.w1, 'end') ?? w0);
  return { ...clip, w0, w1, aiW0: map(clip.aiW0, 'start'), aiW1: map(clip.aiW1, 'end') };
}

export function fmtTime(t: number, precise = false): string {
  if (!Number.isFinite(t) || t < 0) t = 0;
  const total = precise ? Math.round(t * 10) / 10 : Math.floor(t);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  const ss = precise ? sec.toFixed(1).padStart(4, '0') : String(Math.floor(sec)).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

export function fmtDuration(sec: number): string {
  if (sec < 60) return `${Math.round(sec)} dtk`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return s ? `${m} mnt ${s} dtk` : `${m} mnt`;
}
