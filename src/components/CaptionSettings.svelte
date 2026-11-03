<script lang="ts">
  import Segmented from './ui/Segmented.svelte';
  import Switch from './ui/Switch.svelte';
  import type { Settings } from '../lib/types';

  interface Props {
    settings: Settings;
  }
  let { settings = $bindable() }: Props = $props();

  // Each style is shown as itself: a small sample in that look, not an icon.
  const STYLES: { value: Settings['captionStyle']; name: string }[] = [
    { value: 'viral', name: 'Viral' },
    { value: 'box', name: 'Kotak' },
    { value: 'neon', name: 'Neon' },
    { value: 'classic', name: 'Klasik' },
  ];
</script>

<div class="caption-settings">
  <Switch bind:checked={settings.captionEnabled}>Tampilkan caption di video</Switch>

  {#if settings.captionEnabled}
    <div class="styles" role="radiogroup" aria-label="Gaya caption">
      {#each STYLES as s (s.value)}
        <label class="style" class:checked={settings.captionStyle === s.value}>
          <input type="radio" name="caption-style" value={s.value} bind:group={settings.captionStyle} />
          <span class="sample {s.value}" aria-hidden="true">
            <span>{settings.captionUppercase ? 'KATA' : 'Kata'}</span>
            <b>{settings.captionUppercase ? 'INI' : 'ini'}</b>
          </span>
          <span class="name">{s.name}</span>
        </label>
      {/each}
    </div>

    <div class="row">
      <span class="label">Posisi</span>
      <Segmented
        label="Posisi caption"
        bind:value={settings.captionPosition}
        options={[
          { value: 'bottom', label: 'Bawah' },
          { value: 'center', label: 'Tengah' },
          { value: 'top', label: 'Atas' },
        ]}
      />
    </div>
    <Switch bind:checked={settings.captionUppercase}>Huruf besar semua</Switch>
  {/if}
</div>

<style>
  .caption-settings {
    display: grid;
    gap: 12px;
  }
  .styles {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 6px;
  }
  .style {
    position: relative;
    display: grid;
    justify-items: center;
    gap: 6px;
    padding: 6px 6px 8px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
    box-shadow: inset 0 0 0 1px var(--border);
    cursor: pointer;
    transition:
      background-color 0.15s,
      box-shadow 0.15s;
  }
  .style:hover {
    background: var(--raised);
  }
  .style.checked {
    background: var(--accent-soft);
    box-shadow: inset 0 0 0 1px var(--accent);
  }
  .style:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  /* Samples drawn like the captions the export burns in (see CaptionOverlay). */
  .sample {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
    width: 100%;
    height: 34px;
    border-radius: var(--radius-sm);
    background: linear-gradient(160deg, #3a4150, #1d2028);
    font-family: 'Arial Black', 'Arial Bold', system-ui, sans-serif;
    font-size: 11px;
    font-weight: 900;
    color: #fff;
    text-shadow:
      1px 1px 0 #000,
      -1px 1px 0 #000,
      1px -1px 0 #000,
      -1px -1px 0 #000;
  }
  .sample b {
    font-weight: inherit;
  }
  .sample.viral b {
    color: #facc15;
  }
  .sample.box {
    text-shadow: none;
  }
  .sample.box span,
  .sample.box b {
    padding: 1px 3px;
    background: rgba(0, 0, 0, 0.75);
  }
  .sample.box b {
    color: #fde047;
    text-decoration: underline;
  }
  .sample.neon b {
    color: #22d3ee;
    text-shadow:
      1px 1px 0 #1e1b4b,
      -1px -1px 0 #1e1b4b,
      0 0 6px #22d3ee;
  }
  .sample.classic {
    font-family: system-ui, sans-serif;
    font-weight: 700;
  }
  .name {
    font-size: 12px;
    font-weight: 500;
  }
  .row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 12px;
  }
</style>
