<script lang="ts">
  import { untrack } from 'svelte';
  import type { Clip, Settings, Word } from '../lib/types';
  import {
    type AspectRatio,
    type CaptionPosition,
    type CaptionStyle,
    buildExportCommand,
    downloadFile,
    generateAss,
    generateSrt,
    generateVtt,
  } from '../lib/captions';
  import { clipBounds, fmtDuration, fmtTime } from '../lib/transcript';
  import { checkExportStatus, getExportDownloadUrl, startExport, type HelperHealth } from '../lib/helper';
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

  let aspectRatio = $state<AspectRatio>(untrack(() => settings.aspectRatio || '9:16_blur'));
  let captionEnabled = $state(untrack(() => settings.captionEnabled ?? true));
  let captionStyle = $state<CaptionStyle>(untrack(() => settings.captionStyle || 'viral'));
  let captionPosition = $state<CaptionPosition>(untrack(() => settings.captionPosition || 'bottom'));
  let uppercase = $state(untrack(() => settings.captionUppercase ?? true));

  // Export job state
  let isExporting = $state(false);
  let exportProgress = $state(0);
  let exportMessage = $state('');
  let exportError = $state('');
  let downloadReadyUrl = $state('');
  let pollTimer: number | null = null;
  let copiedCmd = $state(false);

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
    buildExportCommand(videoUrl || `https://www.youtube.com/watch?v=${videoId}`, bounds.start, bounds.end, clip.title, {
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
    downloadReadyUrl = '';

    try {
      const { jobId } = await startExport(settings.helperUrl, {
        url: videoUrl || `https://www.youtube.com/watch?v=${videoId}`,
        videoId,
        title: clip.title,
        start: bounds.start,
        end: bounds.end,
        aspectRatio,
        captionStyle: captionEnabled ? captionStyle : 'none',
        captionPosition,
        assContent,
        srtContent,
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

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
  class="backdrop"
  onclick={onclose}
  onkeydown={(e) => e.key === 'Escape' && onclose()}
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
        <h2 id="modal-title">🎬 Ekspor Video & Auto Caption</h2>
        <p class="subtitle">
          <b>{clip.title}</b> · {fmtTime(bounds.start, true)} → {fmtTime(bounds.end, true)} ({fmtDuration(duration)})
        </p>
      </div>
      <button class="ghost close" onclick={onclose} aria-label="Tutup">✕</button>
    </div>

    <div class="modal-body">
      <!-- Section 1: Aspect Ratio -->
      <div class="form-group">
        <label class="group-title" for="aspectRatioSelect">Rasio Aspek Video</label>
        <div class="aspect-cards">
          <label class="radio-card" class:checked={aspectRatio === '9:16_blur'}>
            <input type="radio" name="aspectRatio" value="9:16_blur" bind:group={aspectRatio} />
            <div class="card-icon">📱</div>
            <div class="card-info">
              <span class="card-name">9:16 Vertikal (Blur Background)</span>
              <span class="card-desc">Format Shorts / Reels / TikTok. Video utuh dengan latar blur.</span>
            </div>
          </label>

          <label class="radio-card" class:checked={aspectRatio === '9:16_crop'}>
            <input type="radio" name="aspectRatio" value="9:16_crop" bind:group={aspectRatio} />
            <div class="card-icon">📐</div>
            <div class="card-info">
              <span class="card-name">9:16 Vertikal (Center Crop)</span>
              <span class="card-desc">Potongan tengah vertikal penuh layar.</span>
            </div>
          </label>

          <label class="radio-card" class:checked={aspectRatio === '16:9'}>
            <input type="radio" name="aspectRatio" value="16:9" bind:group={aspectRatio} />
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
            <input type="checkbox" bind:checked={captionEnabled} />
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
                  onclick={() => (captionStyle = 'viral')}
                >
                  🔥 Viral Highlight
                </button>
                <button
                  type="button"
                  class="pill"
                  class:active={captionStyle === 'box'}
                  onclick={() => (captionStyle = 'box')}
                >
                  ⬛ Modern Box
                </button>
                <button
                  type="button"
                  class="pill"
                  class:active={captionStyle === 'neon'}
                  onclick={() => (captionStyle = 'neon')}
                >
                  ✨ Neon Pop
                </button>
                <button
                  type="button"
                  class="pill"
                  class:active={captionStyle === 'classic'}
                  onclick={() => (captionStyle = 'classic')}
                >
                  📄 Klasik
                </button>
              </div>
            </div>

            <div class="sub-group-row">
              <label class="row-item">
                <span class="label">Posisi:</span>
                <select bind:value={captionPosition}>
                  <option value="bottom">Bawah (Rekomendasi)</option>
                  <option value="center">Tengah (Podcast style)</option>
                  <option value="top">Atas</option>
                </select>
              </label>

              <label class="row-item checkbox-item">
                <input type="checkbox" bind:checked={uppercase} />
                <span>HURUF BESAR (ALL CAPS)</span>
              </label>
            </div>
          </div>
        {/if}
      </div>

      <!-- Section 3: Direct Render with Helper -->
      <div class="export-box">
        <div class="export-box-head">
          <h3>⚡ Render & Unduh Video MP4 Langsung</h3>
          <p>Helper akan mengunduh segmen klip dan menyematkan auto caption menggunakan FFmpeg.</p>
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
          {#if helperOk}
            <button class="primary large-btn" onclick={handleStartExport}>
              🚀 Mulai Render Video ({aspectRatio.startsWith('9:16') ? '9:16' : '16:9'})
            </button>
            {#if helperHealth && !helperHealth.ffmpeg_subtitles}
              <div class="note-box">
                ℹ️ FFmpeg terdeteksi tanpa filter libass. Helper akan mengekspor video MP4 dengan subtitle tertanam (soft subtitles).
              </div>
            {/if}
          {:else}
            <div class="warn-box">
              ⚠️ Helper belum terhubung di <code>{settings.helperUrl}</code>. Jalankan helper di komputer kamu untuk render otomatis satu klik.
            </div>
          {/if}
        {/if}

        {#if exportError}
          <div class="error-msg">{exportError}</div>
        {/if}
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
      <div class="form-group">
        <div class="cmd-head">
          <span class="group-title">Perintah Terminal (yt-dlp + FFmpeg)</span>
          <button type="button" class="ghost small" onclick={copyCmd}>
            {copiedCmd ? '✓ Disalin!' : 'Salin Perintah'}
          </button>
        </div>
        <pre class="cmd-block"><code>{exportCmd}</code></pre>
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
    max-width: 640px;
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
    display: flex;
    flex-direction: column;
    gap: 20px;
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
    align-items: center;
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
