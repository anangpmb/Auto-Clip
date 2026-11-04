<script lang="ts">
  import { onMount, type Snippet } from 'svelte';
  import Icon from './Icon.svelte';

  interface Props {
    title: string;
    subtitle?: Snippet;
    /** Wide dialogs hold a preview beside their settings. */
    width?: number;
    onclose: () => void;
    children: Snippet;
    footer?: Snippet;
  }
  let { title, subtitle, width = 640, onclose, children, footer }: Props = $props();

  let dlg: HTMLDialogElement;
  const titleId = `dlg-${Math.random().toString(36).slice(2, 8)}`;

  // A native modal dialog: focus stays inside, the page behind is inert, Esc asks to close.
  onMount(() => {
    const before = document.activeElement as HTMLElement | null;
    dlg.showModal();
    return () => before?.focus?.();
  });
</script>

<dialog
  bind:this={dlg}
  class="modal"
  style:--w="{width}px"
  aria-labelledby={titleId}
  oncancel={(e) => {
    e.preventDefault();
    onclose();
  }}
  onclick={(e) => e.target === dlg && onclose()}
>
  <header class="modal-head">
    <div class="titles">
      <h2 id={titleId}>{title}</h2>
      {#if subtitle}<p class="subtitle">{@render subtitle()}</p>{/if}
    </div>
    <button class="icon-btn ghost" onclick={onclose} aria-label="Tutup" title="Tutup"><Icon name="close" /></button>
  </header>
  <div class="modal-body">{@render children()}</div>
  {#if footer}<footer class="modal-foot">{@render footer()}</footer>{/if}
</dialog>

<style>
  .modal {
    width: min(var(--w), calc(100vw - 32px));
    max-width: none;
    max-height: min(92vh, 1000px);
    padding: 0;
    border: 0;
    border-radius: var(--radius-2xl);
    background: var(--glass-float);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    color: var(--text);
    box-shadow:
      0 0 0 1px rgba(255, 255, 255, 0.14),
      var(--shadow-float),
      inset 0 1px 0 rgba(255, 255, 255, 0.16);
    overflow: hidden;
  }
  .modal[open] {
    display: flex;
    flex-direction: column;
    animation: modal-in 0.22s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .modal::backdrop {
    background:
      radial-gradient(80% 60% at 50% 0%, rgba(255, 110, 30, 0.16), transparent 70%),
      rgba(12, 9, 8, 0.62);
    backdrop-filter: blur(10px);
  }
  .modal-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 16px 16px 14px 20px;
    border-bottom: 1px solid var(--border);
  }
  .titles {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    line-height: 1.3;
  }
  .subtitle {
    margin: 0;
    font-size: 12.5px;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .modal-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 20px;
  }
  .modal-foot {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 20px;
    border-top: 1px solid var(--border);
  }
  @keyframes modal-in {
    from {
      opacity: 0;
      transform: translateY(8px) scale(0.985);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .modal[open] {
      animation: none;
    }
  }
  @media (max-width: 640px) {
    .modal-body {
      padding: 16px;
    }
  }
</style>
