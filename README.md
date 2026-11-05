# AutoClip Web

Potong video YouTube panjang jadi klip pendek. AI memilih momen terbaik, lalu kamu rapikan
awal dan akhir tiap klip berdasarkan transkrip, supaya konteksnya utuh: tidak terpotong di
tengah kalimat, tidak kepanjangan.

Web app-nya statis (bisa di GitHub Pages). Data YouTube diambil oleh **helper** kecil yang
berjalan di PC kamu, karena browser tidak bisa mengambilnya sendiri.

```
GitHub Pages (browser)                     Helper di PC (127.0.0.1:8765)
  tempel link YouTube  ─────────────────▶  yt-dlp: info video + transkrip per kata
  AI memilih klip (API key kamu)
  atur awal/akhir di timeline + transkrip
  salin daftar / perintah yt-dlp / JSON
```

## Menjalankan helper (satu klik)

Butuh [Python 3.10+](https://www.python.org/downloads/). Setelah dipasang, launcher
menyalakan helper dan langsung membuka web app di browser. Kalau helper sudah berjalan,
launcher cukup membuka browser lagi. Tutup jendela helper untuk mematikannya.

**Mac:** jalankan sekali di Terminal:

```
curl -fsSL https://USERNAME.github.io/REPO/install-mac.sh | bash -s https://USERNAME.github.io/REPO/
```

Script ini membuat folder `~/AutoClip` (helper + Python sendiri berisi yt-dlp) dan ikon
**AutoClip** di Desktop. Klik dua kali ikon itu setiap kali mau memakai AutoClip. Launcher
juga mengambil versi helper terbaru dari situs setiap kali dibuka. Jalankan perintah di atas
lagi kapan saja untuk memperbarui yt-dlp.

**Windows:** klik dua kali `helper/AutoClip.bat`. Saat pertama kali, yt-dlp dipasang
otomatis. Ganti `APP_URL` di dalamnya kalau alamat situs kamu berbeda.

**Manual:**

```
pip install -U "yt-dlp[default,deno]"
python helper/autoclip_helper.py --app https://USERNAME.github.io/REPO/ --open
```

`--app` mengizinkan situs itu memakai helper, dan sekaligus membuat helper menyajikan web
app yang sama di `http://127.0.0.1:8765/`. `--open` membuka alamat itu di browser. Alamat
`localhost:5173` (mode pengembangan) selalu diizinkan.

### Browser mana yang dipakai

| Browser | Buka alamat |
|---|---|
| Chrome, Edge | `https://USERNAME.github.io/REPO/` (pilih **Izinkan** saat diminta akses jaringan lokal) |
| Firefox | `https://USERNAME.github.io/REPO/` |
| Safari (Mac) | `http://127.0.0.1:8765/` |

Safari memblokir situs `https://` yang menghubungi helper di `http://127.0.0.1`, tanpa
menampilkan permintaan izin. Lewat `http://127.0.0.1:8765/`, web app dan helper berada di
alamat yang sama, jadi tidak ada yang diblokir. Proyek dan pengaturan disimpan per alamat,
jadi isinya terpisah dari versi GitHub Pages.

Helper harus berjalan di komputer yang sama dengan browser-nya. HP/tablet tidak didukung.

Opsi lain:

| Opsi | Kegunaan |
|---|---|
| `--cookies-from-browser firefox` | Untuk video yang butuh login (dibatasi usia, khusus member) atau saat YouTube minta verifikasi bot |
| `--cookies cookies.txt` | Sama, pakai file cookies format Netscape |
| `--port 8765` | Ganti port (sesuaikan juga di Pengaturan web app) |
| `--open` | Buka web app di browser setelah helper siap |

## Memakai web app

1. Buka **Pengaturan**, pilih penyedia AI (Gemini, OpenAI, Claude, atau OpenRouter), dan isi
   API key. Key hanya disimpan di browser kamu dan dikirim langsung ke penyedia AI.
2. Tempel link YouTube, klik **Ambil transkrip**.
3. Klik **Cari klip dengan AI**.
4. Pilih klip, lalu rapikan potongannya:
   - **Timeline**: seret penanda AWAL (biru) dan AKHIR (biru muda). Garis hijau menunjukkan area
     ideal untuk AKHIR sesuai durasi min/maks. Klik di mana saja untuk memutar dari titik itu.
   - **Transkrip**: seret label AWAL/AKHIR ke kata lain, atau klik sebuah kata untuk memilih
     "Mulai dari kata ini", "Akhiri di kata ini", atau versi per kalimatnya.
   - **Tombol halus**: `« kalimat`, `‹ kata`, `kata ›`, `kalimat »` untuk awal dan akhir.
     Di timeline, tombol panah kiri/kanan menggeser per kata (Shift = per kalimat).
   - **Seret menempel ke kalimat**: kalau aktif, seretan berhenti di batas kalimat.
   - **Putar klip / Cek awal / Cek akhir** untuk mendengar hasilnya.
   - **Kembalikan saran AI** untuk membatalkan perubahan.
5. Ekspor: **Salin daftar**, **Salin perintah yt-dlp** (mengunduh potongan mentah), atau
   **Unduh JSON**.
6. Mau satu video highlight dari beberapa momen? Lihat **Kompilasi highlight** di bawah.

Tanpa API key pun bisa: **Impor klip** (lihat di bawah) memakai AI apa saja di luar app.
7. Mau semua klip jadi MP4 sekaligus? Tekan **Ekspor massal** (lihat di bawah).

Proyek tersimpan otomatis di browser (localStorage).

Transkrip "otomatis" dari YouTube punya waktu per kata yang asli, jadi potongannya paling
presisi. Subtitle "manual" teksnya lebih rapi tapi waktu per katanya diperkirakan.

## Impor klip dari AI lain (tanpa API key)

AI di app ini hanya membaca transkrip dan memilih momen, jadi langkah itu bisa dikerjakan
AI mana saja, misalnya ChatGPT, Claude, atau Gemini versi web yang gratis:

1. Tekan **Impor klip**, lalu **Salin prompt** (atau **Unduh .txt** untuk dilampirkan
   sebagai file). Isinya aturan memilih klip (durasi min/maks, jumlah klip, instruksi
   tambahan dari Pengaturan) dan transkrip dengan nomor kalimat.
2. Tempel di chat AI, lalu salin jawabannya ke kotak **Tempel jawabannya**, atau pilih
   filenya. Teks basa-basi di sekitar JSON tidak masalah. Transkrip yang sangat panjang
   dibagi jadi beberapa prompt; tempel semua jawabannya sekaligus.
3. Periksa daftar klip yang terbaca, lalu **Impor**, **Tambahkan**, atau **Ganti semua klip**.

Format yang diterima:

```
{"clips":[{"start_id":12,"end_id":18,"title":"...","reason":"...","score":80}]}   jawaban prompt tadi
{"clips":[{"start":83.5,"end":"2:10","title":"..."}]}                            detik atau jam:menit:detik
1:23 - 2:10 Judul klip                                                            satu klip per baris
```

File dari **Unduh JSON** juga bisa diimpor ulang. Jawaban yang memakai nomor kalimat
dirapikan ke kalimat dan durasi min/maks seperti hasil AI di app (bisa dimatikan); waktu
yang ditulis sendiri dipakai apa adanya, menempel ke batas kata terdekat. Klip di luar
transkrip dilewati dan alasannya ditampilkan.

## Pratinjau hasil akhir & ekspor video MP4

Tombol **Pratinjau Hasil Akhir & Ekspor** membuka pratinjau video jadi sebelum dirender.
Helper mengambil salinan ringan klip (480p, biasanya beberapa detik), lalu web app
menampilkannya persis seperti hasil ekspor: format 9:16 blur / ikuti wajah / 16:9, kamera
yang mengikuti wajah, dan caption dengan ukuran serta posisi yang sama. Pada format latar
blur, video utama di-crop memenuhi 2/3 tengah layar; latar blur mengisi 1/6 bagian atas dan
bawah. Ganti format atau
gaya caption, pratinjaunya langsung berubah. Jalur wajah dari pratinjau dipakai ulang
saat ekspor, jadi hasilnya sama dan ekspor lebih cepat. Butuh helper 0.4.0 atau lebih baru;
tata letak blur terbaru memerlukan helper 0.6.1 atau lebih baru.

Di panel yang sama ada **Watermark sumber**: satu baris kecil nama channel video sumber
yang dibakar ke video hasil ekspor, supaya penonton tahu darimana video itu diambil.
Posisinya default kanan atas, teksnya bisa diedit, dan ukurannya, opasitasnya, serta
gayanya (teks saja atau latar gelap tipis) bisa diatur. Butuh helper 0.7.0 atau lebih baru;
kalau helper lebih lama, panel ekspor akan memintamu memperbaruinya dulu.

Saat **Mulai Render Video**, helper:

1. Mengunduh hanya potongan klip itu, maksimal 1080p. Potongan diambil langsung per
   fragmen DASH secara paralel (YouTube memperlambat unduhan potongan biasa sampai
   kira-kira secepat video diputar); kalau tidak bisa, otomatis memakai cara yt-dlp biasa.
2. Untuk **9:16 Vertikal (Ikuti Wajah)**: mendeteksi wajah (OpenCV + model YuNet) dan
   pergantian shot, lalu menggerakkan "kamera" virtual. Kamera diam kalau wajah hanya
   bergeser sedikit, ikut bergeser halus kalau subjek berjalan, dan langsung pindah saat
   ganti shot. Seluruh kotak wajah selalu dijaga di dalam frame. Beberapa orang yang
   berdekatan dibingkai bersama; kalau terlalu jauh, kamera mengikuti satu orang dan tidak
   berpindah karena perubahan sesaat. Tanpa wajah, dipakai potongan tengah.
3. Menggambar caption sendiri (Pillow) dengan gaya yang sama dengan pratinjau di editor,
   jadi tidak butuh FFmpeg dengan libass.
4. Merender MP4 (H.264 + AAC) dan browser langsung mengunduhnya.

Kebutuhan: FFmpeg (`brew install ffmpeg` / `winget install ffmpeg`), plus paket Python
`opencv-python-headless` dan `pillow`. Launcher Mac/Windows memasangnya otomatis. Model
wajah (~230 KB) diunduh sekali ke `~/.autoclip/models` dan dicek hash-nya.

## Kompilasi highlight

Gabungkan beberapa momen dari satu video jadi satu video highlight:

1. Di daftar klip, tekan tombol kompilasi (ikon tumpukan dengan **+**) pada klip yang mau
   dimasukkan. Nomor di tombol itu adalah urutan tayangnya di kompilasi.
2. Rapikan awal/akhir tiap klip seperti biasa di editor. Untuk kompilasi, potongan pendek
   (5–20 detik) biasanya paling enak ditonton; turunkan durasi min/maks di **Pengaturan**
   kalau mau AI mencari momen yang lebih pendek.
3. Klik **Atur, Pratinjau & Ekspor** di kartu **Kompilasi highlight**. Di sana kamu bisa
   mengubah urutan adegan (↑ ↓, atau **Urutkan sesuai waktu video**), mengeluarkan adegan,
   atau kembali ke editor untuk merapikan potongannya (✎).
4. Pratinjau memutar semua adegan berurutan, dengan format, kamera ikuti wajah, dan caption
   yang sama dengan hasil ekspor. Tanda di garis waktu menunjukkan pergantian adegan.
5. **Mulai Render Kompilasi** menghasilkan satu MP4. Antar adegan dipotong langsung (hard
   cut) dengan suara yang dihaluskan beberapa milidetik supaya tidak berbunyi klik. Caption
   tidak pernah menyeberang ke adegan berikutnya, dan kamera langsung pindah di tiap potongan.

Pratinjau tiap adegan disimpan sementara oleh helper, jadi mengubah urutan hanya perlu
menggabungkan ulang (beberapa detik), dan adegan yang sudah dipratinjau sendiri tidak
diunduh lagi. Total kompilasi maksimal 10 menit (Shorts dan Reels maks. 3 menit). File
.SRT/.VTT/.ASS juga mengikuti urutan adegan. Butuh helper 0.5.0 atau lebih baru.

## Mode gamer

Format **Vertikal, mode gamer** untuk video game dengan kamera wajah (webcam) di pojok:
gameplay mengisi 2/3 layar dan kamera wajah 1/3 sisanya, di bawah atau di atas (pilih
**Posisi kamera**). Caption selalu berada di area gameplay, jadi tidak menutupi wajah.

- Helper mencari kamera wajah sendiri: wajah yang diam di satu tempat paling lama (wajah
  di dalam game datang dan pergi). Gameplay diambil dari tengah layar setinggi penuh.
- Kurang pas? Di pratinjau, tekan **Atur area**, lalu geser kotak **Kamera** dan
  **Gameplay** (seret sudut kanan bawah untuk ukuran; bisa juga dengan tombol panah dan
  +/−). Bentuk kotak selalu mengikuti slotnya, dan hasil ekspor memotong persis seperti itu.
- Area yang kamu atur disimpan per video, jadi dipakai untuk semua klip dari video itu,
  termasuk ekspor massal. **Kembali ke otomatis** menghapusnya.

Butuh helper 0.6.0 atau lebih baru.

## Ekspor massal

**Ekspor massal** merender beberapa klip sekaligus, masing-masing jadi satu MP4 dengan
format dan caption yang sama. Pilih klipnya, lalu **Render**. Helper mengerjakannya satu per
satu; tiap klip bisa diunduh begitu selesai, atau semuanya sekaligus lewat **Unduh semua
(.zip)**. Nama file diberi nomor sesuai daftar klip (`01 - Judul.mp4`), jadi urutannya
tetap. Jalur wajah dan kamera dari pratinjau yang sudah pernah dibuka dipakai ulang.
Butuh helper 0.6.0 atau lebih baru.

## Pengembangan

```
npm install
npm run dev      # http://localhost:5173
npm test         # unit test logika transkrip & AI
npm run check    # cek tipe Svelte/TypeScript
npm run build    # hasil di dist/
```

Tampilan bergaya glassmorphism di atas kanvas arang hangat: cahaya oranye menyebar dari balik
panel, permukaan kaca tembus pandang dengan garis rambut terang di tepi atasnya, dan satu warna
aksen oranye `#f97316` untuk aksi utama. Blur latar hanya dipakai lapisan yang mengapung
(header, dialog, popover, toast); panel di dalam alur cukup memakai isian kaca agar tetap
ringan. Huruf [Outfit](https://fonts.google.com/specimen/Outfit) dengan fallback `system-ui`.
Token ada di `src/app.css`; komponen dasar (ikon, switch, segmented, dialog, menu) di
`src/components/ui/`. Ikon dari [Lucide](https://lucide.dev) lewat `ui/Icon.svelte`, satu
ketebalan garis untuk semua; tidak ada emoji sebagai ikon.

## Deploy ke GitHub Pages

1. Buat repo baru di GitHub dan push folder ini ke branch `main`.
2. Di repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Setiap push ke `main` akan menjalankan test, build, dan deploy otomatis
   (`.github/workflows/deploy.yml`). Situs muncul di `https://USERNAME.github.io/NAMA-REPO/`.
4. Jalankan helper dengan `--app https://USERNAME.github.io/REPO/`.

## Rencana berikutnya

- Pratinjau area crop "Ikuti Wajah" langsung di editor, dan layout split untuk dua pembicara.
- Tahap 3: input file video lokal dengan transkripsi Whisper di browser, suara hook, efek, musik.
