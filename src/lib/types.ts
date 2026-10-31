export type ProviderId = 'gemini' | 'openai' | 'anthropic' | 'openrouter';

/** One spoken word with its start/end time in seconds. */
export interface Word {
  s: number;
  e: number;
  t: string;
}

/** A sentence-like run of words. Used for AI selection and for snapping. */
export interface Unit {
  id: number;
  w0: number;
  w1: number;
  s: number;
  e: number;
  text: string;
}

export interface Clip {
  id: string;
  title: string;
  reason: string;
  score: number;
  /** Inclusive word range currently used for the clip. */
  w0: number;
  w1: number;
  /** Word range suggested by the AI (for "reset"); null for manual clips. */
  aiW0: number | null;
  aiW1: number | null;
}

export interface VideoInfo {
  id: string;
  title: string;
  channel: string;
  duration: number;
  thumbnail: string;
  url: string;
  language: string | null;
}

export interface Track {
  key: string;
  lang: string;
  kind: 'manual' | 'auto';
  name: string;
}

export type WordTiming = 'exact' | 'estimated';

export interface ProjectMeta {
  id: string;
  video: VideoInfo;
  tracks: Track[];
  track: string;
  wordTiming: WordTiming;
  createdAt: string;
  updatedAt: string;
}

export interface LoadedProject {
  meta: ProjectMeta;
  words: Word[];
  clips: Clip[];
}

export interface ProjectSummary {
  id: string;
  title: string;
  videoId: string;
  clipCount: number;
  updatedAt: string;
}

export interface Settings {
  helperUrl: string;
  provider: ProviderId;
  apiKeys: Partial<Record<ProviderId, string>>;
  models: Partial<Record<ProviderId, string>>;
  minSec: number;
  maxSec: number;
  maxClips: number;
  instructions: string;
  padStart: number;
  padEnd: number;
}
