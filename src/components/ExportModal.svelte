<script lang="ts">
  import { onDestroy } from 'svelte';
  import FinalPreview from './FinalPreview.svelte';
  import type { Clip, Settings, Word } from '../lib/types';
  import {
    buildExportCommand,
    downloadFile,
    generateAss,
    generateSrt,
    generateVtt,
    groupWordsIntoCues,
  } from '../lib/captions';
  import { clipBounds, fmtDuration, fmtTime } from '../lib/transcript';
  import {
    checkExportStatus,
    EXPORT_HELPER_VERSION,
    getExportDownloadUrl,
    PREVIEW_HELPER_VERSION,
    startExport,
    versionBefore,
    type HelperHealth,
  } from '../lib/helper';
  import { copyText } from '../lib/clipboard';

  interface Props {
    clip: Clip;
    words: Word[];
    videoUrl: string;
    videoId: string;
    videoTitle: string;
    settings: Settings;
    helperOk: boolean;
    helperHealth: HelperHealth | null;
    onclose: () => void;
  }

  let {
    clip,
    words,
    videoUrl,
    videoId,
    videoTitle,
    settings,
    helperOk,
    helperHealth,
    onclose,
  }: Props = $props();

  const bounds = $derived(clipBounds(words, clip.w0, clip.w1, settings.padStart, settings.padEnd));
  const duration = $derived(bounds.end - bounds.start);
  const clipWords = $derived(words.slice(clip.w0, clip.w1 + 1));

  // The choices here are the saved settings, so the preview, the editor and the next export agree.
  const aspectRatio = $derived(settings.aspectRatio);
  const captionEnabled = $derived(settings.captionEnabled);
  const captionStyle = $derived(settings.captionStyle);
  const captionPosition = $derived(settings.captionPosition);
  const uppercase = $derived(settings.captionUppercase);
  const sourceUrl = $derived(videoUrl || `https://www.youtube.com/watch?v=${videoId}`);

  /** Set by the preview; the export reuses its face path so both frame the subject alike. */
  let previewId = $state('');
  const previewBlocked = $derived(
    !helperOk
      ? `Pratinjau hasil akhir butuh helper yang berjalan di ${settings.helperUrl}.`
      : versionBefore(helperHealth?.version, PREVIEW_HELPER_VERSION)
        ? `Pratinjau butuh helper versi ${PREVIEW_HELPER_VERSION} atau lebih baru (sekarang ${helperHealth?.version ?? 'lama'}). Tutup helper, lalu buka lagi lewat launcher AutoClip.`
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

  // Older helpers ignore `cues` (no captions) and cannot follow faces.
  const helperOutdated = $derived(!!helperHealth?.ok && versionBefore(helperHealth.version, EXPORT_HELPER_VERSION));
  const warnings = $derived.by(() => {
    const out: string[] = [];
    if (!helperHealth?.ok || helperOutdated) return out;
    if (!helperHealth.ffmpeg) out.push('FFmpeg belum terpasang di komputer ini (Mac: brew install ffmpeg, Windows: winget install ffmpeg).');
    if (aspectRatio === '9:16_crop' && helperHealth.face_detect === false)
      out.push('Deteksi wajah belum terpasang di helper, jadi sementara dipakai potongan tengah. Buka ulang helper lewat launcher AutoClip untuk memasangnya.');
    if (captionEnabled && helperHealth.captions === false)
      out.push('Komponen caption (Pillow) belum terpasang di helper, jadi caption akan dilewati. Buka ulang helper lewat launcher AutoClip untuk memasangnya.');
    return out;
  });

  // Same grouping as the editor preview (CaptionOverlay), so the video matches what you saw.
  const cues = $derived(captionEnabled ? groupWordsIntoCues(clipWords, bounds.start, bounds.end, { uppercase }) : []);

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  const safeTitle = $derived(
    clip.title.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, '_') || 'klip'
  );

  const assContent = $derived(
    captionEnabled
      ? generateAss(clipWords, bounds.start, bounds.end, {
          style: captionStyle,
          position: captionPosition,
          aspectRatio,
          uppercase,
          title: clip.title,
        })
      : ''
  );

  const srtContent = $derived(
    generateSrt(clipWords, bounds.start, bounds.end, { uppercase })
  );

  const exportCmd = $derived(
    buildExportCommand(sourceUrl, bounds.start, bounds.end, clip.title, {
      aspectRatio,
      burnCaptions: captionEnabled,
      srtFilename: `${safeTitle}.srt`,
    })
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
      const { jobId } = await startExport(settings.helperUrl, {
        url: sourceUrl,
        videoId,
        title: clip.title,
        start: bounds.start,
        end: bounds.end,
        aspectRatio,
        captionStyle: captionEnabled ? captionStyle : 'none',
        captionPosition,
        cues,
        previewId: previewId || undefined,
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
    downloadFile(`${safeTitle}.srt`, srtContent, 'text/plain;charset=utf-8');
  }

  function handleDownloadVtt() {
    const vtt = generateVtt(clipWords, bounds.start, bounds.end, { uppercase });
    downloadFile(`${safeTitle}.vtt`, vtt, 'text/vtt;charset=utf-8');
  }

  function handleDownloadAss() {
    downloadFile(`${safeTitle}.ass`, assContent, 'text/plain;charset=utf-8');
  }

  async function copyCmd() {
    await copyText(exportCmd);
    copiedCmd = true;
    setTimeout(() => (copiedCmd = false), 2000);
  }
</script>

<!-- Esc closes the dialog wherever focus is (e.g. after the download link took it). -->
<svelte:window onkeydown={(e) => e.key === 'Escape' && !e.defaultPrevented && onclose()} />

<!-- Keyboard users close it with Esc (window handler above). -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_click_events_have_key_events -->
<div
  class="backdrop"
  onclick={onclose}
  role="dialog"
  aria-modal="true"
  aria-labelledby="modal-title"
  tabindex="0"
>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div class="modal" onclick={(e) => e.stopPropagation()} role="document">
    <div class="modal-head">
      <div>
        <h2 id="modal-title">🎬 Pratinjau & Ekspor</h2>
        <p class="subtitle">
          <b>{clip.title}</b> · {fmtTime(bounds.start, true)} → {fmtTime(bounds.end, true)} ({fmtDuration(duration)})
        </p>
      </div>
      <button class="ghost close" onclick={onclose} aria-label="Tutup">✕</button>
    </div>

    <div class="modal-body">
      <!-- Final result: the clip framed and captioned exactly as the export will be -->
      <section class="preview-col" aria-label="Pratinjau hasil akhir">
        {#if previewBlocked}
          <div class="preview-off">
            <p>{previewBlocked}</p>
            <p class="desc">Format dan caption tetap bisa kamu atur.</p>
          </div>
        {:else}
          <FinalPreview
            helperUrl={settings.helperUrl}
            videoUrl={sourceUrl}
            start={bounds.start}
            end={bounds.end}
            {words}
            w0={clip.w0}
            w1={clip.w1}
            aspect={aspectRatio}
            {captionEnabled}
            {captionStyle}
            {captionPosition}
            {uppercase}
            bind:previewId
          />
        {/if}
      </section>

      <div class="settings-col">
        <!-- Section 1: Aspect Ratio -->
        <div class="form-group">
          <span class="group-title">Rasio Aspek Video</span>
          <div class="aspect-cards">
            <label class="radio-card" class:checked={aspectRatio === '9:16_blur'}>
              <input type="radio" name="aspectRatio" value="9:16_blur" bind:group={settings.aspectRatio} />
              <div class="card-icon">📱</div>
              <div class="card-info">
                <span class="card-name">9:16 Vertikal (Blur Background)</span>
                <span class="card-desc">Format Shorts / Reels / TikTok. Video utuh dengan latar blur.</span>
              </div>
            </label>

            <label class="radio-card" class:checked={aspectRatio === '9:16_crop'}>
              <input type="radio" name="aspectRatio" value="9:16_crop" bind:group={settings.aspectRatio} />
              <div class="card-icon">🎯</div>
              <div class="card-info">
                <span class="card-name">9:16 Vertikal (Ikuti Wajah)</span>
                <span class="card-desc">Penuh layar. Kamera otomatis mengikuti wajah supaya subjek selalu ada di dalam frame.</span>
              </div>
            </label>

            <label class="radio-card" class:checked={aspectRatio === '16:9'}>
              <input type="radio" name="aspectRatio" value="16:9" bind:group={settings.aspectRatio} />
              <div class="card-icon">🖥️</div>
              <div class="card-info">
                <span class="card-name">16:9 Horizontal (Asli)</span>
                <span class="card-desc">Format lanskap standar YouTube asli.</span>
              </div>
            </label>
          </div>
        </div>

        <!-- Section 2: Caption Settings -->
        <div class="form-group">
          <div class="caption-header">
            <label class="toggle-label">
              <input type="checkbox" bind:checked={settings.captionEnabled} />
              <span class="group-title" style="margin: 0;">Sematkan Auto Caption (Burn-in Subtitle)</span>
            </label>
          </div>

          {#if captionEnabled}
            <div class="caption-options">
              <div class="sub-group">
                <span class="label">Gaya Caption:</span>
                <div class="pill-group">
                  <button
                    type="button"
                    class="pill"
                    class:active={captionStyle === 'viral'}
                    aria-pressed={captionStyle === 'viral'}
                    onclick={() => (settings.captionStyle = 'viral')}
                  >
                    🔥 Viral Highlight
                  </button>
                  <button
                    type="button"
                    class="pill"
                    class:active={captionStyle === 'box'}
                    aria-pressed={captionStyle === 'box'}
                    onclick={() => (settings.captionStyle = 'box')}
                  >
                    ⬛ Modern Box
                  </button>
                  <button
                    type="button"
                    class="pill"
                    class:active={captionStyle === 'neon'}
                    aria-pressed={captionStyle === 'neon'}
                    onclick={() => (settings.captionStyle = 'neon')}
                  >
                    ✨ Neon Pop
                  </button>
                  <button
                    type="button"
                    class="pill"
                    class:active={captionStyle === 'classic'}
                    aria-pressed={captionStyle === 'classic'}
                    onclick={() => (settings.captionStyle = 'classic')}
                  >
                    📄 Klasik
                  </button>
                </div>
              </div>

              <div class="sub-group-row">
                <label class="row-item">
                  <span class="label">Posisi:</span>
                  <select bind:value={settings.captionPosition}>
                    <option value="bottom">Bawah (Rekomendasi)</option>
                    <option value="center">Tengah (Podcast style)</option>
                    <option value="top">Atas</option>
                  </select>
                </label>

                <label class="row-item checkbox-item">
                  <input type="checkbox" bind:checked={settings.captionUppercase} />
                  <span>HURUF BESAR (ALL CAPS)</span>
                </label>
              </div>
            </div>
          {/if}
        </div>

        <!-- Section 3: Direct Render with Helper -->
        <div class="export-box">
          <div class="export-box-head">
            <h3>⚡ Render & Unduh Video MP4</h3>
            <p>Hasilnya sama dengan pratinjau, dalam kualitas penuh (maks. 1080p).</p>
          </div>

          {#if isExporting}
            <div class="progress-container">
              <div class="progress-bar">
                <div class="progress-fill" style="width: {exportProgress}%"></div>
              </div>
              <div class="progress-text">
                <span>{exportMessage}</span>
                <span class="pct">{exportProgress}%</span>
              </div>
            </div>
          {:else if downloadReadyUrl}
            <div class="ready-banner">
              <span>🎉 Video berhasil dirender dan siap!</span>
              <a href={downloadReadyUrl} class="button primary" download="{safeTitle}.mp4">Unduh Lagi (MP4)</a>
            </div>
          {:else}
            {#if helperOk && helperOutdated}
              <div class="warn-box">
                ⚠️ Helper kamu versi {helperHealth?.version ?? 'lama'}; ekspor butuh versi {EXPORT_HELPER_VERSION} atau lebih baru.
                Tutup helper, lalu buka lagi lewat launcher AutoClip (Mac: otomatis mengambil versi terbaru). Di Windows, unduh
                <a href="./autoclip_helper.py" download>autoclip_helper.py</a> terbaru ke folder helper.
              </div>
            {:else if helperOk}
              <button class="primary large-btn" onclick={handleStartExport} disabled={!helperHealth?.ffmpeg}>
                🚀 Mulai Render Video ({aspectRatio.startsWith('9:16') ? '9:16' : '16:9'})
              </button>
              {#each warnings as w (w)}
                <div class="note-box">ℹ️ {w}</div>
              {/each}
            {:else}
              <div class="warn-box">
                ⚠️ Helper belum terhubung di <code>{settings.helperUrl}</code>. Jalankan helper di komputer kamu untuk render otomatis satu klik.
              </div>
            {/if}
          {/if}

          {#if exportError}
            <div class="error-msg">{exportError}</div>
          {/if}
          {#each exportNotes as n (n)}
            <div class="note-box">ℹ️ {n}</div>
          {/each}
        </div>

        <!-- Section 4: Subtitle Files Download -->
        <div class="form-group">
          <span class="group-title">Unduh File Caption Terpisah</span>
          <p class="desc">Ekspor transkrip klip ini sebagai file subtitle untuk CapCut, Premiere Pro, atau DaVinci Resolve.</p>
          <div class="button-row">
            <button type="button" onclick={handleDownloadSrt}>💾 Unduh .SRT</button>
            <button type="button" onclick={handleDownloadVtt}>💾 Unduh .VTT</button>
            <button type="button" onclick={handleDownloadAss}>💾 Unduh .ASS (Karaoke)</button>
          </div>
        </div>

        <!-- Section 5: Manual Terminal Command -->
        <details class="form-group manual">
          <summary class="group-title">Perintah Terminal (yt-dlp + FFmpeg)</summary>
          <div class="cmd-head">
            <p class="desc">
              Untuk dijalankan sendiri di terminal. Perintah ini memakai potongan tengah (tanpa deteksi wajah) dan butuh FFmpeg
              dengan libass untuk caption.
            </p>
            <button type="button" class="ghost small" onclick={copyCmd}>
              {copiedCmd ? '✓ Disalin!' : 'Salin Perintah'}
            </button>
          </div>
          <pre class="cmd-block"><code>{exportCmd}</code></pre>
        </details>
      </div>
    </div>

    <div class="modal-foot">
      <button class="ghost" onclick={onclose}>Tutup</button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(4px);
    z-index: 1000;
    display: grid;
    place-items: center;
    padding: 16px;
    overflow-y: auto;
  }

  .modal {
    background: var(--panel, #181b21);
    color: var(--text, #e8eaf0);
    border: 1px solid var(--border, #2d3340);
    border-radius: 12px;
    width: 100%;
    max-width: 1080px;
    box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
    display: flex;
    flex-direction: column;
    max-height: 90vh;
  }

  .modal-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 18px 20px;
    border-bottom: 1px solid var(--border, #2d3340);
  }

  .modal-head h2 {
    margin: 0;
    font-size: 19px;
    font-weight: 700;
  }

  .subtitle {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--muted, #94a3b8);
  }

  .close {
    font-size: 18px;
    line-height: 1;
    padding: 4px 8px;
  }

  .modal-body {
    padding: 20px;
    overflow-y: auto;
    display: grid;
    grid-template-columns: minmax(300px, 0.9fr) minmax(0, 1fr);
    align-items: start;
    gap: 24px;
  }

  .preview-col {
    /* The whole preview (frame, controls, notes) fits beside the settings without being cut off. */
    --preview-stage-h: clamp(300px, calc(90vh - 330px), 600px);
    position: sticky;
    top: 0;
    min-width: 0;
  }

  .preview-off {
    display: grid;
    place-content: center;
    gap: 8px;
    min-height: 300px;
    height: var(--preview-stage-h);
    padding: 24px;
    border: 1px dashed var(--border, #2d3340);
    border-radius: 12px;
    text-align: center;
    font-size: 13px;
  }

  .preview-off p {
    margin: 0;
  }

  .settings-col {
    display: flex;
    flex-direction: column;
    gap: 20px;
    min-width: 0;
  }

  .manual summary {
    cursor: pointer;
  }

  .manual[open] summary {
    margin-bottom: 4px;
  }

  @media (max-width: 860px) {
    .modal-body {
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

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .group-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text, #e8eaf0);
  }

  .desc {
    margin: 0;
    font-size: 12px;
    color: var(--muted, #94a3b8);
  }

  /* Aspect Ratio Radios */
  .aspect-cards {
    display: grid;
    gap: 8px;
  }

  .radio-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    background: var(--panel-2, #212631);
    border: 1px solid var(--border, #2d3340);
    border-radius: var(--radius, 8px);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .radio-card:hover {
    border-color: var(--accent, #6366f1);
  }

  .radio-card.checked {
    border-color: var(--accent, #6366f1);
    background: rgba(99, 102, 241, 0.1);
  }

  .card-icon {
    font-size: 22px;
  }

  .card-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .card-name {
    font-size: 13px;
    font-weight: 600;
  }

  .card-desc {
    font-size: 12px;
    color: var(--muted, #94a3b8);
  }

  /* Caption settings */
  .caption-header {
    display: flex;
    align-items: center;
  }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }

  .caption-options {
    margin-top: 10px;
    padding: 12px 14px;
    background: var(--panel-2, #212631);
    border-radius: var(--radius, 8px);
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .sub-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .sub-group-row {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }

  .row-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }

  .row-item select {
    padding: 4px 8px;
    font-size: 12px;
  }

  .checkbox-item {
    cursor: pointer;
  }

  .label {
    font-size: 12px;
    color: var(--muted, #94a3b8);
  }

  .pill-group {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .pill {
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 20px;
    border: 1px solid var(--border, #2d3340);
    background: transparent;
    cursor: pointer;
  }

  .pill.active {
    background: var(--accent, #6366f1);
    border-color: var(--accent, #6366f1);
    color: #fff;
    font-weight: 600;
  }

  /* Direct Export Box */
  .export-box {
    padding: 16px;
    border-radius: var(--radius, 8px);
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(168, 85, 247, 0.08) 100%);
    border: 1px solid rgba(99, 102, 241, 0.3);
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .export-box-head h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
  }

  .export-box-head p {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--muted, #94a3b8);
  }

  .large-btn {
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 700;
  }

  .progress-container {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .progress-bar {
    height: 10px;
    background: var(--panel-2, #212631);
    border-radius: 5px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #6366f1, #a855f7);
    transition: width 0.3s ease;
  }

  .progress-text {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--muted, #94a3b8);
  }

  .progress-text .pct {
    font-weight: 700;
    color: var(--accent, #6366f1);
  }

  .ready-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    background: rgba(34, 197, 94, 0.12);
    border: 1px solid rgba(34, 197, 94, 0.3);
    border-radius: var(--radius, 8px);
    font-size: 13px;
    font-weight: 600;
    color: #4ade80;
  }

  .warn-box {
    padding: 10px 12px;
    background: rgba(234, 179, 8, 0.1);
    border: 1px solid rgba(234, 179, 8, 0.3);
    border-radius: var(--radius, 8px);
    font-size: 12px;
    color: #facc15;
  }

  .note-box {
    font-size: 11px;
    color: var(--muted, #94a3b8);
    margin-top: 4px;
  }

  .error-msg {
    padding: 8px 12px;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: var(--radius, 8px);
    font-size: 12px;
    color: #f87171;
  }

  .button-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  /* Command Block */
  .cmd-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }

  .cmd-block {
    background: #0f1115;
    padding: 10px 12px;
    border-radius: var(--radius, 8px);
    border: 1px solid var(--border, #2d3340);
    margin: 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    color: #94a3b8;
  }

  .modal-foot {
    display: flex;
    justify-content: flex-end;
    padding: 14px 20px;
    border-top: 1px solid var(--border, #2d3340);
  }
</style>
