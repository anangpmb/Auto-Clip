<script lang="ts">
  import Icon from './ui/Icon.svelte';
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
    onwordedit: (wi: number, text: string) => void;
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
    onwordedit,
  }: Props = $props();

  const MENU_W = 240;
  const MENU_H = 300;

  /** How long following stays paused after the user scrolls the transcript themselves. */
  const FOLLOW_RESUME_MS = 6000;

  let box: HTMLDivElement;
  let drag = $state<Edge | null>(null);
  let menu = $state<{ wi: number; x: number; y: number } | null>(null);
  let editingWord = $state(false);
  let wordDraft = $state('');
  let editInput = $state<HTMLInputElement>();
  /** True while the user is reading elsewhere in the transcript during playback. */
  let followPaused = $state(false);
  let resumeTimer = 0;

  const reduceMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  /**
   * Scroll only the transcript box, never the page, so `el` ends up at `ratio` of the box height.
   * (scrollIntoView would also scroll the window and push the video preview out of view.)
   */
  function scrollBoxTo(el: Element, ratio: number, smooth: boolean) {
    const pane = box.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const top = box.scrollTop + (r.top - pane.top) - ratio * (box.clientHeight - r.height);
    box.scrollTo({ top: Math.max(0, top), behavior: smooth && !reduceMotion ? 'smooth' : 'auto' });
  }

  function resumeFollow() {
    clearTimeout(resumeTimer);
    followPaused = false;
    const el = box.querySelector(`[data-wi="${currentWord}"]`);
    if (el) scrollBoxTo(el, 0.3, true);
  }

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
    editingWord = false;
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
    // Reading elsewhere during playback pauses following instead of fighting the user.
    const userScrolled = () => {
      if (!playing) return;
      followPaused = true;
      clearTimeout(resumeTimer);
      resumeTimer = window.setTimeout(() => (followPaused = false), FOLLOW_RESUME_MS);
    };
    const scrollKeys = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']);
    const keyScroll = (e: KeyboardEvent) => {
      if (scrollKeys.has(e.key)) userScrolled();
    };
    const scrollbarDown = (e: PointerEvent) => {
      if (e.target === box) userScrolled(); // a press on the box itself is its scrollbar
    };
    box.addEventListener('pointerdown', down);
    box.addEventListener('pointerdown', scrollbarDown);
    box.addEventListener('click', click);
    box.addEventListener('scroll', follow);
    box.addEventListener('wheel', userScrolled, { passive: true });
    box.addEventListener('touchmove', userScrolled, { passive: true });
    box.addEventListener('keydown', keyScroll);
    window.addEventListener('keydown', keydown);
    window.addEventListener('scroll', follow);
    window.addEventListener('resize', follow);
    return () => {
      up();
      clearTimeout(resumeTimer);
      box.removeEventListener('pointerdown', down);
      box.removeEventListener('pointerdown', scrollbarDown);
      box.removeEventListener('click', click);
      box.removeEventListener('scroll', follow);
      box.removeEventListener('wheel', userScrolled);
      box.removeEventListener('touchmove', userScrolled);
      box.removeEventListener('keydown', keyScroll);
      window.removeEventListener('keydown', keydown);
      window.removeEventListener('scroll', follow);
      window.removeEventListener('resize', follow);
    };
  });

  // Bring the clip start into view (inside the box only) whenever another clip is opened.
  $effect(() => {
    void focusKey;
    menu = null;
    tick().then(() => {
      const start = box?.querySelector('[data-edge="start"]');
      if (start) scrollBoxTo(start, 0.3, false);
    });
  });

  // Playback stopped: the next play starts following again.
  $effect(() => {
    if (!playing) {
      clearTimeout(resumeTimer);
      followPaused = false;
    }
  });

  // Follow the spoken word while the preview plays. The box only scrolls when the word
  // leaves a comfortable band, then puts it back in the upper third (lyrics-style).
  $effect(() => {
    if (!playing || followPaused || drag || currentWord < lo || currentWord > hi) return;
    const el = box.querySelector(`[data-wi="${currentWord}"]`);
    if (!el) return;
    const pane = box.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const pos = (r.top - pane.top) / Math.max(1, box.clientHeight);
    if (pos < 0.12 || pos > 0.7) scrollBoxTo(el, 0.3, true);
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

  async function beginWordEdit() {
    if (!menu) return;
    wordDraft = words[menu.wi].t;
    editingWord = true;
    await tick();
    editInput?.focus();
    editInput?.select();
  }

  function saveWordEdit() {
    const text = wordDraft.trim();
    if (!menu || !text) return;
    onwordedit(menu.wi, text);
    menu = null;
    editingWord = false;
  }
</script>

<div class="pane" class:dragging={drag} bind:this={box}>
  <button class="more" onclick={() => expand(-1)}><Icon name="arrow-up" size={14} /> Tampilkan 30 detik sebelumnya</button>

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

  <button class="more" onclick={() => expand(1)}><Icon name="arrow-down" size={14} /> Tampilkan 30 detik sesudahnya</button>

  {#if playing && followPaused}
    <button class="follow-chip" onclick={resumeFollow}>
      <Icon name="arrow-down" size={14} />
      Ikuti pemutaran
    </button>
  {/if}

  {#if menu}
    {@const wi = menu.wi}
    {@const u = units[unitIndexOfWord(units, wi)]}
    <div class="menu" style:left="{menu.x}px" style:top="{menu.y}px" style:width="{MENU_W}px">
      {#if editingWord}
        <form class="word-edit" onsubmit={(e) => { e.preventDefault(); saveWordEdit(); }}>
          <label for="transcript-word-edit">Koreksi kata · {fmtTime(words[wi].s, true)}</label>
          <input
            id="transcript-word-edit"
            bind:this={editInput}
            bind:value={wordDraft}
            aria-label="Koreksi kata transkrip"
            onkeydown={(e) => { if (e.key === 'Escape') { e.preventDefault(); editingWord = false; } }}
          />
          <div class="word-edit-actions">
            <button type="button" onclick={() => (editingWord = false)}>Batal</button>
            <button type="submit" disabled={!wordDraft.trim()}>Simpan</button>
          </div>
        </form>
      {:else}
        <div class="menu-title">“{words[wi].t}” · {fmtTime(words[wi].s, true)}</div>
        <button onclick={beginWordEdit}><Icon name="edit" size={14} /> Koreksi kata</button>
        <button onclick={() => pick(() => onstart(Math.min(wi, w1), false))} disabled={wi > w1}>Mulai dari kata ini</button>
        <button onclick={() => pick(() => onend(Math.max(wi, w0), false))} disabled={wi < w0}>Akhiri di kata ini</button>
        <button onclick={() => pick(() => onstart(Math.min(u.w0, w1), false))} disabled={u.w0 > w1}>Mulai dari awal kalimat ini</button>
        <button onclick={() => pick(() => onend(Math.max(u.w1, w0), false))} disabled={u.w1 < w0}>Akhiri di akhir kalimat ini</button>
        <button onclick={() => pick(() => onplay(wi))}><Icon name="play" size={14} /> Putar dari sini</button>
      {/if}
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
  .follow-chip {
    position: sticky;
    bottom: 8px;
    z-index: 4;
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 8px auto 0;
    padding: 8px 14px;
    min-height: 36px;
    border-radius: 999px;
    border: 0;
    background: var(--accent);
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    line-height: 1;
    box-shadow: var(--shadow-satellite);
    animation: chip-in 180ms ease-out;
  }
  .follow-chip:hover {
    background: var(--accent-hover);
  }
  @keyframes chip-in {
    from {
      opacity: 0;
      transform: translateY(6px);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .follow-chip {
      animation: none;
    }
  }
  .more {
    display: flex;
    justify-content: center;
    width: 100%;
    margin: 4px 0;
    padding: 4px;
    font-size: 12px;
    font-weight: 400;
    color: var(--muted);
    background: none;
    border: 1px dashed var(--border-strong);
  }
  .more:hover:not(:disabled) {
    background: var(--ink-1);
    color: var(--text);
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
    background: var(--accent-wash);
  }
  .unit.partial {
    border-left-color: var(--accent-line);
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
    color: var(--faint);
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
    background: rgba(249, 115, 22, 0.55);
    color: #fff;
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
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
    background: var(--raised);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-satellite);
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
    padding: 6px 8px;
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 400;
  }
  .menu button:hover:not(:disabled) {
    background: var(--ink-3);
  }
  .menu button:disabled {
    opacity: 0.35;
  }
  .word-edit {
    display: grid;
    gap: 8px;
    padding: 4px;
  }
  .word-edit label {
    font-size: 12px;
    color: var(--muted);
  }
  .word-edit input {
    width: 100%;
    min-width: 0;
  }
  .word-edit-actions {
    display: flex;
    justify-content: flex-end;
    gap: 4px;
  }
  .word-edit-actions button:last-child {
    color: var(--accent);
    font-weight: 600;
  }
</style>
