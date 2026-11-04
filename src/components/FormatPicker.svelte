<script lang="ts">
  import Segmented from './ui/Segmented.svelte';
  import type { Settings } from '../lib/types';

  interface Props {
    settings: Settings;
    /** Gamer mode needs a newer helper; the option says so instead of failing later. */
    gamingReady?: boolean;
    gamingVersion?: string;
  }
  let { settings = $bindable(), gamingReady = true, gamingVersion = '' }: Props = $props();

  const FORMATS: { value: Settings['aspectRatio']; kind: string; name: string; desc: string }[] = [
    { value: '9:16_blur', kind: 'blur', name: 'Vertikal, latar blur', desc: 'Video di-crop memenuhi 2/3 tengah; latar blur mengisi atas dan bawah.' },
    { value: '9:16_crop', kind: 'crop', name: 'Vertikal, ikuti wajah', desc: 'Penuh layar; kamera otomatis mengikuti wajah.' },
    { value: '9:16_gaming', kind: 'gaming', name: 'Vertikal, mode gamer', desc: 'Gameplay di 2/3 layar, kamera wajah di 1/3 sisanya.' },
    { value: '16:9', kind: 'wide', name: 'Horizontal, asli', desc: 'Format lanskap seperti di YouTube.' },
  ];
</script>

<div class="formats" role="radiogroup" aria-label="Format video">
  {#each FORMATS as f (f.value)}
    {@const locked = f.value === '9:16_gaming' && !gamingReady}
    <label class="format" class:checked={settings.aspectRatio === f.value} class:locked>
      <input type="radio" name="format" value={f.value} bind:group={settings.aspectRatio} disabled={locked} />
      <!-- A diagram of where the picture goes in the frame -->
      <span class="thumb {f.kind}" aria-hidden="true">
        {#if f.value === '9:16_blur'}<i class="inner"></i>{/if}
        {#if f.value === '9:16_crop'}<i class="head"></i>{/if}
        {#if f.value === '9:16_gaming'}<i class="game"></i><i class="cam" class:top={settings.gamingFaceTop}><i class="head"></i></i>{/if}
      </span>
      <span class="info">
        <span class="name">{f.name}</span>
        <span class="desc">{locked ? `Butuh helper ${gamingVersion} atau lebih baru.` : f.desc}</span>
      </span>
    </label>
    {#if f.value === '9:16_gaming' && settings.aspectRatio === '9:16_gaming'}
      <div class="sub">
        <span class="label">Posisi kamera</span>
        <Segmented
          label="Posisi kamera wajah"
          bind:value={
            () => (settings.gamingFaceTop ? 'top' : 'bottom'),
            (v) => (settings.gamingFaceTop = v === 'top')
          }
          options={[
            { value: 'bottom', label: 'Bawah' },
            { value: 'top', label: 'Atas' },
          ]}
        />
      </div>
    {/if}
  {/each}
</div>

<style>
  .formats {
    display: grid;
    gap: 6px;
  }
  .format {
    position: relative;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
    box-shadow: inset 0 0 0 1px var(--border);
    cursor: pointer;
    transition:
      background-color 0.15s,
      box-shadow 0.15s;
  }
  .format:hover {
    background: var(--raised);
  }
  .format.checked {
    background: var(--accent-wash);
    box-shadow:
      inset 0 0 0 1px var(--accent-line),
      0 0 26px -16px rgba(249, 115, 22, 0.9);
  }
  .format.locked {
    cursor: not-allowed;
    opacity: 0.55;
  }
  /* The radio stays for keyboards and screen readers; the card shows the state. */
  input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .format:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .thumb {
    position: relative;
    flex: none;
    display: grid;
    place-items: center;
    width: 22px;
    height: 38px;
    margin: 0 6px;
    overflow: hidden;
    border-radius: 4px;
    background: var(--ink-4);
    box-shadow: inset 0 0 0 1.5px var(--ink-5);
  }
  .thumb.wide {
    width: 38px;
    height: 22px;
    margin: 8px 0;
  }
  .format.checked .thumb {
    box-shadow: inset 0 0 0 1.5px var(--accent);
  }
  .thumb i {
    display: block;
  }
  .inner {
    position: absolute;
    top: 16.7%;
    width: 100%;
    height: 66.7%;
    background: var(--ink-5);
  }
  .format.checked .inner,
  .format.checked .game {
    background: var(--accent);
    opacity: 0.8;
  }
  .head {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--text);
    opacity: 0.85;
  }
  .game {
    position: absolute;
    inset: 0 0 auto 0;
    height: 66.7%;
    background: var(--ink-5);
  }
  .cam {
    position: absolute;
    inset: auto 0 0 0;
    display: grid !important;
    place-items: center;
    height: 33.3%;
  }
  .cam .head {
    width: 6px;
    height: 6px;
  }
  .thumb.gaming:has(.cam.top) .game {
    inset: auto 0 0 0;
  }
  .cam.top {
    inset: 0 0 auto 0;
  }
  .info {
    display: grid;
    gap: 1px;
    min-width: 0;
  }
  .name {
    font-size: 13px;
    font-weight: 600;
  }
  .desc {
    font-size: 12px;
    color: var(--muted);
  }
  .sub {
    display: grid;
    grid-template-columns: auto minmax(0, 220px);
    align-items: center;
    gap: 12px;
    padding: 2px 12px 6px 52px;
  }
</style>
