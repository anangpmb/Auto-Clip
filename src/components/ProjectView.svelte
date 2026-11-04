<script lang="ts">
  import { untrack } from 'svelte';
  import BulkExportModal from './BulkExportModal.svelte';
  import ClipEditor from './ClipEditor.svelte';
  import ExportModal from './ExportModal.svelte';
  import ImportModal from './ImportModal.svelte';
  import Icon from './ui/Icon.svelte';
  import Menu from './ui/Menu.svelte';
  import type { Clip, LoadedProject, Settings } from '../lib/types';
  import {
    buildUnits,
    clipBounds,
    durationStatus,
    fmtDuration,
    fmtTime,
    joinWords,
    remapClip,
    unitIndexOfWord,
    unitsSpanFrom,
    wordIndexAt,
  } from '../lib/transcript';
  import { findClips, newId, PROVIDERS } from '../lib/ai';
  import { copyText } from '../lib/clipboard';
  import { fetchCaptions, type HelperHealth } from '../lib/helper';
  import { saveProject, saveWords } from '../lib/storage';
  import { downloadFile, generateSrt } from '../lib/captions';
  import { inSourceOrder, scenesOf, sceneStarts, SHORTS_SECONDS } from '../lib/compilation';

  interface Props {
    initial: LoadedProject;
    settings: Settings;
    helperOk: boolean;
    helperHealth?: HelperHealth | null;
    onclose: () => void;
    onsettings: () => void;
  }
  let { initial, settings = $bindable(), helperOk, helperHealth = null, onclose, onsettings }: Props = $props();

  // The parent remounts this view per project, so the initial value is all we need.
  let meta = $state(untrack(() => initial.meta));
  let words = $state.raw(untrack(() => initial.words));
  let clips = $state(untrack(() => initial.clips));
  let selectedId = $state<string | null>(untrack(() => initial.clips[0]?.id ?? null));
  let showExportModal = $state(false);
  /** Clip ids joined into one highlight video, in play order. */
  let compilation = $state<string[]>(untrack(() => initial.compilation ?? []));
  let showCompilation = $state(false);
  let showBulk = $state(false);
  let showImport = $state(false);

  const units = $derived(buildUnits(words));
  const selected = $derived(clips.find((c) => c.id === selectedId) ?? null);
  const compClips = $derived(compilation.map((id) => clips.find((c) => c.id === id)).filter((c): c is Clip => !!c));
  const compTotal = $derived.by(() => {
    const scenes = scenesOf(words, compClips, settings.padStart, settings.padEnd);
    return sceneStarts(scenes)[scenes.length];
  });

  let playerTime = 0;
  let aiBusy = $state(false);
  let aiStatus = $state('');
  let error = $state('');
  let toast = $state('');
  let trackBusy = $state(false);
  let controller: AbortController | null = null;

  let saveTimer = 0;
  $effect(() => {
    const m = $state.snapshot(meta);
    const c = $state.snapshot(clips);
    const comp = $state.snapshot(compilation);
    clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
      try {
        saveProject(m, c, comp);
      } catch (e) {
        flash((e as Error).message);
      }
    }, 400);
  });

  let toastTimer = 0;
  function flash(message: string) {
    toast = message;
    clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => (toast = ''), 2500);
  }

  function updateClip(c: Clip) {
    clips = clips.map((x) => (x.id === c.id ? c : x));
  }

  function updateWord(wi: number, text: string) {
    words = words.map((word, i) => (i === wi ? { ...word, t: text } : word));
    try {
      saveWords(meta.id, words);
      saveProject(meta, clips, compilation);
      flash('Kata transkrip diperbarui');
    } catch (e) {
      flash((e as Error).message);
    }
  }

  function deleteClip(id: string) {
    const i = clips.findIndex((c) => c.id === id);
    clips = clips.filter((c) => c.id !== id);
    compilation = compilation.filter((x) => x !== id);
    if (selectedId === id) selectedId = clips[Math.min(i, clips.length - 1)]?.id ?? null;
  }

  /** Clips chosen by an AI outside the app (or by hand), pasted in from the import dialog. */
  function importClips(found: Clip[], mode: 'replace' | 'append') {
    if (mode === 'replace') {
      clips = found;
      compilation = [];
    } else {
      clips = [...clips, ...found].sort((a, b) => a.w0 - b.w0);
    }
    selectedId = found[0]?.id ?? selectedId;
    showImport = false;
    flash(`${found.length} klip diimpor`);
  }

  function toggleInCompilation(id: string) {
    compilation = compilation.includes(id) ? compilation.filter((x) => x !== id) : [...compilation, id];
  }

  function moveScene(id: string, dir: -1 | 1) {
    const i = compilation.indexOf(id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= compilation.length) return;
    const next = [...compilation];
    [next[i], next[j]] = [next[j], next[i]];
    compilation = next;
  }

  function removeScene(id: string) {
    compilation = compilation.filter((x) => x !== id);
    if (!compilation.length) showCompilation = false;
  }

  function editScene(id: string) {
    showCompilation = false;
    selectedId = id;
  }

  function addManualClip() {
    const u = unitIndexOfWord(units, Math.max(0, wordIndexAt(words, playerTime)));
    const e = unitsSpanFrom(units, u, (settings.minSec + settings.maxSec) / 2);
    const clip: Clip = {
      id: newId(),
      title: `Klip manual ${clips.length + 1}`,
      reason: '',
      score: 0,
      w0: units[u].w0,
      w1: units[e].w1,
      aiW0: null,
      aiW1: null,
    };
    clips = [...clips, clip].sort((a, b) => a.w0 - b.w0);
    selectedId = clip.id;
  }

  async function runAI() {
    if (!(settings.apiKeys[settings.provider] ?? '').trim()) {
      onsettings();
      return;
    }
    const ask = compilation.length
      ? 'Ganti semua klip yang ada dengan hasil AI yang baru? Kompilasi highlight juga dikosongkan.'
      : 'Ganti semua klip yang ada dengan hasil AI yang baru?';
    if (clips.length && !confirm(ask)) return;
    aiBusy = true;
    error = '';
    aiStatus = 'Menyiapkan…';
    const ctrl = new AbortController();
    controller = ctrl;
    try {
      const found = await findClips(words, units, $state.snapshot(settings), {
        title: meta.video.title,
        signal: ctrl.signal,
        onProgress: (m) => (aiStatus = m),
      });
      clips = found;
      compilation = [];
      selectedId = found[0]?.id ?? null;
      if (!found.length) error = 'AI tidak menemukan klip yang cocok. Coba ubah durasi atau instruksi tambahan di Pengaturan.';
    } catch (e) {
      if (!ctrl.signal.aborted) error = (e as Error).message;
    } finally {
      aiBusy = false;
      controller = null;
    }
  }

  async function changeTrack(select: HTMLSelectElement) {
    const key = select.value;
    if (key === meta.track) return;
    trackBusy = true;
    error = '';
    try {
      const res = await fetchCaptions(settings.helperUrl, meta.video.url, key);
      const newUnits = buildUnits(res.words);
      clips = clips.map((c) => remapClip(words, res.words, newUnits, c));
      words = res.words;
      meta.track = res.track;
      meta.tracks = res.tracks;
      meta.wordTiming = res.wordTiming;
      saveWords(meta.id, res.words);
    } catch (e) {
      error = (e as Error).message;
      select.value = meta.track;
    } finally {
      trackBusy = false;
    }
  }

  const boundsOf = (c: Clip) => clipBounds(words, c.w0, c.w1, settings.padStart, settings.padEnd);
  const safeName = (s: string) =>
    s
      .replace(/[\\/:*?"<>|%]+/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 80) || 'klip';

  async function copy(text: string, label: string) {
    try {
      await copyText(text);
      flash(`${label} disalin`);
    } catch {
      flash('Gagal menyalin ke clipboard');
    }
  }

  function copyList() {
    const text = clips
      .map((c, i) => {
        const b = boundsOf(c);
        return `${i + 1}. ${c.title}\n   ${fmtTime(b.start, true)} – ${fmtTime(b.end, true)} (${fmtDuration(b.end - b.start)})\n   https://youtu.be/${meta.video.id}?t=${Math.floor(b.start)}`;
      })
      .join('\n\n');
    copy(text, 'Daftar klip');
  }

  function copyYtDlp() {
    const text = clips
      .map((c, i) => {
        const b = boundsOf(c);
        const name = `${String(i + 1).padStart(2, '0')} - ${safeName(c.title)}`;
        return `yt-dlp --download-sections "*${b.start.toFixed(2)}-${b.end.toFixed(2)}" --force-keyframes-at-cuts -o "${name}.%(ext)s" "https://www.youtube.com/watch?v=${meta.video.id}"`;
      })
      .join('\n');
    copy(text, 'Perintah yt-dlp');
  }

  function downloadJson() {
    const data = {
      video: meta.video,
      track: meta.track,
      clips: clips.map((c, i) => {
        const b = boundsOf(c);
        return {
          n: i + 1,
          title: c.title,
          reason: c.reason,
          score: c.score,
          start: +b.start.toFixed(2),
          end: +b.end.toFixed(2),
          duration: +(b.end - b.start).toFixed(2),
          text: joinWords(words, c.w0, c.w1),
        };
      }),
    };
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    a.download = `${safeName(meta.video.title)} - klip.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function downloadSelectedSrt() {
    if (!selected) return;
    const b = boundsOf(selected);
    const clipWords = words.slice(selected.w0, selected.w1 + 1);
    const srt = generateSrt(clipWords, b.start, b.end, { uppercase: settings.captionUppercase });
    downloadFile(`${safeName(selected.title)}.srt`, srt, 'text/plain;charset=utf-8');
    flash('File .srt berhasil diunduh');
  }
</script>

<section class="project">
  <div class="bar">
    <button class="ghost back" onclick={onclose}><Icon name="back" /> Proyek</button>
    {#if meta.video.thumbnail}<img class="thumb" src={meta.video.thumbnail} alt="" />{/if}
    <div class="info">
      <h1 title={meta.video.title}>{meta.video.title}</h1>
      <p>{meta.video.channel} · {fmtTime(meta.video.duration)} · {words.length.toLocaleString('id-ID')} kata</p>
    </div>
    <label class="track">
      <span class="label">Transkrip</span>
      <select value={meta.track} onchange={(e) => changeTrack(e.currentTarget)} disabled={trackBusy || !helperOk}>
        {#each meta.tracks as t (t.key)}
          <option value={t.key}>{t.name} · {t.kind === 'auto' ? 'otomatis' : 'manual'}</option>
        {/each}
      </select>
    </label>
  </div>

  {#if meta.wordTiming === 'estimated'}
    <div class="notice warn">
      <Icon name="warning" />
      <span>
        Transkrip ini dari subtitle manual, jadi waktu per kata hanya perkiraan. Kalau ada pilihan "otomatis", potongannya biasanya
        lebih presisi.
      </span>
    </div>
  {/if}

  <div class="actions">
    {#if aiBusy}
      <span class="busy"><Icon name="loader" class="spin" /> {aiStatus}</span>
      <button onclick={() => controller?.abort()}>Batal</button>
    {:else}
      <button class="primary" onclick={runAI}>
        <Icon name="search" />
        {clips.length ? 'Cari ulang dengan AI' : 'Cari klip dengan AI'}
      </button>
      <button onclick={() => (showImport = true)} title="Tempel klip yang dipilih AI lain (ChatGPT, Claude, Gemini) atau file JSON">
        <Icon name="upload" /> Impor klip
      </button>
      <span class="muted">{PROVIDERS[settings.provider].label} · {settings.minSec}–{settings.maxSec} dtk · maks {settings.maxClips} klip</span>
    {/if}
    <span class="spacer"></span>
    {#if clips.length}
      <button onclick={() => (showBulk = true)} title="Render beberapa klip sekaligus">
        <Icon name="bulk" /> Ekspor massal
      </button>
      <Menu
        label="Lainnya"
        items={[
          { label: 'Unduh caption klip ini (.srt)', icon: 'file', onclick: downloadSelectedSrt, disabled: !selected },
          { label: 'Salin daftar klip', icon: 'copy', onclick: copyList },
          { label: 'Salin perintah yt-dlp', icon: 'terminal', onclick: copyYtDlp },
          { label: 'Unduh JSON', icon: 'download', onclick: downloadJson },
        ]}
      />
    {/if}
  </div>

  {#if error}<div class="notice bad"><Icon name="alert" /><span>{error}</span></div>{/if}

  {#if clips.length}
    <div class="workspace">
      <aside class="list" aria-label="Klip">
        <section class="comp" class:filled={compClips.length > 0} aria-labelledby="comp-title">
          <div class="comp-head">
            <h2 id="comp-title"><Icon name="film" /> Kompilasi highlight</h2>
            {#if compClips.length}
              <span class="comp-meta" class:over={compTotal > SHORTS_SECONDS}>
                {compClips.length} adegan · {fmtDuration(compTotal)}
              </span>
            {/if}
          </div>
          {#if compClips.length}
            <button class="primary comp-open" onclick={() => (showCompilation = true)}>
              <Icon name="clapperboard" /> Atur, Pratinjau & Ekspor
            </button>
          {:else}
            <p class="comp-hint">
              Gabungkan beberapa klip jadi satu video. Tekan
              <span class="chip-sample" aria-hidden="true"><Icon name="layers" size={12} />+</span> di klip, sesuai urutan tayangnya.
            </p>
          {/if}
        </section>

        {#each clips as c, i (c.id)}
          {@const b = boundsOf(c)}
          {@const st = durationStatus(b.end - b.start, settings.minSec, settings.maxSec)}
          {@const edited = c.aiW0 !== null && (c.w0 !== c.aiW0 || c.w1 !== c.aiW1)}
          {@const scene = compilation.indexOf(c.id)}
          <div class="item" class:active={c.id === selectedId}>
            <button class="pick" onclick={() => (selectedId = c.id)} aria-current={c.id === selectedId ? 'true' : undefined}>
              <span class="n">{i + 1}</span>
              <span class="body">
                <span class="t">{c.title}</span>
                <span class="sub">
                  {fmtTime(b.start)}–{fmtTime(b.end)} · <span class="dur {st}">{fmtDuration(b.end - b.start)}</span>
                  {#if c.score}· skor {c.score}{/if}
                  {#if edited}<span class="badge accent">diedit</span>{/if}
                </span>
                <span class="snip">“{joinWords(words, c.w0, Math.min(c.w1, c.w0 + 9))}…”</span>
              </span>
            </button>
            <div class="tools">
              <button
                class="icon-btn small ghost danger"
                onclick={() => deleteClip(c.id)}
                aria-label="Hapus klip {i + 1}"
                title="Hapus klip"><Icon name="trash" size={14} /></button
              >
              <button
                class="in-comp"
                class:on={scene >= 0}
                onclick={() => toggleInCompilation(c.id)}
                aria-pressed={scene >= 0}
                aria-label="Masukkan klip {i + 1} ke kompilasi"
                title={scene >= 0 ? `Adegan ${scene + 1} di kompilasi. Tekan untuk mengeluarkan.` : 'Masukkan ke kompilasi'}
              >
                <Icon name="layers" size={13} />
                {#if scene >= 0}{scene + 1}{:else}+{/if}
              </button>
            </div>
          </div>
        {/each}
        <button class="add" onclick={addManualClip}><Icon name="plus" /> Tambah klip manual</button>
      </aside>

      <div class="panel">
        {#if selected}
          <ClipEditor
            {words}
            {units}
            clip={selected}
            videoId={meta.video.id}
            videoUrl={meta.video.url}
            videoTitle={meta.video.title}
            bind:settings
            {helperOk}
            {helperHealth}
            onchange={updateClip}
            onwordedit={updateWord}
            ontime={(t) => (playerTime = t)}
          />
        {:else}
          <p class="muted">Pilih klip di sebelah kiri.</p>
        {/if}
      </div>
    </div>
  {:else if !aiBusy}
    <div class="empty">
      <Icon name="scissors" size={20} />
      <h2>Transkrip siap</h2>
      <p>
        Tekan <b>Cari klip dengan AI</b> untuk mendapatkan saran potongan, lalu rapikan awal dan akhirnya lewat timeline dan transkrip.
        Tidak punya API key? Pakai <b>Impor klip</b>: salin prompt ke ChatGPT, Claude, atau Gemini, lalu tempel jawabannya. Kamu juga
        bisa membuat klip sendiri.
      </p>
      <div class="empty-actions">
        <button onclick={() => (showImport = true)}><Icon name="upload" /> Impor klip</button>
        <button onclick={addManualClip}><Icon name="plus" /> Tambah klip manual</button>
      </div>
    </div>
  {/if}

  {#if showCompilation && compClips.length}
    <ExportModal
      clips={compClips}
      compilation
      {words}
      videoUrl={meta.video.url}
      videoId={meta.video.id}
      videoTitle={meta.video.title}
      bind:settings
      {helperOk}
      {helperHealth}
      onclose={() => (showCompilation = false)}
      onmove={moveScene}
      onremove={removeScene}
      onedit={editScene}
      onsort={() => (compilation = inSourceOrder(compilation, clips))}
    />
  {/if}

  {#if showExportModal && selected}
    <ExportModal
      clips={[selected]}
      {words}
      videoUrl={meta.video.url}
      videoId={meta.video.id}
      videoTitle={meta.video.title}
      bind:settings
      {helperOk}
      {helperHealth}
      onclose={() => (showExportModal = false)}
    />
  {/if}

  {#if showImport}
    <ImportModal
      {words}
      {units}
      {settings}
      videoTitle={meta.video.title}
      existing={clips.length}
      onimport={importClips}
      onclose={() => (showImport = false)}
    />
  {/if}

  {#if showBulk}
    <BulkExportModal
      {clips}
      {words}
      videoUrl={meta.video.url || `https://www.youtube.com/watch?v=${meta.video.id}`}
      videoId={meta.video.id}
      videoTitle={meta.video.title}
      bind:settings
      {helperOk}
      {helperHealth}
      onclose={() => (showBulk = false)}
    />
  {/if}

  {#if toast}<div class="toast" role="status"><Icon name="check" size={14} /> {toast}</div>{/if}
</section>

<style>
  .project {
    display: grid;
    /* Long nowrap titles must ellipsize, not widen the page past the screen. */
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .back {
    flex: none;
  }
  .thumb {
    width: 88px;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--field);
  }
  .info {
    flex: 1;
    min-width: 0;
  }
  h1 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .info p {
    margin: 2px 0 0;
    color: var(--muted);
    font-size: 12.5px;
  }
  .track {
    display: grid;
    gap: 3px;
  }
  .track select {
    max-width: 260px;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .busy {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }
  .busy :global(.icon) {
    color: var(--accent-text);
  }
  .spacer {
    flex: 1;
  }
  .workspace {
    display: grid;
    grid-template-columns: 320px minmax(0, 1fr);
    gap: 14px;
    align-items: start;
  }
  .list {
    display: grid;
    gap: 8px;
    position: sticky;
    /* Clears the floating header: 12px offset + ~60px bar + breathing room. */
    top: 92px;
    max-height: calc(100vh - 112px);
    overflow-y: auto;
    padding-right: 4px;
  }
  .item {
    position: relative;
    display: flex;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: rgba(255, 255, 255, 0.04);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.07);
    transition:
      background-color 0.18s var(--ease),
      border-color 0.18s var(--ease),
      box-shadow 0.18s var(--ease);
  }
  .item:hover {
    background: rgba(255, 255, 255, 0.075);
    border-color: var(--border-strong);
  }
  .item.active {
    background: var(--accent-wash);
    border-color: var(--accent-line);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.1),
      0 0 24px -14px rgba(249, 115, 22, 0.8);
  }
  /* A lit bar on the left edge marks the clip being edited. */
  .item.active::before {
    content: '';
    position: absolute;
    top: 12px;
    bottom: 12px;
    left: 0;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: var(--accent-grad);
    box-shadow: 0 0 12px rgba(249, 115, 22, 0.75);
  }
  .pick {
    flex: 1;
    display: flex;
    gap: 10px;
    align-items: flex-start;
    text-align: left;
    background: none;
    border: none;
    padding: 12px;
    min-width: 0;
  }
  .pick:hover:not(:disabled) {
    background: none;
  }
  .pick:active:not(:disabled) {
    transform: none;
  }
  .n {
    flex: none;
    width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: var(--ink-3);
    font-size: 11.5px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .item.active .n {
    background: var(--accent);
    color: #fff;
  }
  .body {
    display: grid;
    gap: 3px;
    min-width: 0;
  }
  .t {
    font-weight: 600;
    font-size: 13.5px;
    line-height: 1.35;
  }
  .sub {
    font-size: 12px;
    color: var(--muted);
    font-weight: 400;
  }
  .dur.ok {
    color: var(--ok-text);
  }
  .dur.short,
  .dur.long {
    color: var(--warn-text);
  }
  .sub .badge {
    height: 18px;
    margin-left: 4px;
    vertical-align: 1px;
  }
  .snip {
    font-size: 12px;
    font-weight: 400;
    color: var(--faint);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tools {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    padding: 8px 8px 10px 0;
  }
  .tools :global(.icon-btn .icon) {
    color: var(--faint);
  }
  /* Numbered like a photo picker: the number is the scene's place in the compilation.
     Square and in the accent, so it never reads as the clip's own (round) number. */
  .in-comp {
    gap: 3px;
    justify-content: center;
    min-width: 40px;
    height: 26px;
    padding: 0 7px;
    border-radius: 7px;
    border: 1px dashed var(--ink-5);
    background: transparent;
    color: var(--muted);
    font-size: 13px;
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .in-comp:hover:not(:disabled) {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--text);
  }
  .in-comp.on {
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: var(--accent-grad);
    color: #fff;
    box-shadow:
      var(--glow-accent),
      inset 0 1px 0 rgba(255, 255, 255, 0.26);
  }
  .in-comp.on :global(.icon) {
    color: currentColor;
  }
  .in-comp.on:hover:not(:disabled) {
    background: linear-gradient(135deg, #ffab63, #ff7018);
  }
  .comp {
    display: grid;
    gap: 10px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: rgba(255, 255, 255, 0.04);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
  }
  .comp.filled {
    background: var(--accent-wash);
    border-color: var(--accent-line);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.1),
      0 0 30px -18px rgba(249, 115, 22, 0.9);
  }
  .comp-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .comp h2 {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin: 0;
    font-size: 13px;
    font-weight: 600;
  }
  .comp h2 :global(.icon) {
    color: var(--icon);
  }
  .comp-meta {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .comp-meta.over {
    color: var(--warn-text);
  }
  .comp-open {
    justify-content: center;
  }
  .comp-hint {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .chip-sample {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 18px;
    padding: 0 5px;
    border-radius: 5px;
    border: 1px dashed var(--ink-5);
    font-weight: 600;
    font-size: 11px;
    line-height: 1;
    vertical-align: -3px;
  }
  .add {
    justify-content: center;
    border-style: dashed;
    background: transparent;
    color: var(--muted);
  }
  .panel {
    min-width: 0;
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    background: var(--glass-fill);
    box-shadow: var(--shadow-glass);
  }
  .empty {
    display: grid;
    justify-items: center;
    gap: 8px;
    padding: 44px 20px;
    text-align: center;
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    background: var(--glass-fill);
    box-shadow: var(--shadow-glass);
  }
  .empty > :global(.icon) {
    color: var(--icon);
  }
  .empty h2 {
    margin: 0;
    font-size: 16px;
  }
  .empty-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
  }
  .empty p {
    max-width: 560px;
    margin: 0 auto 8px;
    color: var(--muted);
    font-size: 13px;
  }
  .toast {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 9px 15px;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    background: var(--glass-float);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    box-shadow:
      var(--shadow-float),
      inset 0 1px 0 rgba(255, 255, 255, 0.16);
    font-size: 13px;
    z-index: 20;
  }
  .toast :global(.icon) {
    color: var(--ok-text);
  }
  @media (max-width: 1000px) {
    .workspace {
      /* minmax(0, …): the clip snippets are nowrap and must not stretch the column past the screen. */
      grid-template-columns: minmax(0, 1fr);
    }
    .list {
      position: static;
      max-height: none;
    }
  }
  @media (max-width: 640px) {
    .bar {
      flex-wrap: wrap;
      gap: 10px;
    }
    .thumb {
      width: 72px;
    }
    .info {
      flex: 1 1 0;
    }
    .track {
      flex: 1 1 100%;
    }
    .track select {
      max-width: none;
      width: 100%;
    }
    .panel {
      padding: 14px;
    }
  }
</style>
