import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { CircleHelp, X } from "lucide-react";
import { useAuth } from "../auth";
import type { Role } from "../types";

/** Tutorial di dalam aplikasi (feedback tim 24 Okt 2026): tombol ? di topbar membuka langkah demi langkah untuk
 *  halaman yang sedang dibuka. Setiap langkah menyorot satu bagian layar; bagian yang tidak tampil (beda peran,
 *  beda status dokumen, atau tersembunyi di HP) dilewati. */

interface Step {
  target?: string;  // selector CSS; kosong = kartu di tengah layar
  title: string;
  body: string;
  roles?: Role[];  // hanya untuk peran ini
}

interface Tour { match: RegExp; name: string; steps: Step[] }

const SUBMITTERS: Role[] = ["PIC_KLIEN", "INTAKE_SUPPORT"];
const REVIEWERS: Role[] = ["FINANCE_REVIEWER", "SERVICE_LEAD"];

const TOURS: Tour[] = [
  {
    match: /^\/unggah/, name: "Pembuatan voucher",
    steps: [
      { title: "Membuat pengajuan voucher", body: "Alurnya: isi data pengajuan → unggah invoice → AI membaca total dan menyarankan pajak → Anda memeriksa di halaman berikutnya → ajukan ke Finance Reviewer." },
      { target: "#client", title: "1. Klien", body: "Pilih perusahaan yang mengajukan voucher. Hanya perusahaan yang ditugaskan kepada Anda yang muncul." },
      { target: "#type", title: "Kategori", body: "Vendor, Reimburse, atau Lainnya. Dipakai untuk filter dashboard, tidak dicetak di voucher." },
      { target: "#submitted", title: "Tanggal pengajuan", body: "Bawaannya hari ini. Ubah bila invoice diterima di tanggal lain." },
      { target: "[data-tour=submitter]", title: "2. Diajukan oleh", body: "Nama, jabatan, dan tanda tangan pengaju yang dicetak di voucher. Pilih profil akun PIC atau isi manual." },
      { target: "[data-tour=approver]", title: "3. Disetujui oleh", body: "Pemberi persetujuan dari pihak klien (boleh dikosongkan). Daftarnya diatur di Data Referensi → Penanda tangan." },
      { target: ".mode-cards", title: "4. Mode baca AI", body: "Total saja (bawaan): satu baris voucher per invoice, lebih hemat. Rincian: satu baris per barang/jasa. Mode masih bisa diganti nanti." },
      { target: "details.extras", title: "Fitur tambahan", body: "Saluran dan tenggat, rekening tujuan, dan \"Atur pajak secara otomatis\": saran PPN dan PPh dari AI langsung terpasang (tetap bisa diubah)." },
      { target: ".drop", title: "5. File bukti", body: "Seret atau ketuk untuk memilih PDF/foto invoice. Satu PDF boleh berisi beberapa invoice beserta Faktur Pajak dan timesheet: AI memisahkannya per invoice." },
      { target: ".upload-form .actions .btn.primary", title: "Simpan draf & lanjutkan", body: "AI mulai membaca. Anda langsung dibawa ke halaman draf untuk memeriksa data, pajak, dan pratinjau voucher." },
    ],
  },
  {
    match: /^\/dokumen\/[^/]+$/, name: "Detail dokumen",
    steps: [
      { title: "Halaman detail dokumen", body: "Di kiri bukti asli, di kanan data hasil AI. Tutorial ini menunjukkan bagian yang tampil untuk dokumen ini." },
      { target: ".pdf-pane", title: "Bukti asli", body: "PDF atau foto invoice yang diunggah. Bila satu voucher berisi beberapa invoice, yang tampil adalah bukti yang sedang dipilih." },
      { target: ".sec-nav", title: "Navigasi cepat", body: "Daftar bagian halaman beserta statusnya. Bagian berwarna kuning/merah masih perlu diisi atau diperbaiki; klik untuk melompat ke sana." },
      { target: ".tabs[aria-label=Bukti]", title: "Bukti per invoice", body: "Setiap invoice punya tab sendiri: data, uraian, dan pajaknya diatur per tab. \"Pisahkan otomatis (AI)\" memecah PDF yang berisi beberapa invoice." },
      { target: "#sec-data", title: "Informasi utama", body: "Vendor, nomor, tanggal, dan total hasil baca AI. Cocokkan dengan bukti asli; bila ada yang salah, ubah lalu tekan Simpan bukti." },
      { target: "#sec-uraian", title: "Uraian transaksi", body: "Teks yang dicetak sebagai satu baris di voucher, mis. \"Management Fee & Development Driver A\". Wajib diisi sebelum diajukan." },
      { target: "#sec-rincian", title: "Rincian barang/jasa", body: "Mode rincian: setiap baris dicetak di voucher. Jumlah baris harus sama dengan total invoice." },
      { target: "#sec-pajak", title: "Pajak", body: "AI menyarankan PPN dan potongan PPh dari isi invoice. PPN tercetak dipakai apa adanya. PPh 23 dihitung dari imbalan jasa vendor (bagian yang kena PPN), bukan dari penggantian gaji/BPJS/lembur. Periksa, ubah bila perlu, lalu Terapkan.", roles: SUBMITTERS },
      { target: "#sec-pratinjau", title: "Pratinjau voucher", body: "Simulasi voucher diperbarui setiap kali data atau pajak disimpan: baris invoice, baris potongan PPh, dan total dibayarkan." },
      { target: "#sec-penanda", title: "Penanda tangan", body: "Kotak tanda tangan di voucher: diajukan oleh dan disetujui oleh." },
      { target: "#sec-opsi", title: "Mode AI & fitur", body: "Ganti mode baca AI, fitur rekening, atau pajak otomatis selama pengajuan belum diajukan." },
      { target: "#sec-kirim", title: "Ajukan untuk direview", body: "Aktif setelah kendala wajib beres, uraian terisi, dan pajak setiap bukti dipilih. Simpan perubahan dulu sebelum mengajukan.", roles: SUBMITTERS },
      { target: "#sec-keputusan", title: "Keputusan reviewer", body: "Periksa data, pajak, dan simulasi voucher. Setujui untuk menerbitkan voucher resmi, atau Kembalikan ke PIC dengan alasan yang jelas.", roles: REVIEWERS },
    ],
  },
  {
    match: /^\/antrean/, name: "Dashboard antrean",
    steps: [
      { target: ".status-strip", title: "Saring menurut status", body: "Klik status untuk menampilkan dokumen dengan status itu saja." },
      { target: ".filters", title: "Filter", body: "Saring menurut klien, reviewer, atau kata kunci." },
      { target: "table.docs", title: "Daftar dokumen", body: "Urutan bawaan menurut tenggat. Klik judul kolom untuk mengurutkan; klik Request ID untuk membuka dokumen." },
      { target: ".load-panel", title: "Beban reviewer", body: "Jumlah dokumen yang sedang ditangani setiap Finance Reviewer.", roles: ["SERVICE_LEAD"] },
    ],
  },
  {
    match: /^\/(pengajuan|peninjauan|voucher|riwayat|cari)/, name: "Daftar dokumen",
    steps: [
      { target: ".filters", title: "Filter", body: "Saring daftar menurut status, klien, atau kata kunci." },
      { target: "table.docs, table.table", title: "Daftar", body: "Klik judul kolom untuk mengurutkan. Klik Request ID atau tombol Buka untuk melihat detailnya." },
    ],
  },
  {
    match: /^\/dashboard/, name: "Dashboard",
    steps: [
      { target: ".kpi-status", title: "Dokumen per status", body: "Jumlah dokumen di setiap status. Klik salah satu untuk membuka daftarnya." },
      { target: ".content .card.panel", title: "Ringkasan kinerja", body: "Grafik dan angka kinerja pengajuan sesuai peran Anda." },
    ],
  },
  {
    match: /^\/referensi\/tarif-pajak/, name: "Tarif pajak",
    steps: [
      { target: "table", title: "Tabel tarif pajak", body: "Tarif PPh dengan dan tanpa NPWP yang dipakai sistem saat menghitung potongan. Perubahan tarif tidak mengubah draf yang sudah dihitung." },
    ],
  },
];

