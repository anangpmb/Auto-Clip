<script lang="ts">
  import { untrack } from 'svelte';
  import Player from './Player.svelte';
  import Timeline from './Timeline.svelte';
  import TranscriptPane from './TranscriptPane.svelte';
  import type { Clip, Settings, Unit, Word } from '../lib/types';
  import {
    clipBounds,
    durationStatus,
    fmtDuration,
    fmtTime,
    sentenceStep,
    unitIndexOfWord,
    wordIndexAt,
  } from '../lib/transcript';

  type Edge = 'start' | 'end';
  interface Props {
    words: Word[];
    units: Unit[];
    clip: Clip;
    videoId: string;
    settings: Settings;
    onchange: (clip: Clip) => void;
    ontime?: (t: number) => void;
  }
  let { words, units, clip, videoId, settings, onchange, ontime }: Props = $props();

  let player = $state<ReturnType<typeof Player>>();
  let snap = $state(true);
  let lo = $state(0);
  let hi = $state(0);
  let currentTime = $state(0);
  let playing = $state(false);
  let viewFor = '';

  const bounds = $derived(clipBounds(words, clip.w0, clip.w1, settings.padStart, settings.padEnd));
  const duration = $derived(bounds.end - bounds.start);
  const status = $derived(durationStatus(duration, settings.minSec, settings.maxSec));
  const currentWord = $derived(currentTime > 0 ? wordIndexAt(words, currentTime) : -1);
  const edited = $derived(clip.aiW0 !== null && (clip.w0 !== clip.aiW0 || clip.w1 !== clip.aiW1));

  const unitStartAt = (t: number) => units[unitIndexOfWord(units, Math.max(0, wordIndexAt(words, t)))].w0;
  const unitEndAt = (t: number, atLeast: number) =>
    units[unitIndexOfWord(units, Math.min(words.length - 1, Math.max(atLeast, wordIndexAt(words, t))))].w1;

  $effect(() => {
    if (clip.id === viewFor) return;
    viewFor = clip.id;
    untrack(resetView);
  });

  function resetView() {
    const s = words[clip.w0].s;
    const e = words[clip.w1].e;
    const ctx = Math.max(20, Math.min(60, (e - s) * 0.6));
    lo = unitStartAt(s - ctx);
    hi = unitEndAt(e + ctx, clip.w1);
  }

  /** Grow the visible range so the clip edges keep some context around them. */
  function ensureContext(w0: number, w1: number) {
    if (w0 < lo || words[w0].s - words[lo].s < 10) lo = Math.min(lo, unitStartAt(words[w0].s - 25));
    if (w1 > hi || words[hi].e - words[w1].e < 10) hi = Math.max(hi, unitEndAt(words[w1].e + 25, w1));
  }

  function expand(dir: -1 | 1) {
    if (dir < 0) lo = unitStartAt(words[lo].s - 30);
    else hi = unitEndAt(words[hi].e + 30, Math.min(words.length - 1, hi + 1));
  }

  function setRange(w0: number, w1: number, dragging = false) {
    w0 = Math.max(0, Math.min(w0, words.length - 1));
    w1 = Math.max(0, Math.min(w1, words.length - 1));
    if (w0 > w1 || (w0 === clip.w0 && w1 === clip.w1)) return;
    onchange({ ...clip, w0, w1 });
    if (!dragging) ensureContext(w0, w1);
  }
  const setStart = (wi: number, dragging = false) => setRange(Math.min(wi, clip.w1), clip.w1, dragging);
  const setEnd = (wi: number, dragging = false) => setRange(clip.w0, Math.max(wi, clip.w0), dragging);

  function nudge(edge: Edge, dir: -1 | 1, bySentence: boolean) {
    if (edge === 'start') setStart(bySentence ? sentenceStep(units, 'start', clip.w0, dir) : clip.w0 + dir);
    else setEnd(bySentence ? sentenceStep(units, 'end', clip.w1, dir) : clip.w1 + dir);
  }

  function resetToAi() {
    if (clip.aiW0 === null || clip.aiW1 === null) return;
    onchange({ ...clip, w0: clip.aiW0, w1: clip.aiW1 });
    ensureContext(clip.aiW0, clip.aiW1);
  }

  const playClip = () => player?.playRange(bounds.start, bounds.end);
  const checkStart = () => player?.playRange(bounds.start, Math.min(bounds.end, bounds.start + 4));
  const checkEnd = () => player?.playRange(Math.max(bounds.start, bounds.end - 4), bounds.end);
  function playFromWord(wi: number) {
    const from = Math.max(0, words[wi].s - 0.1);
    player?.playRange(from, from < bounds.end - 1 ? bounds.end : from + 8);
  }
  const seek = (t: number) => player?.playRange(t, t + 8);

  function handleTime(t: number, isPlaying: boolean) {
    currentTime = t;
    playing = isPlaying;
    ontime?.(t);
  }
</script>

