<script lang="ts">
  import type { CaptionCue, CaptionStyle, CaptionPosition } from '../lib/captions';
  import { groupWordsIntoCues } from '../lib/captions';
  import { activeWordIndex } from '../lib/preview';
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
    /**
     * Size and place the caption like the exported video, relative to the frame it sits in
     * (the frame must be a size container). Used by the final-result preview.
     */
    exact?: boolean;
    vertical?: boolean;
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
    exact = false,
    vertical = true,
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
  const activeWord = $derived(activeCue && style !== 'classic' ? activeWordIndex(activeCue, relTime) : -1);
</script>

{#if enabled && activeCue}
  <div class="overlay pos-{position} style-{style}" class:exact class:v={vertical} class:h={!vertical}>
    <div class="caption-box">
      {#each activeCue.words as w, i}
        <span class="word" class:active={i === activeWord}>{w.text}</span>{' '}
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

  /* EXACT: the exported look (helper CaptionRenderer), scaled to the frame it sits in. */
  .overlay.exact {
    --u: 1cqw; /* vertical video: sizes are a share of the width */
    padding: 0;
    animation: none;
  }
  .overlay.exact.h {
    --u: 0.82cqh; /* landscape: a share of the height, a little smaller */
  }
  .overlay.exact.pos-bottom {
    padding-bottom: 14cqh;
  }
  .overlay.exact.pos-top {
    padding-top: 14cqh;
  }
  .overlay.exact.h.pos-bottom {
    padding-bottom: 8cqh;
  }
  .overlay.exact.h.pos-top {
    padding-top: 8cqh;
  }
  .overlay.exact .caption-box {
    --stroke: #000;
    --sw: 0.09em;
    --sd: 0.064em;
    --ring: var(--sw) 0 0 var(--stroke), calc(-1 * var(--sw)) 0 0 var(--stroke), 0 var(--sw) 0 var(--stroke),
      0 calc(-1 * var(--sw)) 0 var(--stroke), var(--sd) var(--sd) 0 var(--stroke),
      calc(-1 * var(--sd)) var(--sd) 0 var(--stroke), var(--sd) calc(-1 * var(--sd)) 0 var(--stroke),
      calc(-1 * var(--sd)) calc(-1 * var(--sd)) 0 var(--stroke);
    font-family: 'Arial Black', 'Arial Bold', Arial, sans-serif;
    font-size: calc(6.3 * var(--u));
    font-weight: 900;
    line-height: 1.3;
    letter-spacing: 0;
    max-width: 85%;
    color: #fff;
    text-shadow: var(--ring);
    transition: none;
  }
  .overlay.exact .word.active {
    display: inline-block;
    padding: 0;
    transform: none;
    transition: none;
    text-shadow: inherit;
  }
  .overlay.exact.style-viral .word.active {
    color: #facc15;
    line-height: 1.05;
    padding: 0 0.18em;
    margin: 0 -0.18em;
    border-radius: 0.2em;
    background: rgba(0, 0, 0, 0.43);
  }
  .overlay.exact.style-neon .caption-box {
    --stroke: rgb(30, 27, 75);
  }
  .overlay.exact.style-neon .word.active {
    color: #22d3ee;
    text-shadow:
      var(--ring),
      0 0 0.12em rgba(34, 211, 238, 0.9),
      0 0 0.3em rgba(34, 211, 238, 0.7);
  }
  .overlay.exact.style-box .caption-box {
    font-size: calc(5.4 * var(--u));
    padding: 0.2em 0.4em;
    border: none;
    border-radius: 0.25em;
    background: rgba(0, 0, 0, 0.78);
    box-shadow: none;
    backdrop-filter: none;
    text-shadow: none;
  }
  .overlay.exact.style-box .word.active {
    color: #fde047;
    text-decoration: underline;
    text-decoration-thickness: 0.06em;
    text-underline-offset: 0.1em;
  }
  .overlay.exact.style-classic .caption-box {
    --stroke: rgba(0, 0, 0, 0.78);
    --sw: 0.05em;
    --sd: 0.035em;
    font-size: calc(5 * var(--u));
    text-shadow:
      var(--ring),
      0 0.06em 0.05em rgba(0, 0, 0, 0.86);
  }
</style>

