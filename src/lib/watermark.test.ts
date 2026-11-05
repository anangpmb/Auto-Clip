import { describe, expect, it } from 'vitest';
import { buildExportCommand } from './captions';
import {
  cleanDrawtextText,
  resolveWatermark,
  watermarkDrawtext,
  watermarkXY,
  type WatermarkSettings,
} from './watermark';

const settings: WatermarkSettings = {
  enabled: true,
  position: 'top-right',
  size: 'small',
  opacity: 0.7,
  style: 'text',
};

describe('source watermark', () => {
  it('uses the channel name when no per-export text is given', () => {
    expect(resolveWatermark(settings, 'Contoh Channel')).toMatchObject({ text: 'Contoh Channel', position: 'top-right' });
  });

  it('prefers an edited text, and falls back to the channel when it is blank', () => {
    expect(resolveWatermark(settings, 'Contoh Channel', '  Klip dari Saya  ')?.text).toBe('Klip dari Saya');
    expect(resolveWatermark(settings, 'Contoh Channel', '   ')?.text).toBe('Contoh Channel');
  });

  it('produces no watermark when switched off or when there is no name', () => {
    expect(resolveWatermark({ ...settings, enabled: false }, 'Contoh Channel')).toBeNull();
    expect(resolveWatermark(settings, '   ')).toBeNull();
  });

  it('clamps opacity and falls back on unknown values instead of failing', () => {
    const w = resolveWatermark({ ...settings, opacity: 5, position: 'nowhere' as never }, 'X');
    expect(w?.opacity).toBe(0.9);
    expect(w?.position).toBe('top-right');
  });

  it('places the box inside the frame with a margin on every corner', () => {
    expect(watermarkXY('top-right', 1080, 1920, 400, 60)).toEqual([1080 - 32 - 400, 67]);
    expect(watermarkXY('bottom-left', 1080, 1920, 400, 60)).toEqual([32, 1920 - 67 - 60]);
    expect(watermarkXY('bottom-right', 1920, 1080, 400, 60)).toEqual([1920 - 58 - 400, 1080 - 38 - 60]);
  });

  it('cleans drawtext text so it cannot break the shell-quoted command', () => {
    expect(cleanDrawtextText("Chan'nel: Test $x, ok")).toBe('Channel Test x ok');
    expect(watermarkDrawtext(resolveWatermark(settings, 'Contoh Channel')!)).toContain("drawtext=text='Contoh Channel'");
    expect(watermarkDrawtext(resolveWatermark(settings, 'Contoh Channel')!)).toContain("x='w-text_w-w*0.03'");
  });

  it('adds the watermark last in the manual export command, after captions', () => {
    const cmd = buildExportCommand('https://www.youtube.com/watch?v=abc', 1, 9, 'Klip', {
      burnCaptions: true,
      srtFilename: 'Klip.srt',
      watermark: resolveWatermark(settings, 'Contoh Channel')!,
    });
    expect(cmd).toContain("subtitles='Klip.srt',drawtext=text='Contoh Channel'");
  });

  it('leaves the manual command unchanged without a watermark', () => {
    const cmd = buildExportCommand('https://www.youtube.com/watch?v=abc', 1, 9, 'Klip', { burnCaptions: false });
    expect(cmd).not.toContain('drawtext');
  });
});
