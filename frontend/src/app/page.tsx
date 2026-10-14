export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-6 text-center">
      <div className="max-w-xl p-8 bg-white rounded-xl border border-slate-200 shadow-sm">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 mb-4">
          AMIGA Robot Admin PoC
        </div>
        <h1 className="text-2xl font-bold text-[#0B3558] tracking-tight mb-2">
          Intelligent Invoice-to-Voucher Processing
        </h1>
        <p className="text-sm text-slate-600 mb-6">
          Sistem otomasi verifikasi invoice vendor menjadi voucher pembayaran resmi dengan penegakan Segregation of Duties (SoD) dan jejak audit permanen.
        </p>
        <div className="flex items-center justify-center gap-3">
          <a
            href="/queue"
            className="px-4 py-2 text-sm font-medium text-white bg-[#006BFF] hover:bg-[#0055CC] rounded-lg transition-colors"
          >
            Masuk ke Antrean
          </a>
          <a
            href="/upload"
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
          >
            Unggah Invoice
          </a>
        </div>
      </div>
    </main>
  );
}
