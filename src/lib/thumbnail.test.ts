import { describe, expect, it } from 'vitest';
import { isDarkFrame, meanLuminance, thumbnailSeekTimes } from './thumbnail';

describe('thumbnail frame picking', () => {
  it('starts at most one second in, then steps forward by half a second', () => {
    expect(thumbnailSeekTimes(60)).toEqual([1, 1.5, 2, 2.5, 3, 3.5]);
    expect(thumbnailSeekTimes(2)).toEqual([0.667, 1.167, 1.667]);
    expect(thumbnailSeekTimes(0.4)).toEqual([0.133]);
    expect(thumbnailSeekTimes(0)).toEqual([0]);
  });

  it('never steps past the end of the clip', () => {
    const times = thumbnailSeekTimes(1.2);
    expect(times[times.length - 1]).toBeLessThanOrEqual(1.15);
  });

  it('reads black as dark and a mid-grey frame as usable', () => {
    const black = new Uint8ClampedArray(64 * 4);
    expect(meanLuminance(black)).toBe(0);
    expect(isDarkFrame(meanLuminance(black))).toBe(true);

    const grey = new Uint8ClampedArray(64 * 4);
    for (let i = 0; i < grey.length; i += 4) {
      grey[i] = 120;
      grey[i + 1] = 120;
      grey[i + 2] = 120;
      grey[i + 3] = 255;
    }
    expect(meanLuminance(grey)).toBeCloseTo(120, 3);
    expect(isDarkFrame(meanLuminance(grey))).toBe(false);
  });

  it('treats a frame just under the threshold as dark', () => {
    expect(isDarkFrame(15.9)).toBe(true);
    expect(isDarkFrame(16)).toBe(false);
  });
});
