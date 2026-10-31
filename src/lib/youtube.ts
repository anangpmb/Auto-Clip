/* Minimal loader for the YouTube IFrame Player API. */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type YTNamespace = any;

declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<YTNamespace> | null = null;

export function loadYouTubeApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!apiPromise) {
    apiPromise = new Promise((resolve, reject) => {
      const previous = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        previous?.();
        resolve(window.YT);
      };
      const script = document.createElement('script');
      script.src = 'https://www.youtube.com/iframe_api';
      script.async = true;
      script.onerror = () => {
        apiPromise = null;
        reject(new Error('Gagal memuat pemutar YouTube. Cek koneksi internet.'));
      };
      document.head.appendChild(script);
    });
  }
  return apiPromise;
}

export function describePlayerError(code: number): string {
  if (code === 101 || code === 150) {
    return 'Pemilik video mematikan pemutaran di situs lain, jadi pratinjau tidak tersedia. Potongan tetap bisa diatur lewat transkrip.';
  }
  if (code === 100) return 'Video tidak ditemukan atau privat.';
  if (code === 153) return 'Pemutar YouTube butuh header referrer. Buka situs ini lewat http(s), bukan file lokal.';
  if (code === 2) return 'ID video tidak valid.';
  return `Pemutar YouTube error (${code}).`;
}
