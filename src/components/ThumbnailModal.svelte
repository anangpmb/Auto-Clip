<script lang="ts">
  import { onDestroy, tick, untrack } from 'svelte';
  import Icon from './ui/Icon.svelte';
  import Modal from './ui/Modal.svelte';
  import { downloadFile } from '../lib/captions';
  import {
    checkPreviewStatus,
    PREVIEW_HELPER_VERSION,
    previewVideoUrl,
    startPreview,
    versionBefore,
    type HelperHealth,
  } from '../lib/helper';
  import { DARK_FRAME_LUMA, isDarkFrame, meanLuminance, thumbnailSeekTimes } from '../lib/thumbnail';

  interface Props {
    helperUrl: string;
    helperOk: boolean;
    helperHealth: HelperHealth | null;
    videoUrl: string;
    start: number;
    end: number;
    clipTitle: string;
    initialHook: string;
    onhookchange: (text: string) => void;
    onclose: () => void;
  }

  let {
    helperUrl,
    helperOk,
    helperHealth,
    videoUrl,
    start,
    end,
    clipTitle,
    initialHook,
    onhookchange,
    onclose,
  }: Props = $props();

  const WIDTH = 720;
  const HEIGHT = 1280;
  const CENTER_TOP = HEIGHT / 6;
  const CENTER_HEIGHT = (HEIGHT * 2) / 3;
  const blocked = $derived(
    !helperOk
      ? `Helper belum terhubung di ${helperUrl}. Jalankan helper untuk mengambil frame klip.`
      : versionBefore(helperHealth?.version, PREVIEW_HELPER_VERSION)
        ? `Fitur ini memerlukan helper versi ${PREVIEW_HELPER_VERSION} atau lebih baru. Tutup helper, lalu buka lagi lewat launcher AutoClip.`
        : !helperHealth?.ffmpeg
          ? 'FFmpeg belum terpasang di komputer ini, jadi frame klip tidak bisa disiapkan.'
          : '',
  );
  let hookText = $state(untrack(() => initialHook));
  let darkWarning = $state('');
  let progress = $state(0);
  let message = $state('');
  let error = $state('');
  let loading = $state(false);
  let ready = $state(false);
  let layout = $state<'full' | 'blur-center'>('full');
  let canvas = $state<HTMLCanvasElement>();
  let sourceFrame: HTMLCanvasElement | null = null;
  let sourceVideo: HTMLVideoElement | null = null;
  let cancelled = false;

  function delay(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function waitForMedia(
    video: HTMLVideoElement,
    event: 'loadedmetadata' | 'seeked',
    timeoutMs = 8000,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        clean();
        reject(new Error(`Menunggu video (${event}) terlalu lama. Coba lagi.`));
      }, timeoutMs);
      const clean = () => {
        clearTimeout(timer);
        video.removeEventListener(event, done);
        video.removeEventListener('error', failed);
      };
      const done = () => {
        clean();
        resolve();
      };
      const failed = () => {
        clean();
        reject(new Error('Gagal membaca frame video dari helper.'));
      };
      video.addEventListener(event, done, { once: true });
      video.addEventListener('error', failed, { once: true });
    });
  }

  /**
   * Wait until a decoded frame is actually presented, not just until the seek
   * finished. A paused, detached video can report `seeked` while drawImage
   * still yields black pixels; requestVideoFrameCallback only fires once a
   * frame is presented, and a brief play is the fallback where it is missing
   * or never fires.
   */
  async function waitForVideoFrame(video: HTMLVideoElement): Promise<void> {
    if (typeof video.requestVideoFrameCallback === 'function') {
      const presented = await new Promise<boolean>((resolve) => {
        let done = false;
        const timer = window.setTimeout(() => {
          if (!done) {
            done = true;
            resolve(false);
          }
        }, 1500);
        video.requestVideoFrameCallback(() => {
          if (!done) {
            done = true;
            clearTimeout(timer);
            resolve(true);
          }
        });
      });
      if (presented) return;
    }
    try {
      await video.play();
    } catch {
      // A play that is refused still leaves the seeked frame to draw.
    }
    await delay(120);
    video.pause();
    await delay(50);
  }

  /** Mean luminance of a drawn frame, or null when the canvas cannot be read. */
  function measureFrame(ctx: CanvasRenderingContext2D): number | null {
    try {
      return meanLuminance(ctx.getImageData(0, 0, WIDTH, HEIGHT).data);
    } catch {
      return null;
    }
  }

  async function makeThumbnail() {
    if (blocked || loading) return;
    loading = true;
    error = '';
    darkWarning = '';
    ready = false;
    progress = 0;
    cancelled = false;
    try {
      message = 'Menyiapkan frame klip...';
      const id = await startPreview(helperUrl, { url: videoUrl, start, end });
      let status: Awaited<ReturnType<typeof checkPreviewStatus>> | null = null;
      for (let i = 0; i < 180; i++) {
        if (cancelled) return;
        status = await checkPreviewStatus(helperUrl, id);
        progress = status.progress;
        message = status.message || 'Memproses klip...';
        if (status.status === 'ready') break;
        if (status.status === 'error') throw new Error(status.error || 'Gagal menyiapkan klip.');
        await delay(1000);
      }
      if (cancelled) return;
      if (!status || status.status !== 'ready') throw new Error('Waktu menyiapkan frame habis. Coba lagi.');

      const video = document.createElement('video');
      sourceVideo = video;
      video.crossOrigin = 'anonymous';
      video.muted = true;
      video.playsInline = true;
      video.preload = 'auto';
      // In the DOM, even off-screen: some browsers do not decode frames for a
      // detached video, so the old detached element could draw black.
      video.setAttribute('aria-hidden', 'true');
      video.style.cssText = 'position:fixed;left:-9999px;top:0;width:320px;height:180px;pointer-events:none;';
      document.body.appendChild(video);
      video.src = previewVideoUrl(helperUrl, id);
      const metadata = waitForMedia(video, 'loadedmetadata');
      video.load();
      await metadata;
      if (cancelled) return;
      if (!video.videoWidth || !video.videoHeight || video.readyState < 1) {
        throw new Error('Video pratinjau tidak bisa dibaca. Coba siapkan ulang.');
      }

      // Try the first second, then step forward: that second can be a fade
      // from black or a dark cut, and a dark frame is retried, not accepted.
      const attempt = document.createElement('canvas');
      attempt.width = WIDTH;
      attempt.height = HEIGHT;
      const actx = attempt.getContext('2d');
      if (!actx) throw new Error('Browser tidak bisa membuat gambar thumbnail.');
      const best = document.createElement('canvas');
      best.width = WIDTH;
      best.height = HEIGHT;
      const bctx = best.getContext('2d');
      if (!bctx) throw new Error('Browser tidak bisa membuat gambar thumbnail.');
      let bestLuma = -1;
      let bestTime = 0;
      let picked: { time: number; luma: number | null } | null = null;
      const scale = Math.max(WIDTH / video.videoWidth, HEIGHT / video.videoHeight);
      const drawWidth = video.videoWidth * scale;
      const drawHeight = video.videoHeight * scale;
      for (const seekTo of thumbnailSeekTimes(video.duration)) {
        if (cancelled) return;
        message = `Mengambil frame di ${seekTo.toFixed(1)} dtk...`;
        const seeked = waitForMedia(video, 'seeked');
        video.currentTime = seekTo;
        await seeked;
        if (cancelled) return;
        await waitForVideoFrame(video);
        if (cancelled) return;
        if (video.readyState < 2) continue;
        actx.clearRect(0, 0, WIDTH, HEIGHT);
        actx.drawImage(video, (WIDTH - drawWidth) / 2, (HEIGHT - drawHeight) / 2, drawWidth, drawHeight);
        const luma = measureFrame(actx);
        if (luma !== null && luma > bestLuma) {
          bestLuma = luma;
          bestTime = seekTo;
          bctx.clearRect(0, 0, WIDTH, HEIGHT);
          bctx.drawImage(attempt, 0, 0);
        }
        if (luma === null || !isDarkFrame(luma)) {
          picked = { time: seekTo, luma };
          break;
        }
      }
      // The attempt canvas holds the frame that broke the loop; the best
      // canvas holds the brightest frame when every attempt was dark.
      const usedBest = !picked;
      if (usedBest) {
        // Every tried frame was dark: keep the brightest one, but say so
        // instead of claiming the thumbnail is ready.
        if (bestLuma < 0) throw new Error('Tidak ada frame video yang bisa diambil.');
        picked = { time: bestTime, luma: bestLuma };
        darkWarning = `Frame yang diambil masih gelap (kecerahan ${Math.round(bestLuma)} dari 255, ambang ${DARK_FRAME_LUMA}). Klip ini mungkin memang dimulai dengan adegan gelap; coba ambil ulang atau pilih klip lain.`;
      }
      sourceFrame = usedBest ? best : attempt;
      video.pause();
      video.remove();
      ready = true;
      message = darkWarning ? 'Thumbnail siap, tapi frame-nya gelap.' : 'Thumbnail siap. Edit teks hook jika perlu.';
      onhookchange(hookText);
      await tick();
      renderThumbnail(hookText);
    } catch (e) {
      sourceVideo?.pause();
      sourceVideo?.remove();
      if (!cancelled) error = (e as Error).message;
    } finally {
      if (!cancelled) loading = false;
    }
  }

  function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
    const lines: string[] = [];
    let line = '';
    for (const word of text.trim().split(/\s+/).filter(Boolean)) {
      const candidate = line ? `${line} ${word}` : word;
      if (line && ctx.measureText(candidate).width > maxWidth) {
        lines.push(line);
        line = word;
      } else {
        line = candidate;
      }
    }
    if (line) lines.push(line);
    return lines;
  }

  function renderThumbnail(text: string) {
    if (!sourceFrame || !canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    if (layout === 'blur-center') {
      const blur = 32;
      const bgScale = Math.max((WIDTH + blur * 2) / WIDTH, (HEIGHT + blur * 2) / HEIGHT);
      const bgWidth = WIDTH * bgScale;
      const bgHeight = HEIGHT * bgScale;
      ctx.save();
      ctx.filter = `blur(${blur}px)`;
      ctx.drawImage(sourceFrame, (WIDTH - bgWidth) / 2, (HEIGHT - bgHeight) / 2, bgWidth, bgHeight);
      ctx.restore();
      ctx.fillStyle = 'rgba(0, 0, 0, 0.24)';
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      const contentScale = Math.max(WIDTH / sourceFrame.width, CENTER_HEIGHT / sourceFrame.height);
      const cropWidth = WIDTH / contentScale;
      const cropHeight = CENTER_HEIGHT / contentScale;
      ctx.drawImage(
        sourceFrame,
        (sourceFrame.width - cropWidth) / 2,
        (sourceFrame.height - cropHeight) / 2,
        cropWidth,
        cropHeight,
        0,
        CENTER_TOP,
        WIDTH,
        CENTER_HEIGHT,
      );
    } else {
      ctx.drawImage(sourceFrame, 0, 0);
    }

    const fade = ctx.createLinearGradient(0, layout === 'blur-center' ? CENTER_TOP : HEIGHT * 0.48, 0, HEIGHT);
    fade.addColorStop(0, 'rgba(0, 0, 0, 0)');
    fade.addColorStop(0.35, 'rgba(0, 0, 0, 0.58)');
    fade.addColorStop(1, 'rgba(0, 0, 0, 0.94)');
    ctx.fillStyle = fade;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    const hook = text.trim() || clipTitle;
    const maxWidth = WIDTH - 64;
    let fontSize = 84;
    let lines: string[];
    do {
      ctx.font = `900 ${fontSize}px Impact, "Arial Narrow", sans-serif`;
      lines = wrapLines(ctx, hook.toLocaleUpperCase(), maxWidth);
      if (lines.length <= 5 || fontSize <= 48) break;
      fontSize -= 4;
    } while (fontSize > 44);
    if (lines.length > 5) {
      lines = lines.slice(0, 5);
      lines[4] = `${lines[4].replace(/[.…]+$/, '')}…`;
    }

    const lineHeight = fontSize * 1.04;
    const startY =
      layout === 'blur-center'
        ? CENTER_TOP + CENTER_HEIGHT - lineHeight * lines.length - 24
        : Math.min(HEIGHT - 90, HEIGHT * 0.72 + Math.max(0, (5 - lines.length) * lineHeight * 0.28));
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';
    ctx.lineWidth = Math.max(8, fontSize * 0.13);
    ctx.strokeStyle = '#080808';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.7)';
    ctx.shadowBlur = 12;
    ctx.shadowOffsetY = 5;
    lines.forEach((line, i) => {
      const y = startY + i * lineHeight;
      ctx.fillStyle = i % 2 === 0 ? '#fff' : '#ffd21f';
      ctx.strokeText(line, WIDTH / 2, y, maxWidth);
      ctx.fillText(line, WIDTH / 2, y, maxWidth);
    });
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;
  }

  async function downloadThumbnail() {
    const target = canvas;
    if (!target || !ready) return;
    const blob = await new Promise<Blob | null>((resolve) => target.toBlob(resolve, 'image/png'));
    if (!blob) {
      error = 'Gagal membuat file PNG thumbnail.';
      return;
    }
    const safeTitle = clipTitle.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, '_') || 'klip';
    downloadFile(`${safeTitle} - thumbnail.png`, blob);
  }

  function updateHook(text: string) {
    hookText = text;
    onhookchange(text);
    if (ready) renderThumbnail(text);
  }

  onDestroy(() => {
    cancelled = true;
    sourceVideo?.pause();
    sourceVideo?.remove();
    if (sourceVideo) {
      sourceVideo.removeAttribute('src');
      sourceVideo.load();
    }
  });
