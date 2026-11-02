<script lang="ts">
  import { untrack } from 'svelte';
  import ClipEditor from './ClipEditor.svelte';
  import ExportModal from './ExportModal.svelte';
  import type { Clip, LoadedProject, Settings } from '../lib/types';
  import {
    buildUnits,
    clipBounds,
    durationStatus,
    fmtDuration,
    fmtTime,
    joinWords,
    remapClip,
    unitIndexOfWord,
    unitsSpanFrom,
    wordIndexAt,
  } from '../lib/transcript';
  import { findClips, newId, PROVIDERS } from '../lib/ai';
  import { copyText } from '../lib/clipboard';
  import { fetchCaptions, type HelperHealth } from '../lib/helper';
  import { saveProject, saveWords } from '../lib/storage';
  import { downloadFile, generateSrt } from '../lib/captions';

  interface Props {
    initial: LoadedProject;
    settings: Settings;
    helperOk: boolean;
    helperHealth?: HelperHealth | null;
    onclose: () => void;
    onsettings: () => void;
  }
  let { initial, settings, helperOk, helperHealth = null, onclose, onsettings }: Props = $props();

  // The parent remounts this view per project, so the initial value is all we need.
  let meta = $state(untrack(() => initial.meta));
  let words = $state.raw(untrack(() => initial.words));
  let clips = $state(untrack(() => initial.clips));
  let selectedId = $state<string | null>(untrack(() => initial.clips[0]?.id ?? null));
  let showExportModal = $state(false);

  const units = $derived(buildUnits(words));
  const selected = $derived(clips.find((c) => c.id === selectedId) ?? null);

  let playerTime = 0;
  let aiBusy = $state(false);
  let aiStatus = $state('');
  let error = $state('');
  let toast = $state('');
  let trackBusy = $state(false);
  let controller: AbortController | null = null;

  let saveTimer = 0;
  $effect(() => {
    const m = $state.snapshot(meta);
    const c = $state.snapshot(clips);
    clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
      try {
        saveProject(m, c);
      } catch (e) {
        flash((e as Error).message);
      }
    }, 400);
  });

  let toastTimer = 0;
  function flash(message: string) {
    toast = message;
    clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => (toast = ''), 2500);
  }

  function updateClip(c: Clip) {
    const i = clips.findIndex((x) => x.id === c.id);
    if (i >= 0) clips[i] = c;
  }

  function deleteClip(id: string) {
    const i = clips.findIndex((c) => c.id === id);
    clips = clips.filter((c) => c.id !== id);
    if (selectedId === id) selectedId = clips[Math.min(i, clips.length - 1)]?.id ?? null;
  }

  function addManualClip() {
    const u = unitIndexOfWord(units, Math.max(0, wordIndexAt(words, playerTime)));
    const e = unitsSpanFrom(units, u, (settings.minSec + settings.maxSec) / 2);
    const clip: Clip = {
      id: newId(),
      title: `Klip manual ${clips.length + 1}`,
      reason: '',
      score: 0,
      w0: units[u].w0,
      w1: units[e].w1,
      aiW0: null,
      aiW1: null,
    };
    clips = [...clips, clip].sort((a, b) => a.w0 - b.w0);
    selectedId = clip.id;
  }

  async function runAI() {
    if (!(settings.apiKeys[settings.provider] ?? '').trim()) {
      onsettings();
      return;
    }
    if (clips.length && !confirm('Ganti semua klip yang ada dengan hasil AI yang baru?')) return;
    aiBusy = true;
    error = '';
    aiStatus = 'Menyiapkan…';
    const ctrl = new AbortController();
    controller = ctrl;
    try {
      const found = await findClips(words, units, $state.snapshot(settings), {
        title: meta.video.title,
        signal: ctrl.signal,
        onProgress: (m) => (aiStatus = m),
      });
      clips = found;
      selectedId = found[0]?.id ?? null;
      if (!found.length) error = 'AI tidak menemukan klip yang cocok. Coba ubah durasi atau instruksi tambahan di Pengaturan.';
    } catch (e) {
      if (!ctrl.signal.aborted) error = (e as Error).message;
    } finally {
      aiBusy = false;
      controller = null;
    }
  }

  async function changeTrack(select: HTMLSelectElement) {
    const key = select.value;
    if (key === meta.track) return;
    trackBusy = true;
    error = '';
    try {
      const res = await fetchCaptions(settings.helperUrl, meta.video.url, key);
      const newUnits = buildUnits(res.words);
      clips = clips.map((c) => remapClip(words, res.words, newUnits, c));
      words = res.words;
      meta.track = res.track;
      meta.tracks = res.tracks;
      meta.wordTiming = res.wordTiming;
      saveWords(meta.id, res.words);
    } catch (e) {
      error = (e as Error).message;
      select.value = meta.track;
    } finally {
      trackBusy = false;
    }
  }

  const boundsOf = (c: Clip) => clipBounds(words, c.w0, c.w1, settings.padStart, settings.padEnd);
  const safeName = (s: string) =>
    s
      .replace(/[\\/:*?"<>|%]+/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 80) || 'klip';

  async function copy(text: string, label: string) {
    try {
      await copyText(text);
      flash(`${label} disalin`);
    } catch {
      flash('Gagal menyalin ke clipboard');
    }
  }

  function copyList() {
    const text = clips
      .map((c, i) => {
        const b = boundsOf(c);
        return `${i + 1}. ${c.title}\n   ${fmtTime(b.start, true)} – ${fmtTime(b.end, true)} (${fmtDuration(b.end - b.start)})\n   https://youtu.be/${meta.video.id}?t=${Math.floor(b.start)}`;
      })
      .join('\n\n');
    copy(text, 'Daftar klip');
  }

  function copyYtDlp() {
    const text = clips
      .map((c, i) => {
        const b = boundsOf(c);
        const name = `${String(i + 1).padStart(2, '0')} - ${safeName(c.title)}`;
        return `yt-dlp --download-sections "*${b.start.toFixed(2)}-${b.end.toFixed(2)}" --force-keyframes-at-cuts -o "${name}.%(ext)s" "https://www.youtube.com/watch?v=${meta.video.id}"`;
      })
      .join('\n');
    copy(text, 'Perintah yt-dlp');
  }

  function downloadJson() {
    const data = {
      video: meta.video,
      track: meta.track,
      clips: clips.map((c, i) => {
        const b = boundsOf(c);
        return {
          n: i + 1,
          title: c.title,
          reason: c.reason,
          score: c.score,
          start: +b.start.toFixed(2),
          end: +b.end.toFixed(2),
          duration: +(b.end - b.start).toFixed(2),
          text: joinWords(words, c.w0, c.w1),
        };
      }),
    };
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    a.download = `${safeName(meta.video.title)} - klip.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function downloadSelectedSrt() {
    if (!selected) return;
    const b = boundsOf(selected);
    const clipWords = words.slice(selected.w0, selected.w1 + 1);
    const srt = generateSrt(clipWords, b.start, b.end, { uppercase: settings.captionUppercase });
    downloadFile(`${safeName(selected.title)}.srt`, srt, 'text/plain;charset=utf-8');
    flash('File .srt berhasil diunduh');
  }
</script>

<section class="project">
  <div class="bar">
    <button class="ghost" onclick={onclose}>← Proyek</button>
    {#if meta.video.thumbnail}<img class="thumb" src={meta.video.thumbnail} alt="" />{/if}
    <div class="info">
      <h1 title={meta.video.title}>{meta.video.title}</h1>
      <p>{meta.video.channel} · {fmtTime(meta.video.duration)} · {words.length.toLocaleString('id-ID')} kata</p>
    </div>
    <label class="track">
      <span>Transkrip</span>
      <select value={meta.track} onchange={(e) => changeTrack(e.currentTarget)} disabled={trackBusy || !helperOk}>
        {#each meta.tracks as t (t.key)}
          <option value={t.key}>{t.name} · {t.kind === 'auto' ? 'otomatis' : 'manual'}</option>
        {/each}
      </select>
    </label>
  </div>

  {#if meta.wordTiming === 'estimated'}
    <div class="notice">
      Transkrip ini dari subtitle manual, jadi waktu per kata hanya perkiraan. Kalau ada pilihan "otomatis", potongannya biasanya
      lebih presisi.
    </div>
  {/if}

  <div class="actions">
    {#if aiBusy}
      <span class="spinner" aria-hidden="true"></span>
      <span>{aiStatus}</span>
      <button onclick={() => controller?.abort()}>Batal</button>
    {:else}
      <button class="primary" onclick={runAI}>{clips.length ? '✨ Cari ulang dengan AI' : '✨ Cari klip dengan AI'}</button>
      <span class="muted">{PROVIDERS[settings.provider].label} · {settings.minSec}–{settings.maxSec} dtk · maks {settings.maxClips} klip</span>
    {/if}
    <span class="spacer"></span>
    {#if clips.length}
      <button class="primary" onclick={() => (showExportModal = true)} title="Ekspor video dengan auto caption">🎬 Ekspor Video</button>
      <button onclick={downloadSelectedSrt} title="Unduh subtitle .srt untuk klip yang dipilih">Unduh Caption (.srt)</button>
      <button onclick={copyList}>Salin daftar</button>
      <button onclick={copyYtDlp} title="Perintah untuk mengunduh potongan mentah dengan yt-dlp">Salin perintah yt-dlp</button>
      <button onclick={downloadJson}>Unduh JSON</button>
    {/if}
  </div>

  {#if error}<div class="error">{error}</div>{/if}

  {#if clips.length}
    <div class="workspace">
      <aside class="list">
        {#each clips as c, i (c.id)}
          {@const b = boundsOf(c)}
          {@const st = durationStatus(b.end - b.start, settings.minSec, settings.maxSec)}
          {@const edited = c.aiW0 !== null && (c.w0 !== c.aiW0 || c.w1 !== c.aiW1)}
          <div class="item" class:active={c.id === selectedId}>
            <button class="pick" onclick={() => (selectedId = c.id)}>
              <span class="n">{i + 1}</span>
              <span class="body">
                <span class="t">{c.title}</span>
                <span class="sub">
                  {fmtTime(b.start)}–{fmtTime(b.end)} · <span class="dur {st}">{fmtDuration(b.end - b.start)}</span>
                  {#if c.score}· skor {c.score}{/if}
                  {#if edited}<span class="badge">diedit</span>{/if}
                </span>
                <span class="snip">“{joinWords(words, c.w0, Math.min(c.w1, c.w0 + 9))}…”</span>
              </span>
            </button>
            <button class="del" onclick={() => deleteClip(c.id)} aria-label="Hapus klip {i + 1}" title="Hapus klip">×</button>
          </div>
        {/each}
        <button class="add" onclick={addManualClip}>+ Tambah klip manual</button>
      </aside>

      <div class="panel">
        {#if selected}
          <ClipEditor
            {words}
            {units}
            clip={selected}
            videoId={meta.video.id}
            videoUrl={meta.video.url}
            videoTitle={meta.video.title}
            {settings}
            {helperOk}
            {helperHealth}
            onchange={updateClip}
            ontime={(t) => (playerTime = t)}
          />
        {:else}
          <p class="muted">Pilih klip di sebelah kiri.</p>
        {/if}
      </div>
    </div>
  {:else if !aiBusy}
    <div class="empty">
      <h2>Transkrip siap</h2>
      <p>
        Klik <b>Cari klip dengan AI</b> untuk mendapatkan saran potongan, lalu rapikan awal dan akhirnya lewat timeline dan transkrip.
        Kamu juga bisa membuat klip sendiri.
      </p>
      <button onclick={addManualClip}>+ Tambah klip manual</button>
    </div>
  {/if}

  {#if showExportModal && selected}
    <ExportModal
      clip={selected}
      {words}
      videoUrl={meta.video.url}
      videoId={meta.video.id}
      videoTitle={meta.video.title}
      {settings}
      {helperOk}
      {helperHealth}
      onclose={() => (showExportModal = false)}
    />
  {/if}

  {#if toast}<div class="toast" role="status">{toast}</div>{/if}
</section>

<style>
  .project {
    display: grid;
    /* Long nowrap titles must ellipsize, not widen the page past the screen. */
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .thumb {
    width: 96px;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    border-radius: 8px;
  }
  .info {
    flex: 1;
    min-width: 0;
  }
  h1 {
    margin: 0;
    font-size: 18px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .info p {
    margin: 2px 0 0;
    color: var(--muted);
    font-size: 13px;
  }
  .track {
    display: grid;
    gap: 2px;
    font-size: 12px;
    color: var(--muted);
  }
  .track select {
    max-width: 260px;
  }
  .notice {
    padding: 8px 12px;
    border-radius: var(--radius);
    background: rgba(251, 191, 36, 0.1);
    border: 1px solid rgba(251, 191, 36, 0.35);
    font-size: 13px;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .spacer {
    flex: 1;
  }
  .workspace {
    display: grid;
    grid-template-columns: 320px minmax(0, 1fr);
    gap: 14px;
    align-items: start;
  }
  .list {
    display: grid;
    gap: 8px;
    position: sticky;
    top: 70px;
    max-height: calc(100vh - 90px);
    overflow-y: auto;
    padding-right: 4px;
  }
  .item {
    position: relative;
    display: flex;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .item.active {
    border-color: var(--accent);
    background: #1d1a24;
  }
  .pick {
    flex: 1;
    display: flex;
    gap: 10px;
    align-items: flex-start;
    text-align: left;
    background: none;
    border: none;
    padding: 10px;
    min-width: 0;
  }
  .n {
    flex: none;
    width: 24px;
    height: 24px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: var(--panel-2);
    font-size: 12px;
    font-weight: 700;
  }
  .item.active .n {
    background: var(--accent);
  }
  .body {
    display: grid;
    gap: 3px;
    min-width: 0;
  }
  .t {
    font-weight: 600;
    font-size: 14px;
  }
  .sub {
    font-size: 12px;
    color: var(--muted);
  }
  .dur.ok {
    color: var(--ok);
  }
  .dur.short,
  .dur.long {
    color: var(--warn);
  }
  .badge {
    margin-left: 4px;
    padding: 0 6px;
    border-radius: 999px;
    font-size: 11px;
    background: rgba(77, 171, 255, 0.18);
    color: var(--accent-2);
  }
  .snip {
    font-size: 12px;
    color: #9aa1b4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .del {
    align-self: flex-start;
    margin: 6px;
    width: 26px;
    height: 26px;
    padding: 0;
    border: none;
    background: none;
    color: var(--muted);
    font-size: 18px;
  }
  .del:hover {
    color: var(--bad);
  }
  .add {
    border-style: dashed;
  }
  .panel {
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .empty {
    padding: 40px 20px;
    text-align: center;
    border: 1px dashed var(--border);
    border-radius: var(--radius);
  }
  .empty h2 {
    margin: 0 0 8px;
  }
  .empty p {
    max-width: 560px;
    margin: 0 auto 16px;
    color: var(--muted);
  }
  .toast {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 16px;
    border-radius: 999px;
    background: #2b3245;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    font-size: 14px;
    z-index: 20;
  }
  @media (max-width: 1000px) {
    .workspace {
      /* minmax(0, …): the clip snippets are nowrap and must not stretch the column past the screen. */
      grid-template-columns: minmax(0, 1fr);
    }
    .list {
      position: static;
      max-height: none;
    }
  }
  @media (max-width: 640px) {
    .bar {
      flex-wrap: wrap;
      gap: 10px;
    }
    .thumb {
      width: 72px;
    }
    .info {
      flex: 1 1 0;
    }
    .track {
      flex: 1 1 100%;
    }
    .track select {
      max-width: none;
      width: 100%;
    }
  }
</style>
