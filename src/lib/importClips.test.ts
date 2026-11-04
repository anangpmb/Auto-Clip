import { describe, expect, it } from 'vitest';
import { DEFAULT_SETTINGS } from './storage';
import { externalPrompts, extractJsonBlocks, parseClipText, parseTime, placeClips } from './importClips';
import type { Unit, Word } from './types';

// 20 sentences of 10 s, two words each: words 2i and 2i+1 at i*10 .. i*10+9.
const words: Word[] = Array.from({ length: 40 }, (_, k) => {
  const i = k >> 1;
  return k % 2 ? { s: i * 10 + 5, e: i * 10 + 9, t: `b${i}.` } : { s: i * 10, e: i * 10 + 4, t: `a${i}` };
});
const units: Unit[] = Array.from({ length: 20 }, (_, i) => ({ id: i, w0: 2 * i, w1: 2 * i + 1, s: i * 10, e: i * 10 + 9, text: `a${i} b${i}.` }));
const loose = { fit: false, minSec: 25, maxSec: 60 };

describe('parseTime', () => {
  it('reads seconds and clock times', () => {
    expect(parseTime(83.5)).toBe(83.5);
    expect(parseTime('83.5')).toBe(83.5);
    expect(parseTime('1:23')).toBe(83);
    expect(parseTime('01:02:03.5')).toBe(3723.5);
    expect(parseTime('00:01:05,250')).toBe(65.25);
    expect(parseTime('soon')).toBeNull();
    expect(parseTime(-3)).toBeNull();
  });
});

describe('extractJsonBlocks', () => {
  it('finds JSON in a chatty answer, ignoring brackets that are not JSON', () => {
    const text = 'Sure! [music] Here:\n```json\n{"clips":[{"start_id":1,"end_id":2,"title":"a } b"}]}\n```\nAnd part 2: [{"start_id":5,"end_id":6}]';
    const blocks = extractJsonBlocks(text);
    expect(blocks).toHaveLength(2);
    expect((blocks[0] as { clips: unknown[] }).clips).toHaveLength(1);
  });
});

describe('parseClipText', () => {
  it('reads the prompt answer (unit ids)', () => {
    const raw = parseClipText('{"clips":[{"start_id":3,"end_id":5,"title":"Hook","reason":"r","score":88}]}');
    expect(raw).toEqual([{ kind: 'ids', a: 3, b: 5, title: 'Hook', reason: 'r', score: 88 }]);
  });

  it('reads times in seconds or clock form, and this app’s own JSON export', () => {
    const exported = JSON.stringify({ video: { id: 'x' }, clips: [{ n: 1, title: 'Satu', start: 21.7, end: 31, duration: 9.3 }] });
    expect(parseClipText(exported)[0]).toMatchObject({ kind: 'times', a: 21.7, b: 31, title: 'Satu' });
    const clock = parseClipText('[{"start_time":"0:40","end_time":"1:05","judul":"Dua"}, {"timestamp":"1:30 - 2:00","name":"Tiga"}]');
    expect(clock.map((c) => [c.a, c.b, c.title])).toEqual([
      [40, 65, 'Dua'],
      [90, 120, 'Tiga'],
    ]);
  });

  it('falls back to lines of timestamps', () => {
    const raw = parseClipText('1. 0:40 - 1:05 Momen lucu\n2) 00:01:30 → 00:02:00 | "Debat panas"\nbukan baris klip');
    expect(raw.map((c) => [c.a, c.b, c.title])).toEqual([
      [40, 65, 'Momen lucu'],
      [90, 120, 'Debat panas'],
    ]);
  });

  it('finds nothing in plain prose', () => {
    expect(parseClipText('Maaf, saya tidak bisa membantu.')).toEqual([]);
  });
});

describe('placeClips', () => {
  it('maps unit ids to their words', () => {
    const { clips, skipped } = placeClips(parseClipText('[{"start_id":6,"end_id":3,"title":"x"}]'), words, units, loose);
    expect(skipped).toEqual([]);
    expect([clips[0].w0, clips[0].w1]).toEqual([6, 13]);
    expect([clips[0].aiW0, clips[0].aiW1]).toEqual([6, 13]);
  });

  it('maps times to the nearest word edges', () => {
    // 41 s is nearest the start of word a4 (40 s); 63 s nearest the end of a6 (64 s)
    const { clips } = placeClips([{ kind: 'times', a: 41, b: 63, title: '', reason: '', score: 0 }], words, units, loose);
    expect([clips[0].w0, clips[0].w1]).toEqual([8, 12]);
    expect(clips[0].title).toBe('Klip impor 1');
  });

  it('fits to whole sentences and the duration range when asked', () => {
    const { clips } = placeClips([{ kind: 'times', a: 41, b: 63, title: '', reason: '', score: 0 }], words, units, { ...loose, fit: true });
    const [s, e] = [words[clips[0].w0].s, words[clips[0].w1].e];
    expect(clips[0].w0 % 2).toBe(0);
    expect(clips[0].w1 % 2).toBe(1);
    expect(e - s).toBeGreaterThanOrEqual(25);
  });

  it('skips clips outside the transcript, says why, and sorts the rest by time', () => {
    const raw = parseClipText('[{"start":500,"end":530,"title":"Jauh"},{"start_id":40,"end_id":44},{"start":100,"end":120},{"start":10,"end":30}]');
    const { clips, skipped } = placeClips(raw, words, units, loose);
    expect(clips.map((c) => c.w0)).toEqual([2, 20]);
    expect(skipped).toHaveLength(2);
    expect(skipped[0]).toMatch(/Jauh/);
  });
});

it('builds one prompt with the rules, the title and the numbered transcript', () => {
  const [p, ...rest] = externalPrompts(units, DEFAULT_SETTINGS, 'Judul video');
  expect(rest).toEqual([]);
  expect(p).toContain('Video title: Judul video');
  expect(p).toContain(`Clip count: return no more than ${DEFAULT_SETTINGS.maxClips} clips.`);
  expect(p).toContain('[19] 3:10');
  expect(p).toContain('"start_id"');
  expect(p.trim().endsWith('Reply with the JSON only.')).toBe(true);
});
