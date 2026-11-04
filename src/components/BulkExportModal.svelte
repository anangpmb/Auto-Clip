<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import CaptionSettings from './CaptionSettings.svelte';
  import FormatPicker from './FormatPicker.svelte';
  import Icon from './ui/Icon.svelte';
  import Modal from './ui/Modal.svelte';
  import type { Clip, Settings, Word } from '../lib/types';
  import { scenesOf, timelineCues } from '../lib/compilation';
  import {
    checkExportStatus,
    exportZipUrl,
    BLUR_LAYOUT_HELPER_VERSION,
    GAMING_HELPER_VERSION,
    getExportDownloadUrl,
    startExport,
    versionBefore,
    type HelperHealth,
  } from '../lib/helper';
  import { loadLayout } from '../lib/storage';
  import { fmtDuration, fmtTime } from '../lib/transcript';

  interface Props {
    clips: Clip[];
    words: Word[];
    videoUrl: string;
    videoId: string;
    videoTitle: string;
    settings: Settings;
    helperOk: boolean;
    helperHealth: HelperHealth | null;
    onclose: () => void;
  }
  let { clips, words, videoUrl, videoId, videoTitle, settings = $bindable(), helperOk, helperHealth, onclose }: Props = $props();

  type RowState = 'queued' | 'working' | 'done' | 'error';
  interface Row {
    id: string;
    n: number;
    title: string;
    jobId: string;
    state: RowState;
    progress: number;
    message: string;
  }

  const scenes = $derived(scenesOf(words, clips, settings.padStart, settings.padEnd));
  let picked = $state<string[]>(untrack(() => clips.map((c) => c.id)));
  let rows = $state<Row[]>([]);
  let starting = $state(false);
  let failure = $state('');
  let timer = 0;

  const running = $derived(rows.some((r) => r.state === 'queued' || r.state === 'working'));
  const started = $derived(rows.length > 0);
  const doneRows = $derived(rows.filter((r) => r.state === 'done'));
  const pickedTotal = $derived(scenes.filter((s) => picked.includes(s.id)).reduce((t, s) => t + s.end - s.start, 0));
  const requiredVersion = $derived(settings.aspectRatio === '9:16_blur' ? BLUR_LAYOUT_HELPER_VERSION : GAMING_HELPER_VERSION);
  const outdated = $derived(versionBefore(helperHealth?.version, requiredVersion));
  const blocked = $derived(
    !helperOk
      ? `Ekspor massal butuh helper yang berjalan di ${settings.helperUrl}.`
      : outdated
        ? `Ekspor massal butuh helper versi ${requiredVersion} atau lebih baru (sekarang ${helperHealth?.version ?? 'lama'}). Tutup helper, lalu buka lagi lewat launcher AutoClip.`
        : !helperHealth?.ffmpeg
          ? 'Ekspor butuh FFmpeg di komputer ini (Mac: brew install ffmpeg, Windows: winget install ffmpeg).'
          : '',
  );
  const zipName = $derived(`${videoTitle} - ${doneRows.length} klip`);

  onDestroy(() => clearInterval(timer));

  function toggle(id: string) {
    picked = picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id];
  }

  async function start() {
    starting = true;
    failure = '';
    const layout = loadLayout(videoId);
    const chosen = scenes.map((s, i) => ({ s, n: i + 1 })).filter(({ s }) => picked.includes(s.id));
    const out: Row[] = [];
    try {
      for (const { s, n } of chosen) {
        // Numbered like the clip list, so the files sort in the same order.
        const title = `${String(n).padStart(2, '0')} - ${s.title}`;
        const { jobId } = await startExport(settings.helperUrl, {
          url: videoUrl,
          videoId,
          title,
          start: s.start,
          end: s.end,
          aspectRatio: settings.aspectRatio,
          captionStyle: settings.captionEnabled ? settings.captionStyle : 'none',
          captionPosition: settings.captionPosition,
          cues: settings.captionEnabled ? timelineCues(words, [s], { uppercase: settings.captionUppercase }) : [],
          gaming:
            settings.aspectRatio === '9:16_gaming'
              ? { face: layout.face, game: layout.game, faceTop: settings.gamingFaceTop }
              : undefined,
        });
        out.push({ id: s.id, n, title: s.title, jobId, state: 'queued', progress: 0, message: 'Menunggu giliran...' });
      }
    } catch (e) {
      failure = (e as Error).message;
    }
    rows = out;
    starting = false;
    if (rows.length) {
      poll();
      timer = window.setInterval(poll, 1500);
    }
  }

  async function poll() {
    for (const r of rows) {
      if (r.state === 'done' || r.state === 'error') continue;
      try {
        const s = await checkExportStatus(settings.helperUrl, r.jobId);
        r.progress = s.progress || 0;
        r.message = s.message || '';
        if (s.status === 'done') {
          r.state = 'done';
          r.message = s.notes?.length ? s.notes.join(' ') : 'Selesai';
        } else if (s.status === 'error') {
          r.state = 'error';
          r.message = s.error || 'Gagal dirender.';
        } else r.state = s.status === 'pending' ? 'queued' : 'working';
      } catch (e) {
        r.state = 'error';
        r.message = (e as Error).message;
      }
    }
    if (!running) clearInterval(timer);
  }

  function close() {
    if (running && !confirm('Video masih dirender. Tutup jendela ini? Proses di helper tetap jalan, tapi daftar unduhannya hilang.')) return;
    onclose();
  }

  const icons: Record<RowState, 'clock' | 'loader' | 'done' | 'alert'> = {
    queued: 'clock',
    working: 'loader',
    done: 'done',
    error: 'alert',
  };
