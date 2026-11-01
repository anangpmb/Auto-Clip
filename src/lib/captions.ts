import type { Word } from './types';

export type CaptionStyle = 'viral' | 'box' | 'classic' | 'neon';
export type CaptionPosition = 'bottom' | 'center' | 'top';
export type AspectRatio = '16:9' | '9:16_blur' | '9:16_crop';

export interface CaptionWord {
  start: number; // in seconds relative to clip start
  end: number;
  text: string;
}

export interface CaptionCue {
  id: number;
  start: number; // relative to clip start
  end: number;
  text: string;
  words: CaptionWord[];
}

export interface CaptionOptions {
  maxWordsPerCue?: number;
  maxDuration?: number;
  pauseThreshold?: number;
  uppercase?: boolean;
}

export interface AssOptions {
  style?: CaptionStyle;
  position?: CaptionPosition;
  aspectRatio?: AspectRatio;
  uppercase?: boolean;
  title?: string;
}

/**
 * Format seconds into SRT timestamp format: HH:MM:SS,mmm
 */
export function formatSrtTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  const ms = Math.floor((s - Math.floor(s)) * 1000);
  return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')},${String(ms).padStart(3, '0')}`;
}

/**
 * Format seconds into WebVTT timestamp format: HH:MM:SS.mmm
 */
export function formatVttTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  const ms = Math.floor((s - Math.floor(s)) * 1000);
  return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

/**
 * Format seconds into ASS timestamp format: H:MM:SS.cc (centiseconds)
 */
export function formatAssTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = Math.floor(s % 60);
  const cs = Math.floor(((s - Math.floor(s)) * 100) % 100);
  return `${hrs}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(cs).padStart(2, '0')}`;
}

/**
 * Groups words within clip bounds into readable subtitle cues.
 * Timestamps in the returned cues are relative to `clipStart`.
 */
export function groupWordsIntoCues(
  words: Word[],
  clipStart: number,
  clipEnd: number,
  options: CaptionOptions = {}
): CaptionCue[] {
  const { maxWordsPerCue = 5, maxDuration = 2.4, pauseThreshold = 0.45, uppercase = false } = options;

  // Filter words that fall within or overlap the clip window
  const inRange = words.filter((w) => w.e >= clipStart && w.s <= clipEnd);
  if (!inRange.length) return [];

  const cues: CaptionCue[] = [];
  let currentWords: CaptionWord[] = [];
  let cueId = 1;

  function commitCue() {
    if (!currentWords.length) return;
    const start = Math.max(0, currentWords[0].start);
    const end = Math.max(start + 0.3, currentWords[currentWords.length - 1].end);
    const text = currentWords.map((w) => w.text).join(' ');
    cues.push({
      id: cueId++,
      start: +start.toFixed(3),
      end: +end.toFixed(3),
      text,
      words: [...currentWords],
    });
    currentWords = [];
  }

  for (let i = 0; i < inRange.length; i++) {
    const w = inRange[i];
    const prev = inRange[i - 1];

    const relStart = Math.max(0, +(w.s - clipStart).toFixed(3));
    const relEnd = Math.max(relStart + 0.05, +(w.e - clipStart).toFixed(3));
    const rawText = uppercase ? w.t.toUpperCase() : w.t;

    const wordItem: CaptionWord = {
      start: relStart,
      end: relEnd,
      text: rawText,
    };

    if (currentWords.length > 0) {
      const prevEnd = currentWords[currentWords.length - 1].end;
      const pause = relStart - prevEnd;
      const cueDuration = relEnd - currentWords[0].start;
      const prevText = prev?.t || '';
      const endsSentence = /[.!?]$/.test(prevText.trim());

      const shouldSplit =
        currentWords.length >= maxWordsPerCue ||
        pause >= pauseThreshold ||
        endsSentence ||
        cueDuration >= maxDuration;

      if (shouldSplit) {
        commitCue();
      }
    }

    currentWords.push(wordItem);
  }

  commitCue();
  return cues;
}

/**
 * Generates SubRip (.srt) subtitle string for a clip.
 */
export function generateSrt(words: Word[], clipStart: number, clipEnd: number, options: CaptionOptions = {}): string {
  const cues = groupWordsIntoCues(words, clipStart, clipEnd, options);
  if (!cues.length) return '';

  return cues
    .map(
      (c) =>
        `${c.id}\n${formatSrtTime(c.start)} --> ${formatSrtTime(c.end)}\n${c.text}\n`
    )
    .join('\n');
}

/**
 * Generates WebVTT (.vtt) subtitle string for a clip.
 */
export function generateVtt(words: Word[], clipStart: number, clipEnd: number, options: CaptionOptions = {}): string {
  const cues = groupWordsIntoCues(words, clipStart, clipEnd, options);
  let vtt = 'WEBVTT\n\n';
  if (!cues.length) return vtt;

  vtt += cues
    .map(
      (c) =>
        `${c.id}\n${formatVttTime(c.start)} --> ${formatVttTime(c.end)}\n${c.text}\n`
    )
    .join('\n');

  return vtt;
}

/**
 * Generates Advanced SubStation Alpha (.ass) subtitle string for a clip.
 * ASS allows stylized viral captions (karaoke highlight, custom fonts, borders, positioning).
 */
