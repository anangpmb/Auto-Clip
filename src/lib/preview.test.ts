import { describe, expect, it } from 'vitest';
import { activeWordIndex, centerCropX, cropXAt, layoutFor } from './preview';
import type { CaptionCue } from './captions';

describe('layoutFor', () => {
  it('maps aspect ratios to the export layouts', () => {
    expect(layoutFor('16:9', 1920, 1080)).toBe('fit');
    expect(layoutFor('9:16_blur', 1920, 1080)).toBe('blur');
    expect(layoutFor('9:16_crop', 1920, 1080)).toBe('crop');
  });

  it('falls back to blur when the source is already narrower than 9:16', () => {
    expect(layoutFor('9:16_crop', 720, 1280)).toBe('crop'); // exactly 9:16 still crops (to itself)
    expect(layoutFor('9:16_crop', 480, 1080)).toBe('blur');
  });

  it('assumes a crop until the source size is known', () => {
    expect(layoutFor('9:16_crop')).toBe('crop');
  });
});

describe('centerCropX', () => {
  it('centres the 9:16 window in a 16:9 frame', () => {
    expect(centerCropX(1920, 1080)).toBeCloseTo((1 - 607.5 / 1920) / 2, 6);
  });
  it('never goes negative', () => {
    expect(centerCropX(480, 1080)).toBe(0);
  });
});

describe('cropXAt', () => {
  const keys: [number, number][] = [
    [0, 0.1],
    [2, 0.3],
    [4.999, 0.3],
    [5, 0.6], // a cut: hold, then jump
    [8, 0.6],
  ];

  it('holds the first and last values outside the keys', () => {
    expect(cropXAt(keys, -1)).toBe(0.1);
    expect(cropXAt(keys, 0)).toBe(0.1);
    expect(cropXAt(keys, 20)).toBe(0.6);
  });

  it('interpolates linearly between keys', () => {
    expect(cropXAt(keys, 1)).toBeCloseTo(0.2, 6);
    expect(cropXAt(keys, 3)).toBeCloseTo(0.3, 6);
    expect(cropXAt(keys, 6.5)).toBeCloseTo(0.6, 6);
  });

  it('jumps at a cut', () => {
    expect(cropXAt(keys, 4.99)).toBeCloseTo(0.3, 6);
    expect(cropXAt(keys, 5.01)).toBeCloseTo(0.6, 6);
  });

  it('handles a single key and no keys', () => {
    expect(cropXAt([[0, 0.4]], 3)).toBe(0.4);
    expect(cropXAt([], 3)).toBeNaN();
  });
});

describe('activeWordIndex', () => {
  const cue: CaptionCue = {
    id: 1,
    start: 1,
    end: 4,
    text: 'A B C',
    words: [
      { start: 1.2, end: 1.5, text: 'A' },
      { start: 2, end: 2.4, text: 'B' },
      { start: 3, end: 3.5, text: 'C' },
    ],
  };

  it('is -1 before the first word starts', () => {
    expect(activeWordIndex(cue, 1.1)).toBe(-1);
  });

  it('keeps a word lit until the next one starts', () => {
    expect(activeWordIndex(cue, 1.3)).toBe(0);
    expect(activeWordIndex(cue, 1.8)).toBe(0); // gap after A
    expect(activeWordIndex(cue, 2.1)).toBe(1);
    expect(activeWordIndex(cue, 3.9)).toBe(2);
  });
});
