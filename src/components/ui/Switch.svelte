<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    checked: boolean;
    disabled?: boolean;
    /** The visible label; the whole row toggles. */
    children?: Snippet;
    label?: string;
  }
  let { checked = $bindable(), disabled = false, children, label }: Props = $props();
</script>

<label class="switch-row" class:disabled>
  <input type="checkbox" role="switch" bind:checked {disabled} aria-label={children ? undefined : label} />
  <span class="track" aria-hidden="true"><span class="knob"></span></span>
  {#if children}<span class="text">{@render children()}</span>{/if}
</label>

<style>
  .switch-row {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-height: 28px;
    cursor: pointer;
    font-size: 13px;
    color: var(--text);
  }
  .switch-row.disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }
  /* The real checkbox stays focusable and clickable, laid over the track. */
  input {
    position: absolute;
    opacity: 0;
    width: 30px;
    height: 18px;
    margin: 0;
    cursor: inherit;
  }
  .track {
    position: relative;
    flex: none;
    width: 30px;
    height: 18px;
    border-radius: 9px;
    background: var(--ink-5);
    transition: background-color 0.2s ease;
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 0.5px 1.5px rgba(0, 0, 0, 0.3);
    transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  }
  input:checked + .track {
    background: var(--accent-grad);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
  }
  input:checked + .track .knob {
    transform: translateX(12px);
  }
  input:focus-visible + .track {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    .track,
    .knob {
      transition: none;
    }
  }
</style>