</script>

<Modal title="Thumbnail klip" width={820} {onclose}>
  {#snippet subtitle()}Buat thumbnail vertikal dengan frame klip dan teks hook{/snippet}

  <div class="thumbnail-layout">
    <div class="image-wrap">
      {#if ready}
        <canvas bind:this={canvas} aria-label="Pratinjau thumbnail"></canvas>
      {:else}
        <div class="empty">
          <Icon name="film" size={24} />
          <span>{loading ? message : 'Frame video akan tampil di sini'}</span>
        </div>
      {/if}
    </div>
    <div class="controls">
      <label for="thumbnail-hook">Kata-kata hook</label>
      <textarea
        id="thumbnail-hook"
        rows="4"
        maxlength="120"
        value={hookText}
        oninput={(e) => updateHook(e.currentTarget.value)}
        placeholder="Contoh: KOK BISA SEBERANI INI?"
      ></textarea>
      <p class="hint">Teks awal memakai judul klip. Klik atau edit teksnya untuk menyesuaikan hook.</p>
      <div class="layout-options" role="group" aria-label="Tata letak thumbnail">
        <button class:active={layout === 'full'} aria-pressed={layout === 'full'} onclick={() => { layout = 'full'; if (ready) renderThumbnail(hookText); }}>
          Layar penuh
        </button>
        <button class:active={layout === 'blur-center'} aria-pressed={layout === 'blur-center'} onclick={() => { layout = 'blur-center'; if (ready) renderThumbnail(hookText); }}>
          Blur + crop tengah
        </button>
      </div>
      {#if layout === 'blur-center'}
        <p class="hint">Latar blur memenuhi layar; video tajam memenuhi 2/3 bagian tengah, dengan ruang sama besar di atas dan bawah.</p>
      {/if}

      {#if blocked}
        <div class="notice"><Icon name="info" size={15} /><span>{blocked}</span></div>
      {/if}
      {#if error}
        <div class="notice bad"><Icon name="alert" size={15} /><span>{error}</span></div>
      {/if}
      {#if darkWarning}
        <div class="notice warn"><Icon name="warning" size={15} /><span>{darkWarning}</span></div>
      {/if}

      {#if loading}
        <div class="progress" aria-live="polite">
          <div class="meter"><i style:width="{progress}%"></i></div>
          <span class="hint">{message}</span>
        </div>
      {:else}
        <button class="primary" onclick={makeThumbnail} disabled={!!blocked}>
          <Icon name={ready ? 'reset' : 'film'} size={15} />
          {ready ? 'Ambil ulang frame' : 'Buat thumbnail'}
        </button>
      {/if}
      <button onclick={downloadThumbnail} disabled={!ready}>
        <Icon name="download" size={15} /> Unduh PNG
      </button>
    </div>
  </div>
</Modal>

<style>
  .thumbnail-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 250px;
    gap: 20px;
    align-items: start;
  }
  .image-wrap {
    overflow: hidden;
    width: 100%;
    max-height: min(66vh, 680px);
    aspect-ratio: 9 / 16;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: #0a0809;
  }
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .empty {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 10px;
    height: 100%;
    padding: 18px;
    color: var(--muted);
    font-size: 13px;
    text-align: center;
  }
  .controls {
    display: grid;
    gap: 10px;
  }
  .controls label {
    font-size: 13px;
    font-weight: 600;
  }
  .controls textarea {
    resize: vertical;
  }
  .controls button {
    justify-content: center;
  }
  .layout-options {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
    padding: 4px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--field);
  }
  .layout-options button {
    min-width: 0;
    padding: 7px 5px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--muted);
    font-size: 11px;
  }
  .layout-options button.active {
    background: var(--raised);
    color: var(--text);
    box-shadow: var(--shadow-satellite);
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .progress {
    display: grid;
    gap: 7px;
  }
  .meter {
    height: 5px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--field);
  }
  .meter i {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width 180ms ease;
  }
  .notice {
    display: flex;
    gap: 7px;
    align-items: flex-start;
    font-size: 12px;
  }
  .notice :global(.icon) {
    flex: none;
    margin-top: 1px;
  }
  @media (max-width: 700px) {
    .thumbnail-layout {
      grid-template-columns: minmax(0, 1fr);
    }
    .image-wrap {
      max-height: 60vh;
    }
  }
</style>
