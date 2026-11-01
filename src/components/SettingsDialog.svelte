<script lang="ts">
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

<dialog bind:this={dlg} onclose={() => (open = false)}>
  <form method="dialog" class="body">
    <header>
      <h2>Pengaturan</h2>
      <button class="ghost" aria-label="Tutup">✕</button>
    </header>

    <fieldset>
      <legend>AI pemilih klip</legend>
      <label>
        Penyedia
        <select bind:value={settings.provider}>
          {#each providerIds as id (id)}
            <option value={id}>{PROVIDERS[id].label}</option>
          {/each}
        </select>
      </label>
      <label>
        API key {PROVIDERS[provider].label}
        <span class="row">
          <input
            type={showKey ? 'text' : 'password'}
            value={settings.apiKeys[provider] ?? ''}
            oninput={(e) => (settings.apiKeys[provider] = e.currentTarget.value)}
            autocomplete="off"
            spellcheck="false"
          />
          <button type="button" class="small" onclick={() => (showKey = !showKey)}>{showKey ? 'Sembunyikan' : 'Lihat'}</button>
        </span>
        <a href={PROVIDERS[provider].keyUrl} target="_blank" rel="noreferrer">Dapatkan API key ↗</a>
      </label>
      <label>
        Model
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
        <label>Durasi min (dtk) <input type="number" min="5" bind:value={settings.minSec} onchange={fixDurations} /></label>
        <label>Durasi maks (dtk) <input type="number" min="10" bind:value={settings.maxSec} onchange={fixDurations} /></label>
        <label>Jumlah klip maks <input type="number" min="1" max="30" bind:value={settings.maxClips} onchange={fixDurations} /></label>
      </div>
      <label>
        Instruksi tambahan untuk AI (opsional)
        <textarea rows="3" bind:value={settings.instructions} placeholder="Contoh: fokus ke momen lucu dan debat panas"></textarea>
      </label>
      <div class="grid3">
        <label>Jeda sebelum kata pertama (dtk) <input type="number" min="0" max="1" step="0.05" bind:value={settings.padStart} /></label>
        <label>Jeda setelah kata terakhir (dtk) <input type="number" min="0" max="1.5" step="0.05" bind:value={settings.padEnd} /></label>
      </div>
    </fieldset>

    <fieldset>
      <legend>Ekspor Video & Auto Caption</legend>
      <div class="grid2">
        <label>
          Rasio aspek default
          <select bind:value={settings.aspectRatio}>
            <option value="9:16_blur">9:16 Vertikal (Blur Background - Shorts/Reels/TikTok)</option>
            <option value="9:16_crop">9:16 Vertikal (Center Crop)</option>
            <option value="16:9">16:9 Horizontal (Asli)</option>
          </select>
        </label>
        <label>
          Gaya caption default
          <select bind:value={settings.captionStyle}>
            <option value="viral">🔥 Viral Highlight (Karaoke)</option>
            <option value="box">⬛ Modern Box</option>
            <option value="neon">✨ Neon Pop</option>
            <option value="classic">📄 Klasik Subtitle</option>
          </select>
        </label>
      </div>
      <div class="grid2">
        <label>
          Posisi caption
          <select bind:value={settings.captionPosition}>
            <option value="bottom">Bawah (Standar)</option>
            <option value="center">Tengah (Podcast)</option>
            <option value="top">Atas</option>
          </select>
        </label>
        <label class="check-label">
          <input type="checkbox" bind:checked={settings.captionUppercase} />
          <span>Format HURUF BESAR (ALL CAPS)</span>
        </label>
      </div>
    </fieldset>

    <fieldset>
      <legend>Helper</legend>
      <label>
        Alamat helper
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
    border: 1px solid var(--border);
    border-radius: 14px;
    background: var(--panel);
    color: var(--text);
  }
  dialog::backdrop {
    background: rgba(0, 0, 0, 0.6);
  }
  .body {
    display: grid;
    gap: 14px;
    padding: 18px 20px;
  }
  header,
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  footer {
    justify-content: flex-end;
  }
  h2 {
    margin: 0;
    font-size: 18px;
  }
  fieldset {
    display: grid;
    gap: 10px;
    margin: 0;
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  legend {
    padding: 0 6px;
    font-weight: 700;
    font-size: 13px;
  }
  label {
    display: grid;
    gap: 4px;
    font-size: 13px;
    color: var(--muted);
  }
  label a {
    color: var(--accent-2);
    font-size: 12px;
  }
  .row {
    display: flex;
    gap: 6px;
  }
  .row input {
    flex: 1;
  }
  .grid2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px;
    align-items: end;
  }
  .check-label {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    margin-bottom: 6px;
  }
  .grid3 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
</style>
