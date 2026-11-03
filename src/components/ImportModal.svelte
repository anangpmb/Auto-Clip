<script lang="ts">
  import Icon from './ui/Icon.svelte';
  import Modal from './ui/Modal.svelte';
  import Switch from './ui/Switch.svelte';
  import { downloadFile } from '../lib/captions';
  import { copyText } from '../lib/clipboard';
  import { externalPrompts, parseClipText, placeClips } from '../lib/importClips';
  import { clipBounds, durationStatus, fmtDuration, fmtTime } from '../lib/transcript';
  import type { Clip, Settings, Unit, Word } from '../lib/types';

  interface Props {
    words: Word[];
    units: Unit[];
    settings: Settings;
    videoTitle: string;
    /** How many clips the project has; importing can add to them or replace them. */
    existing: number;
    onimport: (clips: Clip[], mode: 'replace' | 'append') => void;
    onclose: () => void;
  }
  let { words, units, settings, videoTitle, existing, onimport, onclose }: Props = $props();

  const prompts = $derived(externalPrompts(units, settings, videoTitle));
  const chars = $derived(prompts.reduce((n, p) => n + p.length, 0));
  let copied = $state(-1);

  let text = $state('');
  let fileName = $state('');
  let fitChoice = $state<boolean | null>(null);
  const raw = $derived(parseClipText(text));
  // Answers to the prompt (sentence numbers) are fitted like the in-app AI's; exact times are kept.
  const fit = $derived(fitChoice ?? (raw.length > 0 && raw.every((r) => r.kind === 'ids')));
  const result = $derived(placeClips(raw, words, units, { fit, minSec: settings.minSec, maxSec: settings.maxSec }));
  const safeTitle = $derived(videoTitle.replace(/[\\/:*?"<>|]+/g, '').trim().slice(0, 60) || 'video');

  async function copy(i: number) {
    try {
      await copyText(prompts[i]);
      copied = i;
      setTimeout(() => (copied = -1), 1800);
    } catch {
      download(i); // clipboard blocked: the file still gets the prompt across
    }
  }

  function download(i: number) {
    const part = prompts.length > 1 ? ` (bagian ${i + 1})` : '';
    downloadFile(`Prompt klip - ${safeTitle}${part}.txt`, prompts[i], 'text/plain;charset=utf-8');
  }

  async function pickFile(input: HTMLInputElement) {
    const file = input.files?.[0];
    if (!file) return;
    fileName = file.name;
    text = await file.text();
    fitChoice = null;
    input.value = '';
  }

  const bounds = (c: Clip) => clipBounds(words, c.w0, c.w1, settings.padStart, settings.padEnd);
</script>

<Modal title="Impor klip" width={760} {onclose}>
  {#snippet subtitle()}Pilih momen dengan AI apa saja di luar app ini, lalu tempel hasilnya di sini{/snippet}

  <div class="steps">
    <section class="step">
      <span class="n" aria-hidden="true">1</span>
      <div class="step-body">
        <h3 class="group-title">Minta AI lain memilih momen</h3>
        <p class="hint">
          Salin prompt ini, lalu tempel ke ChatGPT, Claude, Gemini, atau AI lain. Isinya aturan memilih klip (durasi {settings.minSec}–{settings.maxSec}
          dtk, maks {settings.maxClips} klip, plus instruksi tambahan dari Pengaturan) dan transkrip bernomor. Tidak perlu API key.
        </p>
        {#each prompts as _, i (i)}
          <div class="prompt-row">
            {#if prompts.length > 1}<span class="part">Bagian {i + 1} dari {prompts.length}</span>{/if}
            <button class="small" onclick={() => copy(i)}>
              <Icon name={copied === i ? 'check' : 'copy'} size={14} />
              {copied === i ? 'Disalin' : 'Salin prompt'}
            </button>
            <button class="small ghost" onclick={() => download(i)}><Icon name="download" size={14} /> Unduh .txt</button>
          </div>
        {/each}
        <p class="hint">
          {chars.toLocaleString('id-ID')} karakter (±{Math.round(chars / 4).toLocaleString('id-ID')} token).
          {prompts.length > 1
            ? 'Transkripnya panjang, jadi dibagi: kirim tiap bagian di chat terpisah, lalu tempel semua jawabannya di bawah.'
            : 'Kalau chat-nya menolak teks sepanjang ini, unduh .txt lalu lampirkan sebagai file.'}
        </p>
      </div>
    </section>

    <section class="step">
      <span class="n" aria-hidden="true">2</span>
      <div class="step-body">
        <div class="paste-head">
          <h3 class="group-title"><label for="import-text">Tempel jawabannya</label></h3>
          <label class="file-btn">
            <Icon name="upload" size={14} /> Pilih file
            <input type="file" accept=".json,.txt,application/json,text/plain" onchange={(e) => pickFile(e.currentTarget)} />
          </label>
        </div>
        <textarea
          id="import-text"
          rows="7"
          bind:value={text}
          oninput={() => {
            fitChoice = null;
            fileName = '';
          }}
          spellcheck="false"
          placeholder={'{"clips":[{"start_id":12,"end_id":18,"title":"…"}]}\n\natau JSON dengan "start"/"end" (detik atau 1:23), atau baris seperti:\n1:23 - 2:10 Judul klip'}
        ></textarea>
        <p class="hint">
          {fileName ? `Dari ${fileName}. ` : ''}Bisa juga file dari <b>Unduh JSON</b> app ini, atau daftar buatan sendiri.
        </p>

        {#if text.trim()}
          {#if result.clips.length}
            <div class="found">
              <div class="found-head">
                <span class="badge ok">{result.clips.length} klip terbaca</span>
                <Switch bind:checked={() => fit, (v) => (fitChoice = v)}>
                  Rapikan ke kalimat dan durasi {settings.minSec}–{settings.maxSec} dtk
                </Switch>
              </div>
              <ol class="clips">
                {#each result.clips as c, i (c.id)}
                  {@const b = bounds(c)}
                  {@const st = durationStatus(b.end - b.start, settings.minSec, settings.maxSec)}
                  <li>
                    <span class="ci">{i + 1}</span>
                    <span class="ct">{c.title}</span>
                    <span class="cm">{fmtTime(b.start)}–{fmtTime(b.end)} · <span class="dur {st}">{fmtDuration(b.end - b.start)}</span></span>
                  </li>
                {/each}
              </ol>
            </div>
          {:else}
            <div class="notice warn">
              <Icon name="warning" />
              <span>Belum ada klip yang terbaca. Pastikan jawabannya berisi JSON seperti contoh, atau baris "awal - akhir judul".</span>
            </div>
          {/if}
          {#if result.skipped.length}
            <div class="notice warn">
              <Icon name="warning" />
              <span>
                {result.skipped.length} klip dilewati:
                {#each result.skipped as s (s)}<br />{s}{/each}
              </span>
            </div>
          {/if}
        {/if}
      </div>
    </section>
  </div>

  {#snippet footer()}
    <button class="ghost" onclick={onclose}>Batal</button>
    {#if existing}
      <button onclick={() => onimport(result.clips, 'append')} disabled={!result.clips.length}>
        <Icon name="plus" /> Tambahkan ke {existing} klip
      </button>
    {/if}
    <button class="primary" onclick={() => onimport(result.clips, 'replace')} disabled={!result.clips.length}>
      <Icon name="upload" />
      {existing ? 'Ganti semua klip' : `Impor ${result.clips.length || ''} klip`}
    </button>
  {/snippet}
</Modal>

<style>
  .steps {
    display: grid;
    gap: 22px;
  }
  .step {
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr);
    gap: 12px;
  }
  .n {
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--accent-soft);
    color: var(--accent-text);
    font-size: 12px;
    font-weight: 700;
  }
  .step-body {
    display: grid;
    gap: 10px;
    min-width: 0;
  }
  .step-body .group-title {
    line-height: 24px;
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .prompt-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .part {
    min-width: 120px;
    font-size: 12.5px;
    font-weight: 500;
  }
  .paste-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .file-btn {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--raised);
    font-size: 12px;
    font-weight: 500;
    line-height: 18px;
    cursor: pointer;
  }
  .file-btn:hover {
    background: var(--raised-hover);
  }
  .file-btn:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .file-btn input {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }
  .file-btn :global(.icon) {
    color: var(--icon);
  }
  textarea {
    width: 100%;
    resize: vertical;
    font-family: ui-monospace, 'SF Mono', 'Cascadia Code', Consolas, monospace;
    font-size: 12px;
  }
  .found {
    display: grid;
    gap: 8px;
  }
  .found-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px 12px;
  }
  .clips {
    display: grid;
    gap: 2px;
    max-height: 240px;
    overflow-y: auto;
    margin: 0;
    padding: 4px;
    border-radius: var(--radius-lg);
    background: var(--panel-2);
    list-style: none;
  }
  .clips li {
    display: grid;
    grid-template-columns: 22px minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    font-size: 13px;
  }
  .clips li:hover {
    background: var(--ink-2);
  }
  .ci {
    font-size: 12px;
    color: var(--faint);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .ct {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }
  .cm {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .dur.ok {
    color: var(--ok-text);
  }
  .dur.short,
  .dur.long {
    color: var(--warn-text);
  }
</style>
