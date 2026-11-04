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
  // The hero strip counts what is already saved here; nothing is invented.
  const totalClips = $derived(recent.reduce((n, p) => n + p.clipCount, 0));
  const lastSaved = $derived(
    recent.length
      ? new Date(Math.max(...recent.map((p) => Date.parse(p.updatedAt)))).toLocaleDateString('id-ID', {
          day: 'numeric',
          month: 'short',
        })
      : '',
  );

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
    <span class="eyebrow"><Icon name="scissors" size={13} /> Pemotong klip bertenaga AI</span>
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
    {#if recent.length}
      <div class="stats">
        <div class="stat"><b>{recent.length}</b><span>Proyek</span></div>
        <div class="stat"><b>{totalClips}</b><span>Klip</span></div>
        <div class="stat"><b>{lastSaved}</b><span>Terakhir disimpan</span></div>
      </div>
    {/if}
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
    gap: 26px;
    max-width: 1000px;
    margin: 0 auto;
  }
  /* The hero is one big pane of glass with orange light pooled behind the headline. */
  .hero {
    position: relative;
    isolation: isolate;
    display: grid;
    justify-items: center;
    gap: 14px;
    padding: 46px 30px 30px;
    border: 1px solid var(--border);
    border-radius: var(--radius-2xl);
    background: var(--glass-fill);
    box-shadow: var(--shadow-glass);
    overflow: hidden;
    text-align: center;
  }
  /* Light pools at the top of the pane and falls away down it. */
  .hero::before {
    content: '';
    position: absolute;
    inset: 0;
    z-index: -1;
    background: radial-gradient(
      780px 480px at 50% -10%,
      rgba(255, 132, 46, 0.5),
      rgba(255, 96, 16, 0.16) 56%,
      transparent 78%
    );
    pointer-events: none;
  }
  /* A specular sheen along the top edge, like light catching the rim of the glass. */
  .hero::after {
    content: '';
    position: absolute;
    inset: 0 0 auto;
    height: 1px;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 176, 120, 0.55) 32%,
      rgba(255, 255, 255, 0.8) 50%,
      rgba(255, 176, 120, 0.55) 68%,
      transparent
    );
    opacity: 0.7;
    pointer-events: none;
  }
  .eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px 5px 10px;
    border: 1px solid rgba(249, 115, 22, 0.34);
    border-radius: 999px;
    background: rgba(249, 115, 22, 0.12);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12);
    color: var(--accent-text);
    font-size: 11.5px;
    font-weight: 500;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }
  h1 {
    margin: 0;
    max-width: 22ch;
    color: #fff;
    font-size: clamp(30px, 4.8vw, 46px);
    font-weight: 600;
    letter-spacing: -0.03em;
    line-height: 1.08;
  }
  .hero p {
    margin: 0 auto;
    max-width: 60ch;
    color: var(--muted);
    font-size: 15px;
    line-height: 1.6;
    text-wrap: pretty;
  }
  /* The URL field and its button share one glass capsule. */
  form {
    display: flex;
    align-items: center;
    gap: 8px;
    max-width: 720px;
    width: 100%;
    margin: 12px auto 0;
    padding: 6px 6px 6px 16px;
    border: 1px solid var(--border-strong);
    border-radius: 18px;
    background: linear-gradient(150deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.035));
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.16),
      0 26px 60px -34px rgba(0, 0, 0, 0.95);
    backdrop-filter: blur(10px);
    transition:
      border-color 0.18s var(--ease),
      box-shadow 0.18s var(--ease);
  }
  form:focus-within {
    border-color: var(--accent);
    box-shadow:
      0 0 0 3px var(--accent-soft),
      inset 0 1px 0 rgba(255, 255, 255, 0.16);
  }
  form input {
    flex: 1;
    min-width: 0;
    padding: 8px 0;
    border: 0;
    background: transparent;
    box-shadow: none;
    font-size: 14.5px;
    text-align: left;
  }
  form input:focus {
    border-color: transparent;
    box-shadow: none;
  }
  form button {
    flex: none;
    padding: 8px 18px;
    border-radius: 13px;
  }
  .form-error {
    max-width: 720px;
    width: 100%;
    margin: 0 auto;
    text-align: left;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    width: 100%;
    max-width: 720px;
    margin: 18px auto 0;
    padding: 14px 6px;
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    background: rgba(255, 255, 255, 0.07);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.14),
      0 20px 40px -34px rgba(0, 0, 0, 0.9);
    backdrop-filter: blur(12px);
  }
  .stat {
    display: grid;
    justify-items: center;
    gap: 2px;
    padding: 0 8px;
  }
  .stat + .stat {
    border-left: 1px solid rgba(255, 255, 255, 0.08);
  }
  .stat b {
    color: #fff;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }
  .stat span {
    color: var(--muted);
    font-size: 11.5px;
  }
  .setup {
    padding: 22px 24px;
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    background: var(--glass-fill);
    box-shadow: var(--shadow-glass);
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
    box-shadow: inset 0 0 0 1px rgba(248, 113, 113, 0.24);
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
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--field);
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.35);
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
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 12px;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  .recent h2::before {
    content: '';
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 10px rgba(249, 115, 22, 0.9);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
  }
  .card {
    position: relative;
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    background: var(--glass-fill);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.12),
      0 22px 44px -34px rgba(0, 0, 0, 0.95);
    overflow: hidden;
    transition:
      transform 0.3s var(--ease),
      border-color 0.3s var(--ease),
      box-shadow 0.3s var(--ease);
  }
  .card:hover {
    transform: translateY(-3px);
    border-color: var(--accent-line);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.16),
      0 28px 56px -30px rgba(0, 0, 0, 0.95),
      0 0 26px -10px rgba(249, 115, 22, 0.45);
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
    opacity: 0.94;
    transition:
      transform 0.5s var(--ease),
      opacity 0.3s var(--ease);
  }
  .card:hover .open img {
    transform: scale(1.035);
    opacity: 1;
  }
  .open .t {
    margin-top: 10px;
    padding: 0 12px;
    font-weight: 600;
    font-size: 14px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .open .sub {
    padding: 0 12px;
    font-size: 12px;
    color: var(--muted);
  }
  .del {
    position: absolute;
    top: 8px;
    right: 8px;
    border: 1px solid var(--border);
    background: rgba(15, 10, 8, 0.72);
    backdrop-filter: blur(8px);
    opacity: 0;
    transition:
      opacity 0.18s var(--ease),
      background-color 0.18s var(--ease);
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
    .hero {
      padding: 34px 18px 22px;
      gap: 12px;
      border-radius: var(--radius-xl);
    }
    .hero p {
      font-size: 14px;
    }
    form {
      flex-direction: column;
      align-items: stretch;
      gap: 6px;
      padding: 8px;
      border-radius: 16px;
    }
    form input {
      padding: 8px 6px;
    }
    form button {
      justify-content: center;
      padding: 9px 14px;
    }
    .stats {
      padding: 12px 2px;
    }
    .stat b {
      font-size: 19px;
    }
    .setup {
      padding: 18px;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .card,
    .card:hover,
    .card:hover .open img {
      transform: none;
      transition: none;
    }
  }
</style>
