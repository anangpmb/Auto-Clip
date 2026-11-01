<script lang="ts">
  import type { CaptionCue, CaptionStyle, CaptionPosition } from '../lib/captions';
  import { groupWordsIntoCues } from '../lib/captions';
  import type { Word } from '../lib/types';

  interface Props {
    words: Word[];
    w0: number;
    w1: number;
    clipStart: number;
    clipEnd: number;
    currentTime: number;
    enabled?: boolean;
    style?: CaptionStyle;
    position?: CaptionPosition;
    uppercase?: boolean;
  }

  let {
    words,
    w0,
    w1,
    clipStart,
    clipEnd,
    currentTime,
    enabled = true,
    style = 'viral',
    position = 'bottom',
    uppercase = true,
  }: Props = $props();

  const clipWords = $derived(words.slice(w0, w1 + 1));
  const cues = $derived(
    groupWordsIntoCues(clipWords, clipStart, clipEnd, {
      uppercase,
      maxWordsPerCue: 5,
    })
  );

  const relTime = $derived(Math.max(0, currentTime - clipStart));
  const activeCue = $derived<CaptionCue | null>(
    currentTime >= clipStart - 0.2 && currentTime <= clipEnd + 0.2
      ? cues.find((c) => relTime >= c.start && relTime <= c.end) ?? null
      : null
  );
</script>

{#if enabled && activeCue}
  <div class="overlay pos-{position} style-{style}">
    <div class="caption-box">
      {#each activeCue.words as w}
        {@const isActive = relTime >= w.start && relTime <= w.end}
        <span class="word" class:active={isActive}>{w.text}</span>{' '}
      {/each}
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: absolute;
    inset: 0;
    pointer-events: none;
    display: flex;
    justify-content: center;
    padding: 24px;
    z-index: 3;
    animation: fadeIn 0.15s ease-out;
  }

  .pos-bottom {
    align-items: flex-end;
    padding-bottom: 32px;
  }
  .pos-center {
    align-items: center;
  }
  .pos-top {
    align-items: flex-start;
    padding-top: 32px;
  }

  .caption-box {
    text-align: center;
    line-height: 1.35;
    font-weight: 800;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    letter-spacing: 0.02em;
    max-width: 85%;
    transition: all 0.1s ease;
  }

  /* VIRAL / KARAOKE STYLE */
  .style-viral .caption-box {
    font-size: 26px;
    color: #ffffff;
    text-shadow:
      -2px -2px 0 #000,
      2px -2px 0 #000,
      -2px 2px 0 #000,
      2px 2px 0 #000,
      0 3px 6px rgba(0, 0, 0, 0.9);
  }
  .style-viral .word.active {
    color: #facc15;
    background: rgba(0, 0, 0, 0.4);
    padding: 2px 6px;
    border-radius: 6px;
    display: inline-block;
    transform: scale(1.08);
    transition: transform 0.08s ease;
    text-shadow:
      -2px -2px 0 #000,
      2px -2px 0 #000,
      -2px 2px 0 #000,
      2px 2px 0 #000,
      0 0 12px rgba(250, 204, 21, 0.8);
  }

  /* MODERN BOX STYLE */
  .style-box .caption-box {
    font-size: 20px;
    background: rgba(0, 0, 0, 0.78);
    color: #ffffff;
    padding: 8px 16px;
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    backdrop-filter: blur(4px);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.5);
  }
  .style-box .word.active {
    color: #fde047;
    font-weight: 900;
    text-decoration: underline;
    text-underline-offset: 4px;
  }

  /* CLASSIC SUBTITLE STYLE */
  .style-classic .caption-box {
    font-size: 20px;
    color: #ffffff;
    font-weight: 600;
    text-shadow:
      0 1px 3px rgba(0, 0, 0, 0.9),
      0 2px 8px rgba(0, 0, 0, 0.8);
  }
  .style-classic .word.active {
    color: #ffffff;
  }

  /* NEON POP STYLE */
  .style-neon .caption-box {
    font-size: 26px;
    color: #ffffff;
    text-shadow:
      -2px -2px 0 #1e1b4b,
      2px -2px 0 #1e1b4b,
      -2px 2px 0 #1e1b4b,
      2px 2px 0 #1e1b4b;
  }
  .style-neon .word.active {
    color: #22d3ee;
    display: inline-block;
    transform: scale(1.1);
    text-shadow:
      -2px -2px 0 #000,
      2px -2px 0 #000,
      -2px 2px 0 #000,
      2px 2px 0 #000,
      0 0 16px rgba(34, 211, 238, 0.9);
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(3px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @media (max-width: 640px) {
    .style-viral .caption-box,
    .style-neon .caption-box {
      font-size: 20px;
    }
    .style-box .caption-box,
    .style-classic .caption-box {
      font-size: 16px;
    }
  }
</style>

