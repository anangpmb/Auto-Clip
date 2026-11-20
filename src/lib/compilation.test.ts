import { describe, expect, it } from 'vitest';
import { groupWordsIntoCues } from './captions';
import { inSourceOrder, sceneIndexAt, scenesOf, sceneStarts, timelineCues, type Scene } from './compilation';
import { clipBoundsOrTime } from './transcript';
import type { Clip, Word } from './types';

// Two sentences far apart in the source: words 0-2 around 10 s, words 3-5 around 50 s.
const words: Word[] = [
  { s: 10.0, e: 10.4, t: 'halo' },
  { s: 10.5, e: 10.9, t: 'semua' },
  { s: 11.0, e: 11.6, t: 'teman' },
  { s: 50.0, e: 50.5, t: 'ini' },
  { s: 50.6, e: 51.0, t: 'bagian' },
  { s: 51.1, e: 51.8, t: 'terbaik' },
];
const clip = (id: string, w0: number, w1: number): Clip => ({
  id,
  title: id,
  reason: '',
  score: 0,
  w0,
  w1,
  aiW0: null,
  aiW1: null,
});

describe('scene timeline', () => {
  const scenes = scenesOf(words, [clip('b', 3, 5), clip('a', 0, 2)], 0.2, 0.2);

  it('plays the scenes back to back in the given order', () => {
    expect(scenes.map((s) => s.id)).toEqual(['b', 'a']);
    const starts = sceneStarts(scenes);
    expect(starts[0]).toBe(0);
    expect(starts[1]).toBeCloseTo(51.8 + 0.2 - (50.0 - 0.2), 6);
    expect(starts[2]).toBeCloseTo(starts[1] + (11.6 + 0.2 - (10.0 - 0.2)), 6);
  });

  it('finds the scene playing at a time', () => {
    const starts = sceneStarts(scenes);
    expect(sceneIndexAt(starts, 0)).toBe(0);
    expect(sceneIndexAt(starts, starts[1] - 0.01)).toBe(0);
    expect(sceneIndexAt(starts, starts[1])).toBe(1);
    expect(sceneIndexAt(starts, starts[2] + 5)).toBe(1);
  });

  it('moves each scene’s captions to where the scene plays', () => {
    const cues = timelineCues(words, scenes, { uppercase: true });
    const starts = sceneStarts(scenes);
    expect(cues.map((c) => c.text)).toEqual(['INI BAGIAN TERBAIK', 'HALO SEMUA TEMAN']);
    expect(cues.map((c) => c.id)).toEqual([1, 2]);
    expect(cues[0].start).toBeCloseTo(0.2, 3);
    expect(cues[1].start).toBeCloseTo(starts[1] + 0.2, 3);
    expect(cues[1].words[2].start).toBeCloseTo(starts[1] + 0.2 + 1.0, 3);
  });

  it('never lets a caption run into the next scene', () => {
    const tight: Scene[] = [
      { id: 'x', title: 'x', w0: 0, w1: 2, start: 9.9, end: 11.0 }, // cut before "teman" ends
      { id: 'y', title: 'y', w0: 3, w1: 5, start: 49.9, end: 52 },
    ];
    const cues = timelineCues(words, tight);
    const starts = sceneStarts(tight);
    for (const c of cues.filter((c) => c.start < starts[1])) {
      expect(c.end).toBeLessThanOrEqual(starts[1] + 1e-9);
      for (const w of c.words) expect(w.end).toBeLessThanOrEqual(starts[1] + 1e-9);
    }
  });

  it('matches the single-clip captions for one scene', () => {
    const one = scenesOf(words, [clip('a', 0, 2)], 0.2, 0.2);
    const plain = groupWordsIntoCues(words.slice(0, 3), one[0].start, one[0].end, { uppercase: true });
    expect(timelineCues(words, one, { uppercase: true })).toEqual(plain);
  });

  it('sorts clip ids by where they are in the video', () => {
    expect(inSourceOrder(['b', 'a'], [clip('b', 3, 5), clip('a', 0, 2)])).toEqual(['a', 'b']);
  });
});

// A no-transcript video: no words, a manual clip defined by seconds alone.
const empty: Word[] = [];
const timeClip = (id: string, t0: number, t1: number): Clip => ({
  id,
  title: id,
  reason: '',
  score: 0,
  w0: 0,
  w1: 0,
  aiW0: null,
  aiW1: null,
  t0,
  t1,
});

describe('timeless (no-transcript) clips', () => {
  it('cuts a time clip with padding and no word constraints', () => {
    const b = clipBoundsOrTime(empty, timeClip('a', 10, 20), 0.2, 0.35);
    expect(b.start).toBe(10 - 0.2);
    expect(b.end).toBe(20 + 0.35);
  });

  it('does not clip the start below zero', () => {
    const b = clipBoundsOrTime(empty, timeClip('a', 0.1, 8), 0.5, 0.2);
    expect(b.start).toBe(0);
    expect(b.end).toBeCloseTo(8.2, 6);
  });

  it('builds scenes from time clips', () => {
    const scenes = scenesOf(empty, [timeClip('a', 10, 20)], 0.2, 0.35);
    expect(scenes[0].start).toBeCloseTo(9.8, 6);
    expect(scenes[0].end).toBeCloseTo(20.35, 6);
    expect(scenes[0].timeless).toBe(true);
    expect(timelineCues(empty, scenes, { uppercase: true })).toEqual([]);
  });

  it('sorts timeless clips with word clips by their start time', () => {
    const clips = [clip('b', 0, 2), timeClip('a', 5, 9)];
    // "b" starts at words[0].s = 10, "a" at t0 = 5, so "a" should come first.
    expect(inSourceOrder(['b', 'a'], clips, words)).toEqual(['a', 'b']);
  });

  it('keeps captions of neighbouring word scenes and skips timeless ones in a mixed compilation', () => {
    const mixed: Scene[] = [
      { id: 'a', title: 'a', w0: 3, w1: 5, start: 49.8, end: 52.15, timeless: false },
      { id: 't', title: 't', w0: 0, w1: 0, start: 9.8, end: 20.35, timeless: true },
    ];
    const cues = timelineCues(words, mixed, { uppercase: true });
    expect(cues.map((c) => c.text)).toEqual(['INI BAGIAN TERBAIK']);
  });
});
