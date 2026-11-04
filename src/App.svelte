<script lang="ts">
  import Home from './components/Home.svelte';
  import ProjectView from './components/ProjectView.svelte';
  import SettingsDialog from './components/SettingsDialog.svelte';
  import Icon from './components/ui/Icon.svelte';
  import { checkHelper, type HelperHealth } from './lib/helper';
  import { loadSettings, saveSettings } from './lib/storage';
  import type { LoadedProject, Settings } from './lib/types';

  let settings = $state<Settings>(loadSettings());
  let project = $state.raw<LoadedProject | null>(null);
  let settingsOpen = $state(false);
  let health = $state<HelperHealth | null>(null);
  let checking = $state(true);

  $effect(() => {
    saveSettings($state.snapshot(settings));
  });

  // Poll the helper: often while it is down, rarely once it is up.
  $effect(() => {
    const url = settings.helperUrl;
    let stopped = false;
    let timer = 0;
    const poll = async () => {
      const h = await checkHelper(url);
      if (stopped) return;
      health = h;
      checking = false;
      timer = window.setTimeout(poll, h?.ok ? 30_000 : 4_000);
    };
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  });

  const status = $derived(
    checking
      ? { cls: 'wait', text: 'Mengecek helper…' }
      : health?.ok
        ? { cls: 'ok', text: 'Helper tersambung', extra: health.yt_dlp ? ` · yt-dlp ${health.yt_dlp}` : '' }
        : health?.error === 'origin_not_allowed'
          ? { cls: 'warn', text: 'Helper menolak situs ini' }
          : { cls: 'bad', text: 'Helper belum berjalan' },
  );
</script>

<header class="top">
  <button class="brand" onclick={() => (project = null)}>
    <img src="./favicon.svg" alt="" width="26" height="26" />
    <span>AutoClip <b>Web</b></span>
  </button>
  <span class="status {status.cls}" title={settings.helperUrl}
    ><i></i><span class="status-text">{status.text}</span>{#if status.extra}<span class="status-extra">{status.extra}</span>{/if}</span
  >
  <button class="ghost settings-btn" onclick={() => (settingsOpen = true)} aria-label="Pengaturan">
    <Icon name="settings" /><span class="settings-label">Pengaturan</span>
  </button>
</header>

<main>
  {#if project}
    {#key project.meta.id}
      <ProjectView
        initial={project}
        bind:settings
        helperOk={!!health?.ok}
        helperHealth={health}
        onclose={() => (project = null)}
        onsettings={() => (settingsOpen = true)}
      />
    {/key}
  {:else}
    <Home {settings} {health} {checking} onopen={(p) => (project = p)} />
  {/if}
</main>

<SettingsDialog bind:open={settingsOpen} bind:settings />

<style>
  .top {
    position: sticky;
    top: 12px;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: 14px;
    width: calc(100% - 24px);
    max-width: 1400px;
    margin: 12px auto 0;
    padding: 9px 12px 9px 16px;
    border: 1px solid var(--border);
    border-radius: 20px;
    background: linear-gradient(160deg, rgba(60, 48, 44, 0.86), rgba(24, 20, 20, 0.92));
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    box-shadow:
      var(--shadow-float),
      inset 0 1px 0 rgba(255, 255, 255, 0.14);
  }
  .brand img {
    border-radius: 9px;
    box-shadow: 0 8px 20px -10px rgba(249, 115, 22, 0.9);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0;
    background: none;
    border: none;
    font-size: 15px;
    font-weight: 600;
  }
  .brand:hover:not(:disabled) {
    background: none;
  }
  .brand b {
    color: var(--muted);
    font-weight: 500;
  }
  .status {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    min-width: 0;
    padding: 0 11px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: rgba(255, 255, 255, 0.06);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
    font-size: 12px;
    color: var(--muted);
  }
  .status i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--muted);
  }
  .status.ok i {
    background: var(--ok);
    box-shadow: 0 0 0 3px var(--ok-soft), 0 0 12px rgba(74, 222, 128, 0.7);
  }
  .status.warn i {
    background: var(--warn);
    box-shadow: 0 0 0 3px var(--warn-soft);
  }
  .status.bad i {
    background: var(--bad);
    box-shadow: 0 0 0 3px var(--bad-soft);
  }
  .brand,
  .status,
  .settings-btn {
    white-space: nowrap;
  }
  .status-text {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .status i {
    flex: none;
  }
  .settings-btn {
    min-height: 36px;
  }
  main {
    padding: 22px 20px 60px;
    max-width: 1400px;
    margin: 0 auto;
  }
  /* Keep the floating header to one short row on phones so it covers as little as possible. */
  @media (max-width: 640px) {
    .top {
      top: 8px;
      gap: 8px;
      width: calc(100% - 16px);
      margin-top: 8px;
      padding: 8px 8px 8px 12px;
      border-radius: 16px;
    }
    .status-extra,
    .settings-label {
      display: none;
    }
    .settings-btn {
      min-width: 40px;
      justify-content: center;
      padding: 0;
    }
    .status {
      padding: 0 9px;
    }
    main {
      padding: 18px 12px 48px;
    }
  }
  /* Very narrow phones: the wordmark loses its suffix, so the status stays readable. */
  @media (max-width: 420px) {
    .top {
      gap: 6px;
      padding-left: 10px;
      padding-right: 6px;
    }
    .brand {
      gap: 8px;
      font-size: 14px;
    }
    .brand b {
      display: none;
    }
    .status {
      gap: 5px;
      padding: 0 8px;
      font-size: 11px;
    }
    .settings-btn {
      min-width: 36px;
    }
  }
</style>
