import { describe, expect, it } from 'vitest';
import {
  formatSrtTime,
  formatVttTime,
  formatAssTime,
  groupWordsIntoCues,
  generateSrt,
  generateVtt,
  generateAss,
  buildExportCommand,
} from './captions';
import type { Word } from './types';

describe('captions time formatting', () => {
  it('formats SRT time correctly', () => {
    expect(formatSrtTime(0)).toBe('00:00:00,000');
    expect(formatSrtTime(65.432)).toBe('00:01:05,432');
    expect(formatSrtTime(3661.05)).toBe('01:01:01,050');
  });

  it('formats VTT time correctly', () => {
    expect(formatVttTime(0)).toBe('00:00:00.000');
    expect(formatVttTime(65.432)).toBe('00:01:05.432');
  });

  it('formats ASS time correctly (centiseconds)', () => {
    expect(formatAssTime(0)).toBe('0:00:00.00');
    expect(formatAssTime(65.43)).toBe('0:01:05.43');
    expect(formatAssTime(3661.5)).toBe('1:01:01.50');
  });
});

describe('groupWordsIntoCues', () => {
  const sampleWords: Word[] = [
    { s: 10.0, e: 10.4, t: 'Halo' },
    { s: 10.5, e: 10.9, t: 'semuanya' },
    { s: 11.0, e: 11.3, t: 'apa' },
    { s: 11.4, e: 11.8, t: 'kabar.' },
    { s: 13.0, e: 13.5, t: 'Hari' }, // notice gap 11.8 to 13.0
    { s: 13.6, e: 14.0, t: 'ini' },
    { s: 14.1, e: 14.5, t: 'kita' },
    { s: 14.6, e: 15.0, t: 'belajar' },
  ];

  it('filters words outside clip range and offsets relative to clip start', () => {
    const cues = groupWordsIntoCues(sampleWords, 10.0, 16.0);
    expect(cues.length).toBeGreaterThanOrEqual(2);
    // First cue relative start should be 0.0
    expect(cues[0].start).toBeCloseTo(0.0, 2);
    expect(cues[0].text).toContain('Halo');
    // Second cue should split due to punctuation or pause
    expect(cues[1].text).toContain('Hari');
    expect(cues[1].start).toBeCloseTo(3.0, 2);
  });

  it('supports uppercase option', () => {
    const cues = groupWordsIntoCues(sampleWords, 10.0, 16.0, { uppercase: true });
    expect(cues[0].text).toBe('HALO SEMUANYA APA KABAR.');
  });
});

describe('generateSrt', () => {
  const sampleWords: Word[] = [
    { s: 5.0, e: 5.5, t: 'Klip' },
    { s: 5.6, e: 6.0, t: 'pertama' },
  ];

  it('generates valid SRT format', () => {
    const srt = generateSrt(sampleWords, 5.0, 7.0);
    expect(srt).toContain('1\n00:00:00,000 -->');
    expect(srt).toContain('Klip pertama');
  });
});

describe('generateVtt', () => {
  const sampleWords: Word[] = [
    { s: 5.0, e: 5.5, t: 'Klip' },
    { s: 5.6, e: 6.0, t: 'pertama' },
  ];

  it('generates valid WebVTT format', () => {
    const vtt = generateVtt(sampleWords, 5.0, 7.0);
    expect(vtt.startsWith('WEBVTT')).toBe(true);
    expect(vtt).toContain('00:00:00.000 -->');
    expect(vtt).toContain('Klip pertama');
  });
});

describe('generateAss', () => {
  const sampleWords: Word[] = [
    { s: 0.0, e: 0.5, t: 'AutoClip' },
    { s: 0.6, e: 1.0, t: 'Viral' },
  ];

  it('generates valid ASS header and dialogue', () => {
    const ass = generateAss(sampleWords, 0.0, 2.0, { style: 'viral', aspectRatio: '9:16_blur' });
    expect(ass).toContain('[Script Info]');
    expect(ass).toContain('PlayResX: 1080');
    expect(ass).toContain('PlayResY: 1920');
    expect(ass).toContain('Dialogue:');
  });

  it('highlights the word being spoken, like the preview', () => {
    const ass = generateAss(sampleWords, 0.0, 2.0, { style: 'viral', aspectRatio: '9:16_blur', uppercase: true });
    const lines = ass.split('\n').filter((l) => l.startsWith('Dialogue:'));
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain('0:00:00.00,0:00:00.60');
    expect(lines[0]).toContain('{\\c&H15CCFA&}AUTOCLIP{\\r} VIRAL');
    expect(lines[1]).toContain('AUTOCLIP {\\c&H15CCFA&}VIRAL{\\r}');
  });

  it('generates classic style as one plain line per cue', () => {
    const ass = generateAss(sampleWords, 0.0, 2.0, { style: 'classic', aspectRatio: '16:9' });
    expect(ass).toContain('PlayResX: 1920');
    expect(ass).toContain('PlayResY: 1080');
    expect(ass).not.toContain('\\c&H');
    expect(ass.split('\n').filter((l) => l.startsWith('Dialogue:'))).toHaveLength(1);
  });

  it('keeps braces and backslashes out of caption text', () => {
    const ass = generateAss([{ s: 0, e: 0.5, t: '{\\b1}hai' }], 0, 1, { style: 'classic', uppercase: false });
    expect(ass).toContain(',,/b1hai');
  });
});

describe('buildExportCommand', () => {
  it('generates valid yt-dlp and ffmpeg command', () => {
    const cmd = buildExportCommand('https://youtu.be/xyz', 10.0, 25.5, 'Momen Lucu', {
      aspectRatio: '9:16_blur',
      burnCaptions: true,
    });
    expect(cmd).toContain('yt-dlp --download-sections "*10.00-25.50"');
    expect(cmd).toContain('Momen_Lucu.mp4');
    expect(cmd).toContain('boxblur');
    expect(cmd).toContain('subtitles=');
  });
});

