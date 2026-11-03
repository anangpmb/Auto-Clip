<script lang="ts" generics="T extends string">
  interface Props {
    value: T;
    options: { value: T; label: string }[];
    /** Names the group for screen readers. */
    label: string;
    disabled?: boolean;
  }
  let { value = $bindable(), options, label, disabled = false }: Props = $props();
  const index = $derived(Math.max(0, options.findIndex((o) => o.value === value)));

  // Arrow keys move the choice, like native radio buttons.
  function key(e: KeyboardEvent) {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (index + step + options.length) % options.length;
    value = options[next].value;
    ((e.currentTarget as HTMLElement).parentElement?.children[next + 1] as HTMLElement | undefined)?.focus();
  }
</script>

<div class="seg" role="radiogroup" aria-label={label} style:--n={options.length} class:disabled>
  <span class="thumb" style:transform="translateX({index * 100}%)" aria-hidden="true"></span>
  {#each options as o, i (o.value)}
    <button
      type="button"
      role="radio"
      aria-checked={i === index}
      tabindex={i === index ? 0 : -1}
      class:on={i === index}
      {disabled}
      onclick={() => (value = o.value)}
      onkeydown={key}>{o.label}</button
    >
  {/each}
</div>

<style>
  .seg {
    position: relative;
    display: grid;
    grid-template-columns: repeat(var(--n), minmax(0, 1fr));
    padding: 2px;
    border-radius: var(--radius-md);
    background: var(--ink-2);
  }
  .thumb {
    position: absolute;
    top: 2px;
    bottom: 2px;
    left: 2px;
    width: calc((100% - 4px) / var(--n));
    border-radius: var(--radius-sm);
    background: var(--raised);
    box-shadow: 0 0 0 1px var(--ink-3), 0 1px 2px rgba(0, 0, 0, 0.3);
    transition: transform 0.3s cubic-bezier(0.22, 1, 0.36, 1);
  }
  button {
    position: relative;
    display: grid;
    place-items: center;
    min-width: 0;
    height: 28px;
    padding: 0 10px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--muted);
    font-size: 12.5px;
    font-weight: 500;
    white-space: nowrap;
    transition: color 0.2s ease;
  }
  button:hover:not(:disabled) {
    background: transparent;
    color: var(--text);
  }
  button.on {
    color: var(--text);
  }
  button:focus-visible {
    outline-offset: -2px;
  }
  .disabled {
    opacity: 0.5;
  }
  @media (prefers-reduced-motion: reduce) {
    .thumb {
      transition: none;
    }
  }
</style>
