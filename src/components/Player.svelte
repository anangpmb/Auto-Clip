<script lang="ts">
  import { onMount } from 'svelte';
  import { describePlayerError, loadYouTubeApi } from '../lib/youtube';

  interface Props {
    videoId: string;
    ontime?: (t: number, playing: boolean) => void;
  }
  let { videoId, ontime }: Props = $props();

  let wrap: HTMLDivElement;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let player: any = null;
  let ready = $state(false);
  let error = $state('');
  let stopAt: number | null = null;

  onMount(() => {
    let dead = false;
    // YT.Player replaces its target node, so give it one Svelte does not own.
    const target = document.createElement('div');
    wrap.appendChild(target);
    loadYouTubeApi()
      .then((YT) => {
        if (dead) return;
        player = new YT.Player(target, {
          videoId,
          width: '100%',
          height: '100%',
          playerVars: { rel: 0, playsinline: 1, modestbranding: 1, origin: location.origin },
          events: {
            onReady: () => (ready = true),
            onError: (e: { data: number }) => (error = describePlayerError(e.data)),
          },
        });
      })
      .catch((e: Error) => (error = e.message));

    const timer = setInterval(() => {
      if (!ready || !player?.getCurrentTime) return;
      const t: number = player.getCurrentTime();
      const playing = player.getPlayerState() === 1;
      if (stopAt !== null && playing && t >= stopAt) {
        player.pauseVideo();
        stopAt = null;
      }
      ontime?.(t, playing);
    }, 100);

    return () => {
      dead = true;
      clearInterval(timer);
      try {
        player?.destroy();
      } catch {
        /* already gone */
      }
    };
  });

  /** Play from start and pause automatically at end. */
  export function playRange(start: number, end: number) {
    if (!ready) return;
    stopAt = end;
    player.seekTo(start, true);
    player.playVideo();
  }

  export function pause() {
    stopAt = null;
    if (ready) player.pauseVideo();
  }
</script>

<div class="player">
  <div class="frame" bind:this={wrap}></div>
  {#if error}
    <div class="error">
      <p>{error}</p>
      <a href={`https://www.youtube.com/watch?v=${videoId}`} target="_blank" rel="noreferrer">Buka di YouTube ↗</a>
    </div>
  {:else if !ready}
    <div class="loading">Memuat pemutar…</div>
  {/if}
</div>

<style>
  .player {
    position: relative;
    aspect-ratio: 16 / 9;
    background: #000;
    border-radius: var(--radius);
    overflow: hidden;
  }
  .frame,
  .frame :global(iframe) {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
  }
  .loading,
  .error {
    position: absolute;
    inset: 0;
    display: grid;
    place-content: center;
    gap: 8px;
    padding: 20px;
    text-align: center;
    color: var(--muted);
    font-size: 14px;
  }
  .error {
    background: rgba(10, 12, 16, 0.92);
    color: var(--text);
  }
  .error a {
    color: var(--accent-2);
  }
</style>