</script>

<Modal title="Ekspor massal" width={720} onclose={close}>
  {#snippet subtitle()}
    {#if started}
      {doneRows.length} dari {rows.length} klip selesai
    {:else}
      Render beberapa klip sekaligus, masing-masing jadi satu MP4
    {/if}
  {/snippet}

  {#if !started}
    <div class="setup">
      <section class="group">
        <div class="group-head">
          <h3 class="group-title">Klip</h3>
          <button
            class="ghost small"
            onclick={() => (picked = picked.length === clips.length ? [] : clips.map((c) => c.id))}
          >
            {picked.length === clips.length ? 'Kosongkan pilihan' : 'Pilih semua'}
          </button>
        </div>
        <ul class="rows">
          {#each scenes as s, i (s.id)}
            <li>
              <label class="row pick" class:on={picked.includes(s.id)}>
                <input type="checkbox" checked={picked.includes(s.id)} onchange={() => toggle(s.id)} />
                <span class="n">{i + 1}</span>
                <span class="body">
                  <span class="t">{s.title}</span>
                  <span class="sub">{fmtTime(s.start)}–{fmtTime(s.end)} · {fmtDuration(s.end - s.start)}</span>
                </span>
              </label>
            </li>
          {/each}
        </ul>
        <p class="hint">{picked.length} klip dipilih · total {fmtDuration(pickedTotal)} video</p>
      </section>

      <section class="group">
        <h3 class="group-title">Format</h3>
        <FormatPicker bind:settings gamingReady={!outdated} gamingVersion={GAMING_HELPER_VERSION} />
        {#if settings.aspectRatio === '9:16_gaming'}
          <div class="notice">
            <Icon name="info" />
            <span>
              Area kamera dan gameplay memakai yang terakhir kamu atur di pratinjau video ini. Kalau belum pernah diatur, kamera wajah
              dicari otomatis di tiap klip.
            </span>
          </div>
        {/if}
      </section>

      <section class="group">
        <h3 class="group-title">Caption</h3>
        <CaptionSettings bind:settings />
      </section>

      {#if blocked}
        <div class="notice warn"><Icon name="warning" /><span>{blocked}</span></div>
      {/if}
      {#if failure}
        <div class="notice bad"><Icon name="alert" /><span>{failure}</span></div>
      {/if}
    </div>
  {:else}
    <ul class="rows" aria-live="polite">
      {#each rows as r (r.jobId)}
        <li class="row job {r.state}">
          <span class="state-icon"><Icon name={icons[r.state]} class={r.state === 'working' ? 'spin' : ''} /></span>
          <span class="body">
            <span class="t">{r.n}. {r.title}</span>
            {#if r.state === 'working'}
              <span class="meter"><i style:width="{r.progress}%"></i></span>
            {/if}
            <span class="sub">{r.message}</span>
          </span>
          {#if r.state === 'done'}
            <a class="dl" href={getExportDownloadUrl(settings.helperUrl, r.jobId)} download aria-label="Unduh klip {r.n}">
              <Icon name="download" size={14} /> MP4
            </a>
          {/if}
        </li>
      {/each}
    </ul>
    {#if failure}
      <div class="notice bad"><Icon name="alert" /><span>Sebagian klip tidak terkirim: {failure}</span></div>
    {/if}
  {/if}

  {#snippet footer()}
    {#if !started}
      <span class="foot-note">Klip dirender satu per satu oleh helper.</span>
      <button class="ghost" onclick={close}>Batal</button>
      <button class="primary" onclick={start} disabled={!!blocked || starting || !picked.length}>
        <Icon name={starting ? 'loader' : 'clapperboard'} class={starting ? 'spin' : ''} />
        Render {picked.length} klip
      </button>
    {:else}
      <span class="foot-note">
        {running ? 'Jendela ini boleh dibiarkan terbuka sampai semua selesai.' : 'Semua klip sudah diproses.'}
      </span>
      <a
        class="button primary"
        class:disabled={!doneRows.length}
        aria-disabled={!doneRows.length}
        href={doneRows.length ? exportZipUrl(settings.helperUrl, doneRows.map((r) => r.jobId), zipName) : undefined}
        download
      >
        <Icon name="archive" /> Unduh {running ? 'yang selesai' : 'semua'} (.zip)
      </a>
    {/if}
  {/snippet}
</Modal>

<style>
  .setup {
    display: grid;
    gap: 22px;
  }
  .group {
    display: grid;
    gap: 10px;
  }
  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .rows {
    display: grid;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
  }
  .pick {
    cursor: pointer;
  }
  .pick:hover {
    background: var(--raised);
  }
  .n {
    flex: none;
    width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border-radius: 6px;
    background: var(--ink-2);
    font-size: 12px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .pick.on .n {
    background: var(--accent-soft);
    color: var(--accent-text);
  }
  .body {
    flex: 1;
    min-width: 0;
    display: grid;
    gap: 3px;
  }
  .t {
    font-size: 13px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub {
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .state-icon {
    display: grid;
    flex: none;
    color: var(--icon);
  }
  .job.working .state-icon {
    color: var(--accent-text);
  }
  .job.done .state-icon {
    color: var(--ok-text);
  }
  .job.error .state-icon {
    color: var(--bad-text);
  }
  .job.error .sub {
    color: var(--bad-text);
  }
  .meter {
    display: block;
  }
  .dl {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex: none;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent-text);
    text-decoration: none;
  }
  .foot-note {
    flex: 1;
    font-size: 12px;
    color: var(--muted);
  }
  a.button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: var(--radius-md);
    background: var(--accent);
    color: #fff;
    font-size: 13px;
    font-weight: 500;
    line-height: 20px;
    text-decoration: none;
  }
  a.button:hover {
    background: var(--accent-hover);
  }
  a.button.disabled {
    opacity: 0.45;
    pointer-events: none;
  }
  @media (max-width: 640px) {
    .foot-note {
      display: none;
    }
  }
</style>
