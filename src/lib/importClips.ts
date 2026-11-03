/**
 * Clips chosen outside the app: by any AI chat (with the prompt from externalPrompts) or by
 * hand, pasted back as JSON or as plain lines of timestamps.
 */
import { buildSystemPrompt, chunkUnits, formatUnits, newId } from './ai';
import { fitDuration, nearestBoundary, unitIndexOfWord } from './transcript';
import type { Clip, Settings, Unit, Word } from './types';

/** Transcript characters per prompt; one prompt covers about an hour of speech. */
const PROMPT_CHARS = 100_000;
const MAX_IMPORT = 100;

/**
 * Prompts to paste into another AI chat: the in-app rules, the title and the numbered
 * transcript. A very long transcript is split into parts; each part's answer is pasted back.
 */
export function externalPrompts(units: Unit[], s: Settings, title: string): string[] {
  const parts = chunkUnits(units, PROMPT_CHARS, s.maxSec + 30);
  const perPart = parts.length > 1 ? Math.min(s.maxClips, Math.ceil(s.maxClips / parts.length) + 2) : s.maxClips;
  const rules = buildSystemPrompt(s, perPart);
  return parts.map((part, i) => {
    const which = parts.length > 1 ? ` (part ${i + 1} of ${parts.length}; pick the best moments in this part)` : '';
    return `${rules}\n\nVideo title: ${title}\n\nTranscript${which}:\n${formatUnits(part)}\n\nReply with the JSON only.`;
  });
}

/** Seconds from 83.5, "83.5", "1:23", "01:02:03.5" or "01:02:03,500"; null if it is none of these. */
export function parseTime(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) && v >= 0 ? v : null;
  if (typeof v !== 'string') return null;
  const t = v.trim().replace(',', '.');
  if (/^\d+(\.\d+)?$/.test(t)) return parseFloat(t);
  const m = /^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/.exec(t);
  if (!m) return null;
  return (m[1] ? +m[1] * 3600 : 0) + +m[2] * 60 + parseFloat(m[3]);
}

/** Every top-level JSON object or array in a text, so chatty answers and several pasted answers work. */
export function extractJsonBlocks(text: string): unknown[] {
  const found: unknown[] = [];
  let i = 0;
  while (i < text.length) {
    const open = text[i];
    if (open !== '{' && open !== '[') {
      i++;
      continue;
    }
    // Find the matching close bracket, skipping strings.
    let depth = 0;
    let inStr = false;
    let end = -1;
    for (let j = i; j < text.length; j++) {
      const c = text[j];
      if (inStr) {
        if (c === '\\') j++;
        else if (c === '"') inStr = false;
      } else if (c === '"') inStr = true;
      else if (c === '{' || c === '[') depth++;
      else if (c === '}' || c === ']') {
        depth--;
        if (depth === 0) {
          end = j;
          break;
        }
      }
    }
    if (end < 0) break;
    try {
      found.push(JSON.parse(text.slice(i, end + 1)));
      i = end + 1;
    } catch {
      i++; // not JSON after all (e.g. "[music]"); look further in
    }
  }
  return found;
}

/** A clip as found in the pasted text, before it is placed on the transcript. */
export interface RawClip {
  /** Unit ids (the prompt's [id] numbers) or seconds. */
  kind: 'ids' | 'times';
  a: number;
  b: number;
  title: string;
  reason: string;
  score: number;
}

const LIST_KEYS = ['clips', 'moments', 'highlights', 'segments', 'items', 'results', 'klip'];
const START_KEYS = ['start', 'start_time', 'startTime', 'start_sec', 'from', 'begin', 'awal', 'mulai'];
const END_KEYS = ['end', 'end_time', 'endTime', 'end_sec', 'to', 'finish', 'akhir', 'selesai'];
const TITLE_KEYS = ['title', 'name', 'judul', 'hook', 'headline'];
const REASON_KEYS = ['reason', 'alasan', 'why', 'description', 'summary'];

const first = (o: Record<string, unknown>, keys: string[]) => keys.map((k) => o[k]).find((v) => v !== undefined && v !== null && v !== '');
const LINE = /(\d{1,2}(?::\d{1,2}){1,2}(?:[.,]\d+)?)\s*(?:-|–|—|->|→|to|sampai|s\/d)\s*(\d{1,2}(?::\d{1,2}){1,2}(?:[.,]\d+)?)\s*[-–—:|]?\s*(.*)/i;