// Pengenalan umum: dipakai di halaman tanpa tutorial khusus, dan sebagai penutup tutorial halaman
const GENERAL: Step[] = [
  { target: ".side nav", title: "Menu", body: "Pindah halaman dari sini. Menu yang tampil menyesuaikan peran Anda." },
  { target: ".side a[href='/unggah']", title: "Pembuatan Voucher", body: "Mulai pengajuan baru dari invoice vendor atau reimburse.", roles: SUBMITTERS },
  { target: ".side a[href='/pengajuan']", title: "Pengajuan Saya", body: "Status semua pengajuan Anda: draf, siap ditinjau, ada kendala, disetujui.", roles: SUBMITTERS },
  { target: ".side a[href='/antrean']", title: "Dashboard Antrean", body: "Semua dokumen yang menunggu ditinjau, urut menurut tenggat.", roles: REVIEWERS },
  { target: ".side a[href='/peninjauan']", title: "Peninjauan Saya", body: "Dokumen yang ditugaskan kepada Anda.", roles: ["FINANCE_REVIEWER"] },
  { target: ".top form[role=search]", title: "Cari dokumen", body: "Ketik Request ID atau nama vendor lalu tekan Enter." },
  { target: ".fab", title: "Asisten AI", body: "Tanya soal SOP, status invoice, atau cara memakai aplikasi." },
  { target: ".user-link", title: "Akun", body: "Profil \"Diajukan oleh\", tanda tangan elektronik, dan hubungkan bot Telegram." },
];

