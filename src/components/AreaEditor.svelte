<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './ui/Icon.svelte';
  import { FACE_ASPECT, fitBox, GAME_ASPECT, type Box } from '../lib/preview';

  type Which = 'game' | 'face';
  interface Props {
    /** The preview's video; its current frame is the picture to draw the areas on. */
    video: HTMLVideoElement;
    srcW: number;
    srcH: number;
    /** The areas as they are used now (already in their slot's shape). */
    game: Box;
    face: Box;
    gameManual: boolean;
    faceManual: boolean;
    onchange: (which: Which, box: Box) => void;
    onreset: () => void;
    ondone: () => void;
  }
  let { video, srcW, srcH, game, face, gameManual, faceManual, onchange, onreset, ondone }: Props = $props();

  let frameEl: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let fw = $state(0);
  let fh = $state(0);
  const aspectOf = (w: Which) => (w === 'game' ? GAME_ASPECT : FACE_ASPECT);
  const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

  function draw() {
    const ctx = canvas?.getContext('2d');
    if (!ctx || video.readyState < 2) return;
    const dpr = Math.min(2, devicePixelRatio || 1);
    canvas.width = Math.max(1, Math.round(fw * dpr));
    canvas.height = Math.max(1, Math.round(fh * dpr));
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  }

  onMount(() => {
    video.pause();
    const redraw = () => draw();
    video.addEventListener('seeked', redraw);
    video.addEventListener('loadeddata', redraw);
    return () => {
      video.removeEventListener('seeked', redraw);
      video.removeEventListener('loadeddata', redraw);
    };
  });

  $effect(() => {
    void fw;
    void fh;
    draw();
  });

  /** Grow or shrink a box from its top-left corner, keeping its shape and staying in the frame. */
  function resized(start: Box, which: Which, h: number): Box {
    const a = aspectOf(which);
    const maxH = Math.min(1 - start[1], ((1 - start[0]) * srcW) / (a * srcH));
    const nh = clamp(h, 0.08, Math.max(0.08, maxH));
    return [start[0], start[1], (nh * a * srcH) / srcW, nh];
  }

  function drag(e: PointerEvent, which: Which, mode: 'move' | 'resize') {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const target = e.currentTarget as HTMLElement;
    target.setPointerCapture(e.pointerId);
    const start = which === 'game' ? game : face;
    const x0 = e.clientX;
    const y0 = e.clientY;
    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - x0) / fw;
      const dy = (ev.clientY - y0) / fh;
      if (mode === 'move') {
        onchange(which, [clamp(start[0] + dx, 0, 1 - start[2]), clamp(start[1] + dy, 0, 1 - start[3]), start[2], start[3]]);
      } else {
        // Follow whichever way the pointer moved further, in the box's own shape.
        const fromX = ((start[2] + dx) * srcW) / (aspectOf(which) * srcH);
        onchange(which, resized(start, which, Math.max(fromX, start[3] + dy)));
      }
    };
    const up = () => {
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
      target.removeEventListener('pointercancel', up);
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
    target.addEventListener('pointercancel', up);
  }

  function key(e: KeyboardEvent, which: Which) {
    const b = which === 'game' ? game : face;
    const step = e.shiftKey ? 0.05 : 0.01;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    if (moves[e.key]) {
      const [dx, dy] = moves[e.key];
      onchange(which, [clamp(b[0] + dx, 0, 1 - b[2]), clamp(b[1] + dy, 0, 1 - b[3]), b[2], b[3]]);
    } else if (e.key === '+' || e.key === '=') {
      onchange(which, fitBox(resized(b, which, b[3] * 1.05), srcW, srcH, aspectOf(which)));
    } else if (e.key === '-' || e.key === '_') {
      onchange(which, resized(b, which, b[3] / 1.05));
    } else return;
    e.preventDefault();
  }

  const pct = (v: number) => `${(v * 100).toFixed(3)}%`;