function fromObject(o: Record<string, unknown>): RawClip | null {
  const text = (keys: string[]) => String(first(o, keys) ?? '').trim();
  const score = Math.round(Number(first(o, ['score', 'viral_score', 'nilai', 'rating'])) || 0);
  if (o.start_id !== undefined && o.end_id !== undefined) {
    const a = Math.round(Number(o.start_id));
    const b = Math.round(Number(o.end_id));
    if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
    return { kind: 'ids', a, b, title: text(TITLE_KEYS), reason: text(REASON_KEYS), score };
  }
  let a = parseTime(first(o, START_KEYS));
  let b = parseTime(first(o, END_KEYS));
  if (a === null || b === null) {
    // "timestamp": "1:23 - 2:10"
    const m = LINE.exec(String(first(o, ['timestamp', 'time', 'range', 'waktu']) ?? ''));
    if (!m) return null;
    [a, b] = [parseTime(m[1]), parseTime(m[2])];
    if (a === null || b === null) return null;
  }
  return { kind: 'times', a, b, title: text(TITLE_KEYS), reason: text(REASON_KEYS), score };
}

/** The clips in a pasted answer, a JSON file (this app's own export too) or lines of timestamps. */
export function parseClipText(text: string): RawClip[] {
  const out: RawClip[] = [];
  for (const block of extractJsonBlocks(text)) {
    const list = Array.isArray(block)
      ? block
      : block && typeof block === 'object'
        ? ((LIST_KEYS.map((k) => (block as Record<string, unknown>)[k]).find(Array.isArray) as unknown[] | undefined) ?? [block])
        : [];
    for (const item of list) {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const c = fromObject(item as Record<string, unknown>);
        if (c) out.push(c);
      }
    }
  }
  if (!out.length) {
    // No JSON: lines such as "1:23 - 2:10 The title" or "00:01:23 → 00:02:10 | The title".
    for (const line of text.split(/\r?\n/)) {
      const m = LINE.exec(line);
      const a = m && parseTime(m[1]);
      const b = m && parseTime(m[2]);
      if (m && a !== null && b !== null) out.push({ kind: 'times', a, b, title: m[3].replace(/^["“]|["”]$/g, '').trim(), reason: '', score: 0 });
    }
  }
  return out.slice(0, MAX_IMPORT);
}

export interface ImportOptions {
  /** Snap to sentences and fit into minSec..maxSec, like the in-app AI does. */
  fit: boolean;
  minSec: number;
  maxSec: number;
}

export interface ImportResult {
  clips: Clip[];
  /** One line per clip left out, saying why. */
  skipped: string[];
}

/** Places pasted clips on the transcript: unit ids map to their words, times to the nearest word edges. */
export function placeClips(raw: RawClip[], words: Word[], units: Unit[], opts: ImportOptions): ImportResult {
  const clips: Clip[] = [];
  const skipped: string[] = [];
  const lastUnit = units.length - 1;
  const lastWord = words.length - 1;
  const end = words[lastWord]?.e ?? 0;
  raw.forEach((r, n) => {
    const name = r.title ? `"${r.title}"` : `Klip ${n + 1}`;
    let [a, b] = r.a <= r.b ? [r.a, r.b] : [r.b, r.a];
    let u0: number;
    let u1: number;
    let w0: number;
    let w1: number;
    if (r.kind === 'ids') {
      if (b < 0 || a > lastUnit) return skipped.push(`${name}: nomor kalimat ${r.a}–${r.b} tidak ada di transkrip ini.`);
      [u0, u1] = [Math.max(0, a), Math.min(lastUnit, b)];
      [w0, w1] = [units[u0].w0, units[u1].w1];
    } else {
      if (b - a < 0.5) return skipped.push(`${name}: terlalu pendek.`);
      if (a >= end || b <= 0) return skipped.push(`${name}: di luar transkrip (video ini ${Math.round(end)} detik).`);
      [a, b] = [Math.max(0, a), Math.min(end, b)];
      w0 = nearestBoundary(words, units, a, 0, lastWord, 'start', false);
      w1 = nearestBoundary(words, units, b, w0, lastWord, 'end', false);
      [u0, u1] = [unitIndexOfWord(units, w0), unitIndexOfWord(units, w1)];
    }
    if (opts.fit) {
      [u0, u1] = fitDuration(units, u0, u1, opts.minSec, opts.maxSec);
      [w0, w1] = [units[u0].w0, units[u1].w1];
    }
    if (w1 < w0) return skipped.push(`${name}: tidak berisi kata.`);
    clips.push({
      id: newId(),
      title: r.title.slice(0, 120) || `Klip impor ${clips.length + 1}`,
      reason: r.reason,
      score: Math.min(100, Math.max(0, r.score)),
      w0,
      w1,
      aiW0: w0,
      aiW1: w1,
    });
  });
  return { clips: clips.sort((x, y) => x.w0 - y.w0), skipped };
}
