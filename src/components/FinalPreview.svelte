<script lang="ts">
  import AreaEditor from './AreaEditor.svelte';
  import CaptionOverlay from './CaptionOverlay.svelte';
  import Icon from './ui/Icon.svelte';
  import type { AspectRatio, CaptionCue, CaptionPosition, CaptionStyle } from '../lib/captions';
  import { sceneIndexAt, sceneStarts } from '../lib/compilation';
  import { checkPreviewStatus, previewVideoUrl, startPreview, type PreviewStatus } from '../lib/helper';
  import {
    centerCropX,
    cropXAt,
    FACE_ASPECT,
    fitBox,
    FULL_FRAME,
    GAME_ASPECT,
    gamingCaptionArea,
    layoutFor,
    type Box,
  } from '../lib/preview';
  import { fmtTime } from '../lib/transcript';

  interface Props {
    helperUrl: string;
    videoUrl: string;
    /** What plays, in seconds of the source video: one clip, or a compilation's scenes in order. */
    scenes: { start: number; end: number; title?: string }[];
    /** Captions timed from the start of the final video: the same cues the export burns in. */
    cues: CaptionCue[];
    aspect: AspectRatio;
    captionEnabled: boolean;
    captionStyle: CaptionStyle;
    captionPosition: CaptionPosition;
    /** The helper's id for this preview; the export reuses its face path. */
    previewId?: string;
    /** Gamer mode areas set by hand (null: found automatically / centred) and where the webcam goes. */
    faceBox?: Box | null;
    gameBox?: Box | null;
    faceTop?: boolean;
    /** Out: the webcam the helper found, so the export uses the same one. */
    detectedFace?: Box | null;
  }
  let {
    helperUrl,
    videoUrl,
    scenes,
    cues,
    aspect,
    captionEnabled,
    captionStyle,
    captionPosition,
    previewId = $bindable(''),
    faceBox = $bindable(null),
    gameBox = $bindable(null),
    faceTop = false,
    detectedFace = $bindable(null),
  }: Props = $props();

  let status = $state<PreviewStatus | null>(null);
  let error = $state('');
  let attempt = $state(0);
  let elapsed = $state(0);

  let video = $state<HTMLVideoElement | null>(null);
  let backdrop = $state<HTMLCanvasElement | null>(null);
  let faceCanvas = $state<HTMLCanvasElement | null>(null);
  let frameH = $state(0);
  let frameW = $state(0);
  let time = $state(0);
  let playing = $state(false);
  /** The big play button shows until the first play and after the end, so it never hides a caption mid-clip. */
  let started = $state(false);
  let mediaDuration = $state(0);
  let editing = $state(false);

  const ready = $derived(status?.status === 'ready');
  const src = $derived(ready && previewId ? `${previewVideoUrl(helperUrl, previewId)}#t=0.001` : '');
  const srcW = $derived(status?.width || 16);
  const srcH = $derived(status?.height || 9);
  const vertical = $derived(aspect !== '16:9');
  const layout = $derived(layoutFor(aspect, status?.width, status?.height));
  const crop = $derived(status?.crop ?? null);
  const starts = $derived(sceneStarts(scenes));
  const many = $derived(scenes.length > 1);
  const total = $derived(mediaDuration || status?.duration || starts[starts.length - 1]);
  const sceneNow = $derived(sceneIndexAt(starts, time));
  /** Cut points, so only a real change of scenes asks the helper for a new preview. */
  const sceneKey = $derived(JSON.stringify(scenes.map((s) => [+s.start.toFixed(2), +s.end.toFixed(2)])));
  const reduceMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Gamer mode: both areas in their slot's shape, exactly as the export will crop them.
  const gaming = $derived(layout === 'gaming');
  $effect(() => {
    detectedFace = status?.facecam?.box ?? null;
  });
  const gameFit = $derived(fitBox(gameBox ?? FULL_FRAME, srcW, srcH, GAME_ASPECT));
  const faceFit = $derived(fitBox(faceBox ?? detectedFace ?? FULL_FRAME, srcW, srcH, FACE_ASPECT));
  /** The video sized and placed so the gameplay area fills the top (or bottom) two thirds. */
  const gameView = $derived.by(() => {
    const paneH = (frameH * 2) / 3;
    const w = frameW / gameFit[2];
    const h = paneH / gameFit[3];
    return { w, h, x: -gameFit[0] * w, y: (faceTop ? frameH / 3 : 0) - gameFit[1] * h };
  });

  const note = $derived.by(() => {
    if (!ready) return null;
    const scan = status?.crop_state;
    if (aspect === '9:16_gaming') {
      if (scan === 'pending' || scan === 'running')
        return { busy: true, text: `Mencari kamera wajah… ${status?.crop_progress ?? 0}%.` };
      if (faceBox) return { busy: false, text: 'Area kamera diatur manual.' };
      if (detectedFace) return { busy: false, text: 'Kamera wajah ditemukan otomatis. Geser lewat "Atur area" kalau kurang pas.' };
      if (scan === 'unavailable') return { busy: false, text: 'Deteksi wajah belum terpasang di helper. Atur area kamera secara manual.' };
      return { busy: false, text: 'Kamera wajah tidak terdeteksi. Atur area kamera secara manual.' };
    }
    if (aspect !== '9:16_crop') return null;
    switch (scan) {
      case 'pending':
      case 'running':
        return { busy: true, text: `Mendeteksi wajah… ${status?.crop_progress ?? 0}%. Sementara ini potongan tengah.` };
      case 'done':
        return status?.crop?.faces
          ? { busy: false, text: 'Kamera mengikuti wajah, persis seperti hasil ekspor.' }
          : { busy: false, text: 'Tidak ada wajah terdeteksi, jadi dipakai potongan tengah.' };
      case 'none':
        return { busy: false, text: 'Video sumber sudah vertikal, jadi dipakai latar blur.' };
      case 'unavailable':
        return { busy: false, text: 'Deteksi wajah belum terpasang di helper, jadi dipakai potongan tengah.' };
      case 'error':
        return { busy: false, text: 'Deteksi wajah gagal di pratinjau; ekspor akan mencobanya lagi.' };
    }
    return null;
  });

  // Ask the helper for a light copy of the clip, then poll until the video and the face scan are in.
  let lastKey = '';
  $effect(() => {
    const base = helperUrl;
    const key = sceneKey;
    const spans = JSON.parse(key) as [number, number][];
    const params =
      spans.length === 1
        ? { url: videoUrl, start: spans[0][0], end: spans[0][1] }
        : { url: videoUrl, segments: spans.map(([start, end]) => ({ start, end })) };
    void attempt;
    // Reordering scenes is often a few clicks in a row; ask once they settle.
    const delay = lastKey && lastKey !== key ? 500 : 0;
    lastKey = key;
    let stopped = false;
    let timer = 0;
    status = null;
    error = '';
    previewId = '';
    editing = false;
    elapsed = 0;
    const began = Date.now();
    const clock = window.setInterval(() => (elapsed = Math.round((Date.now() - began) / 1000)), 1000);
    const fail = (e: unknown) => {
      if (stopped) return;
      error = e instanceof Error ? e.message : String(e);
      clearInterval(clock);
    };
    const poll = async (id: string) => {
      try {
        const s = await checkPreviewStatus(base, id);
        if (stopped) return;
        status = s;
        if (s.status === 'error') return fail(new Error(s.error || 'Pratinjau gagal disiapkan.'));
        if (s.status === 'ready') clearInterval(clock);
        const settled = s.status === 'ready' && s.crop_state !== 'pending' && s.crop_state !== 'running';
        if (!settled) timer = window.setTimeout(() => poll(id), s.status === 'ready' ? 600 : 1000);
      } catch (e) {
        fail(e);
      }
    };
    const ask = window.setTimeout(
      () =>
        startPreview(base, params).then((id) => {
          if (stopped) return;
          previewId = id;
          poll(id);
        }, fail),
      delay,
    );
    return () => {
      stopped = true;
      clearTimeout(ask);
      clearTimeout(timer);
      clearInterval(clock);
    };
  });

  /** Lays out one frame the way the export renders it. */
  function paint(t: number) {
    const v = video;
    if (!v) return;
    time = t;
    if (layout === 'crop') {
      // The 9:16 window slides along the face path; the video is as tall as the frame.
      const x = crop?.keys.length ? cropXAt(crop.keys, t) : centerCropX(srcW, srcH);
      v.style.transform = `translate3d(${((-x * frameH * srcW) / srcH).toFixed(2)}px, 0, 0)`;
    } else if (layout === 'gaming') {
      v.style.transform = `translate3d(${gameView.x.toFixed(2)}px, ${gameView.y.toFixed(2)}px, 0)`;
    } else {
      v.style.transform = '';
    }
    if (v.readyState < 2) return;
    if (layout === 'blur' && backdrop) drawBackdrop(v, backdrop);
    if (layout === 'gaming' && faceCanvas) drawFace(v, faceCanvas);
  }

  /** The source scaled to cover the frame, as ffmpeg does before blurring it; CSS adds the blur. */
  function drawBackdrop(v: HTMLVideoElement, c: HTMLCanvasElement) {
    const ctx = c.getContext('2d');
    const vw = v.videoWidth;
    const vh = v.videoHeight;
    if (!ctx || !vw || !vh) return;
    const scale = Math.max(c.width / vw, c.height / vh);
    const sw = c.width / scale;
    const sh = c.height / scale;
    ctx.drawImage(v, (vw - sw) / 2, (vh - sh) / 2, sw, sh, 0, 0, c.width, c.height);
  }

  /** The webcam area, scaled into the camera third of the frame. */
  function drawFace(v: HTMLVideoElement, c: HTMLCanvasElement) {
    const ctx = c.getContext('2d');
    const vw = v.videoWidth;
    const vh = v.videoHeight;
    if (!ctx || !vw || !vh) return;
    const dpr = Math.min(2, devicePixelRatio || 1);
    const cw = Math.max(1, Math.round(frameW * dpr));
    const ch = Math.max(1, Math.round((frameH / 3) * dpr));
    if (c.width !== cw || c.height !== ch) [c.width, c.height] = [cw, ch];
    const [x, y, w, h] = faceFit;
    ctx.drawImage(v, x * vw, y * vh, w * vw, h * vh, 0, 0, cw, ch);
  }

  // Repaint when the layout, the face path, the areas or the frame size change, also while paused.
  $effect(() => {
    void gameView;
    void faceFit;
    void faceCanvas;
    if (video) paint(video.currentTime);
  });

  // While playing, repaint for every video frame so the crop moves exactly with the picture.
  let loopId = 0;
  function startLoop() {
    const id = ++loopId;
    const v = video;
    if (!v) return;
    const next = () => {
      if (id !== loopId || v.paused || v.ended) return;
      if (typeof v.requestVideoFrameCallback === 'function') {
        v.requestVideoFrameCallback(() => {
          if (id !== loopId) return;
          paint(v.currentTime);
          next();
        });
      } else {
        requestAnimationFrame(() => {
          if (id !== loopId) return;
          paint(v.currentTime);
          next();
        });
      }
    };
    next();
  }

  function toggle() {
    const v = video;
    if (!v) return;
    if (v.paused || v.ended) {
      editing = false;
      if (v.ended || v.currentTime >= total - 0.05) v.currentTime = 0;
      v.play().catch(() => {});
    } else {
      v.pause();
    }
  }

  function seek(t: number) {
    const v = video;
    if (!v) return;
    v.currentTime = t;
    paint(t);
  }
