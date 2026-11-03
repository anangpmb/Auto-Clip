<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import CaptionSettings from './CaptionSettings.svelte';
  import FinalPreview from './FinalPreview.svelte';
  import FormatPicker from './FormatPicker.svelte';
  import Icon from './ui/Icon.svelte';
  import Modal from './ui/Modal.svelte';
  import type { Clip, Settings, Word } from '../lib/types';
  import { assWordsPerCue, buildExportCommand, cuesToAss, cuesToSrt, cuesToVtt, downloadFile } from '../lib/captions';
  import { MAX_FINAL_SECONDS, scenesOf, sceneStarts, SHORTS_SECONDS, timelineCues } from '../lib/compilation';
  import { fmtDuration, fmtTime } from '../lib/transcript';
  import {
    checkExportStatus,
    COMPILATION_HELPER_VERSION,
    EXPORT_HELPER_VERSION,
    GAMING_HELPER_VERSION,
    getExportDownloadUrl,
    PREVIEW_HELPER_VERSION,
    startExport,
    versionBefore,
    type HelperHealth,
  } from '../lib/helper';
  import type { Box } from '../lib/preview';
  import { loadLayout, saveLayout } from '../lib/storage';
  import { copyText } from '../lib/clipboard';

  interface Props {
    /** What goes into the video, in play order: one clip, or the scenes of a compilation. */
    clips: Clip[];
    /** Shows the scene list (order, edit, remove) and names the file as a compilation. */
    compilation?: boolean;
    words: Word[];
    videoUrl: string;
    videoId: string;
    videoTitle: string;
    settings: Settings;
    helperOk: boolean;
    helperHealth: HelperHealth | null;
    onclose: () => void;
    onmove?: (id: string, dir: -1 | 1) => void;
    onremove?: (id: string) => void;
    /** Go back to the editor to trim this scene. */
    onedit?: (id: string) => void;
    onsort?: () => void;
  }

  let {
    clips,
    compilation = false,
    words,
    videoUrl,
    videoId,
    videoTitle,
    settings = $bindable(),
    helperOk,
    helperHealth,
    onclose,
    onmove,
    onremove,
    onedit,
    onsort,
  }: Props = $props();

  const scenes = $derived(scenesOf(words, clips, settings.padStart, settings.padEnd));
  const many = $derived(scenes.length > 1);
  const duration = $derived(sceneStarts(scenes)[scenes.length]);
  const tooLong = $derived(duration > MAX_FINAL_SECONDS);
  const inSourceOrder = $derived(scenes.every((s, i) => i === 0 || scenes[i - 1].start <= s.start));
  const title = $derived(compilation ? `Highlight - ${videoTitle}` : clips[0]?.title || videoTitle);

  // The choices here are the saved settings, so the preview, the editor and the next export agree.
  const aspectRatio = $derived(settings.aspectRatio);
  const captionEnabled = $derived(settings.captionEnabled);
  const captionStyle = $derived(settings.captionStyle);
  const captionPosition = $derived(settings.captionPosition);
  const uppercase = $derived(settings.captionUppercase);
  const gamingMode = $derived(aspectRatio === '9:16_gaming');
  const sourceUrl = $derived(videoUrl || `https://www.youtube.com/watch?v=${videoId}`);

  // Gamer mode areas picked by hand belong to the video (a webcam stays put), so every clip shares them.
  // The dialog opens for one video, so the areas saved when it opened are the ones to start from.
  const saved = untrack(() => loadLayout(videoId));
  let faceBox = $state<Box | null>(saved.face);
  let gameBox = $state<Box | null>(saved.game);
  let detectedFace = $state<Box | null>(null);
  $effect(() => saveLayout(videoId, { face: $state.snapshot(faceBox), game: $state.snapshot(gameBox) }));

  /** Set by the preview; the export reuses its face path so both frame the subject alike. */
  let previewId = $state('');
  const gamingReady = $derived(!versionBefore(helperHealth?.version, GAMING_HELPER_VERSION));
  const previewVersion = $derived(
    gamingMode ? GAMING_HELPER_VERSION : many ? COMPILATION_HELPER_VERSION : PREVIEW_HELPER_VERSION,
  );
  const exportVersion = $derived(gamingMode ? GAMING_HELPER_VERSION : many ? COMPILATION_HELPER_VERSION : EXPORT_HELPER_VERSION);
  const tooLongText = 'Total kompilasi lebih dari 10 menit. Keluarkan atau pendekkan beberapa adegan.';
  const what = $derived(gamingMode ? 'Mode gamer' : many ? 'Kompilasi' : 'Pratinjau');
  const previewBlocked = $derived(
    tooLong
      ? tooLongText
      : !helperOk
        ? `Pratinjau hasil akhir butuh helper yang berjalan di ${settings.helperUrl}.`
        : versionBefore(helperHealth?.version, previewVersion)
          ? `${what} butuh helper versi ${previewVersion} atau lebih baru (sekarang ${helperHealth?.version ?? 'lama'}). Tutup helper, lalu buka lagi lewat launcher AutoClip.`
          : !helperHealth?.ffmpeg
            ? 'Pratinjau butuh FFmpeg di komputer ini (Mac: brew install ffmpeg, Windows: winget install ffmpeg).'
            : '',
  );

  // Export job state
  let isExporting = $state(false);
  let exportProgress = $state(0);
  let exportMessage = $state('');
  let exportError = $state('');
  let downloadReadyUrl = $state('');
  let exportNotes = $state<string[]>([]);
  let pollTimer: number | null = null;
  let copiedCmd = $state(false);

  // Older helpers ignore `cues` (no captions), cannot follow faces, join scenes or split for games.
  const helperOutdated = $derived(!!helperHealth?.ok && versionBefore(helperHealth.version, exportVersion));
  const warnings = $derived.by(() => {
    const out: string[] = [];
    if (!helperHealth?.ok || helperOutdated) return out;
    if (!helperHealth.ffmpeg) out.push('FFmpeg belum terpasang di komputer ini (Mac: brew install ffmpeg, Windows: winget install ffmpeg).');
    if ((aspectRatio === '9:16_crop' || gamingMode) && helperHealth.face_detect === false)
      out.push('Deteksi wajah belum terpasang di helper, jadi wajah tidak dicari otomatis. Buka ulang helper lewat launcher AutoClip untuk memasangnya.');
    if (captionEnabled && helperHealth.captions === false)
      out.push('Komponen caption (Pillow) belum terpasang di helper, jadi caption akan dilewati. Buka ulang helper lewat launcher AutoClip untuk memasangnya.');
    return out;
  });

  // Same grouping as the editor preview (CaptionOverlay), timed on the final video; the
  // preview shows exactly these cues and the export burns them in.
  const cues = $derived(captionEnabled ? timelineCues(words, scenes, { uppercase }) : []);

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  const safeTitle = $derived(title.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, '_') || 'klip');

  // The manual command cuts one stretch, so it is only offered for a single clip.
  const exportCmd = $derived(
    scenes.length === 1 && !gamingMode
      ? buildExportCommand(sourceUrl, scenes[0].start, scenes[0].end, title, {
          aspectRatio,
          burnCaptions: captionEnabled,
          srtFilename: `${safeTitle}.srt`,
        })
      : '',
  );

  function stopExport() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    isExporting = false;
  }

  async function handleStartExport() {
    isExporting = true;
    exportProgress = 5;
    exportMessage = 'Mengirim permintaan ke helper...';
    exportError = '';
    exportNotes = [];
    downloadReadyUrl = '';

    try {
      const spans = scenes.map(({ start, end }) => ({ start, end }));
      const { jobId } = await startExport(settings.helperUrl, {
        url: sourceUrl,
        videoId,
        title,
        ...(many ? { segments: spans } : spans[0]),
        aspectRatio,
        captionStyle: captionEnabled ? captionStyle : 'none',
        captionPosition,
        cues,
        previewId: previewId || undefined,
        gaming: gamingMode
          ? { face: $state.snapshot(faceBox) ?? detectedFace, game: $state.snapshot(gameBox), faceTop: settings.gamingFaceTop }
          : undefined,
      });

      pollTimer = window.setInterval(async () => {
        try {
          const status = await checkExportStatus(settings.helperUrl, jobId);
          exportProgress = status.progress || exportProgress;
          exportMessage = status.message || 'Memproses...';

          if (status.status === 'done') {
            stopExport();
            exportProgress = 100;
            exportMessage = 'Selesai! Mengunduh video...';
            exportNotes = status.notes ?? [];
            const dlUrl = getExportDownloadUrl(settings.helperUrl, jobId);
            downloadReadyUrl = dlUrl;

            // Trigger browser download automatically
            const a = document.createElement('a');
            a.href = dlUrl;
            a.download = status.filename || `${safeTitle}.mp4`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          } else if (status.status === 'error') {
            stopExport();
            exportError = status.error || 'Terjadi kesalahan saat memproses ekspor.';
            exportNotes = status.notes ?? [];
          }
        } catch (e) {
          stopExport();
          exportError = (e as Error).message;
        }
      }, 1200);
    } catch (e) {
      stopExport();
      exportError = (e as Error).message;
    }
  }

  function handleDownloadSrt() {
    downloadFile(`${safeTitle}.srt`, cuesToSrt(timelineCues(words, scenes, { uppercase })), 'text/plain;charset=utf-8');
  }

  function handleDownloadVtt() {
    downloadFile(`${safeTitle}.vtt`, cuesToVtt(timelineCues(words, scenes, { uppercase })), 'text/vtt;charset=utf-8');
  }

  function handleDownloadAss() {
    const assCues = timelineCues(words, scenes, { uppercase, maxWordsPerCue: assWordsPerCue(aspectRatio) });
    const ass = cuesToAss(assCues, { style: captionStyle, position: captionPosition, aspectRatio, title });
    downloadFile(`${safeTitle}.ass`, ass, 'text/plain;charset=utf-8');
  }

  async function copyCmd() {
    await copyText(exportCmd);
    copiedCmd = true;
    setTimeout(() => (copiedCmd = false), 2000);
  }
