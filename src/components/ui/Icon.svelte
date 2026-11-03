<script lang="ts" module>
  // One icon family (Lucide) at one absolute stroke, so icons side by side share a weight.
  // Each icon is imported on its own so the bundle carries only these.
  import Archive from '@lucide/svelte/icons/folder-archive';
  import ArrowDown from '@lucide/svelte/icons/arrow-down';
  import ArrowLeft from '@lucide/svelte/icons/arrow-left';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import Captions from '@lucide/svelte/icons/captions';
  import Check from '@lucide/svelte/icons/check';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronsLeft from '@lucide/svelte/icons/chevrons-left';
  import ChevronsRight from '@lucide/svelte/icons/chevrons-right';
  import CircleAlert from '@lucide/svelte/icons/circle-alert';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Clapperboard from '@lucide/svelte/icons/clapperboard';
  import Clock from '@lucide/svelte/icons/clock';
  import Copy from '@lucide/svelte/icons/copy';
  import Crop from '@lucide/svelte/icons/crop';
  import Download from '@lucide/svelte/icons/download';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import Eye from '@lucide/svelte/icons/eye';
  import EyeOff from '@lucide/svelte/icons/eye-off';
  import FileText from '@lucide/svelte/icons/file-text';
  import Film from '@lucide/svelte/icons/film';
  import Gamepad from '@lucide/svelte/icons/gamepad-2';
  import Info from '@lucide/svelte/icons/info';
  import Layers from '@lucide/svelte/icons/layers';
  import ListChecks from '@lucide/svelte/icons/list-checks';
  import Loader from '@lucide/svelte/icons/loader-circle';
  import Magnet from '@lucide/svelte/icons/magnet';
  import Pause from '@lucide/svelte/icons/pause';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Play from '@lucide/svelte/icons/play';
  import Plus from '@lucide/svelte/icons/plus';
  import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
  import Scissors from '@lucide/svelte/icons/scissors';
  import Settings from '@lucide/svelte/icons/settings';
  import SortTime from '@lucide/svelte/icons/arrow-down-narrow-wide';
  import Terminal from '@lucide/svelte/icons/terminal';
  import TextSearch from '@lucide/svelte/icons/text-search';
  import Trash from '@lucide/svelte/icons/trash-2';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import X from '@lucide/svelte/icons/x';

  const ICONS = {
    archive: Archive,
    'arrow-down': ArrowDown,
    'arrow-up': ArrowUp,
    back: ArrowLeft,
    captions: Captions,
    check: Check,
    'chevron-down': ChevronDown,
    'chevron-left': ChevronLeft,
    'chevron-right': ChevronRight,
    'chevrons-left': ChevronsLeft,
    'chevrons-right': ChevronsRight,
    alert: CircleAlert,
    done: CircleCheck,
    clapperboard: Clapperboard,
    clock: Clock,
    copy: Copy,
    crop: Crop,
    download: Download,
    external: ExternalLink,
    eye: Eye,
    'eye-off': EyeOff,
    file: FileText,
    film: Film,
    gamepad: Gamepad,
    info: Info,
    layers: Layers,
    bulk: ListChecks,
    loader: Loader,
    magnet: Magnet,
    pause: Pause,
    edit: Pencil,
    play: Play,
    plus: Plus,
    reset: RotateCcw,
    scissors: Scissors,
    settings: Settings,
    'sort-time': SortTime,
    terminal: Terminal,
    search: TextSearch,
    trash: Trash,
    warning: TriangleAlert,
    close: X,
  } as const;

  export type IconName = keyof typeof ICONS;
</script>

<script lang="ts">
  interface Props {
    name: IconName;
    /** 16 in buttons and rows, 14 in small controls, 20 for a lone glyph. */
    size?: number;
    class?: string;
  }
  let { name, size = 16, class: cls = '' }: Props = $props();
  const Glyph = $derived(ICONS[name]);
</script>

<Glyph {size} strokeWidth={1.75} absoluteStrokeWidth class="icon {cls}" aria-hidden="true" focusable="false" />
