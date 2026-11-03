<script lang="ts">
  import { onMount } from 'svelte';
  import type { Unit, Word } from '../lib/types';
  import { fmtDuration, fmtTime, nearestBoundary, unitIndexOfWord } from '../lib/transcript';

  type Edge = 'start' | 'end';
  interface Props {
    words: Word[];
    units: Unit[];
    /** Visible word range. */
    lo: number;
    hi: number;
    /** Clip word range. */
    w0: number;
    w1: number;
    current: number;
    minSec: number;
    maxSec: number;
    snap: boolean;
    onstart: (wi: number) => void;
    onend: (wi: number) => void;
    ondragend: () => void;
    onseek: (t: number) => void;
    onexpand: (dir: -1 | 1) => void;
    onnudge: (edge: Edge, dir: -1 | 1, bySentence: boolean) => void;
  }
  let { words, units, lo, hi, w0, w1, current, minSec, maxSec, snap, onstart, onend, ondragend, onseek, onexpand, onnudge }: Props =
    $props();

  let track: HTMLDivElement;
  let drag = $state<Edge | null>(null);

  const vs = $derived(words[lo]?.s ?? 0);
  const ve = $derived(words[hi]?.e ?? vs + 1);
  const span = $derived(Math.max(1, ve - vs));
  const cs = $derived(words[w0].s);
  const ce = $derived(words[w1].e);
  const visUnits = $derived(units.slice(unitIndexOfWord(units, lo), unitIndexOfWord(units, hi) + 1));
  const ticks = $derived.by(() => {
    const step = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600].find((s) => span / s <= 8) ?? 600;
    const out: number[] = [];
    for (let t = Math.ceil(vs / step) * step; t <= ve; t += step) out.push(t);
    return out;
  });

  const pct = (t: number) => Math.min(100, Math.max(0, ((t - vs) / span) * 100));

  function timeAt(clientX: number) {
    const r = track.getBoundingClientRect();
    return vs + Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * span;
  }

  onMount(() => {
    const down = (e: PointerEvent) => {
      const handle = (e.target as HTMLElement).closest<HTMLElement>('[data-handle]');
      if (handle) {
        drag = handle.dataset.handle as Edge;
        track.setPointerCapture(e.pointerId);
        e.preventDefault();
        return;
      }
      onseek(timeAt(e.clientX));
    };
    const move = (e: PointerEvent) => {
      if (!drag) return;
      const wi = nearestBoundary(words, units, timeAt(e.clientX), lo, hi, drag, snap);
      if (wi < 0) return;
      if (drag === 'start') onstart(Math.min(wi, w1));
      else onend(Math.max(wi, w0));
    };
    const up = (e: PointerEvent) => {
      if (!drag) return;
      drag = null;
      if (track.hasPointerCapture(e.pointerId)) track.releasePointerCapture(e.pointerId);
      ondragend();
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

  function key(e: KeyboardEvent, edge: Edge) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    onnudge(edge, e.key === 'ArrowLeft' ? -1 : 1, e.shiftKey);
  }
</script>

<div class="timeline">
  <div class="head">
    <button class="ghost small" onclick={() => onexpand(-1)}>⟵ 30 dtk</button>
    <span class="hint">Geser penanda <b>AWAL</b> / <b>AKHIR</b>. Klik di mana saja untuk memutar dari titik itu.</span>
    <button class="ghost small" onclick={() => onexpand(1)}>30 dtk ⟶</button>
  </div>

  <div class="track" class:dragging={drag} bind:this={track}>
    <div class="ruler">
      {#each ticks as t (t)}
        <span style:left="{pct(t)}%">{fmtTime(t)}</span>
      {/each}
    </div>
    <div class="lane">
      {#each visUnits as u (u.id)}
        <div class="unit" class:alt={u.id % 2 === 1} style:left="{pct(u.s)}%" style:width="{pct(u.e) - pct(u.s)}%" title={u.text}></div>
      {/each}
      <div
        class="zone"
        style:left="{pct(cs + minSec)}%"
        style:width="{pct(cs + maxSec) - pct(cs + minSec)}%"
        title="Area ideal untuk AKHIR ({minSec}–{maxSec} dtk)"
      ></div>
      <div class="sel" style:left="{pct(cs)}%" style:width="{pct(ce) - pct(cs)}%">
        <span>{fmtDuration(ce - cs)}</span>
      </div>
      {#if current >= vs && current <= ve}
        <div class="playhead" style:left="{pct(current)}%"></div>
      {/if}
      <div
        class="handle start"
        data-handle="start"
        style:left="{pct(cs)}%"
        role="slider"
        tabindex="0"
        aria-label="Awal klip (panah kiri/kanan per kata, Shift per kalimat)"
        aria-valuemin={Math.floor(vs)}
        aria-valuemax={Math.ceil(ve)}
        aria-valuenow={Math.round(cs)}
        aria-valuetext={fmtTime(cs, true)}
        onkeydown={(e) => key(e, 'start')}
      >
        <span class="tag">AWAL {fmtTime(cs, true)}</span>
      </div>
      <div
        class="handle end"
        data-handle="end"
        style:left="{pct(ce)}%"
        role="slider"
        tabindex="0"
        aria-label="Akhir klip (panah kiri/kanan per kata, Shift per kalimat)"
        aria-valuemin={Math.floor(vs)}
        aria-valuemax={Math.ceil(ve)}
        aria-valuenow={Math.round(ce)}
        aria-valuetext={fmtTime(ce, true)}
        onkeydown={(e) => key(e, 'end')}
      >
        <span class="tag">AKHIR {fmtTime(ce, true)}</span>
      </div>
    </div>
  </div>
</div>

<style>
  .timeline {
    display: grid;
    gap: 8px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .hint {
    flex: 1;
    text-align: center;
    font-size: 12px;
    color: var(--muted);
  }
  .track {
    position: relative;
    padding: 22px 0 26px;
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
    height: 18px;
  }
  .ruler span {
    position: absolute;
    transform: translateX(-50%);
    font-size: 10px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .lane {
    position: relative;
    height: 56px;
    background: var(--panel-2);
    border-radius: 8px;
    overflow: visible;
  }
  .unit {
    position: absolute;
    top: 0;
    bottom: 0;
    background: rgba(255, 255, 255, 0.04);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
  }
  .unit.alt {
    background: rgba(255, 255, 255, 0.08);
  }
  .zone {
    position: absolute;
    bottom: 0;
    height: 6px;
    background: repeating-linear-gradient(45deg, rgba(52, 211, 153, 0.55) 0 6px, rgba(52, 211, 153, 0.2) 6px 12px);
    border-radius: 3px;
    pointer-events: none;
  }
  .sel {
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
  .sel span {
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
    text-shadow: 0 1px 2px #000;
  }
  .playhead {
    position: absolute;
    top: -4px;
    bottom: -4px;
    width: 2px;
    background: #fff;
    pointer-events: none;
  }
  .handle {
    position: absolute;
    top: -6px;
    bottom: -6px;
    width: 14px;
    margin-left: -7px;
    border-radius: 4px;
    background: var(--accent);
    cursor: ew-resize;
    z-index: 2;
    outline-offset: 2px;
  }
  .handle::after {
    content: '';
    position: absolute;
    left: 6px;
    top: 14px;
    bottom: 14px;
    width: 2px;
    background: rgba(255, 255, 255, 0.85);
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
