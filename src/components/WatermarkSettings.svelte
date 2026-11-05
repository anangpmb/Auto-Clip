<script lang="ts">
  import Segmented from './ui/Segmented.svelte';
  import Switch from './ui/Switch.svelte';
  import type { Settings } from '../lib/types';
  import type { WatermarkPosition, WatermarkSize, WatermarkStyle } from '../lib/watermark';

  interface Props {
    settings: Settings;
    /** The channel name for this video; the text field edits it for this export. */
    channel: string;
    text: string;
  }
  let { settings = $bindable(), channel, text = $bindable() }: Props = $props();

  const POSITIONS: { value: WatermarkPosition; label: string }[] = [
    { value: 'top-left', label: 'Kiri atas' },
    { value: 'top-right', label: 'Kanan atas' },
    { value: 'bottom-left', label: 'Kiri bawah' },
    { value: 'bottom-right', label: 'Kanan bawah' },
  ];
</script>

<div class="watermark-settings">
  <Switch bind:checked={settings.watermark.enabled}>Tampilkan nama channel sumber di video</Switch>

  {#if settings.watermark.enabled}
    <label class="field">
      <span class="label">Teks watermark</span>
      <input type="text" bind:value={text} placeholder={channel} maxlength="120" aria-label="Teks watermark" />
      <span class="hint">Kosongkan untuk memakai nama channel apa adanya. Biarkan kosong dan nama channel tidak ada, maka tidak ada watermark.</span>
    </label>

    <div class="row">
      <span class="label">Posisi</span>
      <div class="positions" role="radiogroup" aria-label="Posisi watermark">
        {#each POSITIONS as p (p.value)}
          <label class="pos" class:checked={settings.watermark.position === p.value}>
            <input type="radio" name="watermark-position" value={p.value} bind:group={settings.watermark.position} />
            <span>{p.label}</span>
          </label>
        {/each}
      </div>
    </div>

    <div class="row">
      <span class="label">Ukuran</span>
      <Segmented
        label="Ukuran watermark"
        bind:value={settings.watermark.size as WatermarkSize}
        options={[
          { value: 'small', label: 'Kecil' },
          { value: 'medium', label: 'Sedang' },
        ]}
      />
    </div>

    <div class="row">
      <span class="label">Gaya</span>
      <Segmented
        label="Gaya watermark"
        bind:value={settings.watermark.style as WatermarkStyle}
        options={[
          { value: 'text', label: 'Teks saja' },
          { value: 'shaded', label: 'Latar gelap' },
        ]}
      />
    </div>

    <label class="field">
      <span class="label">Opasitas: {Math.round(settings.watermark.opacity * 100)}%</span>
      <input
        type="range"
        min="0.4"
        max="0.9"
        step="0.1"
        bind:value={settings.watermark.opacity}
        aria-label="Opasitas watermark"
      />
    </label>
  {/if}
</div>

<style>
  .watermark-settings {
    display: grid;
    gap: 12px;
  }
  .field {
    display: grid;
    gap: 6px;
  }
  .label {
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
  }
  .hint {
    font-size: 12px;
    color: var(--muted);
  }
  .row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 12px;
  }
  .positions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 6px;
  }
  .pos {
    display: grid;
    place-items: center;
    min-height: 32px;
    padding: 0 8px;
    border-radius: var(--radius-md);
    background: var(--panel-2);
    box-shadow: inset 0 0 0 1px var(--border);
    font-size: 12.5px;
    cursor: pointer;
  }
  .pos:hover {
    background: var(--raised);
  }
  .pos.checked {
    background: var(--accent-wash);
    box-shadow: inset 0 0 0 1px var(--accent-line);
  }
  .pos:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .pos input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  input[type='text'] {
    min-width: 0;
  }
  input[type='range'] {
    accent-color: var(--accent);
  }
</style>
