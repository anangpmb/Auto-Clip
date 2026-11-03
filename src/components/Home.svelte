<script lang="ts">
  import Icon from './ui/Icon.svelte';
  import { newId } from '../lib/ai';
  import { copyText } from '../lib/clipboard';
  import { fetchCaptions, type HelperHealth } from '../lib/helper';
  import { deleteProject, listProjects, loadProject, saveProject, saveWords } from '../lib/storage';
  import type { LoadedProject, ProjectMeta, Settings } from '../lib/types';

  interface Props {
    settings: Settings;
    health: HelperHealth | null;
    checking: boolean;
    onopen: (project: LoadedProject) => void;
  }
  let { settings, health, checking, onopen }: Props = $props();

  let url = $state('');
  let busy = $state(false);
  let error = $state('');
  let copied = $state('');
  let recent = $state(listProjects());

  const ua = navigator.userAgent;
  const isMac = /Macintosh/.test(ua);
  // Phones cannot reach a helper on the computer: 127.0.0.1 is the phone itself.
  const isMobile = /iPhone|iPad|iPod|Android/i.test(ua) || (isMac && navigator.maxTouchPoints > 1);
  const isSafari = /Safari\//.test(ua) && !/Chrome\/|Chromium\/|CriOS\/|FxiOS\/|Edg(A|iOS)?\//.test(ua);
  const isPages = location.protocol === 'https:';
  // Safari silently blocks https pages from calling http://127.0.0.1, with no permission prompt.
  const safariBlocked = !isMobile && isSafari && isPages;
  const py = isMac ? 'python3' : 'python';
  const pip = isMac ? 'pip3' : 'pip';
  const appUrl = location.origin + location.pathname.replace(/index\.html$/, '');
  const command = isPages ? `${py} autoclip_helper.py --app ${appUrl} --open` : `${py} autoclip_helper.py`;
  const installMac = `curl -fsSL ${appUrl}install-mac.sh | bash -s ${appUrl}`;
  const localUrl = $derived(`${settings.helperUrl.trim().replace(/\/+$/, '')}/`);
  const rejected = $derived(health?.error === 'origin_not_allowed');

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    if (!url.trim() || busy) return;
    busy = true;
    error = '';
    try {
      const res = await fetchCaptions(settings.helperUrl, url.trim());
      const now = new Date().toISOString();
      const meta: ProjectMeta = {
        id: newId(),
        video: res.video,
        tracks: res.tracks,
        track: res.track,
        wordTiming: res.wordTiming,
        createdAt: now,
        updatedAt: now,
      };
      saveWords(meta.id, res.words);
      saveProject(meta, []);
      onopen({ meta, words: res.words, clips: [] });
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  function open(id: string) {
    const p = loadProject(id);
    if (p) onopen(p);
    else {
      error = 'Proyek ini rusak atau sudah terhapus.';
      remove(id);
    }
  }

  function remove(id: string) {
    deleteProject(id);
    recent = listProjects();
  }

  async function copy(key: string, text: string) {
    try {
      await copyText(text);
      copied = key;
      setTimeout(() => (copied = ''), 1500);
    } catch {
      /* the command stays visible for manual copying */
    }
  }
</script>

<section class="home">
  <div class="hero">
    <h1>Potong video YouTube jadi klip pendek</h1>
    <p>Tempel link video. AI memilih momen terbaik, lalu kamu rapikan awal dan akhir tiap klip berdasarkan transkrip.</p>
    <form onsubmit={submit}>
      <input
        type="url"
        bind:value={url}
        placeholder="https://www.youtube.com/watch?v=…"
        aria-label="Link video YouTube"
        disabled={busy}
        required
      />
      <button class="primary" disabled={busy || !health?.ok}>
        <Icon name={busy ? 'loader' : 'captions'} class={busy ? 'spin' : ''} />
        {busy ? 'Mengambil transkrip…' : 'Ambil transkrip'}
      </button>
    </form>
    {#if error}<div class="notice bad form-error"><Icon name="alert" /><span>{error}</span></div>{/if}
  </div>

  {#if !checking && !health?.ok}
    <div class="setup">
      {#if isMobile}
        <div class="browser-issue">
          <h2><Icon name="info" /> Buka di komputer</h2>
          <p>
            Helper berjalan di komputer, dan HP/tablet tidak bisa menjangkaunya. Buka situs ini di komputer yang menjalankan
            helper.
          </p>
        </div>
      {:else if rejected}
        <h2><Icon name="warning" /> Helper berjalan, tapi menolak situs ini</h2>
        <p>Matikan helper (tutup jendelanya), lalu jalankan ulang dengan izin untuk alamat situs ini:</p>
        {@render cmd('run', command)}
      {:else}
        {#if safariBlocked}
          <div class="browser-issue">
            <h2><Icon name="info" /> Di Safari, pakai alamat lokal</h2>
            <p>
              Safari memblokir situs https ini untuk menghubungi helper (tanpa menampilkan permintaan izin). Kalau helper sudah
              berjalan, buka <a href={localUrl}>{localUrl}</a>. Launcher AutoClip di bawah membuka alamat itu otomatis.
            </p>
          </div>
        {/if}
        <h2><Icon name="terminal" /> Pasang helper sekali, lalu buka dengan satu klik</h2>
        <p>
          Browser tidak bisa mengambil data YouTube sendiri. Helper kecil di komputer kamu yang melakukannya (pakai yt-dlp), lalu
          mengirim hasilnya ke halaman ini.
        </p>
        {#if isMac}
          <ol>
            <li>
              Kalau belum ada, install <a href="https://www.python.org/downloads/macos/" target="_blank" rel="noreferrer">Python 3.10+</a>.
            </li>
            <li>Buka <b>Terminal</b>, lalu jalankan sekali:</li>
          </ol>
          {@render cmd('install', installMac)}
          <ol start="3">
            <li>Klik dua kali <b>AutoClip</b> di Desktop. Helper menyala dan web app langsung terbuka di browser.</li>
          </ol>
        {:else}
          <ol>
            <li>
              Kalau belum ada, install <a href="https://www.python.org/downloads/" target="_blank" rel="noreferrer">Python 3.10+</a>
              dan centang <i>Add python.exe to PATH</i>.
            </li>
            <li>
              Unduh <a href="./AutoClip.bat" download>AutoClip.bat</a> dan
              <a href="./autoclip_helper.py" download>autoclip_helper.py</a> ke folder yang sama.
            </li>
            <li>
              Klik dua kali <b>AutoClip.bat</b>. Helper menyala dan web app langsung terbuka di browser. Pertama kali, yt-dlp dipasang
              otomatis.
            </li>
          </ol>
        {/if}
        <details>
          <summary>Cara manual lewat terminal</summary>
          <p>Install yt-dlp: <code>{pip} install -U "yt-dlp[default,deno]"</code>, lalu di folder <code>autoclip_helper.py</code>:</p>
          {@render cmd('run', command)}
        </details>
        <p class="muted">
          Chrome/Edge akan meminta izin agar situs ini boleh mengakses perangkat di jaringan lokal. Pilih <b>Izinkan</b>. Halaman
          ini mengecek helper otomatis setiap beberapa detik.
        </p>
      {/if}
    </div>
  {/if}

  {#snippet cmd(key: string, text: string)}
    <div class="cmd">
      <code>{text}</code>
      <button class="small" onclick={() => copy(key, text)}>
        <Icon name={copied === key ? 'check' : 'copy'} size={14} />
        {copied === key ? 'Tersalin' : 'Salin'}
      </button>
    </div>
  {/snippet}

  {#if recent.length}
    <div class="recent">
      <h2>Proyek terakhir</h2>
      <div class="grid">
        {#each recent as p (p.id)}
          <div class="card">
            <button class="open" onclick={() => open(p.id)}>
              <img src={`https://i.ytimg.com/vi/${p.videoId}/mqdefault.jpg`} alt="" loading="lazy" />
              <span class="t">{p.title}</span>
              <span class="sub">{p.clipCount} klip · {new Date(p.updatedAt).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })}</span>
            </button>
            <button class="del icon-btn small" onclick={() => remove(p.id)} aria-label="Hapus proyek {p.title}" title="Hapus proyek">
              <Icon name="trash" size={14} />
            </button>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</section>

<style>
  .home {
    display: grid;
    gap: 28px;
    max-width: 980px;
    margin: 0 auto;
  }
  .hero {
    display: grid;
    gap: 12px;
    padding: 36px 0 8px;
    text-align: center;
  }
  h1 {
    margin: 0;
    font-size: clamp(24px, 3.6vw, 34px);
    font-weight: 650;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  .hero p {
    margin: 0 auto;
    max-width: 620px;
    color: var(--muted);
  }
  form {
    display: flex;
    gap: 8px;
    max-width: 720px;
    width: 100%;
    margin: 10px auto 0;
  }
  form input {
    flex: 1;
    padding: 9px 14px;
    font-size: 14px;
  }
  form button {
    padding-inline: 16px;
  }
  .form-error {
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    text-align: left;
  }
  .setup {
    padding: 20px 22px;
    border-radius: var(--radius-xl);
    background: var(--panel);
  }
  .setup h2 {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 600;
  }
  .setup h2 :global(.icon) {
    color: var(--warn-text);
  }
  .browser-issue {
    margin: 0 0 16px;
    padding: 12px 14px;
    border-radius: var(--radius-md);
    background: var(--bad-soft);
  }
  .browser-issue h2 :global(.icon) {
    color: var(--bad-text);
  }
  .browser-issue p {
    margin: 0;
  }
  .browser-issue a {
    font-weight: 700;
  }
  .setup p,
  .setup ol {
    margin: 6px 0;
    font-size: 14px;
  }
  .setup li {
    margin: 4px 0;
  }
  .cmd {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 10px 0;
    padding: 6px 6px 6px 12px;
    border-radius: var(--radius-md);
    background: var(--field);
    overflow-x: auto;
  }
  .cmd code {
    flex: 1;
    padding: 0;
    background: none;
    white-space: nowrap;
  }
  .cmd button {
    flex: none;
  }
  details {
    margin: 10px 0 6px;
    font-size: 14px;
  }
  summary {
    cursor: pointer;
    color: var(--muted);
  }
  .recent h2 {
    font-size: 14px;
    font-weight: 600;
    margin: 0 0 10px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
  }
  .card {
    position: relative;
    border-radius: var(--radius-lg);
    background: var(--panel);
    overflow: hidden;
    transition: background-color 0.15s;
  }
  .card:hover {
    background: var(--panel-2);
  }
  .open {
    display: grid;
    gap: 4px;
    width: 100%;
    padding: 0 0 10px;
    background: none;
    border: none;
    border-radius: 0;
    text-align: left;
    font-weight: 400;
  }
  .open:hover:not(:disabled) {
    background: none;
  }
  .open:active:not(:disabled) {
    transform: none;
  }
  .open img {
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    background: var(--panel-2);
  }
  .open .t {
    padding: 0 10px;
    font-weight: 600;
    font-size: 14px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .open .sub {
    padding: 0 10px;
    font-size: 12px;
    color: var(--muted);
  }
  .del {
    position: absolute;
    top: 6px;
    right: 6px;
    border: none;
    background: rgba(0, 0, 0, 0.65);
    opacity: 0;
    transition: opacity 0.15s;
  }
  .card:hover .del,
  .del:focus-visible {
    opacity: 1;
  }
  .del:hover:not(:disabled) {
    background: var(--bad);
  }
  .del:hover :global(.icon) {
    color: #fff;
  }
  @media (hover: none) {
    .del {
      opacity: 1;
    }
  }
  @media (max-width: 640px) {
    form {
      flex-direction: column;
    }
  }
</style>
