<script lang="ts">
  import { onMount, tick } from 'svelte';
  import type { Unit, Word } from '../lib/types';
  import { fmtTime, unitIndexOfWord } from '../lib/transcript';

  type Edge = 'start' | 'end';
  interface Props {
    words: Word[];
    units: Unit[];
    lo: number;
    hi: number;
    w0: number;
    w1: number;
    currentWord: number;
    playing: boolean;
    snap: boolean;
    /** Changes when another clip is opened; scrolls the clip start into view. */
    focusKey: string;
    onstart: (wi: number, dragging: boolean) => void;
    onend: (wi: number, dragging: boolean) => void;
    ondragend: () => void;
    onplay: (wi: number) => void;
    onseek: (t: number) => void;
    onexpand: (dir: -1 | 1) => void;
  }
  let {
    words,
    units,
    lo,
    hi,
    w0,
    w1,
    currentWord,
    playing,
    snap,
    focusKey,
    onstart,
    onend,
    ondragend,
    onplay,
    onseek,
    onexpand,
  }: Props = $props();

  const MENU_W = 240;
  const MENU_H = 215;

  let box: HTMLDivElement;
  let drag = $state<Edge | null>(null);
  let menu = $state<{ wi: number; x: number; y: number } | null>(null);

  const visUnits = $derived(units.slice(unitIndexOfWord(units, lo), unitIndexOfWord(units, hi) + 1));
  const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, k) => a + k);

  function wordFromPoint(x: number, y: number): number | null {
    const el = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-wi]');
    return el ? Number(el.dataset.wi) : null;
  }

  /**
   * Anchor the word menu under (or above, near the bottom) its word. It is fixed to the
   * viewport so the pane's scroll area cannot clip it, and closes once the word scrolls away.
   */
  function placeMenu(wi: number) {
    const word = box.querySelector<HTMLElement>(`[data-wi="${wi}"]`);
    const r = word?.getBoundingClientRect();
    const pane = box.getBoundingClientRect();
    if (!r || r.bottom < pane.top || r.top > pane.bottom) {
      menu = null;
      return;
    }
    const below = r.bottom + 4;
    menu = {
      wi,
      x: Math.min(Math.max(8, r.left), window.innerWidth - MENU_W - 8),
      y: below + MENU_H > window.innerHeight - 8 ? Math.max(8, r.top - MENU_H - 4) : below,
    };
  }

  function applyDrag(edge: Edge, wi: number) {
    const u = units[unitIndexOfWord(units, wi)];
    if (edge === 'start') onstart(Math.min(snap ? u.w0 : wi, w1), true);
    else onend(Math.max(snap ? u.w1 : wi, w0), true);
  }

  onMount(() => {
    const move = (e: PointerEvent) => {
      if (!drag) return;
      const r = box.getBoundingClientRect();
      if (e.clientY < r.top + 36) box.scrollTop -= 12;
      else if (e.clientY > r.bottom - 36) box.scrollTop += 12;
      const wi = wordFromPoint(e.clientX, e.clientY);
      if (wi !== null) applyDrag(drag, wi);
    };
    const up = () => {
      if (!drag) return;
      drag = null;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
      ondragend();
    };
    const down = (e: PointerEvent) => {
      const handle = (e.target as HTMLElement).closest<HTMLElement>('[data-edge]');
      if (!handle) return;
      e.preventDefault();
      menu = null;
      drag = handle.dataset.edge as Edge;
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
      window.addEventListener('pointercancel', up);
    };
    const click = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest('.menu') || target.closest('[data-edge]')) return;
      const word = target.closest<HTMLElement>('[data-wi]');
      if (!word) {
        menu = null;
        return;
      }
      placeMenu(Number(word.dataset.wi));
    };
    const keydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') menu = null;
    };
    const follow = () => {
      if (menu) placeMenu(menu.wi);
    };
    box.addEventListener('pointerdown', down);
    box.addEventListener('click', click);
    box.addEventListener('scroll', follow);
    window.addEventListener('keydown', keydown);
    window.addEventListener('scroll', follow);
    window.addEventListener('resize', follow);
    return () => {
      up();
      box.removeEventListener('pointerdown', down);
      box.removeEventListener('click', click);
      box.removeEventListener('scroll', follow);
      window.removeEventListener('keydown', keydown);
      window.removeEventListener('scroll', follow);
      window.removeEventListener('resize', follow);
    };
  });

  // Bring the clip start into view whenever another clip is opened.
  $effect(() => {
    void focusKey;
    menu = null;
    tick().then(() => box?.querySelector('[data-edge="start"]')?.scrollIntoView({ block: 'center' }));
  });

  // Follow the spoken word while the preview plays.
  $effect(() => {
    if (!playing || drag || currentWord < lo || currentWord > hi) return;
    box.querySelector(`[data-wi="${currentWord}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });

  async function expand(dir: -1 | 1) {
    const before = box.scrollHeight;
    onexpand(dir);
    if (dir < 0) {
      await tick();
      box.scrollTop += box.scrollHeight - before;
    }
  }

  function pick(action: () => void) {
    action();
    menu = null;
  }
</script>

<div class="pane" class:dragging={drag} bind:this={box}>
  <button class="more" onclick={() => expand(-1)}>↑ Tampilkan 30 detik sebelumnya</button>

  {#each visUnits as u (u.id)}
    <div class="unit" class:inside={u.w0 >= w0 && u.w1 <= w1} class:partial={u.w1 >= w0 && u.w0 <= w1 && !(u.w0 >= w0 && u.w1 <= w1)}>
      <button class="ts" onclick={() => onseek(u.s)} title="Putar dari sini">{fmtTime(u.s)}</button>
      <p>
        {#each range(u.w0, u.w1) as wi (wi)}
          <span class="w" class:in={wi >= w0 && wi <= w1} class:cur={wi === currentWord} data-wi={wi}
            >{#if wi === w0}<span class="mark start" data-edge="start" title="Seret untuk mengubah awal">AWAL</span>{/if}{words[wi]
              .t}{#if wi === w1}<span class="mark end" data-edge="end" title="Seret untuk mengubah akhir">AKHIR</span>{/if}</span
          >{' '}
        {/each}
      </p>
    </div>
  {/each}

  <button class="more" onclick={() => expand(1)}>↓ Tampilkan 30 detik sesudahnya</button>

  {#if menu}
    {@const wi = menu.wi}
    {@const u = units[unitIndexOfWord(units, wi)]}
    <div class="menu" style:left="{menu.x}px" style:top="{menu.y}px" style:width="{MENU_W}px">
      <div class="menu-title">“{words[wi].t}” · {fmtTime(words[wi].s, true)}</div>
      <button onclick={() => pick(() => onstart(Math.min(wi, w1), false))} disabled={wi > w1}>⟦ Mulai dari kata ini</button>
      <button onclick={() => pick(() => onend(Math.max(wi, w0), false))} disabled={wi < w0}>Akhiri di kata ini ⟧</button>
      <button onclick={() => pick(() => onstart(Math.min(u.w0, w1), false))} disabled={u.w0 > w1}>⟦ Mulai dari awal kalimat ini</button>
      <button onclick={() => pick(() => onend(Math.max(u.w1, w0), false))} disabled={u.w1 < w0}>Akhiri di akhir kalimat ini ⟧</button>
      <button onclick={() => pick(() => onplay(wi))}>▶ Putar dari sini</button>
    </div>
  {/if}
</div>

<style>
  .pane {
    position: relative;
    max-height: 420px;
    overflow-y: auto;
    padding: 6px 10px 10px;
    background: var(--panel-2);
    border-radius: var(--radius);
    line-height: 1.9;
  }
  .pane.dragging {
    cursor: grabbing;
    user-select: none;
  }
  .more {
    display: block;
    width: 100%;
    margin: 4px 0;
    padding: 4px;
    font-size: 12px;
    color: var(--muted);
    background: none;
    border: 1px dashed var(--border);
  }
  .unit {
    display: grid;
    grid-template-columns: 52px 1fr;
    gap: 8px;
    padding: 2px 6px;
    border-left: 3px solid transparent;
    border-radius: 4px;
  }
  .unit.inside {
    border-left-color: var(--accent);
    background: rgba(255, 77, 109, 0.06);
  }
  .unit.partial {
    border-left-color: rgba(255, 77, 109, 0.45);
  }
  .ts {
    align-self: start;
    margin-top: 5px;
    padding: 0 4px;
    font-size: 11px;
    line-height: 1.6;
    color: var(--muted);
    background: none;
    border: none;
    font-variant-numeric: tabular-nums;
    text-align: left;
  }
  .ts:hover {
    color: var(--text);
  }
  p {
    margin: 0;
  }
  .w {
    color: #6b7286;
    cursor: pointer;
    border-radius: 3px;
    padding: 1px 0;
  }
  .w:hover {
    background: rgba(255, 255, 255, 0.1);
  }
  .w.in {
    color: var(--text);
  }
  .w.cur {
    background: rgba(77, 171, 255, 0.35);
    color: #fff;
  }
  .mark {
    display: inline-block;
    margin: 0 4px;
    padding: 0 5px;
    font-size: 10px;
    font-weight: 800;
    line-height: 18px;
    letter-spacing: 0.04em;
    border-radius: 4px;
    cursor: grab;
    touch-action: none;
    user-select: none;
    vertical-align: 1px;
  }
  .mark.start {
    background: var(--accent);
    color: #fff;
  }
  .mark.end {
    background: var(--accent-2);
    color: #001;
  }
  .menu {
    position: fixed;
    z-index: 30;
    display: grid;
    padding: 6px;
    background: #23283a;
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    line-height: 1.3;
  }
  .menu-title {
    padding: 4px 8px 6px;
    font-size: 12px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .menu button {
    text-align: left;
    padding: 7px 8px;
    background: none;
    border: none;
    border-radius: 6px;
    font-size: 13px;
  }
  .menu button:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.08);
  }
  .menu button:disabled {
    opacity: 0.35;
  }
</style>
