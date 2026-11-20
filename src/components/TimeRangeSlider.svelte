<script lang="ts">
  import { onMount } from 'svelte';
  import { fmtDuration, fmtTime } from '../lib/transcript';

  type Edge = 'start' | 'end';
  interface Props {
    start: number;
    end: number;
    min: number;
    max: number;
    current?: number;
    onstart: (t: number, dragging?: boolean) => void;
    onend: (t: number, dragging?: boolean) => void;
    ondragend?: () => void;
  }
  let { start, end, min, max, current = -1, onstart, onend, ondragend }: Props = $props();

  let track: HTMLDivElement;
  let drag = $state<Edge | null>(null);

  const span = $derived(Math.max(1e-3, max - min));
  const pct = (t: number) => Math.min(100, Math.max(0, ((t - min) / span) * 100));
  const lo = $derived(pct(start));
  const hi = $derived(pct(end));

  function timeAt(clientX: number) {
    const r = track.getBoundingClientRect();
    return Math.min(max, Math.max(min, min + Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * span));
  }

  const ticks = $derived.by(() => {
    const step = [1, 5, 10, 15, 30, 60, 120, 300, 600].find((s) => span / s <= 10) ?? 600;
    const out: number[] = [];
    for (let t = Math.ceil(min / step) * step; t <= max; t += step) out.push(t);
    return out;
  });

  onMount(() => {
    const down = (e: PointerEvent) => {
      const handle = (e.target as HTMLElement).closest<HTMLElement>('[data-handle]');
      if (handle) {
        drag = handle.dataset.handle as Edge;
        track.setPointerCapture(e.pointerId);
        e.preventDefault();
        return;
      }
      // A press on the rail moves the nearest handle, keeping the clip's shape.
      const t = timeAt(e.clientX);
      const dl = Math.abs(t - start);
      const dr = Math.abs(t - end);
      drag = dl <= dr ? 'start' : 'end';
      apply(drag, t, true);
      track.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (drag) apply(drag, timeAt(e.clientX), true);
    };
    const up = (e: PointerEvent) => {
      if (!drag) return;
      drag = null;
      if (track.hasPointerCapture(e.pointerId)) track.releasePointerCapture(e.pointerId);
      ondragend?.();
    };
    track.addEventListener('pointerdown', down);
    track.addEventListener('pointermove', move);
    track.addEventListener('pointerup', up);
    track.addEventListener('pointercancel', up);
    return () => {
      track.removeEventListener('pointerdown', down);
      track.removeEventListener('pointermove', move);
      track.removeEventListener('pointerup', up);
      track.removeEventListener('pointercancel', up);
    };
  });

  function apply(edge: Edge, t: number, dragging: boolean) {
    if (edge === 'start') onstart(Math.min(t, end), dragging);
    else onend(Math.max(t, start), dragging);
  }

  function key(e: KeyboardEvent, edge: Edge) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const by = (e.shiftKey ? 5 : 1) * (e.key === 'ArrowLeft' ? -1 : 1);
    apply(edge, (edge === 'start' ? start : end) + by, false);
  }
</script>

<div class="range" aria-label="Rentang waktu klip">
  <div class="track" class:dragging={drag} bind:this={track}>
    <div class="ruler">
      {#each ticks as t (t)}
        <span style:left="{pct(t)}%">{fmtTime(t)}</span>
      {/each}
    </div>
    <div class="rail">
      {#if current >= min && current <= max}
        <div class="playhead" style:left="{pct(current)}%"></div>
      {/if}
    </div>
    <div class="zone" style:left="{lo}%" style:right="{100 - hi}%">
      <span>{fmtDuration(end - start)}</span>
    </div>
    <div
      class="handle start"
      data-handle="start"
      style:left="{lo}%"
      role="slider"
      tabindex="0"
      aria-label="Awal klip (panah kiri/kanan per detik, Shift per 5 detik)"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(start)}
      aria-valuetext={fmtTime(start, true)}
      onkeydown={(e) => key(e, 'start')}
    >
      <span class="tag">AWAL {fmtTime(start, true)}</span>
    </div>
    <div
      class="handle end"
      data-handle="end"
      style:left="{hi}%"
      role="slider"
      tabindex="0"
      aria-label="Akhir klip (panah kiri/kanan per detik, Shift per 5 detik)"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(end)}
      aria-valuetext={fmtTime(end, true)}
      onkeydown={(e) => key(e, 'end')}
    >
      <span class="tag">AKHIR {fmtTime(end, true)}</span>
    </div>
  </div>
</div>

<style>
  .range {
    display: grid;
    gap: 8px;
  }
  .track {
    position: relative;
    padding: 22px 0 30px;
    cursor: pointer;
    touch-action: none;
    user-select: none;
  }
  .track.dragging {
    cursor: grabbing;
  }
  .ruler {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 16px;
  }
  .ruler span {
    position: absolute;
    transform: translateX(-50%);
    font-size: 10px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .rail {
    position: relative;
    height: 56px;
    border: 1px solid var(--border);
    background: var(--panel-2);
    border-radius: 8px;
    overflow: visible;
  }
  .playhead {
    position: absolute;
    top: -4px;
    bottom: -4px;
    width: 2px;
    background: #fff;
    pointer-events: none;
  }
  .zone {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--accent-soft);
    border-top: 2px solid var(--accent);
    border-bottom: 2px solid var(--accent);
    display: grid;
    place-items: center;
    pointer-events: none;
    overflow: hidden;
  }
  .zone span {
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
    text-shadow: 0 1px 2px #000;
  }
  .handle {
    position: absolute;
    top: -6px;
    bottom: -6px;
    width: 14px;
    margin-left: -7px;
    border-radius: 4px;
    background: var(--accent-grad);
    box-shadow:
      0 0 14px rgba(249, 115, 22, 0.6),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
    cursor: ew-resize;
    z-index: 2;
    outline-offset: 2px;
  }
  .handle.end {
    background: var(--accent-2);
  }
  .tag {
    position: absolute;
    top: 100%;
    margin-top: 4px;
    font-size: 10px;
    font-weight: 700;
    white-space: nowrap;
    padding: 1px 5px;
    border-radius: 4px;
    background: var(--accent);
    color: #fff;
    font-variant-numeric: tabular-nums;
  }
  .handle.start .tag {
    left: 0;
  }
  .handle.end .tag {
    right: 0;
    background: var(--accent-2);
    color: #001;
  }
</style>
