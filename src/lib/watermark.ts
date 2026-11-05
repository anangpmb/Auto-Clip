/** Source-channel watermark: one quiet line of attribution burned into the exported video. */

export type WatermarkPosition = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
export type WatermarkSize = 'small' | 'medium';
export type WatermarkStyle = 'text' | 'shaded';

export interface WatermarkSettings {
  enabled: boolean;
  position: WatermarkPosition;
  size: WatermarkSize;
  opacity: number;
  style: WatermarkStyle;
}

export interface WatermarkPayload extends WatermarkSettings {
  text: string;
}

export const DEFAULT_WATERMARK_SETTINGS: WatermarkSettings = {
  enabled: true,
  position: 'top-right',
  size: 'small',
  opacity: 0.7,
  style: 'text',
};

export const WATERMARK_POSITIONS: WatermarkPosition[] = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];
export const WATERMARK_SIZES: WatermarkSize[] = ['small', 'medium'];
export const WATERMARK_STYLES: WatermarkStyle[] = ['text', 'shaded'];

/** Font height as a share of the frame height, so preview and export scale alike. */
export function watermarkFontShare(size: WatermarkSize): number {
  return size === 'medium' ? 0.04 : 0.028;
}

function clampOpacity(v: number): number {
  if (!Number.isFinite(v)) return DEFAULT_WATERMARK_SETTINGS.opacity;
  return Math.min(0.9, Math.max(0.4, v));
}

/**
 * The watermark that actually goes into a video: the saved preferences plus the
 * channel name for this project, or a per-export edit of it. An empty text or a
 * switched-off watermark means no watermark, never a placeholder.
 */
export function resolveWatermark(
  settings: Partial<WatermarkSettings> | undefined,
  channel: string,
  textOverride?: string,
): WatermarkPayload | null {
  const merged: WatermarkSettings = { ...DEFAULT_WATERMARK_SETTINGS, ...settings };
  if (!merged.enabled) return null;
  const text = (textOverride?.trim() || channel.trim()).slice(0, 120);
  if (!text) return null;
  return {
    enabled: true,
    position: WATERMARK_POSITIONS.includes(merged.position) ? merged.position : DEFAULT_WATERMARK_SETTINGS.position,
    size: WATERMARK_SIZES.includes(merged.size) ? merged.size : DEFAULT_WATERMARK_SETTINGS.size,
    opacity: clampOpacity(merged.opacity),
    style: WATERMARK_STYLES.includes(merged.style) ? merged.style : DEFAULT_WATERMARK_SETTINGS.style,
    text,
  };
}

/** Top-left corner of the watermark box inside a frame, in pixels. */
export function watermarkXY(
  position: WatermarkPosition,
  frameW: number,
  frameH: number,
  boxW: number,
  boxH: number,
): [number, number] {
  const mx = Math.round(frameW * 0.03);
  const my = Math.round(frameH * 0.035);
  const x = position.endsWith('right') ? frameW - mx - boxW : mx;
  const y = position.startsWith('bottom') ? frameH - my - boxH : my;
  return [Math.max(0, x), Math.max(0, y)];
}

/**
 * Characters that would break the shell-quoted manual export command are dropped
 * from the drawtext text (the helper render keeps the full channel name). The
 * remaining text is safe inside the single quotes drawtext uses.
 */
export function cleanDrawtextText(text: string): string {
  return text.replace(/[^A-Za-z0-9 _\-.&()]+/g, '').replace(/\s+/g, ' ').trim();
}

/** FFmpeg drawtext filter for the manual yt-dlp + FFmpeg command. */
export function watermarkDrawtext(w: WatermarkPayload): string {
  const text = cleanDrawtextText(w.text);
  if (!text) return '';
  const pos: Record<WatermarkPosition, string> = {
    'top-left': "x='w*0.03':y='h*0.035'",
    'top-right': "x='w-text_w-w*0.03':y='h*0.035'",
    'bottom-left': "x='w*0.03':y='h-text_h-h*0.035'",
    'bottom-right': "x='w-text_w-w*0.03':y='h-text_h-h*0.035'",
  };
  const fontcolor = `white@${w.opacity}`;
  const base = `drawtext=text='${text}':fontsize='h*${watermarkFontShare(w.size)}':fontcolor=${fontcolor}:${pos[w.position]}`;
  return w.style === 'shaded'
    ? `${base}:box=1:boxcolor=black@0.45:boxborderw=10`
    : `${base}:borderw=1:bordercolor=black@${w.opacity}`;
}