const SEEN_KEY = "amiga.tour.seen";

function visible(el: Element | null): el is HTMLElement {
  if (!(el instanceof HTMLElement)) return false;
  const r = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && r.right > 0 && r.left < window.innerWidth && style.visibility !== "hidden";
}

function find(target?: string): HTMLElement | null {
  if (!target) return null;
  try {
    const found = Array.from(document.querySelectorAll(target)).find(visible);
    return found instanceof HTMLElement ? found : null;
  } catch {
    return null;
  }
}

function tourFor(pathname: string) {
  return TOURS.find((t) => t.match.test(pathname));
}

export function TourButton() {
  const { pathname } = useLocation();
  const { has } = useAuth();
  const [steps, setSteps] = useState<Step[] | null>(null);
  const [seen, setSeen] = useState(() => {
    try { return localStorage.getItem(SEEN_KEY) === "1"; } catch { return true; }
  });

  useEffect(() => { setSteps(null); }, [pathname]);

  const start = () => {
    const tour = tourFor(pathname);
    const allowed = (s: Step) => !s.roles || has(...s.roles);
    const own = (tour?.steps ?? []).filter(allowed);
    const general = GENERAL.filter(allowed);
    const hint = "Lanjut atau panah kanan untuk langkah berikutnya, Esc untuk menutup. Tombol ? bisa dibuka lagi kapan saja.";
    const body = own.length ? own : general;
    // Kartu pembuka: langkah pertama tutorial halaman bila tanpa sorotan, selain itu kartu umum
    const intro: Step = body[0] && !body[0].target
      ? { ...body[0], body: `${body[0].body} ${hint}` }
      : { title: tour ? `Tutorial: ${tour.name}` : "Tutorial AMIGA Robot Admin", body: hint };
    const rest = body[0] && !body[0].target ? body.slice(1) : body;
    // Langkah yang bagiannya tidak tampil di layar dilewati; kartu tanpa target selalu tampil
    const list = [intro, ...rest].filter((s) => !s.target || find(s.target));
    setSteps(list);
    if (!seen) {
      setSeen(true);
      try { localStorage.setItem(SEEN_KEY, "1"); } catch { /* abaikan */ }
    }
  };

  return (
    <>
      <button type="button" className={`btn ghost sm icon-btn tour-btn${seen ? "" : " pulse"}`} onClick={start}
              aria-label="Tutorial halaman ini" title="Tutorial halaman ini">
        <CircleHelp />
      </button>
      {steps && steps.length > 0 && <TourOverlay steps={steps} onClose={() => setSteps(null)} />}
    </>
  );
}

