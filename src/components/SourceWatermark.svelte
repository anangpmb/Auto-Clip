<script lang="ts">
  import type { WatermarkPayload } from '../lib/watermark';
  import { watermarkFontShare } from '../lib/watermark';

  interface Props {
    watermark: WatermarkPayload | null;
  }
  let { watermark }: Props = $props();
</script>

{#if watermark}
  <!--
    Attribution burned into the video, shown here exactly where the export puts it.
    One quiet line, no animation: its job is to name the source, not to compete
    with the video. Hidden from screen readers because it is video content, not UI.
  -->
  <div
    class="watermark pos-{watermark.position} style-{watermark.style}"
    style:--wm-size="{watermarkFontShare(watermark.size) * 100}cqh"
    style:opacity={watermark.opacity}
    aria-hidden="true"
  >
    <span>{watermark.text}</span>
  </div>
{/if}

<style>
  .watermark {
    position: absolute;
    inset: 0;
    z-index: 2;
    pointer-events: none;
    display: flex;
    padding: 3.5cqh 3cqw;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: var(--wm-size);
    font-weight: 600;
    line-height: 1.2;
    color: #fff;
  }
  .watermark span {
    max-width: 85%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .pos-top-left {
    align-items: flex-start;
    justify-content: flex-start;
  }
  .pos-top-right {
    align-items: flex-start;
    justify-content: flex-end;
  }
  .pos-bottom-left {
    align-items: flex-end;
    justify-content: flex-start;
  }
  .pos-bottom-right {
    align-items: flex-end;
    justify-content: flex-end;
  }
  /* Text only: a thin dark outline keeps it readable over any footage. */
  .style-text span {
    text-shadow:
      -1px -1px 0 rgba(0, 0, 0, 0.85),
      1px -1px 0 rgba(0, 0, 0, 0.85),
      -1px 1px 0 rgba(0, 0, 0, 0.85),
      1px 1px 0 rgba(0, 0, 0, 0.85),
      0 1px 3px rgba(0, 0, 0, 0.8);
  }
  /* Shaded: a single dark wash behind the text, for very bright footage. */
  .style-shaded span {
    padding: 0.35em 0.65em;
    border-radius: 0.35em;
    background: rgba(0, 0, 0, 0.45);
  }
  @media (prefers-reduced-motion: reduce) {
    .watermark {
      animation: none;
    }
  }
</style>
