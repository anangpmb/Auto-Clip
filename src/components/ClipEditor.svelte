<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import Player from './Player.svelte';
  import Timeline from './Timeline.svelte';
  import TranscriptPane from './TranscriptPane.svelte';
  import TimeRangeSlider from './TimeRangeSlider.svelte';
  import CaptionOverlay from './CaptionOverlay.svelte';
  import ExportModal from './ExportModal.svelte';
  import ThumbnailModal from './ThumbnailModal.svelte';
  import Icon from './ui/Icon.svelte';
  import Segmented from './ui/Segmented.svelte';
  import Switch from './ui/Switch.svelte';
  import type { Clip, Settings, Unit, Word } from '../lib/types';
  import type { HelperHealth } from '../lib/helper';
  import {
    clipBoundsOrTime,
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
    videoUrl?: string;
    videoTitle?: string;
    videoChannel?: string;
    /** Source video length in seconds; used as the slider range for clips without a transcript. */
    videoDuration?: number;
    settings: Settings;
    helperOk?: boolean;
    helperHealth?: HelperHealth | null;
    onchange: (clip: Clip) => void;
    onwordedit: (wi: number, text: string) => void;
    /** Edit a whole sentence/unit; may change the word count and re-anchor clips. */
    onunitedit?: (ui: number, text: string) => void;
    ontime?: (t: number) => void;
    /** Add a new time-based (no-transcript) manual clip at the current playhead. */
    onaddtimeless?: () => void;
  }
  let {
    words,
    units,
    clip,
    videoId,
    videoUrl = '',
    videoTitle = '',
    videoChannel = '',
    videoDuration = 0,
    settings = $bindable(),
    helperOk = false,
    helperHealth = null,
    onchange,
    onwordedit,
    onunitedit,
    ontime,
    onaddtimeless,
  }: Props = $props();

  let player = $state<ReturnType<typeof Player>>();
  let snap = $state(true);
  let lo = $state(0);
  let hi = $state(0);
  let currentTime = $state(0);
  let playing = $state(false);
  let viewFor = '';
  let showExportModal = $state(false);
  let showThumbnailModal = $state(false);

  // Mini player: when the preview has been used and the user scrolls it out of view
  // (e.g. to edit the transcript), it floats in the corner instead of disappearing.
  let playerSlot: HTMLDivElement;
  let slotHidden = $state(false);
  let engaged = $state(false);
  let miniDismissed = $state(false);
  const floating = $derived(slotHidden && engaged && !miniDismissed);

  onMount(() => {
    const header = (document.querySelector('header.top') as HTMLElement | null)?.offsetHeight ?? 0;
    const io = new IntersectionObserver(([entry]) => (slotHidden = entry.intersectionRatio < 0.35), {
      rootMargin: `-${header}px 0px 0px 0px`,
      threshold: [0, 0.35, 1],
    });
    io.observe(playerSlot);
    return () => io.disconnect();
  });

  function showDockedPlayer() {
    const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    playerSlot.scrollIntoView({ block: 'start', behavior: smooth ? 'smooth' : 'auto' });
  }

  const timeless = $derived(clip.t0 !== undefined && clip.t1 !== undefined);
  const bounds = $derived(clipBoundsOrTime(words, clip, settings.padStart, settings.padEnd));
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
    if (timeless) {
      // Fit the whole (known) video into view; words may exist, but the clip ignores them.
      lo = 0;
      hi = Math.max(0, words.length - 1);
      return;
    }
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

  // Where the timeline handles sit: the free cut times if the user dragged them, else the
  // actual clip bounds (which include padding) so handles match what is played.
  const freeStart = $derived(clip.tlo ?? bounds.start);
  const freeEnd = $derived(clip.thi ?? bounds.end);

  function setRange(w0: number, w1: number, dragging = false) {
    w0 = Math.max(0, Math.min(w0, words.length - 1));
    w1 = Math.max(0, Math.min(w1, words.length - 1));
    if (w0 > w1 || (w0 === clip.w0 && w1 === clip.w1)) return;
    // Word-based change clears any free cut times, back to word-derived bounds.
    onchange({ ...clip, w0, w1, tlo: undefined, thi: undefined });
    if (!dragging) ensureContext(w0, w1);
  }
  const setStart = (wi: number, dragging = false) => setRange(Math.min(wi, clip.w1), clip.w1, dragging);
  const setEnd = (wi: number, dragging = false) => setRange(clip.w0, Math.max(wi, clip.w0), dragging);

  function nudge(edge: Edge, dir: -1 | 1, bySentence: boolean) {
    if (edge === 'start') setStart(bySentence ? sentenceStep(units, 'start', clip.w0, dir) : clip.w0 + dir);
    else setEnd(bySentence ? sentenceStep(units, 'end', clip.w1, dir) : clip.w1 + dir);
  }

  /** Free-form timeline drag: store tlo/thi and keep w0/w1 as the covered words. */
  function dragStart(t: number) {
    t = Math.min(t, freeEnd);
    // The new start time usually lands inside a word; keep the clip's end word but extend
    // the highlighted word range to the word containing t so captions cover the clip.
    const w0 = Math.max(0, wordIndexAt(words, t));
    onchange({ ...clip, w0, tlo: t, thi: freeEnd });
  }
  function dragEnd(t: number) {
    t = Math.max(t, freeStart);
    const w1 = Math.min(words.length - 1, wordIndexAt(words, t));
    onchange({ ...clip, w1, thi: t, tlo: freeStart });
  }

  function resetToAi() {
    if (clip.aiW0 === null || clip.aiW1 === null) return;
    onchange({ ...clip, w0: clip.aiW0, w1: clip.aiW1, tlo: undefined, thi: undefined });
    ensureContext(clip.aiW0, clip.aiW1);
  }

  // --- Editing a clip defined by time alone (no transcript). ---
  const sliderMax = $derived(videoDuration > 0 ? videoDuration : 3600);
  const sliderMin = 0;
  const timeStart = $derived(clip.t0 ?? sliderMin);
  const timeEnd = $derived(clip.t1 ?? sliderMax);
  function setTimeStart(t: number, dragging = false) {
    t = Math.max(0, Math.min(t, timeEnd - 0.1));
    if (t === timeStart) return;
    onchange({ ...clip, t0: t, t1: timeEnd });
  }
  function setTimeEnd(t: number, dragging = false) {
    t = Math.min(sliderMax, Math.max(t, timeStart + 0.1));
    if (t === timeEnd) return;
    onchange({ ...clip, t0: timeStart, t1: t });
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
    if (isPlaying && !playing) {
      engaged = true;
      miniDismissed = false; // a new play brings the mini player back
    }
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
    <!-- The slot keeps the player's space; only the shell moves, so the iframe never reloads. -->
    <div class="player-slot" bind:this={playerSlot}>
      <div class="player-shell" class:floating role={floating ? 'region' : undefined} aria-label={floating ? 'Pratinjau klip' : undefined}>
        {#if floating}
          <div class="mini-bar">
            <span class="mini-title">{playing ? 'Memutar' : 'Dijeda'} · {fmtTime(currentTime)}</span>
            <button class="icon-btn ghost" onclick={showDockedPlayer} aria-label="Kembali ke pemutar" title="Kembali ke pemutar">
              <Icon name="arrow-up" />
            </button>
            <button class="icon-btn ghost" onclick={() => (miniDismissed = true)} aria-label="Tutup pemutar mini" title="Tutup pemutar mini">
              <Icon name="close" />
            </button>
          </div>
        {/if}
        {#key videoId}
          <Player bind:this={player} {videoId} ontime={handleTime}>
            <CaptionOverlay
              {words}
              w0={clip.w0}
              w1={clip.w1}
              clipStart={bounds.start}
              clipEnd={bounds.end}
              {currentTime}
              enabled={!timeless && settings.captionEnabled}
              style={settings.captionStyle}
              position={settings.captionPosition}
              uppercase={settings.captionUppercase}
            />
          </Player>
        {/key}
      </div>
    </div>

    <div class="side">
      <div class="duration {status}">
        <span class="big">{fmtDuration(duration)}</span>
        <span class="range">{fmtTime(bounds.start, true)}–{fmtTime(bounds.end, true)}</span>
        <span class="badge {status === 'ok' ? 'ok' : 'warn'} dur-badge">
          {#if status === 'short'}Lebih pendek dari {settings.minSec} dtk{:else if status === 'long'}Lebih panjang dari {settings.maxSec} dtk{:else}Durasi pas{/if}
        </span>
      </div>

      <div class="play">
        <button class="play-main" onclick={playClip}><Icon name="play" /> Putar klip</button>
        <button onclick={checkStart} title="Putar 4 detik pertama">Cek awal</button>
        <button onclick={checkEnd} title="Putar 4 detik terakhir">Cek akhir</button>
        <button class="icon-btn" onclick={() => player?.pause()} aria-label="Jeda" title="Jeda"><Icon name="pause" /></button>
      </div>

      <button
        class="primary export-btn"
        onclick={() => {
          player?.pause(); // the final-result preview plays its own sound
          showExportModal = true;
        }}
      >
        <Icon name="clapperboard" /> Pratinjau hasil akhir & ekspor
      </button>
      <button class="thumbnail-btn" onclick={() => (showThumbnailModal = true)}>
        <Icon name="film" /> Buat thumbnail
      </button>
      {#if !timeless && onaddtimeless}
        <button class="ghost timeline-btn" onclick={() => onaddtimeless?.()} title="Buat klip baru yang diedit berdasarkan waktu, tanpa transkrip">
          <Icon name="clock" size={15} /> Klip manual tanpa transkrip
        </button>
      {/if}

      <div class="caption-bar">
        {#if timeless}
          <span class="caption-na"><Icon name="captions" size={14} /> Caption tidak tersedia — klip ini tidak punya transkrip.</span>
        {:else}
          <Switch bind:checked={settings.captionEnabled}><Icon name="captions" size={14} /> Caption</Switch>
          {#if settings.captionEnabled}
            <div class="cap-options">
              <select bind:value={settings.captionStyle} aria-label="Gaya caption">
                <option value="viral">Viral</option>
                <option value="box">Kotak</option>
                <option value="neon">Neon</option>
                <option value="classic">Klasik</option>
              </select>
              <Segmented
                label="Posisi caption"
                bind:value={settings.captionPosition}
                options={[
                  { value: 'bottom', label: 'Bawah' },
                  { value: 'center', label: 'Tengah' },
                  { value: 'top', label: 'Atas' },
                ]}
              />
            </div>
          {/if}
        {/if}
      </div>

      {#if !timeless}
        <div class="nudges">
          {#each [{ edge: 'start' as Edge, name: 'Awal' }, { edge: 'end' as Edge, name: 'Akhir' }] as row (row.edge)}
            <div class="nudge" role="group" aria-label="Geser {row.name.toLowerCase()} klip">
              <span class="lbl">{row.name}</span>
              <button onclick={() => nudge(row.edge, -1, true)} title={row.edge === 'start' ? 'Tambah 1 kalimat sebelumnya' : 'Buang kalimat terakhir'}>
                <Icon name="chevrons-left" size={14} /> kalimat
              </button>
              <button onclick={() => nudge(row.edge, -1, false)} title="Mundur 1 kata"><Icon name="chevron-left" size={14} /> kata</button>
              <button onclick={() => nudge(row.edge, 1, false)} title="Maju 1 kata">kata <Icon name="chevron-right" size={14} /></button>
              <button onclick={() => nudge(row.edge, 1, true)} title={row.edge === 'start' ? 'Buang kalimat pertama' : 'Tambah 1 kalimat berikutnya'}>
                kalimat <Icon name="chevrons-right" size={14} />
              </button>
            </div>
          {/each}
        </div>
      {/if}

      <div class="opts">
        {#if timeless}
          <span class="opts-hint">Geser penanda <b>AWAL</b> / <b>AKHIR</b> pada garis waktu di bawah, atau gunakan panah pada penanda.</span>
        {:else}
          <Switch bind:checked={snap}>Seret menempel ke kalimat</Switch>
        {/if}
        {#if edited}
          <button class="ghost small" onclick={resetToAi}><Icon name="reset" size={14} /> Kembalikan saran AI</button>
        {/if}
      </div>
    </div>
  </div>

  {#if timeless}
    <TimeRangeSlider
      start={timeStart}
      end={timeEnd}
      min={sliderMin}
      max={sliderMax}
      current={currentTime}
      onstart={setTimeStart}
      onend={setTimeEnd}
    />
  {:else}
  <Timeline
    {words}
    {units}
    {lo}
    {hi}
    startSec={freeStart}
    endSec={freeEnd}
    current={currentTime}
    minSec={settings.minSec}
    maxSec={settings.maxSec}
    onstart={dragStart}
    onend={dragEnd}
    ondragend={() => ensureContext(clip.w0, clip.w1)}
    onseek={seek}
    onexpand={expand}
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
    {onwordedit}
    {onunitedit}
  />
  {/if}

  {#if floating}
    <!-- Extra room so the end of the transcript can be scrolled above the mini player. -->
    <div class="mini-spacer" aria-hidden="true"></div>
  {/if}

  {#if showExportModal}
    <ExportModal
      clips={[clip]}
      {words}
      videoUrl={videoUrl || `https://www.youtube.com/watch?v=${videoId}`}
      {videoId}
      videoTitle={videoTitle || clip.title}
      {videoChannel}
      bind:settings
      helperOk={helperOk ?? false}
      helperHealth={helperHealth ?? null}
      onclose={() => (showExportModal = false)}
    />
  {/if}

  {#if showThumbnailModal}
    <ThumbnailModal
      helperUrl={settings.helperUrl}
      {helperOk}
      {helperHealth}
      videoUrl={videoUrl || `https://www.youtube.com/watch?v=${videoId}`}
      start={bounds.start}
      end={bounds.end}
      clipTitle={clip.title}
      initialHook={clip.thumbnailHook || clip.title}
      onhookchange={(text) => onchange({ ...clip, thumbnailHook: text })}
      onclose={() => (showThumbnailModal = false)}
    />
  {/if}
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
    font-size: 17px;
    font-weight: 600;
    line-height: 26px;
    background: transparent;
    border: 1px solid transparent;
    padding: 4px 8px;
    margin-left: -9px;
  }
  .title:hover {
    border-color: var(--border);
    background: var(--panel-2);
  }
  .title:focus {
    background: var(--field);
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
  .player-slot {
    position: relative;
    aspect-ratio: 16 / 9;
    scroll-margin-top: 96px;
  }
  .player-shell {
    position: absolute;
    inset: 0;
  }
  .player-shell.floating {
    position: fixed;
    inset: auto 20px 20px auto;
    width: min(380px, calc(100vw - 40px));
    z-index: 40;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-xl);
    background: var(--glass-float);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    overflow: hidden;
    box-shadow:
      var(--shadow-float),
      inset 0 1px 0 rgba(255, 255, 255, 0.16);
    animation: mini-in 200ms ease-out;
  }
  .player-shell.floating :global(.player) {
    border-radius: 0;
  }
  .mini-spacer {
    height: min(260px, 40vh);
  }
  .mini-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 4px 4px 12px;
  }
  .mini-title {
    flex: 1;
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  @media (max-width: 640px) {
    .player-shell.floating {
      inset: auto 12px 12px auto;
      width: min(240px, 62vw);
    }
    .mini-spacer {
      height: 200px;
    }
  }
  @keyframes mini-in {
    from {
      opacity: 0;
      transform: translateY(12px) scale(0.97);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .player-shell.floating {
      animation: none;
    }
  }
  .duration {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: baseline;
    gap: 2px 10px;
    padding: 12px 14px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
  }
  .big {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.01em;
    font-variant-numeric: tabular-nums;
  }
  .range {
    font-size: 12.5px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .dur-badge {
    grid-column: 1 / -1;
    justify-self: start;
    margin-top: 4px;
  }
  .play {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .play-main :global(.icon) {
    fill: currentColor;
  }
  .export-btn {
    justify-content: center;
    width: 100%;
    min-height: 38px;
  }
  .thumbnail-btn {
    justify-content: center;
    width: 100%;
    min-height: 36px;
  }
  .timeline-btn {
    justify-content: center;
    width: 100%;
    min-height: 34px;
  }
  .caption-bar {
    display: grid;
    gap: 8px;
    padding: 10px 12px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
  }
  .caption-bar :global(.switch-row .icon) {
    color: var(--icon);
  }
  .cap-options {
    display: grid;
    grid-template-columns: minmax(86px, auto) minmax(0, 1fr);
    gap: 8px;
  }
  .cap-options select {
    padding: 4px 8px;
    font-size: 12.5px;
  }
  .nudges {
    display: grid;
    gap: 6px;
  }
  .nudge {
    display: grid;
    grid-template-columns: 46px repeat(4, minmax(0, 1fr));
    gap: 4px;
    align-items: center;
  }
  .nudge button {
    justify-content: center;
    gap: 2px;
    padding: 4px 2px;
    font-size: 12px;
  }
  .lbl {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .opts {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }
  .opts-hint {
    font-size: 12.5px;
    color: var(--muted);
  }
  .caption-na {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    color: var(--muted);
  }
  @media (max-width: 900px) {
    .top {
      grid-template-columns: 1fr;
    }
  }
</style>
