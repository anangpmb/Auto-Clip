import type { Clip, ProviderId, Settings, Unit, Word } from './types';
import { fitDuration, fmtTime } from './transcript';

export const PROVIDERS: Record<ProviderId, { label: string; defaultModel: string; keyUrl: string }> = {
  gemini: { label: 'Google Gemini', defaultModel: 'gemini-3.5-flash-lite', keyUrl: 'https://aistudio.google.com/apikey' },
  openai: { label: 'OpenAI', defaultModel: 'gpt-5-mini', keyUrl: 'https://platform.openai.com/api-keys' },
  anthropic: { label: 'Anthropic Claude', defaultModel: 'claude-sonnet-5-5', keyUrl: 'https://console.anthropic.com/settings/keys' },
  openrouter: { label: 'OpenRouter', defaultModel: 'deepseek/deepseek-v4-flash', keyUrl: 'https://openrouter.ai/keys' },
};

/** Transcript characters sent to the model per request. */
const CHUNK_CHARS = 60_000;
const REQUEST_TIMEOUT_MS = 180_000;

export function newId(): string {
  return crypto.randomUUID();
}

export function buildSystemPrompt(s: Settings, maxClips: number): string {
  const target = Math.round((s.minSec + s.maxSec) / 2);
  let prompt = `You are an experienced short-form video editor. You receive the transcript of a long video, split into numbered units. Each line looks like:
[id] mm:ss (length) text

Pick segments that work as standalone vertical short videos (TikTok, Reels, Shorts).

Rules:
1. Length: every clip must last between ${s.minSec} and ${s.maxSec} seconds in total. Aim for about ${target} seconds.
2. Context: a viewer who has not seen the full video must understand the clip. Include the setup or question the moment depends on.
3. Clean start: begin on a unit that opens a new thought, question or story. Never begin mid-argument or on a connector (and, but, so, because, then, dan, tapi, jadi, karena, terus, nah).
4. Clean ending: end on the unit that completes the thought: the answer, punchline, conclusion or reaction. If the next unit still continues the same sentence or idea, include it or end earlier at a complete point.
5. Each clip covers a different moment. Small overlaps at the edges are fine.
6. Skip ads, sponsor reads, intros, outros and requests to like or subscribe.
7. Prefer moments with a strong hook in the first seconds: a bold claim, a question, a surprise, humour, conflict or emotion.

Write "title" and "reason" in the same language as the transcript. title: at most 70 characters, catchy, no hashtags. reason: one short sentence on why the moment works. score: 1-100 for viral potential; be critical.

Return JSON only, in this shape:
{"clips":[{"start_id":0,"end_id":0,"title":"","reason":"","score":0}]}
Return at most ${maxClips} clips, best first, or {"clips":[]} if nothing qualifies.`;
  if (s.instructions.trim()) prompt += `\n\nExtra instructions from the user:\n${s.instructions.trim()}`;
  return prompt;
}

export function formatUnits(units: Unit[]): string {
  return units.map((u) => `[${u.id}] ${fmtTime(u.s)} (${Math.max(1, Math.round(u.e - u.s))}s) ${u.text}`).join('\n');
}

/** Split units into request-sized chunks that overlap by about overlapSec. */
export function chunkUnits(units: Unit[], maxChars: number, overlapSec: number): Unit[][] {
  const chunks: Unit[][] = [];
  let i = 0;
  while (i < units.length) {
    let chars = 0;
    let j = i;
    while (j < units.length && (j === i || chars + units[j].text.length + 20 <= maxChars)) {
      chars += units[j].text.length + 20;
      j++;
    }
    chunks.push(units.slice(i, j));
    if (j >= units.length) break;
    let k = j;
    while (k > i + 1 && units[j - 1].e - units[k - 1].s < overlapSec) k--;
    i = k;
  }
  return chunks;
}

