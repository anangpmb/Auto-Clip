<script lang="ts">
  import { newId } from '../lib/ai';
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
  let copied = $state(false);
  let recent = $state(listProjects());

  const origin = location.origin;
  const command = `python autoclip_helper.py --allow-origin ${origin}`;
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

  async function copyCommand() {
    await navigator.clipboard.writeText(command);
    copied = true;
    setTimeout(() => (copied = false), 1500);
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
        {busy ? 'Mengambil transkrip…' : 'Ambil transkrip'}
      </button>
    </form>
    {#if error}<div class="error">{error}</div>{/if}
  </div>

  {#if !checking && !health?.ok}
    <div class="setup">
      {#if rejected}
        <h2>Helper berjalan, tapi menolak situs ini</h2>
        <p>Matikan helper (Ctrl+C), lalu jalankan ulang dengan izin untuk alamat situs ini:</p>
      {:else}
        <h2>Jalankan helper dulu</h2>
        <p>
          Browser tidak bisa mengambil data YouTube sendiri. Helper kecil di PC kamu yang melakukannya (pakai yt-dlp), lalu
          mengirim hasilnya ke halaman ini.
        </p>
        <ol>
          <li>Install <a href="https://www.python.org/downloads/" target="_blank" rel="noreferrer">Python 3.10+</a>, lalu jalankan <code>pip install -U "yt-dlp[default,deno]"</code></li>
          <li>
            Unduh <a href="./autoclip_helper.py" download>autoclip_helper.py</a> (juga ada di folder <code>helper/</code> repo ini).
          </li>
          <li>Di folder file itu, jalankan:</li>
        </ol>
      {/if}
      <div class="cmd">
        <code>{command}</code>
        <button class="small" onclick={copyCommand}>{copied ? 'Tersalin ✓' : 'Salin'}</button>
      </div>
      <p class="muted">
        Chrome/Edge akan meminta izin agar situs ini boleh mengakses perangkat di jaringan lokal. Pilih <b>Izinkan</b>. Halaman ini
        mengecek helper otomatis setiap beberapa detik.
      </p>
    </div>
  {/if}

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
            <button class="del" onclick={() => remove(p.id)} aria-label="Hapus proyek {p.title}" title="Hapus proyek">×</button>
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
    font-size: clamp(26px, 4vw, 38px);
    letter-spacing: -0.02em;
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
    padding: 12px 14px;
    font-size: 15px;
  }
  .setup {
    padding: 18px 20px;
    border: 1px solid rgba(251, 191, 36, 0.35);
    background: rgba(251, 191, 36, 0.06);
    border-radius: var(--radius);
  }
  .setup h2 {
    margin: 0 0 6px;
    font-size: 17px;
  }
  .setup p,
  .setup ol {
    margin: 6px 0;
    font-size: 14px;
  }
  .setup li {
    margin: 4px 0;
  }
  .setup a {
    color: var(--accent-2);
  }
  .cmd {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 10px 0;
    padding: 8px 10px;
    border-radius: 8px;
    background: #0b0d11;
    overflow-x: auto;
  }
  .cmd code {
    flex: 1;
    white-space: nowrap;
  }
  .recent h2 {
    font-size: 16px;
    margin: 0 0 10px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
  }
  .card {
    position: relative;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--panel);
    overflow: hidden;
  }
  .open {
    display: grid;
    gap: 4px;
    width: 100%;
    padding: 0 0 10px;
    background: none;
    border: none;
    text-align: left;
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
    width: 26px;
    height: 26px;
    padding: 0;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.6);
    border: none;
    font-size: 16px;
  }
  .del:hover {
    background: var(--bad);
  }
  @media (max-width: 640px) {
    form {
      flex-direction: column;
    }
  }
</style>