interface Box { top: number; left: number; width: number; height: number }

function TourOverlay({ steps, onClose }: { steps: Step[]; onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [cardPos, setCardPos] = useState<{ top: number; left: number } | null>(null);
  const step = steps[index];
  const last = index === steps.length - 1;

  const next = useCallback(() => (last ? onClose() : setIndex((i) => i + 1)), [last, onClose]);
  const prev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  // Gulir bagian yang disorot ke tengah layar
  useEffect(() => {
    const el = find(step.target);
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
    cardRef.current?.focus();
  }, [step]);

  // Ikuti posisi bagian itu saat halaman bergulir, berubah ukuran, atau masih beranimasi
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const el = find(step.target);
      if (el) {
        // Koordinat halaman (bukan layar): sorotan ikut bergulir bersama halaman tanpa menunggu frame berikutnya
        const r = el.getBoundingClientRect();
        const pad = 6;
        const next = { top: r.top + window.scrollY - pad, left: r.left + window.scrollX - pad,
                       width: r.width + pad * 2, height: r.height + pad * 2 };
        setBox((b) => (b && Math.abs(b.top - next.top) < 0.5 && Math.abs(b.left - next.left) < 0.5
          && Math.abs(b.width - next.width) < 0.5 && Math.abs(b.height - next.height) < 0.5 ? b : next));
      } else {
        setBox(null);
      }
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [step]);

  // Kartu di bawah bagian yang disorot bila muat, selain itu di atasnya; selalu di dalam layar
  useLayoutEffect(() => {
    const card = cardRef.current;
    if (!card) return;
    const w = card.offsetWidth, h = card.offsetHeight, vw = window.innerWidth, vh = window.innerHeight, gap = 12;
    if (!box || vw <= 600) {
      setCardPos(null);  // tengah layar (atau lembar bawah di HP), lewat CSS
      return;
    }
    // Hitung di koordinat layar (bagian yang disorot sudah digulir ke tengah), simpan di koordinat halaman
    const sy = window.scrollY, sx = window.scrollX;
    const boxTop = box.top - sy;
    let top = boxTop + box.height + gap;
    if (top + h > vh - 8) top = boxTop - h - gap;
    if (top < 8) top = Math.min(Math.max(8, vh - h - 8), boxTop + gap);
    const left = Math.min(Math.max(8, box.left - sx), vw - w - 8);
    setCardPos({ top: top + sy, left: left + sx });
  }, [box, index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev, onClose]);

  return createPortal(
    <div className="tour" aria-live="polite">
      {/* Klik di luar kartu tidak menutup tutorial, supaya tidak tertutup tanpa sengaja */}
      {box ? <div className="tour-spot" style={box} /> : <div className="tour-dim" />}
      <div ref={cardRef} className={`tour-card${cardPos ? "" : " centered"}`} style={cardPos ?? undefined}
           role="dialog" aria-modal="true" aria-labelledby="tour-title" tabIndex={-1}>
        <button type="button" className="btn ghost sm icon-btn tour-close" onClick={onClose} aria-label="Tutup tutorial"><X /></button>
        <small className="tour-count">Langkah {index + 1} dari {steps.length}</small>
        <h3 id="tour-title">{step.title}</h3>
        <p>{step.body}</p>
        <div className="tour-actions">
          <div className="tour-dots" aria-hidden="true">
            {steps.map((_, i) => <span key={i} className={i === index ? "on" : ""} />)}
          </div>
          {index > 0 && <button type="button" className="btn sm" onClick={prev}>Sebelumnya</button>}
          <button type="button" className="btn primary sm" onClick={next}>{last ? "Selesai" : "Lanjut"}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
