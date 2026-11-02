import type { Clip, LoadedProject, ProjectMeta, ProjectSummary, Settings, Word } from './types';

const SETTINGS_KEY = 'autoclip.settings.v1';
const INDEX_KEY = 'autoclip.projects.v1';
const metaKey = (id: string) => `autoclip.project.${id}`;
const wordsKey = (id: string) => `autoclip.words.${id}`;

export const DEFAULT_SETTINGS: Settings = {
  helperUrl: 'http://127.0.0.1:8765',
  provider: 'gemini',
  apiKeys: {},
  models: {},
  minSec: 30,
  maxSec: 90,
  maxClips: 8,
  instructions: '',
  padStart: 0.15,
  padEnd: 0.35,
  captionEnabled: true,
  captionStyle: 'viral',
  captionPosition: 'bottom',
  captionUppercase: true,
  aspectRatio: '9:16_blur',
};

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

/** Write, evicting the oldest projects when storage is full. */
function write(key: string, value: unknown) {
  const raw = JSON.stringify(value);
  for (let attempt = 0; attempt < 10; attempt++) {
    try {
      localStorage.setItem(key, raw);
      return;
    } catch {
      const index = listProjects();
      const victim = index.filter((p) => !key.endsWith(p.id)).pop();
      if (!victim) break;
      deleteProject(victim.id);
    }
  }
  throw new Error('Penyimpanan browser penuh. Hapus beberapa proyek lama.');
}

export function loadSettings(): Settings {
  const s = read<Partial<Settings>>(SETTINGS_KEY) ?? {};
  return { ...DEFAULT_SETTINGS, ...s, apiKeys: { ...s.apiKeys }, models: { ...s.models } };
}

export function saveSettings(s: Settings) {
  write(SETTINGS_KEY, s);
}

/** Most recently updated first. */
export function listProjects(): ProjectSummary[] {
  return (read<ProjectSummary[]>(INDEX_KEY) ?? []).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

function upsertIndex(meta: ProjectMeta, clipCount: number) {
  const index = listProjects().filter((p) => p.id !== meta.id);
  index.unshift({ id: meta.id, title: meta.video.title, videoId: meta.video.id, clipCount, updatedAt: meta.updatedAt });
  write(INDEX_KEY, index);
}

/** Words are large and rarely change, so they live under their own key. */
export function saveWords(id: string, words: Word[]) {
  write(wordsKey(id), words.map((w) => [w.s, w.e, w.t]));
}

export function saveProject(meta: ProjectMeta, clips: Clip[], compilation: string[] = []) {
  const updated = { ...meta, updatedAt: new Date().toISOString() };
  write(metaKey(meta.id), { meta: updated, clips, compilation });
  upsertIndex(updated, clips.length);
}

export function loadProject(id: string): LoadedProject | null {
  const data = read<{ meta: ProjectMeta; clips: Clip[]; compilation?: string[] }>(metaKey(id));
  const words = read<[number, number, string][]>(wordsKey(id));
  if (!data || !words) return null;
  return {
    meta: data.meta,
    clips: data.clips,
    compilation: data.compilation ?? [],
    words: words.map(([s, e, t]) => ({ s, e, t })),
  };
}

export function deleteProject(id: string) {
  localStorage.removeItem(metaKey(id));
  localStorage.removeItem(wordsKey(id));
  const index = (read<ProjectSummary[]>(INDEX_KEY) ?? []).filter((p) => p.id !== id);
  localStorage.setItem(INDEX_KEY, JSON.stringify(index));
}
