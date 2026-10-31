import { describe, expect, it } from 'vitest';
import type { Word } from './types';
import {
  buildUnits,
  clipBounds,
  fitDuration,
  fmtTime,
  nearestBoundary,
  remapClip,
  sentenceStep,
  unitIndexOfWord,
  wordIndexAt,
} from './transcript';

/** Words spoken back to back at 0.4 s each, with a pause after each group. */
function speech(groups: string[][], pause = 1.5): Word[] {
  const words: Word[] = [];
  let t = 0;
  for (const g of groups) {
    for (const w of g) {
      words.push({ s: t, e: t + 0.35, t: w });
      t += 0.4;
    }
    t += pause;
  }
  return words;
}

describe('buildUnits', () => {
  it('splits on pauses when there is no punctuation', () => {
    const words = speech([
      ['jadi', 'gini', 'ceritanya'],
      ['aku', 'pernah', 'kerja', 'di', 'pabrik'],
      ['terus', 'dipecat'],
    ]);
    const units = buildUnits(words);
    expect(units.map((u) => u.text)).toEqual(['jadi gini ceritanya', 'aku pernah kerja di pabrik', 'terus dipecat']);
    expect(units.map((u) => u.id)).toEqual([0, 1, 2]);
  });

  it('splits on sentence punctuation without a pause', () => {
    const words = speech([['Halo', 'semua.', 'Hari', 'ini', 'kita', 'bahas', 'AI.']]);
    expect(buildUnits(words).map((u) => u.text)).toEqual(['Halo semua.', 'Hari ini kita bahas AI.']);
  });

  it('covers every word exactly once', () => {
    const words = speech([Array.from({ length: 95 }, (_, i) => `w${i}`)], 0);
    const units = buildUnits(words);
    expect(units[0].w0).toBe(0);
    expect(units.at(-1)!.w1).toBe(94);
    for (let i = 1; i < units.length; i++) expect(units[i].w0).toBe(units[i - 1].w1 + 1);
    expect(units.every((u) => u.w1 - u.w0 + 1 <= 40)).toBe(true);
  });
});

describe('lookups', () => {
  const words = speech([['a', 'b', 'c'], ['d', 'e']]);
  const units = buildUnits(words);

  it('wordIndexAt finds the word being spoken', () => {
    expect(wordIndexAt(words, -1)).toBe(-1);
    expect(wordIndexAt(words, 0)).toBe(0);
    expect(wordIndexAt(words, 0.5)).toBe(1);
    expect(wordIndexAt(words, 999)).toBe(4);
  });

  it('unitIndexOfWord maps words to their unit', () => {
    expect([0, 1, 2, 3, 4].map((w) => unitIndexOfWord(units, w))).toEqual([0, 0, 0, 1, 1]);
  });

  it('nearestBoundary respects the snap setting and range', () => {
    // word starts: 0, .4, .8, 2.7, 3.1
    expect(nearestBoundary(words, units, 0.7, 0, 4, 'start', false)).toBe(2);
    expect(nearestBoundary(words, units, 0.7, 0, 4, 'start', true)).toBe(0);
    expect(nearestBoundary(words, units, 2.0, 0, 4, 'end', true)).toBe(2);
    expect(nearestBoundary(words, units, 0, 3, 4, 'start', false)).toBe(3);
  });
});

describe('sentenceStep', () => {
  const words = speech([['a', 'b', 'c'], ['d', 'e', 'f'], ['g', 'h']]);
  const units = buildUnits(words); // [0-2] [3-5] [6-7]

  it('moves the start by whole sentences', () => {
    expect(sentenceStep(units, 'start', 3, -1)).toBe(0);
    expect(sentenceStep(units, 'start', 4, -1)).toBe(3); // mid-sentence: back to its start
    expect(sentenceStep(units, 'start', 3, 1)).toBe(6);
    expect(sentenceStep(units, 'start', 0, -1)).toBe(0);
  });

  it('moves the end by whole sentences', () => {
    expect(sentenceStep(units, 'end', 5, 1)).toBe(7);
    expect(sentenceStep(units, 'end', 4, 1)).toBe(5); // mid-sentence: forward to its end
    expect(sentenceStep(units, 'end', 5, -1)).toBe(2);
    expect(sentenceStep(units, 'end', 7, 1)).toBe(7);
  });
});

describe('clipBounds', () => {
  it('pads both edges when there is room', () => {
    const words = speech([['a'], ['b'], ['c']]);
    const b = clipBounds(words, 1, 1, 0.15, 0.35);
    expect(b.start).toBeCloseTo(words[1].s - 0.15);
    expect(b.end).toBeCloseTo(words[1].e + 0.35);
  });

  it('never cuts into neighbouring words', () => {
    const words: Word[] = [
      { s: 0, e: 0.3, t: 'a' },
      { s: 0.32, e: 0.6, t: 'b' },
      { s: 0.62, e: 0.9, t: 'c' },
    ];
    const b = clipBounds(words, 1, 1, 0.15, 0.35);
    expect(b.start).toBeGreaterThanOrEqual(words[0].e);
    expect(b.end).toBeLessThanOrEqual(words[2].s);
    expect(b.end).toBeGreaterThanOrEqual(words[1].e);
  });
});

describe('fitDuration', () => {
  // ten units of 10 s each
  const units = Array.from({ length: 10 }, (_, i) => ({ id: i, w0: i, w1: i, s: i * 10, e: i * 10 + 9, text: '' }));

  it('grows a short clip forward first', () => {
    expect(fitDuration(units, 2, 2, 30, 60)).toEqual([2, 5]);
  });
  it('grows backwards at the end of the video', () => {
    expect(fitDuration(units, 9, 9, 30, 60)).toEqual([6, 9]);
  });
  it('trims a long clip from the end', () => {
    expect(fitDuration(units, 0, 9, 10, 40)).toEqual([0, 3]);
  });
});

it('remapClip keeps a clip at the same moment on new words', () => {
  const oldWords = speech([['a', 'b', 'c'], ['d', 'e']]);
  const newWords = oldWords.flatMap((w) => [
    { s: w.s, e: w.s + 0.15, t: w.t },
    { s: w.s + 0.2, e: w.e, t: w.t + '2' },
  ]);
  const clip = { id: 'x', title: '', reason: '', score: 0, w0: 3, w1: 4, aiW0: 3, aiW1: 4 };
  const out = remapClip(oldWords, newWords, buildUnits(newWords), clip);
  expect(newWords[out.w0].s).toBeCloseTo(oldWords[3].s);
  expect(newWords[out.w1].e).toBeCloseTo(oldWords[4].e);
});

it('fmtTime formats minutes, hours and tenths', () => {
  expect(fmtTime(5)).toBe('0:05');
  expect(fmtTime(65.4)).toBe('1:05');
  expect(fmtTime(3725)).toBe('1:02:05');
  expect(fmtTime(59.96, true)).toBe('1:00.0');
  expect(fmtTime(61.25, true)).toBe('1:01.3');
});
