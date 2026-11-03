<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon, { type IconName } from './Icon.svelte';

  interface Item {
    label: string;
    icon: IconName;
    onclick: () => void;
    disabled?: boolean;
  }
  interface Props {
    label: string;
    items: Item[];
    trigger?: Snippet;
  }
  let { label, items, trigger }: Props = $props();

  let open = $state(false);
  let root: HTMLDivElement;
  let list = $state<HTMLDivElement | null>(null);

  function choose(item: Item) {
    open = false;
    item.onclick();
  }

  $effect(() => {
    if (!open) return;
    (list?.querySelector('button:not(:disabled)') as HTMLElement | null)?.focus();
    const away = (e: PointerEvent) => !root.contains(e.target as Node) && (open = false);
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        open = false;
        (root.querySelector('.trigger') as HTMLElement | null)?.focus();
      } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const all = [...(list?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])];
        const i = all.indexOf(document.activeElement as HTMLButtonElement);
        all[(i + (e.key === 'ArrowDown' ? 1 : -1) + all.length) % all.length]?.focus();
      }
    };
    window.addEventListener('pointerdown', away);
    window.addEventListener('keydown', key);
    return () => {
      window.removeEventListener('pointerdown', away);
      window.removeEventListener('keydown', key);
    };
  });
</script>

<div class="menu" bind:this={root}>
  <button class="trigger" class:open aria-haspopup="menu" aria-expanded={open} onclick={() => (open = !open)}>
    {#if trigger}{@render trigger()}{:else}{label} <Icon name="chevron-down" size={14} />{/if}
  </button>
  {#if open}
    <div class="pop" role="menu" aria-label={label} bind:this={list}>
      {#each items as item (item.label)}
        <button role="menuitem" disabled={item.disabled} onclick={() => choose(item)}>
          <Icon name={item.icon} />
          {item.label}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .menu {
    position: relative;
  }
  .trigger.open {
    background: var(--raised-hover);
  }
  .pop {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    z-index: 30;
    display: grid;
    min-width: 230px;
    padding: 4px;
    border-radius: var(--radius-lg);
    background: var(--raised);
    box-shadow: var(--shadow-satellite);
    animation: pop-in 0.14s ease-out;
  }
  .pop button {
    justify-content: flex-start;
    padding: 6px 10px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    text-align: left;
    white-space: nowrap;
  }
  .pop button:hover:not(:disabled),
  .pop button:focus-visible {
    background: var(--ink-3);
    outline: none;
  }
  @keyframes pop-in {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .pop {
      animation: none;
    }
  }
</style>