<div class="editor">
  <div class="head">
    <input
      class="title"
      value={clip.title}
      oninput={(e) => onchange({ ...clip, title: e.currentTarget.value })}
      aria-label="Judul klip"
    />
    {#if clip.reason}<p class="reason">{clip.reason}</p>{/if}
  </div>

  <div class="top">
    {#key videoId}
      <Player bind:this={player} {videoId} ontime={handleTime} />
    {/key}

    <div class="side">
      <div class="duration {status}">
        <span class="big">{fmtDuration(duration)}</span>
        <span class="range">{fmtTime(bounds.start, true)} → {fmtTime(bounds.end, true)}</span>
        <span class="note">
          {#if status === 'short'}Lebih pendek dari {settings.minSec} dtk{:else if status === 'long'}Lebih panjang dari {settings.maxSec} dtk{:else}Durasi pas ({settings.minSec}–{settings.maxSec} dtk){/if}
        </span>
      </div>

      <div class="play">
        <button class="primary" onclick={playClip}>▶ Putar klip</button>
        <button onclick={checkStart} title="Putar 4 detik pertama">Cek awal</button>
        <button onclick={checkEnd} title="Putar 4 detik terakhir">Cek akhir</button>
        <button onclick={() => player?.pause()} aria-label="Jeda">⏸</button>
      </div>

      <div class="nudge">
        <span class="lbl start">AWAL</span>
        <button onclick={() => nudge('start', -1, true)} title="Tambah 1 kalimat sebelumnya">« kalimat</button>
        <button onclick={() => nudge('start', -1, false)} title="Mundur 1 kata">‹ kata</button>
        <button onclick={() => nudge('start', 1, false)} title="Maju 1 kata">kata ›</button>
        <button onclick={() => nudge('start', 1, true)} title="Buang kalimat pertama">kalimat »</button>
      </div>
      <div class="nudge">
        <span class="lbl end">AKHIR</span>
        <button onclick={() => nudge('end', -1, true)} title="Buang kalimat terakhir">« kalimat</button>
        <button onclick={() => nudge('end', -1, false)} title="Mundur 1 kata">‹ kata</button>
        <button onclick={() => nudge('end', 1, false)} title="Maju 1 kata">kata ›</button>
        <button onclick={() => nudge('end', 1, true)} title="Tambah 1 kalimat berikutnya">kalimat »</button>
      </div>

      <div class="opts">
        <label><input type="checkbox" bind:checked={snap} /> Seret menempel ke kalimat</label>
        {#if edited}
          <button class="ghost small" onclick={resetToAi}>↺ Kembalikan saran AI</button>
        {/if}
      </div>
    </div>
  </div>

  <Timeline
    {words}
    {units}
    {lo}
    {hi}
    w0={clip.w0}
    w1={clip.w1}
    current={currentTime}
    minSec={settings.minSec}
    maxSec={settings.maxSec}
    {snap}
    onstart={(wi) => setStart(wi, true)}
    onend={(wi) => setEnd(wi, true)}
    ondragend={() => ensureContext(clip.w0, clip.w1)}
    onseek={seek}
    onexpand={expand}
    onnudge={nudge}
  />

  <TranscriptPane
    {words}
    {units}
    {lo}
    {hi}
    w0={clip.w0}
    w1={clip.w1}
    {currentWord}
    {playing}
    {snap}
    focusKey={clip.id}
    onstart={setStart}
    onend={setEnd}
    ondragend={() => ensureContext(clip.w0, clip.w1)}
    onplay={playFromWord}
    onseek={seek}
    onexpand={expand}
  />
</div>

<style>
  .editor {
    display: grid;
    gap: 14px;
  }
  .head {
    display: grid;
    gap: 4px;
  }
  .title {
    font-size: 18px;
    font-weight: 700;
    background: transparent;
    border: 1px solid transparent;
    padding: 4px 8px;
    margin-left: -8px;
  }
  .title:hover,
  .title:focus {
    border-color: var(--border);
    background: var(--panel-2);
  }
  .reason {
    margin: 0;
    color: var(--muted);
    font-size: 13px;
  }
  .top {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(260px, 1fr);
    gap: 14px;
    align-items: start;
  }
  .side {
    display: grid;
    gap: 10px;
  }
  .duration {
    display: grid;
    gap: 2px;
    padding: 10px 12px;
    border-radius: var(--radius);
    background: var(--panel-2);
    border-left: 4px solid var(--ok);
  }
  .duration.short,
  .duration.long {
    border-left-color: var(--warn);
  }
  .big {
    font-size: 22px;
    font-weight: 800;
  }
  .range {
    font-size: 13px;
    font-variant-numeric: tabular-nums;
  }
  .note {
    font-size: 12px;
    color: var(--muted);
  }
  .duration.short .note,
  .duration.long .note {
    color: var(--warn);
  }
  .play,
  .nudge {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .nudge button {
    flex: 1;
    padding: 6px 4px;
    font-size: 12px;
  }
  .lbl {
    width: 52px;
    font-size: 11px;
    font-weight: 800;
    text-align: center;
    padding: 3px 0;
    border-radius: 4px;
  }
  .lbl.start {
    background: var(--accent);
  }
  .lbl.end {
    background: var(--accent-2);
    color: #001;
  }
  .opts {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    font-size: 13px;
    color: var(--muted);
  }
  .opts label {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  @media (max-width: 900px) {
    .top {
      grid-template-columns: 1fr;
    }
  }
</style>