</script>

<div class="preview">
  <div class="stage">
    <div class="frame" class:v={vertical} class:h={!vertical} class:hidden={editing} bind:clientHeight={frameH} bind:clientWidth={frameW}>
      {#if src}
        {#if layout === 'blur'}
          <canvas class="backdrop" bind:this={backdrop} width="72" height="128" aria-hidden="true"></canvas>
        {/if}
        <!-- svelte-ignore a11y_media_has_caption -->
        <video
          bind:this={video}
          class="media {layout}"
          style:width={layout === 'crop' ? `${(frameH * srcW) / srcH}px` : gaming ? `${gameView.w}px` : undefined}
          style:height={gaming ? `${gameView.h}px` : undefined}
          {src}
          preload="auto"
          playsinline
          onloadedmetadata={(e) => (mediaDuration = e.currentTarget.duration || 0)}
          onloadeddata={(e) => paint(e.currentTarget.currentTime)}
          onplay={() => {
            playing = true;
            started = true;
            startLoop();
          }}
          onpause={(e) => {
            playing = false;
            paint(e.currentTarget.currentTime);
          }}
          onended={() => {
            playing = false;
            started = false;
          }}
          onseeked={(e) => paint(e.currentTarget.currentTime)}
          ontimeupdate={(e) => e.currentTarget.paused && paint(e.currentTarget.currentTime)}
          onerror={() => (error = 'Video pratinjau tidak bisa diputar. Coba siapkan ulang.')}
        ></video>
        {#if gaming}
          <canvas class="face-pane" class:top={faceTop} bind:this={faceCanvas} aria-hidden="true"></canvas>
        {/if}
        <CaptionOverlay
          {cues}
          clipStart={0}
          clipEnd={total}
          currentTime={time}
          enabled={captionEnabled}
          style={captionStyle}
          position={captionPosition}
          exact
          {vertical}
          area={gaming ? gamingCaptionArea(faceTop) : null}
        />
        <button class="hit" onclick={toggle} aria-label={playing ? 'Jeda pratinjau' : 'Putar pratinjau'}>
          {#if !playing && !started}
            <span class="big-play" aria-hidden="true"><Icon name="play" size={26} /></span>
          {/if}
        </button>
      {/if}

      {#if error || !src}
        <div class="state" role="status" aria-live="polite">
          {#if error}
            <Icon name="alert" size={20} class="state-icon bad" />
            <p class="err">{error}</p>
            <button onclick={() => attempt++}><Icon name="reset" /> Siapkan ulang</button>
          {:else}
            <Icon name="loader" size={20} class="state-icon spin" />
            <p>{status?.message || 'Menyiapkan pratinjau…'}</p>
            <div class="bar" class:still={reduceMotion} aria-hidden="true"><i></i></div>
            <p class="muted">{elapsed} dtk · {many ? 'biasanya ±5 dtk per adegan' : 'biasanya 5–20 dtk'}</p>
          {/if}
        </div>
      {/if}
    </div>

    {#if editing && video}
      <AreaEditor
        {video}
        {srcW}
        {srcH}
        game={gameFit}
        face={faceFit}
        gameManual={!!gameBox}
        faceManual={!!faceBox}
        onchange={(which, box) => (which === 'game' ? (gameBox = box) : (faceBox = box))}
        onreset={() => {
          gameBox = null;
          faceBox = null;
        }}
        ondone={() => (editing = false)}
      />
    {/if}
  </div>

  <div class="controls">
    <button class="icon-btn ctl" onclick={toggle} disabled={!src || !!error} aria-label={playing ? 'Jeda' : 'Putar'}>
      <Icon name={playing ? 'pause' : 'play'} />
    </button>
    <div class="scrub-wrap">
      <input
        class="scrub"
        type="range"
        min="0"
        max={total}
        step="0.01"
        value={time}
        oninput={(e) => seek(+e.currentTarget.value)}
        disabled={!src || !!error}
        aria-label="Posisi pratinjau"
        aria-valuetext={many ? `${fmtTime(time)}, adegan ${sceneNow + 1} dari ${scenes.length}` : fmtTime(time)}
      />
      {#if many}
        <!-- Where one scene cuts to the next -->
        <div class="cuts" aria-hidden="true">
          {#each starts.slice(1, -1) as at, i (i)}
            <i style:left="{(100 * at) / total}%"></i>
          {/each}
        </div>
      {/if}
    </div>
    <span class="time">{fmtTime(time)} / {fmtTime(total)}</span>
    {#if gaming}
      <button class="small area-btn" class:on={editing} onclick={() => (editing = !editing)} disabled={!src || !!error} aria-pressed={editing}>
        <Icon name="crop" size={14} /> Atur area
      </button>
    {/if}
  </div>

  <p class="foot">
    {#if many}
      <span class="scene-now">Adegan {sceneNow + 1} dari {scenes.length}{scenes[sceneNow]?.title ? ` · ${scenes[sceneNow].title}` : ''}</span>
    {/if}
    {#if note}
      <span class="note" class:busy={note.busy}>{note.text}</span>
    {/if}
    <span class="muted">Pratinjau 480p; video ekspor 1080p.</span>
  </p>
</div>

<style>
  .preview {
    display: grid;
    gap: 10px;
    min-width: 0;
  }
  /* Same size for every aspect ratio, so switching formats never shifts the page. */
  .stage {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    height: var(--preview-stage-h, min(62vh, 600px));
    min-height: 300px;
    padding: 10px;
    border-radius: var(--radius-xl);
    background: #0b0b0d;
    container-type: size;
  }
  .frame {
    position: relative;
    flex: none;
    overflow: hidden;
    background: #000;
    border-radius: var(--radius-md);
    container-type: size;
  }
  .frame.hidden {
    position: absolute;
    visibility: hidden;
  }
  .frame.v {
    height: min(100cqh, 100cqw * 16 / 9);
    aspect-ratio: 9 / 16;
  }
  .frame.h {
    width: min(100cqw, 100cqh * 16 / 9);
    aspect-ratio: 16 / 9;
  }
  .stage :global(.editor) {
    max-height: 100%;
    overflow: auto;
  }
  .media {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .media.crop,
  .media.gaming {
    inset: 0 auto auto 0;
    max-width: none;
    object-fit: fill;
    will-change: transform;
  }
  .media.crop {
    bottom: 0;
  }
  .face-pane {
    position: absolute;
    left: 0;
    top: calc(100% * 2 / 3);
    z-index: 1;
    width: 100%;
    height: calc(100% / 3);
    background: #000;
  }
  .face-pane.top {
    top: 0;
  }
  .backdrop {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    filter: blur(3cqw);
    transform: scale(1.15);
  }
  .media.blur {
    inset: 16.6667% 0 auto;
    width: 100%;
    height: 66.6667%;
    object-fit: cover;
  }
  .hit {
    position: absolute;
    inset: 0;
    z-index: 4;
    display: grid;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
  }
  .hit:hover:not(:disabled) {
    background: transparent;
  }
  .hit:active:not(:disabled) {
    transform: none;
  }
  .hit:focus-visible {
    outline-offset: -3px;
  }
  .big-play {
    display: grid;
    place-items: center;
    width: 60px;
    height: 60px;
    /* A play triangle looks centred a little toward its point. */
    padding-left: 3px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    transition: transform 0.15s ease-out;
  }
  .big-play :global(.icon) {
    fill: currentColor;
  }
  .hit:hover .big-play {
    transform: scale(1.06);
  }
  .state {
    position: absolute;
    inset: 0;
    z-index: 5;
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 10px;
    padding: 18px;
    text-align: center;
    font-size: 13px;
    background: #0b0b0d;
  }
  .state p {
    margin: 0;
  }
  .state :global(.state-icon) {
    color: var(--accent-text);
  }
  .state :global(.state-icon.bad) {
    color: var(--bad-text);
  }
  .err {
    color: #fecaca;
  }
  .bar {
    width: 140px;
    height: 4px;
    border-radius: 2px;
    background: var(--ink-3);
    overflow: hidden;
  }
  .bar i {
    display: block;
    width: 40%;
    height: 100%;
    border-radius: 2px;
    background: var(--accent);
    animation: slide 1.3s ease-in-out infinite;
  }
  .bar.still i {
    width: 100%;
    opacity: 0.5;
    animation: none;
  }
  @keyframes slide {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(250%);
    }
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .ctl {
    flex: none;
    width: 40px;
    height: 40px;
    border-radius: 50%;
  }
  .ctl :global(.icon) {
    color: var(--text);
    fill: currentColor;
  }
  .scrub-wrap {
    position: relative;
    flex: 1;
    min-width: 0;
    display: flex;
  }
  .scrub {
    flex: 1;
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    box-shadow: none;
    accent-color: var(--accent);
  }
  /* Inset by about half a thumb, where the range track starts and ends. */
  .cuts {
    position: absolute;
    inset: 0 8px;
    pointer-events: none;
  }
  .cuts i {
    position: absolute;
    top: 50%;
    width: 2px;
    height: 12px;
    margin: -6px 0 0 -1px;
    border-radius: 1px;
    background: var(--text);
    opacity: 0.7;
  }
  .time {
    flex: none;
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .area-btn {
    flex: none;
  }
  .area-btn.on {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .foot {
    display: grid;
    gap: 2px;
    margin: 0;
    font-size: 12px;
  }
  .scene-now {
    color: var(--text);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .note {
    color: var(--text);
  }
  .note.busy {
    color: var(--warn-text);
  }
  @media (max-width: 860px) {
    .stage {
      height: var(--preview-stage-h, min(52vh, 520px));
    }
  }
</style>