export function parseModelJson(text: string): unknown {
  const t = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
  try {
    return JSON.parse(t);
  } catch {
    /* fall through to brace extraction */
  }
  const a = t.indexOf('{');
  const b = t.lastIndexOf('}');
  if (a >= 0 && b > a) {
    try {
      return JSON.parse(t.slice(a, b + 1));
    } catch {
      /* reported below */
    }
  }
  throw new Error('Jawaban AI bukan JSON yang valid. Coba lagi atau ganti model.');
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Turn the model's answer for one chunk into clips on word indices. */
export function toClips(raw: unknown, units: Unit[], chunk: Unit[], minSec: number, maxSec: number): Clip[] {
  const list = Array.isArray(raw) ? raw : (raw as { clips?: unknown } | null)?.clips;
  if (!Array.isArray(list) || !chunk.length) return [];
  const lo = chunk[0].id;
  const hi = chunk[chunk.length - 1].id;
  const out: Clip[] = [];
  for (const r of list as Record<string, unknown>[]) {
    let a = Math.round(Number(r?.start_id ?? r?.start));
    let b = Math.round(Number(r?.end_id ?? r?.end));
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
    if (a > b) [a, b] = [b, a];
    a = clamp(a, lo, hi);
    b = clamp(b, lo, hi);
    [a, b] = fitDuration(units, a, b, minSec, maxSec);
    const w0 = units[a].w0;
    const w1 = units[b].w1;
    out.push({
      id: newId(),
      title: String(r.title ?? '').trim().slice(0, 120) || 'Klip tanpa judul',
      reason: String(r.reason ?? '').trim(),
      score: clamp(Math.round(Number(r.score) || 0), 0, 100),
      w0,
      w1,
      aiW0: w0,
      aiW1: w1,
    });
  }
  return out;
}

/** Keep the best clips, drop ones that mostly overlap a better one, sort by time. */
export function dedupe(clips: Clip[], words: Word[], max: number): Clip[] {
  const kept: Clip[] = [];
  for (const c of [...clips].sort((a, b) => b.score - a.score)) {
    const cs = words[c.w0].s;
    const ce = words[c.w1].e;
    const clash = kept.some((k) => {
      const ks = words[k.w0].s;
      const ke = words[k.w1].e;
      const overlap = Math.min(ce, ke) - Math.max(cs, ks);
      return overlap > 0.5 * Math.min(ce - cs, ke - ks);
    });
    if (!clash) kept.push(c);
    if (kept.length >= max) break;
  }
  return kept.sort((a, b) => a.w0 - b.w0);
}

async function httpError(res: Response, provider: ProviderId): Promise<Error> {
  const raw = await res.text().catch(() => '');
  let msg = raw.slice(0, 300);
  try {
    const j = JSON.parse(raw);
    msg = j?.error?.message || j?.message || msg;
  } catch {
    /* keep raw text */
  }
  const label = PROVIDERS[provider].label;
  let hint = '';
  if (res.status === 401 || res.status === 403) hint = 'API key ditolak atau tidak punya akses ke model ini. ';
  else if (res.status === 404) hint = 'Model tidak ditemukan. Cek nama model di Pengaturan. ';
  else if (res.status === 429) hint = 'Kuota atau batas permintaan habis. Tunggu sebentar atau cek paket API kamu. ';
  else if (res.status >= 500) hint = 'Server AI sedang sibuk. Coba lagi sebentar lagi. ';
  return new Error(`${label} (${res.status}): ${hint}${msg}`);
}

async function postJson(url: string, headers: Record<string, string>, body: unknown, provider: ProviderId, signal?: AbortSignal) {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    if (timeout.aborted) throw new Error('AI terlalu lama menjawab. Coba lagi.');
    throw new Error(`Tidak bisa menghubungi ${PROVIDERS[provider].label}. Cek koneksi internet.`);
  }
  if (!res.ok) throw await httpError(res, provider);
  return res.json();
}

export async function callModel(s: Settings, system: string, user: string, signal?: AbortSignal): Promise<string> {
  const provider = s.provider;
  const key = (s.apiKeys[provider] ?? '').trim();
  const model = (s.models[provider] ?? '').trim() || PROVIDERS[provider].defaultModel;

  if (provider === 'gemini') {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;
    const data = await postJson(
      url,
      { 'x-goog-api-key': key },
      {
        systemInstruction: { parts: [{ text: system }] },
        contents: [{ role: 'user', parts: [{ text: user }] }],
        generationConfig: { responseMimeType: 'application/json', temperature: 0.4 },
      },
      provider,
      signal,
    );
    const cand = data?.candidates?.[0];
    const text = (cand?.content?.parts ?? [])
      .filter((p: { thought?: boolean }) => !p.thought)
      .map((p: { text?: string }) => p.text ?? '')
      .join('');
    if (!text) throw new Error(`Gemini tidak memberi jawaban (${cand?.finishReason ?? data?.promptFeedback?.blockReason ?? 'kosong'}).`);
    return text;
  }

  if (provider === 'anthropic') {
    const data = await postJson(
      'https://api.anthropic.com/v1/messages',
      {
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      { model, max_tokens: 8000, system, messages: [{ role: 'user', content: user }] },
      provider,
      signal,
    );
    return (data?.content ?? [])
      .filter((b: { type: string }) => b.type === 'text')
      .map((b: { text: string }) => b.text)
      .join('');
  }

  const url = provider === 'openai' ? 'https://api.openai.com/v1/chat/completions' : 'https://openrouter.ai/api/v1/chat/completions';
  const body: Record<string, unknown> = {
    model,
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
  };
  if (provider === 'openai') body.response_format = { type: 'json_object' };
  const data = await postJson(url, { Authorization: `Bearer ${key}` }, body, provider, signal);
  return data?.choices?.[0]?.message?.content ?? '';
}

export interface FindClipsOptions {
  title: string;
  signal?: AbortSignal;
  onProgress?: (message: string) => void;
}

export async function findClips(words: Word[], units: Unit[], s: Settings, opts: FindClipsOptions): Promise<Clip[]> {
  if (!(s.apiKeys[s.provider] ?? '').trim()) throw new Error('Isi API key dulu di Pengaturan.');
  if (!units.length) throw new Error('Transkrip kosong.');
  const chunks = chunkUnits(units, CHUNK_CHARS, s.maxSec + 30);
  const perChunk = Math.min(s.maxClips, Math.max(3, Math.ceil(s.maxClips / chunks.length) + 2));
  const system = buildSystemPrompt(s, perChunk);
  const all: Clip[] = [];
  for (let i = 0; i < chunks.length; i++) {
    opts.onProgress?.(chunks.length > 1 ? `AI membaca bagian ${i + 1} dari ${chunks.length}…` : 'AI membaca transkrip…');
    const user = `Video title: ${opts.title}\n\nTranscript:\n${formatUnits(chunks[i])}`;
    const text = await callModel(s, system, user, opts.signal);
    all.push(...toClips(parseModelJson(text), units, chunks[i], s.minSec, s.maxSec));
  }
  return dedupe(all, words, s.maxClips);
}