</script>

<Modal title={compilation ? 'Kompilasi highlight' : 'Pratinjau & ekspor'} width={1100} {onclose}>
  {#snippet subtitle()}
    {#if compilation}
      {scenes.length} adegan jadi satu video · total {fmtDuration(duration)}
    {:else}
      {title} · {fmtTime(scenes[0].start, true)}–{fmtTime(scenes[0].end, true)} · {fmtDuration(duration)}
    {/if}
  {/snippet}

  <div class="layout">
    <!-- Final result: the clip framed and captioned exactly as the export will be -->
    <section class="preview-col" aria-label="Pratinjau hasil akhir">
      {#if previewBlocked}
        <div class="preview-off">
          <Icon name="info" size={20} />
          <p>{previewBlocked}</p>
          <p class="muted">Format dan caption tetap bisa kamu atur.</p>
        </div>
      {:else}
        <FinalPreview
          helperUrl={settings.helperUrl}
          videoUrl={sourceUrl}
          {scenes}
          {cues}
          aspect={aspectRatio}
          {captionEnabled}
          {captionStyle}
          {captionPosition}
          faceTop={settings.gamingFaceTop}
          bind:previewId
          bind:faceBox
          bind:gameBox
          bind:detectedFace
        />
      {/if}
    </section>

    <div class="settings-col">
      {#if compilation}
        <!-- The scenes, in the order they play -->
        <section class="group">
          <div class="group-head">
            <h3 class="group-title">Urutan adegan</h3>
            <button type="button" class="ghost small" onclick={() => onsort?.()} disabled={inSourceOrder}>
              <Icon name="sort-time" size={14} /> Urutkan sesuai waktu video
            </button>
          </div>
          <ol class="scenes">
            {#each scenes as s, i (s.id)}
              <li class="scene">
                <span class="scene-n" aria-hidden="true">{i + 1}</span>
                <span class="scene-body">
                  <span class="scene-title">{s.title}</span>
                  <span class="scene-sub">{fmtTime(s.start)}–{fmtTime(s.end)} · {fmtDuration(s.end - s.start)}</span>
                </span>
                <span class="scene-tools">
                  <button
                    type="button"
                    class="icon-btn small ghost"
                    onclick={() => onmove?.(s.id, -1)}
                    disabled={i === 0}
                    aria-label="Naikkan adegan {i + 1}"
                    title="Naikkan"><Icon name="arrow-up" size={14} /></button
                  >
                  <button
                    type="button"
                    class="icon-btn small ghost"
                    onclick={() => onmove?.(s.id, 1)}
                    disabled={i === scenes.length - 1}
                    aria-label="Turunkan adegan {i + 1}"
                    title="Turunkan"><Icon name="arrow-down" size={14} /></button
                  >
                  <button
                    type="button"
                    class="icon-btn small ghost"
                    onclick={() => onedit?.(s.id)}
                    aria-label="Ubah potongan adegan {i + 1} di editor"
                    title="Ubah potongan di editor"><Icon name="edit" size={14} /></button
                  >
                  <button
                    type="button"
                    class="icon-btn small ghost danger"
                    onclick={() => onremove?.(s.id)}
                    aria-label="Keluarkan adegan {i + 1} dari kompilasi"
                    title="Keluarkan dari kompilasi"><Icon name="close" size={14} /></button
                  >
                </span>
              </li>
            {/each}
          </ol>
          <p class="hint" class:warn-text={duration > SHORTS_SECONDS}>
            Total {fmtDuration(duration)}{tooLong
              ? ': lebih dari batas 10 menit.'
              : duration > SHORTS_SECONDS
                ? ': lebih dari 3 menit, batas Shorts dan Reels.'
                : '.'} Untuk merapikan awal atau akhir sebuah adegan, buka di editor.
          </p>
        </section>
      {/if}

      <section class="group">
        <h3 class="group-title">Format</h3>
        <FormatPicker bind:settings {gamingReady} gamingVersion={GAMING_HELPER_VERSION} />
      </section>

      <section class="group">
        <h3 class="group-title">Caption</h3>
        <CaptionSettings bind:settings />
      </section>

      <!-- Render with the helper -->
      <section class="render">
        <div class="render-head">
          <h3 class="group-title">Render MP4</h3>
          <p class="hint">{many ? 'Semua adegan digabung jadi satu video, sama' : 'Sama'} dengan pratinjau, dalam kualitas penuh (maks. 1080p).</p>
        </div>

        {#if isExporting}
          <div class="progress" aria-live="polite">
            <div class="meter"><i style:width="{exportProgress}%"></i></div>
            <div class="progress-text">
              <span>{exportMessage}</span>
              <span class="pct">{exportProgress}%</span>
            </div>
          </div>
        {:else if downloadReadyUrl}
          <div class="notice ok">
            <Icon name="done" />
            <span class="grow">Video selesai dirender dan sedang diunduh.</span>
            <a href={downloadReadyUrl} class="again" download="{safeTitle}.mp4"><Icon name="download" size={14} /> Unduh lagi</a>
          </div>
        {:else if tooLong}
          <div class="notice warn"><Icon name="warning" /><span>{tooLongText}</span></div>
        {:else if helperOk && helperOutdated}
          <div class="notice warn">
            <Icon name="warning" />
            <span>
              Helper kamu versi {helperHealth?.version ?? 'lama'}; {what.toLowerCase()} butuh versi {exportVersion} atau lebih baru. Tutup
              helper, lalu buka lagi lewat launcher AutoClip (Mac: otomatis mengambil versi terbaru). Di Windows, unduh
              <a href="./autoclip_helper.py" download>autoclip_helper.py</a> terbaru ke folder helper.
            </span>
          </div>
        {:else if helperOk}
          <button class="primary render-btn" onclick={handleStartExport} disabled={!helperHealth?.ffmpeg}>
            <Icon name="clapperboard" />
            Render {many ? 'kompilasi' : 'video'} {aspectRatio.startsWith('9:16') ? '9:16' : '16:9'}
          </button>
          {#each warnings as w (w)}
            <div class="notice"><Icon name="info" /><span>{w}</span></div>
          {/each}
        {:else}
          <div class="notice warn">
            <Icon name="warning" />
            <span>Helper belum terhubung di <code>{settings.helperUrl}</code>. Jalankan helper di komputer kamu untuk render otomatis.</span>
          </div>
        {/if}

        {#if exportError}
          <div class="notice bad"><Icon name="alert" /><span>{exportError}</span></div>
        {/if}
        {#each exportNotes as n (n)}
          <div class="notice"><Icon name="info" /><span>{n}</span></div>
        {/each}
      </section>

      <section class="group">
        <h3 class="group-title">File caption terpisah</h3>
        <p class="hint">
          Transkrip {many ? 'kompilasi ini (mengikuti urutan adegan)' : 'klip ini'} sebagai subtitle untuk CapCut, Premiere Pro, atau DaVinci
          Resolve.
        </p>
        <div class="button-row">
          <button type="button" class="small" onclick={handleDownloadSrt}><Icon name="file" size={14} /> .srt</button>
          <button type="button" class="small" onclick={handleDownloadVtt}><Icon name="file" size={14} /> .vtt</button>
          <button type="button" class="small" onclick={handleDownloadAss}><Icon name="file" size={14} /> .ass (karaoke)</button>
        </div>
      </section>

      {#if exportCmd}
        <details class="group manual">
          <summary><Icon name="terminal" size={14} /> Perintah terminal (yt-dlp + FFmpeg)</summary>
          <div class="cmd-head">
            <p class="hint">
              Untuk dijalankan sendiri. Perintah ini memakai potongan tengah (tanpa deteksi wajah) dan butuh FFmpeg dengan libass untuk
              caption.
            </p>
            <button type="button" class="small" onclick={copyCmd}>
              <Icon name={copiedCmd ? 'check' : 'copy'} size={14} />
              {copiedCmd ? 'Disalin' : 'Salin'}
            </button>
          </div>
          <pre class="cmd-block"><code>{exportCmd}</code></pre>
        </details>
      {/if}
    </div>
  </div>
</Modal>

<style>
  .layout {
    display: grid;
    grid-template-columns: minmax(300px, 0.9fr) minmax(0, 1fr);
    align-items: start;
    gap: 24px;
  }

  .preview-col {
    /* The whole preview (frame, controls, notes) fits beside the settings without being cut off. */
    --preview-stage-h: clamp(300px, calc(92vh - 300px), 620px);
    position: sticky;
    top: 0;
    min-width: 0;
  }

  .preview-off {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 8px;
    min-height: 300px;
    height: var(--preview-stage-h);
    padding: 24px;
    border-radius: var(--radius-xl);
    background: var(--panel-2);
    text-align: center;
    font-size: 13px;
    color: var(--muted);
  }

  .preview-off p {
    margin: 0;
    max-width: 340px;
  }

  .settings-col {
    display: flex;
    flex-direction: column;
    gap: 22px;
    min-width: 0;
  }

  .group {
    display: grid;
    gap: 10px;
  }

  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px 12px;
    flex-wrap: wrap;
  }

  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }

  .warn-text {
    color: var(--warn-text);
  }

  /* Compilation scenes */
  .scenes {
    display: grid;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .scene {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 6px 6px 10px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
  }

  .scene-n {
    flex: none;
    width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border-radius: 6px;
    background: var(--accent-soft);
    color: var(--accent-text);
    font-size: 12px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .scene-body {
    flex: 1;
    min-width: 0;
    display: grid;
    gap: 1px;
  }

  .scene-title {
    font-size: 13px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .scene-sub {
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

  .scene-tools {
    flex: none;
    display: flex;
    gap: 2px;
  }

  /* Render */
  .render {
    display: grid;
    gap: 10px;
    padding: 14px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
  }

  .render-head {
    display: grid;
    gap: 2px;
  }

  .render-btn {
    justify-content: center;
    min-height: 40px;
    font-size: 14px;
  }

  .progress {
    display: grid;
    gap: 6px;
  }

  .progress-text {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    font-size: 12px;
    color: var(--muted);
  }

  .pct {
    font-weight: 600;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }

  .grow {
    flex: 1;
  }

  .again {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex: none;
    font-weight: 600;
    text-decoration: none;
  }

  .button-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .manual summary {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    width: fit-content;
    font-size: 13px;
    font-weight: 500;
    color: var(--muted);
    cursor: pointer;
  }

  .cmd-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }

  .cmd-block {
    margin: 0;
    padding: 10px 12px;
    border-radius: var(--radius-md);
    background: var(--field);
    font-size: 11px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    color: var(--muted);
  }

  .cmd-block code {
    padding: 0;
    background: none;
  }

  @media (max-width: 860px) {
    .layout {
      grid-template-columns: minmax(0, 1fr);
    }
    .preview-col {
      --preview-stage-h: min(56vh, 520px);
      position: static;
    }
    .preview-off {
      height: auto;
    }
  }
</style>