export function generateAss(words: Word[], clipStart: number, clipEnd: number, options: AssOptions = {}): string {
  const {
    style = 'viral',
    position = 'bottom',
    aspectRatio = '16:9',
    uppercase = true,
    title = 'AutoClip Subtitle',
  } = options;

  const isVertical = aspectRatio.startsWith('9:16');
  const resX = isVertical ? 1080 : 1920;
  const resY = isVertical ? 1920 : 1080;

  // Font sizing and margin adjustments
  let fontSize = isVertical ? 68 : 52;
  let outlineSize = isVertical ? 6 : 4;
  let shadowSize = isVertical ? 2 : 2;
  let marginV = isVertical ? 280 : 80;
  if (position === 'center') marginV = isVertical ? 860 : 480;
  if (position === 'top') marginV = isVertical ? 260 : 80;

  // Alignment in ASS: 2 = Bottom Center, 5 = Middle Center, 8 = Top Center
  const alignment = position === 'center' ? 5 : position === 'top' ? 8 : 2;

  // Colors in ASS format: &HAABBGGRR (Hex)
  // Default White: &H00FFFFFF
  // Active Highlight Yellow: &H0000FFFF (BGR) -> &H0015CCFA (Amber/Yellow)
  let primaryColor = '&H00FFFFFF';
  let secondaryColor = '&H0015CCFA'; // Highlight color
  let outlineColor = '&H00000000';
  let backColor = '&H80000000';
  let borderStyle = 1; // 1 = Outline + drop shadow, 3 = Opaque box

  if (style === 'box') {
    borderStyle = 3; // Opaque box background
    fontSize = isVertical ? 58 : 46;
    outlineSize = isVertical ? 12 : 8;
    backColor = '&H99000000'; // 60% black background
  } else if (style === 'neon') {
    secondaryColor = '&H00FFFF00'; // Cyan highlight
    outlineColor = '&H00330011';
    outlineSize = isVertical ? 7 : 5;
  } else if (style === 'classic') {
    fontSize = isVertical ? 54 : 42;
    outlineSize = isVertical ? 4 : 3;
    secondaryColor = '&H00FFFFFF';
  }

  const cues = groupWordsIntoCues(words, clipStart, clipEnd, { uppercase, maxWordsPerCue: isVertical ? 4 : 6 });

  let ass = `[Script Info]
Title: ${title}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: ${resX}
PlayResY: ${resY}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,${fontSize},${primaryColor},${secondaryColor},${outlineColor},${backColor},-1,0,0,0,100,100,1,0,${borderStyle},${outlineSize},${shadowSize},${alignment},40,40,${marginV},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`;

  for (const cue of cues) {
    const cueStartStr = formatAssTime(cue.start);
    const cueEndStr = formatAssTime(cue.end);

    if (style === 'viral' || style === 'neon') {
      // For each word in the cue, emit timed karaoke tag {\k<centiseconds>}
      // Or dialogue events that highlight each word during its speech
      let lineText = '';
      for (const w of cue.words) {
        const durCs = Math.max(5, Math.round((w.end - w.start) * 100));
        lineText += `{\\k${durCs}}${w.text} `;
      }
      ass += `Dialogue: 0,${cueStartStr},${cueEndStr},Default,,0,0,0,,${lineText.trim()}\n`;
    } else {
      // Clean regular subtitle text
      ass += `Dialogue: 0,${cueStartStr},${cueEndStr},Default,,0,0,0,,${cue.text}\n`;
    }
  }

  return ass;
}

/**
 * Triggers a file download in the browser.
 */
export function downloadFile(filename: string, content: string | Blob, mimeType = 'text/plain;charset=utf-8'): void {
  const blob = typeof content === 'string' ? new Blob([content], { type: mimeType }) : content;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Builds a ready-to-run FFmpeg and yt-dlp export command for the user to copy.
 */
export function buildExportCommand(
  url: string,
  start: number,
  end: number,
  title: string,
  options: {
    aspectRatio?: AspectRatio;
    burnCaptions?: boolean;
    srtFilename?: string;
  } = {}
): string {
  const { aspectRatio = '16:9', burnCaptions = true, srtFilename } = options;
  const safeTitle = title.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, '_') || 'clip';
  const outName = `${safeTitle}.mp4`;
  const srtName = srtFilename || `${safeTitle}.srt`;

  let filter = '';
  if (aspectRatio === '9:16_blur') {
    filter = `[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2`;
    if (burnCaptions) filter += `,subtitles='${srtName}'`;
  } else if (aspectRatio === '9:16_crop') {
    filter = `crop=ih*9/16:ih,scale=1080:1920`;
    if (burnCaptions) filter += `,subtitles='${srtName}'`;
  } else if (burnCaptions) {
    filter = `subtitles='${srtName}'`;
  }

  const vfPart = filter ? (filter.includes(';') ? `-filter_complex "${filter}"` : `-vf "${filter}"`) : '';

  return (
    `yt-dlp --download-sections "*${start.toFixed(2)}-${end.toFixed(2)}" --force-keyframes-at-cuts ` +
    `-f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b" -o "raw_${outName}" "${url}" && ` +
    `ffmpeg -i "raw_${outName}" ${vfPart ? vfPart + ' ' : ''}-c:v libx264 -c:a aac -pix_fmt yuv420p "${outName}" && ` +
    `rm "raw_${outName}"`
  );
}

