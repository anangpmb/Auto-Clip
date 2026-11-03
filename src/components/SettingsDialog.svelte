<script lang="ts">
  import Icon from './ui/Icon.svelte';
  import Switch from './ui/Switch.svelte';
  import { PROVIDERS } from '../lib/ai';
  import { DEFAULT_SETTINGS } from '../lib/storage';
  import type { ProviderId, Settings } from '../lib/types';

  interface Props {
    open: boolean;
    settings: Settings;
  }
  let { open = $bindable(), settings = $bindable() }: Props = $props();

  let dlg: HTMLDialogElement;
  let showKey = $state(false);
  const provider = $derived(settings.provider);
  const providerIds = Object.keys(PROVIDERS) as ProviderId[];

  $effect(() => {
    if (open && !dlg.open) dlg.showModal();
    else if (!open && dlg.open) dlg.close();
  });

  function fixDurations() {
    settings.minSec = Math.max(5, Math.round(settings.minSec || DEFAULT_SETTINGS.minSec));
    settings.maxSec = Math.max(settings.minSec + 5, Math.round(settings.maxSec || DEFAULT_SETTINGS.maxSec));
    settings.maxClips = Math.min(30, Math.max(1, Math.round(settings.maxClips || DEFAULT_SETTINGS.maxClips)));
  }
</script>

<dialog bind:this={dlg} onclose={() => (open = false)} aria-labelledby="settings-title">
  <form method="dialog" class="body">
    <header>
      <h2 id="settings-title">Pengaturan</h2>
      <button class="icon-btn ghost" aria-label="Tutup" title="Tutup"><Icon name="close" /></button>
    </header>

    <fieldset>
      <legend>AI pemilih klip</legend>
      <label>
        <span class="label">Penyedia</span>
        <select bind:value={settings.provider}>
          {#each providerIds as id (id)}
            <option value={id}>{PROVIDERS[id].label}</option>
          {/each}
        </select>
      </label>
      <label>
        <span class="label">API key {PROVIDERS[provider].label}</span>
        <span class="row">
          <input
            type={showKey ? 'text' : 'password'}
            value={settings.apiKeys[provider] ?? ''}
            oninput={(e) => (settings.apiKeys[provider] = e.currentTarget.value)}
            autocomplete="off"
            spellcheck="false"
          />
          <button
            type="button"
            class="icon-btn"
            onclick={() => (showKey = !showKey)}
            aria-label={showKey ? 'Sembunyikan API key' : 'Lihat API key'}
            title={showKey ? 'Sembunyikan' : 'Lihat'}
          >
            <Icon name={showKey ? 'eye-off' : 'eye'} />
          </button>
        </span>
        <a class="ext" href={PROVIDERS[provider].keyUrl} target="_blank" rel="noreferrer">
          Dapatkan API key <Icon name="external" size={12} />
        </a>
      </label>
      <label>
        <span class="label">Model</span>
        <input
          value={settings.models[provider] ?? ''}
          oninput={(e) => (settings.models[provider] = e.currentTarget.value)}
          placeholder={PROVIDERS[provider].defaultModel}
          spellcheck="false"
        />
        <span class="hint">Kosongkan untuk memakai {PROVIDERS[provider].defaultModel}.</span>
      </label>
      <p class="hint">API key hanya disimpan di browser ini dan dikirim langsung ke penyedia AI.</p>
    </fieldset>

    <fieldset>
      <legend>Klip</legend>
      <div class="grid3">
        <label><span class="label">Durasi min (dtk)</span> <input type="number" min="5" bind:value={settings.minSec} onchange={fixDurations} /></label>
        <label><span class="label">Durasi maks (dtk)</span> <input type="number" min="10" bind:value={settings.maxSec} onchange={fixDurations} /></label>
        <label><span class="label">Jumlah klip maks</span> <input type="number" min="1" max="30" bind:value={settings.maxClips} onchange={fixDurations} /></label>
      </div>
      <label>
        <span class="label">Instruksi tambahan untuk AI (opsional)</span>
        <textarea rows="3" bind:value={settings.instructions} placeholder="Contoh: fokus ke momen lucu dan debat panas"></textarea>
      </label>
      <div class="grid3">
        <label><span class="label">Jeda sebelum kata pertama (dtk)</span> <input type="number" min="0" max="1" step="0.05" bind:value={settings.padStart} /></label>
        <label><span class="label">Jeda setelah kata terakhir (dtk)</span> <input type="number" min="0" max="1.5" step="0.05" bind:value={settings.padEnd} /></label>
      </div>
    </fieldset>

    <fieldset>
      <legend>Ekspor video dan caption</legend>
      <div class="grid2">
        <label>
          <span class="label">Format default</span>
          <select bind:value={settings.aspectRatio}>
            <option value="9:16_blur">Vertikal, latar blur</option>
            <option value="9:16_crop">Vertikal, ikuti wajah</option>
            <option value="9:16_gaming">Vertikal, mode gamer</option>
            <option value="16:9">Horizontal, asli</option>
          </select>
        </label>
        <label>
          <span class="label">Gaya caption default</span>
          <select bind:value={settings.captionStyle}>
            <option value="viral">Viral (kata disorot)</option>
            <option value="box">Kotak</option>
            <option value="neon">Neon</option>
            <option value="classic">Klasik</option>
          </select>
        </label>
      </div>
      <div class="grid2">
        <label>
          <span class="label">Posisi caption</span>
          <select bind:value={settings.captionPosition}>
            <option value="bottom">Bawah</option>
            <option value="center">Tengah</option>
            <option value="top">Atas</option>
          </select>
        </label>
        <div class="switch-cell">
          <Switch bind:checked={settings.captionUppercase}>Huruf besar semua</Switch>
        </div>
      </div>
    </fieldset>

    <fieldset>
      <legend>Helper</legend>
      <label>
        <span class="label">Alamat helper</span>
        <input bind:value={settings.helperUrl} spellcheck="false" />
      </label>
    </fieldset>

    <footer>
      <button class="primary">Selesai</button>
    </footer>
  </form>
</dialog>

<style>
  dialog {
    width: min(620px, calc(100vw - 32px));
    max-height: calc(100vh - 48px);
    padding: 0;
    border: 0;
    border-radius: var(--radius-xl);
    background: var(--panel);
    color: var(--text);
    box-shadow: var(--shadow-float);
  }
  dialog::backdrop {
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(3px);
  }
  .body {
    display: grid;
    gap: 6px;
    padding: 16px 20px 18px;
  }
  header,
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  header {
    margin: 0 -4px 4px 0;
  }
  footer {
    justify-content: flex-end;
    padding-top: 10px;
  }
  h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  fieldset {
    display: grid;
    gap: 12px;
    margin: 0;
    padding: 16px 0;
    border: 0;
    border-top: 1px solid var(--border);
  }
  legend {
    float: left;
    width: 100%;
    margin: 0 0 2px;
    padding: 0;
    font-weight: 600;
    font-size: 13px;
  }
  label {
    display: grid;
    gap: 5px;
    font-size: 13px;
  }
  .row {
    display: flex;
    gap: 6px;
  }
  .row input {
    flex: 1;
    min-width: 0;
  }
  .ext {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    width: fit-content;
    font-size: 12px;
  }
  .grid2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
    align-items: end;
  }
  .switch-cell {
    display: flex;
    align-items: center;
    min-height: 34px;
  }
  .grid3 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    align-items: end;
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
</style>
