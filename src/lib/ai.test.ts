import { describe, expect, it } from 'vitest';
import type { Unit, Word } from './types';
import { chunkUnits, dedupe, parseModelJson, toClips } from './ai';

// 20 units of 10 s, one word each
const units: Unit[] = Array.from({ length: 20 }, (_, i) => ({ id: i, w0: i, w1: i, s: i * 10, e: i * 10 + 9, text: `unit ${i}` }));
const words: Word[] = units.map((u) => ({ s: u.s, e: u.e, t: u.text }));

describe('parseModelJson', () => {
  it('reads plain, fenced and chatty JSON', () => {
    expect(parseModelJson('{"clips":[]}')).toEqual({ clips: [] });
    expect(parseModelJson('```json\n{"clips":[1]}\n```')).toEqual({ clips: [1] });
    expect(parseModelJson('Here you go:\n{"clips":[2]}\nThanks')).toEqual({ clips: [2] });
  });
  it('throws a readable error on garbage', () => {
    expect(() => parseModelJson('no json here')).toThrow(/JSON/);
  });
});

describe('toClips', () => {
  it('maps unit ids to words, swaps, clamps and fits the duration', () => {
    const raw = {
      clips: [
        { start_id: 5, end_id: 3, title: 'Swapped', reason: 'r', score: 80 },
        { start_id: -4, end_id: 1, title: 'Clamped', score: 120 },
        { start_id: 'x', end_id: 2 },
      ],
    };
    const out = toClips(raw, units, units.slice(0, 10), 25, 60);
    expect(out).toHaveLength(2);
    expect([out[0].w0, out[0].w1]).toEqual([3, 5]);
    expect(out[0].score).toBe(80);
    expect(out[1].w0).toBe(0);
    expect(out[1].score).toBe(100);
    // units 0-1 last 19 s, so the end grows to reach the 25 s minimum
    expect(units[out[1].w1].e - units[out[1].w0].s).toBeGreaterThanOrEqual(25);
    expect(out[0].aiW0).toBe(out[0].w0);
  });

  it('accepts a bare array', () => {
    expect(toClips([{ start_id: 0, end_id: 3, title: 't' }], units, units, 10, 60)).toHaveLength(1);
  });
});

it('dedupe keeps the better of two overlapping clips and sorts by time', () => {
  const mk = (w0: number, w1: number, score: number) => ({ id: `${w0}`, title: '', reason: '', score, w0, w1, aiW0: w0, aiW1: w1 });
  const out = dedupe([mk(10, 14, 90), mk(0, 3, 50), mk(11, 15, 70), mk(5, 7, 60)], words, 10);
  expect(out.map((c) => c.w0)).toEqual([0, 5, 10]);
});

it('chunkUnits covers everything with overlap', () => {
  const chunks = chunkUnits(units, 150, 25);
  expect(chunks.length).toBeGreaterThan(1);
  expect(chunks[0][0].id).toBe(0);
  expect(chunks.at(-1)!.at(-1)!.id).toBe(19);
  for (let i = 1; i < chunks.length; i++) {
    expect(chunks[i][0].id).toBeLessThanOrEqual(chunks[i - 1].at(-1)!.id);
    expect(chunks[i][0].id).toBeGreaterThan(chunks[i - 1][0].id);
  }
});