</script>

<div class="editor">
  <div class="ed-head">
    <span class="ed-title"><Icon name="crop" size={14} /> Atur area gameplay dan kamera</span>
    <span class="ed-hint">Seret untuk menggeser, sudut kanan bawah untuk ukuran</span>
  </div>
  <div class="ed-frame" style:aspect-ratio="{srcW} / {srcH}" bind:this={frameEl} bind:clientWidth={fw} bind:clientHeight={fh}>
    <canvas bind:this={canvas} aria-hidden="true"></canvas>
    {#each [{ which: 'game' as Which, box: game, label: 'Gameplay', manual: gameManual }, { which: 'face' as Which, box: face, label: 'Kamera', manual: faceManual }] as a (a.which)}
      <div
        class="area {a.which}"
        style:left={pct(a.box[0])}
        style:top={pct(a.box[1])}
        style:width={pct(a.box[2])}
        style:height={pct(a.box[3])}
        role="slider"
        tabindex="0"
        aria-label="Area {a.label}. Panah untuk menggeser, plus atau minus untuk ukuran."
        aria-valuetext="{Math.round(a.box[0] * 100)}% dari kiri, {Math.round(a.box[1] * 100)}% dari atas, tinggi {Math.round(a.box[3] * 100)}%"
        aria-valuenow={Math.round(a.box[3] * 100)}
        onpointerdown={(e) => drag(e, a.which, 'move')}
        onkeydown={(e) => key(e, a.which)}
      >
        <span class="tag">{a.label}{a.manual ? '' : ' · otomatis'}</span>
        <span class="grip" aria-hidden="true" onpointerdown={(e) => drag(e, a.which, 'resize')}></span>
      </div>
    {/each}
  </div>
  <div class="ed-foot">
    <button class="small" onclick={onreset} disabled={!gameManual && !faceManual}>
      <Icon name="reset" size={14} /> Kembali ke otomatis
    </button>
    <button class="small primary" onclick={ondone}><Icon name="check" size={14} /> Selesai</button>
  </div>
</div>

<style>
  .editor {
    display: grid;
    gap: 10px;
    width: 100%;
  }
  .ed-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 4px 12px;
  }
  .ed-title {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
  }
  .ed-hint {
    font-size: 12px;
    color: var(--muted);
  }
  .ed-frame {
    position: relative;
    width: 100%;
    overflow: hidden;
    border-radius: var(--radius-md);
    background: #000;
    touch-action: none;
    user-select: none;
  }
  canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  .area {
    position: absolute;
    border: 2px solid var(--accent);
    border-radius: 6px;
    background: rgba(249, 115, 22, 0.14);
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35), 0 0 22px -6px rgba(249, 115, 22, 0.6);
    cursor: move;
    touch-action: none;
  }
  .area.face {
    border-color: #fff;
    background: rgba(255, 255, 255, 0.1);
  }
  .area:focus-visible {
    outline: 2px solid #fff;
    outline-offset: 2px;
  }
  .tag {
    position: absolute;
    top: 4px;
    left: 4px;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--accent);
    color: #fff;
    font-size: 11px;
    font-weight: 600;
    line-height: 1.3;
    white-space: nowrap;
    pointer-events: none;
  }
  .area.face .tag {
    background: #fff;
    color: #111;
  }
  /* The handle is larger than it looks, so it is easy to catch with a finger. */
  .grip {
    position: absolute;
    right: -8px;
    bottom: -8px;
    width: 22px;
    height: 22px;
    cursor: nwse-resize;
  }
  .grip::after {
    content: '';
    position: absolute;
    right: 6px;
    bottom: 6px;
    width: 10px;
    height: 10px;
    border-radius: 2px;
    background: var(--accent);
    box-shadow: 0 0 0 2px #000;
  }
  .area.face .grip::after {
    background: #fff;
  }
  .ed-foot {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
</style>
