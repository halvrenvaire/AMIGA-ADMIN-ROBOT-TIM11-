export {};

/**
 * System testing per fitur (TS-xxx), dipetakan ke sheet "System Testing - Execution Data"
 * pada Test Summary Report. Memakai invoice fixture sendiri (cypress/fixtures/sys_*.pdf)
 * supaya tidak dianggap duplikat dari invoice UAT.
 */

const REVIEWER_EMAIL: Record<string, string> = {
  "Dewi (Finance Reviewer)": "reviewer1@amiga.test",
  "Agus (Finance Reviewer)": "reviewer2@amiga.test",
  "Yoga (Intake + Reviewer)": "multi@amiga.test",
};
const docs: Record<string, { id: string; requestId: string }> = {};
const stamp = Date.now();
const NEW_USER = `qa.${stamp}@amiga.test`;
const NEW_USER_PASSWORD = "QaAmiga2026!";

function upload(email: string, fixture: string, key: string) {
  cy.visitAs(email, "/unggah");
  cy.get("main input[type=file]").selectFile(`cypress/fixtures/${fixture}`, { force: true });
  cy.contains("button", "Preview").click();
  cy.contains("button", "Kirim ke antrean").click();
  cy.contains("Draf dibuat").find("b").invoke("text").then((requestId) => {
    cy.contains("a", "Buka draf").click();
    cy.location("pathname").should("match", /^\/dokumen\/[0-9a-f-]+$/).then((path) => {
      docs[key] = { id: path.split("/").pop()!, requestId };
    });
  });
}

const waitStatus = (label: string) => cy.contains(".page-head .badge", label, { timeout: 30_000 });
const meta = (label: string) => cy.contains(".meta dt", label).next("dd");

/** Draf hasil AI dikirim PIC ke Finance Reviewer (alur draf, feedback owner). */
function submitDraft() {
  waitStatus("Draf");
  // PIC wajib memilih pajak sendiri (AI hanya menyarankan): pilih "Tanpa potongan" bila belum dipilih
  cy.get(".tax-panel").then(($p) => {
    if ($p.text().includes("belum dipilih")) {
      cy.get("#tax-code").select("Tanpa potongan");
      cy.contains("button", "Terapkan pajak").click();
      cy.contains(".alert", "diterapkan");
    }
  });
  cy.contains(".decision button", "Kirim ke reviewer").click();
  cy.contains(".alert", "Terkirim ke Finance Reviewer");
}
const reviewer = () => meta("Finance Reviewer").invoke("text").then((n) => REVIEWER_EMAIL[n]);
const password = () => cy.env(["SEED_PASSWORD"], { log: false }).then((e) => e.SEED_PASSWORD as string);

describe("System Testing AMIGA Robot Admin", () => {
  // --- Login ---
  it("TS-001 Login dengan akun valid", () => {
    cy.visit("/login");
    password().then((pw) => {
      cy.get("#email").type("lead@amiga.test");
      cy.get("#password").type(pw, { log: false });
    });
    cy.contains("button", "Masuk").click();
    cy.location("pathname").should("eq", "/dashboard");
    cy.get(".hero h1").should("contain.text", "Hendra");
    cy.get(".user").should("contain.text", "Hendra");
  });

  it("TS-002 Login dengan password salah", () => {
    cy.visit("/login");
    cy.get("#email").type("lead@amiga.test");
    cy.get("#password").type("salah-sekali");
    cy.contains("button", "Masuk").click();
    cy.contains(".alert", "Email atau password salah");
    cy.location("pathname").should("eq", "/login");
  });

  it("TS-003 Login tanpa mengisi data", () => {
    cy.visit("/login");
    cy.contains("button", "Masuk").click();
    cy.get("#email:invalid").should("exist");
    cy.get("#password:invalid").should("exist");
    cy.location("pathname").should("eq", "/login");
  });

  it("TS-004 Sesi dengan token tidak valid diarahkan ke login", () => {
    cy.visit("/antrean", { onBeforeLoad: (win) => win.localStorage.setItem("amiga.token", "token-palsu") });
    cy.location("pathname").should("eq", "/login");
  });

  // --- Hak akses & navigasi ---
  it("TS-005 Menu sesuai peran dan URL terlarang dialihkan", () => {
    cy.visitAs("pic.alpha@amiga.test", "/antrean");
    cy.location("pathname").should("eq", "/dashboard");
    cy.get(".nav").should("not.contain.text", "Dashboard Antrean").and("contain.text", "Pembuatan Voucher");
    cy.get(".nav").should("contain.text", "Asisten AI"); // Asisten untuk semua peran, data sesuai klien
    cy.get(".fab").should("exist");
  });

  // --- Unggah dokumen ---
  it("TS-006 Unggah invoice PDF valid", () => {
    upload("pic.alpha@amiga.test", "sys_normal_a.pdf", "a");
    cy.then(() => expect(docs.a.requestId).to.match(/^REQ-\d{8}-[0-9A-F]{6}$/));
    submitDraft();
    waitStatus("Siap ditinjau");
  });

  it("TS-007 Unggah file selain PDF ditolak", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.get("main input[type=file]").selectFile("cypress/fixtures/bukan_pdf.txt", { force: true });
    cy.contains(".alert", "harus berformat PDF");
    cy.get(".file-list li").should("not.exist");
  });

  it("TS-008 Unggah PDF lebih dari 5 halaman ditolak", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.get("main input[type=file]").selectFile("cypress/fixtures/enam_halaman.pdf", { force: true });
    cy.contains("button", "Preview").click();
    cy.contains("button", "Kirim ke antrean").click();
    cy.contains(".alert", "6 halaman").and("contain.text", "Maksimal 5 halaman");
  });

  it("TS-009 Kategori voucher dan nama Diajukan oleh bisa dipilih", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.contains("h1", "Pembuatan voucher");
    cy.get("#type option").then((opts) => {
      expect([...opts].map((o) => o.textContent)).to.deep.eq(
        ["Voucher Pengeluaran Vendor", "Voucher Pengeluaran Reimburse", "Lainnya"]);
    });
    cy.get("#type").select("Voucher Pengeluaran Reimburse");
    cy.get("#submitter-name").should("have.value", "Rina (PIC Alpha)").clear().type("Andi Wijaya");
    cy.get(".company-box").should("contain.text", "Andi Wijaya");
    cy.get("main input[type=file]").selectFile("cypress/fixtures/sys_normal_b.pdf", { force: true });
    cy.contains("button", "Preview").click();
    cy.contains(".meta dt", "Kategori").next("dd").should("have.text", "Voucher Pengeluaran Reimburse");
    cy.contains(".meta dt", "Diajukan oleh").next("dd").should("contain.text", "Andi Wijaya");
    cy.contains("button", "Kembali ubah").click();
    // Filter kategori di Pengajuan Saya
    cy.visitAs("pic.alpha@amiga.test", "/pengajuan");
    cy.get("select[aria-label=Kategori]").select("Lainnya");
    cy.contains(".empty", "Belum ada dokumen yang cocok");
  });

  // --- Dashboard antrean ---
  it("TS-010 Dashboard Antrean menampilkan semua widget", () => {
    cy.visitAs("lead@amiga.test", "/antrean");
    cy.get(".stats .stat").should("have.length", 4);
    cy.get(".status-strip button").should("have.length", 8);
    cy.contains("h2", "Beban reviewer");
    cy.contains("h2", "Antrean dokumen");
    cy.then(() => cy.contains("table", docs.a.requestId));
  });

  it("TS-011 Filter status pada Dashboard", () => {
    cy.visitAs("lead@amiga.test", "/antrean");
    cy.contains(".status-strip button", "Siap ditinjau").click();
    cy.get("table.docs tbody tr").each((row) => cy.wrap(row).find(".badge").should("have.text", "Siap ditinjau"));
  });

  it("TS-012 Pencarian Request ID di top bar", () => {
    cy.then(() => {
      cy.visitAs("lead@amiga.test", "/antrean");
      cy.get("form[role=search] input").type(`${docs.a.requestId}{enter}`);
      cy.location("pathname").should("eq", "/cari");
      cy.get("table.docs tbody tr").should("have.length", 1).and("contain.text", docs.a.requestId);
    });
  });

  // --- Peninjauan ---
  it("TS-013 Layar peninjauan split-screen PDF dan data", () => {
    cy.then(() => {
      cy.visitAs("reviewer1@amiga.test", `/dokumen/${docs.a.id}`);
      cy.get(".pdf-pane iframe", { timeout: 15_000 }).should("have.attr", "src").and("match", /^blob:/);
      meta("Nama vendor").should("contain.text", "PT Konsultan Prima");
      cy.get("table.compact tbody tr").should("have.length", 4); // 3 baris + jumlah rincian
      cy.get("#f-vendor_name").should("not.exist"); // reviewer tidak mengedit
    });
  });

  it("TS-014 PIC mengedit draf per invoice; kendala menahan pengiriman ke reviewer", () => {
    upload("pic.alpha@amiga.test", "sys_normal_b.pdf", "b");
    waitStatus("Draf");
    cy.get("#f-total").invoke("val").then((original) => {
      cy.get("#f-total").clear().type("6000000");
      cy.contains(".decision button", "Simpan bukti 1").click();
      cy.contains(".issue", "CALCULATION_DISCREPANCY");
      waitStatus("Ada kendala");
      cy.contains(".decision button", "Kirim ke reviewer").should("be.disabled");
      // Kembalikan ke nilai semula: lolos lagi dan bisa dikirim
      cy.get("#f-total").clear().type(String(original));
      cy.contains(".decision button", "Simpan bukti 1").click();
      cy.contains(".alert", "Tersimpan dan lolos verifikasi ulang");
      submitDraft();
      waitStatus("Siap ditinjau");
    });
  });

  it("TS-044 Simulasi voucher sebelum dikirim", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.b.id}`);
      cy.contains("button", "Lihat simulasi voucher").click();
      cy.get(".modal iframe", { timeout: 15_000 }).should("have.attr", "src").and("match", /^blob:/);
      cy.get(".modal button[aria-label=Tutup]").click();
      cy.token("pic.alpha@amiga.test").then((t) =>
        cy.request({ url: `/api/documents/${docs.b.id}/voucher-preview`, headers: { Authorization: `Bearer ${t}` } })
          .its("headers.content-type").should("eq", "application/pdf"));
    });
  });

  it("TS-015 Kembalikan ke PIC wajib disertai alasan", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.b.id}`);
      reviewer().then((email) => {
        cy.visitAs(email, `/dokumen/${docs.b.id}`);
        cy.contains(".decision button", "Kembalikan ke PIC").click();
        cy.contains(".modal button", "Kembalikan").should("be.disabled");
        cy.get("#reason").type("Mohon lampirkan invoice dengan total yang benar.");
        cy.contains(".modal button", "Kembalikan").click();
        cy.contains(".page-head .badge", "Ada kendala");
        cy.contains(".issue", "RETURNED_BY_REVIEWER").and("contain.text", "total yang benar");
      });
    });
  });

  it("TS-016 Tandai bukan duplikat oleh reviewer", () => {
    upload("pic.alpha@amiga.test", "sys_dup_c.pdf", "c1");
    submitDraft();
    waitStatus("Siap ditinjau");
    upload("pic.alpha@amiga.test", "sys_dup_c.pdf", "c2");
    waitStatus("Draf");
    cy.contains(".issue", "POSSIBLE_DUPLICATE");
    submitDraft(); // kemungkinan duplikat diputuskan reviewer
    cy.then(() => {
      cy.visitAs("reviewer1@amiga.test", `/dokumen/${docs.c2.id}`);
      cy.contains("button", "Tandai bukan duplikat").click();
      cy.get("#reason").type("Tagihan termin kedua, sudah dikonfirmasi ke vendor.");
      cy.contains(".modal button", "Tandai").click();
      cy.contains(".page-head .badge", "Siap ditinjau");
    });
  });

  // --- Service Lead ---
  it("TS-017 Service Lead mengalihkan reviewer", () => {
    cy.then(() => {
      cy.visitAs("lead@amiga.test", `/dokumen/${docs.c2.id}`);
      meta("Finance Reviewer").invoke("text").then((before) => {
        cy.contains("button", "Alihkan reviewer").click();
        cy.get(".modal input#reason").should("be.enabled").click().type("Pemerataan beban");
        cy.contains(".modal button", "Alihkan").click();
        cy.contains(".alert", "Reviewer dialihkan");
        meta("Finance Reviewer").should("not.have.text", before);
        cy.get(".page-head .badge").should("have.text", "Siap ditinjau");
      });
    });
  });

  it("TS-028 Pilihan reviewer pengalihan tidak memuat pengunggah (SoD)", () => {
    upload("multi@amiga.test", "sys_multi_d.pdf", "d"); // multi@ = Intake + Reviewer
    submitDraft();
    waitStatus("Siap ditinjau");
    cy.then(() => {
      cy.visitAs("lead@amiga.test", `/dokumen/${docs.d.id}`);
      meta("Finance Reviewer").invoke("text").then((current) => {
        cy.contains("button", "Alihkan reviewer").click();
        cy.get("#rv option").should("have.length.at.least", 1).each((opt) => {
          expect(opt.text()).not.to.contain("Yoga");
          expect(opt.text()).not.to.contain(current);
        });
        cy.contains(".modal button", "Batal").click();
      });
    });
  });

  // --- Voucher & riwayat ---
  it("TS-018 Setujui dokumen dan voucher terbentuk", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.a.id}`);
      reviewer().then((email) => {
        cy.visitAs(email, `/dokumen/${docs.a.id}`);
        // Rekening vendor belum terverifikasi di data E2E: reviewer wajib mengonfirmasi pengecekan
        cy.get(".account-confirm input[type=checkbox]").check();
        cy.contains(".decision button", "Setujui").click();
        cy.contains(".alert", /Disetujui\. Voucher VCH\/\d{4}\/\d{2}\/\d{4}/);
      });
    });
  });

  it("TS-019 Pratinjau voucher dengan Batas Otorisasi", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.a.id}/voucher`);
      cy.contains(".alert", "Batas Otorisasi");
      cy.get(".pdf-pane iframe", { timeout: 15_000 }).should("have.attr", "src").and("match", /^blob:/);
      cy.token("pic.alpha@amiga.test").then((t) =>
        cy.request({ url: `/api/documents/${docs.a.id}/voucher`, headers: { Authorization: `Bearer ${t}` } })
          .its("headers.content-type").should("eq", "application/pdf"));
    });
  });

  it("TS-020 Riwayat dokumen menampilkan kronologi audit", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.a.id}/riwayat`);
      cy.contains(".timeline", "Invoice diunggah");
      cy.contains(".timeline", "AI selesai membaca invoice");
      cy.contains(".timeline", "Disetujui Finance Reviewer");
      cy.contains(".timeline", "Voucher dibuat");
    });
  });

  // --- Asisten AI ---
  it("TS-021 Asisten menjawab pertanyaan SOP", () => {
    cy.visitAs("reviewer1@amiga.test", "/antrean");
    cy.get(".fab").click();
    cy.contains(".suggest button", "Apa arti MISSING_EVIDENCE?").click();
    cy.contains(".chat .msg.bot .msg-meta", "kutipan SOP", { timeout: 45_000 });
  });

  // --- System Admin ---
  // Peran dan perusahaan dipilih lewat MultiSelect: buka daftarnya (bila belum terbuka), lalu klik opsinya
  const pick = (id: string, label: string) => {
    cy.get(`#${id}`).closest(".ms").then(($ms) => { if (!$ms.find(".ms-menu").length) cy.get(`#${id}`).click(); });
    cy.get(`#${id}`).closest(".ms").contains(".ms-menu li", label).click();
  };
  const unpick = (id: string, label: string) =>
    cy.get(`#${id}`).closest(".ms").find(`button[aria-label="Hapus ${label}"]`).click();

  it("TS-022 Admin menambahkan pengguna dengan peran ganda", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("button", "Tambah pengguna").click();
    cy.get("#u-name").type("QA Tester");
    cy.get("#u-email").type(NEW_USER);
    cy.get("#u-pass").type(NEW_USER_PASSWORD, { log: false });
    pick("u-roles", "Intake Support");
    pick("u-roles", "Finance Reviewer");
    pick("u-clients", "PT Klien Alpha");
    cy.contains(".modal .alert", "semua perusahaan");
    cy.contains(".modal button", "Simpan").click();
    cy.contains("tr", NEW_USER).should("contain.text", "Intake Support").and("contain.text", "Finance Reviewer")
      .and("contain.text", "Review: semua perusahaan");
  });

  it("TS-040 Admin tidak menugaskan perusahaan untuk Finance Reviewer dan Service Lead", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("button", "Tambah pengguna").click();
    pick("u-roles", "Finance Reviewer");
    cy.contains(".modal label", "Perusahaan yang ditugaskan").should("not.exist");
    cy.contains(".modal .alert", "semua perusahaan");
    unpick("u-roles", "Finance Reviewer");
    pick("u-roles", "Service Lead");
    cy.contains(".modal label", "Perusahaan yang ditugaskan").should("not.exist");
    cy.contains(".modal .alert", "Service Lead mengawasi semua invoice");
    pick("u-roles", "Intake Support");
    cy.contains(".modal label", "Perusahaan yang ditugaskan");
    cy.contains(".modal button", "Batal").click();
  });

  it("TS-023 Kombinasi peran terlarang tidak bisa dipilih", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("button", "Tambah pengguna").click();
    pick("u-roles", "PIC Klien");
    cy.contains(".ms-menu li", "Intake Support").should("have.attr", "aria-disabled", "true")
      .and("contain.text", "Tidak bisa digabung dengan PIC Klien").click();
    cy.get("#u-roles").closest(".ms").find(".ms-chip").should("have.length", 1);
    unpick("u-roles", "PIC Klien");
    pick("u-roles", "System Admin");
    cy.contains(".ms-menu li", "Finance Reviewer").should("have.attr", "aria-disabled", "true");
    cy.contains(".modal button", "Batal").click();
  });

  it("TS-024 Akun dinonaktifkan tidak bisa login", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("tr", NEW_USER).contains("button", "Nonaktifkan").click();
    cy.contains("tr", NEW_USER).should("contain.text", "Nonaktif");
    cy.visit("/login", { onBeforeLoad: (win) => win.localStorage.removeItem("amiga.token") });
    cy.get("#email").type(NEW_USER);
    cy.get("#password").type(NEW_USER_PASSWORD, { log: false });
    cy.contains("button", "Masuk").click();
    cy.contains(".alert", "dinonaktifkan");
  });

  it("TS-025 Admin tidak bisa mengubah akunnya sendiri", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("tr", "admin@amiga.test").within(() => {
      cy.contains("button", "Ubah").should("be.disabled");
      cy.contains("button", "Nonaktifkan").should("be.disabled");
    });
  });

  it("TS-026 Nama klien duplikat ditolak", () => {
    cy.visitAs("admin@amiga.test", "/admin/klien");
    cy.get("input[aria-label=\"Nama klien baru\"]").type("pt klien alpha");
    cy.contains("button", "Tambah").click();
    cy.contains(".alert", "sudah terdaftar");
  });

  // --- Fitur tambahan permintaan owner (14 Okt 2026) ---
  it("TS-029 Dashboard metrik menampilkan KPI status, tren, dan panel kinerja", () => {
    cy.visitAs("lead@amiga.test", "/dashboard");
    cy.get(".kpi-status .kpi-mini").should("have.length", 8);
    cy.contains(".stat", "Invoice masuk").find(".stat-val").invoke("text").then((t) => expect(Number(t)).to.be.greaterThan(0));
    cy.contains("h2", "Tren harian");
    cy.get(".recharts-line").should("have.length", 3);
    cy.contains("h2", "Kecepatan proses");
    cy.contains("h2", "Kualitas & kendala");
    cy.contains("h2", "Nilai pembayaran");
    cy.contains(".seg button", "7 hari").click();
    cy.contains("p", "Kinerja back office");
    cy.contains(".kpi-mini", "Siap ditinjau").click();
    cy.location("search").should("eq", "?status=READY_FOR_REVIEW");
  });

  it("TS-030 PIC mendaftarkan vendor; nama yang sudah ada tidak perlu ditambahkan", () => {
    cy.visitAs("pic.alpha@amiga.test", "/referensi/vendor");
    cy.contains("button", "Tambah vendor").click();
    cy.get("#v-name").type("PT Vendor Uji Sistem");
    cy.get("#v-npwp").type("01.234.567.8-901.000");
    cy.get("#v-bank_name").type("BCA");
    cy.get("#v-account_no").type("5550001111");
    cy.contains(".modal button", "Simpan").click();
    cy.contains("tr", "PT Vendor Uji Sistem").should("contain.text", "5550001111");
    cy.contains("button", "Tambah vendor").click();
    cy.get("#v-name").type("pt. VENDOR uji-sistem");
    cy.contains(".modal .alert", "sudah terdaftar");
    cy.contains(".modal button", "Simpan").should("be.disabled");
  });

  it("TS-031 PIC mendaftarkan penanda tangan; default terpilih otomatis saat unggah", () => {
    cy.visitAs("pic.alpha@amiga.test", "/referensi/penanda-tangan");
    cy.contains("section h2", "Disetujui oleh").closest("section").contains("button", "Tambah").click();
    cy.get("#s-name").type("Dian Pratama");
    cy.get("#s-pos").type("Bendahara");
    cy.contains(".modal button", "Simpan").click();
    cy.contains("section h2", "Disetujui oleh").closest("section").should("contain.text", "Dian Pratama");
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    // Default = satu kotak "Disetujui oleh"; "Diajukan oleh" = perusahaan
    cy.get(".approver-row").should("have.length", 1);
    cy.get(".approver-row select").find("option:selected").should("contain.text", "Dian Pratama");
    cy.get(".company-box").should("contain.text", "PT Klien Alpha");
  });

  it("TS-032 Penanda tangan dokumen bisa diubah sebelum voucher terbit", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.c1.id}`);
      cy.contains("section", "Penanda tangan voucher").within(() => {
        cy.contains("button", "Ubah").click();
        cy.contains("button", "Tambah kotak tanda tangan").click();
        cy.get(".approver-row select").last().should("be.enabled").select("Dian Pratama · Bendahara");
        cy.contains("button", "Simpan").click();
      });
      cy.contains(".alert", "Penanda tangan voucher diperbarui");
      cy.contains("section", "Penanda tangan voucher").should("contain.text", "Dian Pratama").and("contain.text", "Bendahara");
    });
  });

  it("TS-033 Manajemen voucher: filter dan pengelompokan", () => {
    cy.visitAs("reviewer1@amiga.test", "/voucher");
    cy.get("table.docs tr.group-row").should("have.length.at.least", 1).first().should("contain.text", "PT Klien Alpha");
    cy.get("select[aria-label=Kelompokkan]").select("Status");
    cy.get("tr.group-row").should("contain.text", "Disetujui");
    // Voucher dari TS-018 (disetujui, belum diunduh klien) selalu ada di spec ini
    cy.get("select[aria-label=Status]").select("AMIGA_REVIEWED");
    // Tabel dimuat ulang setelah filter berubah: tunggu sampai semua badge sesuai
    cy.get("table.docs tbody .badge").should(($badges) => {
      expect($badges.length).to.be.greaterThan(0);
      $badges.each((_, b) => { expect(b.textContent).to.eq("Disetujui"); });
    });
    cy.contains("tr.total-row", "Total");
  });

  it("TS-038 Satu voucher dari beberapa invoice, ditinjau di Preview sebelum dikirim", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    // PIC hanya bisa memilih perusahaan yang ditugaskan kepadanya
    cy.get("#client option").should("have.length", 1).and("have.text", "PT Klien Alpha");
    cy.contains("button", "Tambah kotak tanda tangan").click();
    cy.get(".approver-row").should("have.length", 2);
    cy.get("main input[type=file]").selectFile(
      ["cypress/fixtures/sys_normal_a.pdf", "cypress/fixtures/sys_multi_d.pdf"], { force: true });
    cy.get(".file-list li").should("have.length", 2);
    cy.contains("button", "Kirim ke antrean").should("not.exist");
    cy.contains("button", "Preview").click();
    cy.contains("h1", "Preview pengajuan");
    cy.contains(".meta dt", "Perusahaan").next("dd").should("have.text", "PT Klien Alpha");
    cy.contains(".meta dt", "Diajukan oleh").next("dd").should("contain.text", "Rina (PIC Alpha)");
    cy.contains(".meta dt", "Disetujui oleh").next("dd").find("li").should("have.length", 2);
    cy.contains(".meta dt", "Jumlah invoice").next("dd").should("have.text", "2 file");
    cy.contains(".file-list.selectable button", "sys_multi_d.pdf").click();
    cy.get(".pdf-preview iframe").should("have.attr", "title", "Preview sys_multi_d.pdf");
    // URL PDF di iframe harus masih hidup (tidak dicabut sebelum dimuat)
    cy.get(".pdf-preview iframe").invoke("attr", "src").then((src) =>
      cy.window().then((win) => win.fetch(src as string).then((r) => expect(r.ok).to.eq(true))));
    // Kembali ubah: isian dan file tetap ada
    cy.contains("button", "Kembali ubah").click();
    cy.get(".file-list li").should("have.length", 2);
    cy.contains("button", "Preview").click();
    cy.contains("button", "Kirim ke antrean").click();
    cy.contains("Draf dibuat");
    cy.contains("a", "Buka draf").click();
    cy.contains(".pdf-head", "2 invoice");
    cy.contains(".meta dt", "File invoice").next("dd").should("contain.text", "sys_normal_a.pdf").and("contain.text", "sys_multi_d.pdf");
  });

  it("TS-039 Peran ganda yang memperbaiki data tidak bisa meninjau dokumen itu (SoD)", () => {
    upload("pic.alpha@amiga.test", "sys_dup_c.pdf", "e"); // duplikat c1 → draf dengan POSSIBLE_DUPLICATE
    waitStatus("Draf");
    cy.then(() => {
      // Yoga (Intake + Reviewer) bertindak sebagai pengaju: mengirim draf ke reviewer
      cy.visitAs("multi@amiga.test", `/dokumen/${docs.e.id}`);
      submitDraft();
      cy.contains(".issue", "POSSIBLE_DUPLICATE");
      cy.contains("button", "Tandai bukan duplikat").click();
      cy.get("#reason").type("Tagihan berbeda, sudah dicek.");
      cy.contains(".modal button", "Tandai").click();
      cy.contains(".alert", "Pihak pengaju");
      cy.contains(".modal button", "Batal").click();
      // Reviewer lain menandai bukan duplikat; Yoga tidak pernah menjadi reviewernya
      cy.visitAs("reviewer1@amiga.test", `/dokumen/${docs.e.id}`);
      cy.contains("button", "Tandai bukan duplikat").click();
      cy.get("#reason").type("Tagihan berbeda, sudah dikonfirmasi.");
      cy.contains(".modal button", "Tandai").click();
      cy.contains(".page-head .badge", "Siap ditinjau");
      meta("Finance Reviewer").should("not.contain.text", "Yoga");
      cy.token("multi@amiga.test").then((t) =>
        cy.request({ method: "POST", url: `/api/documents/${docs.e.id}/approve`, failOnStatusCode: false,
                     headers: { Authorization: `Bearer ${t}` } }).its("status").should("eq", 403));
    });
  });

  it("TS-043 PIC membatalkan pengajuan yang salah unggah", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.e.id}`); // dari TS-039, siap ditinjau
      cy.contains("button", "Batalkan pengajuan").click();
      cy.contains(".modal button", "Batalkan pengajuan").should("be.disabled");
      cy.get("#reason").type("Salah unggah, file ganda.");
      cy.contains(".modal button", "Batalkan pengajuan").click();
      cy.contains(".page-head .badge", "Dibatalkan");
      cy.contains(".alert.warn", "dibatalkan").and("contain.text", "Salah unggah, file ganda.");
      cy.contains("button", "Batalkan pengajuan").should("not.exist");
      // Reviewer tidak bisa lagi menyetujuinya
      cy.token("reviewer1@amiga.test").then((t) =>
        cy.request({ method: "POST", url: `/api/documents/${docs.e.id}/approve`, failOnStatusCode: false,
                     headers: { Authorization: `Bearer ${t}` } }).its("status").should("eq", 409));
      cy.visitAs("pic.alpha@amiga.test", "/pengajuan");
      cy.contains("button", "Dibatalkan").click();
      cy.contains("tr", docs.e.requestId).should("contain.text", "Dibatalkan");
    });
  });

  it("TS-045 PIC memilih pajak per invoice; voucher membayar nilai bersih", () => {
    cy.visitAs("pic.alpha@amiga.test", "/referensi/tarif-pajak");
    cy.get("table tbody tr").should("have.length", 5);
    cy.contains(".alert", "perlu dikonfirmasi konsultan pajak");
    cy.contains("button", "Ubah").should("not.exist");

    upload("pic.alpha@amiga.test", "sys_normal_a.pdf", "tax");
    waitStatus("Draf");
    cy.contains(".tax-hint", "Keputusan tetap di Anda");
    cy.get("#tax-code").select("PPh 23");
    cy.get("#tax-npwp").select("Tidak punya NPWP");
    cy.contains(".tax-calc", "4%");
    cy.contains("button", "Terapkan pajak").click();
    cy.contains(".alert", "Pajak bukti 1 diterapkan");
    cy.contains(".tax-summary", "Potongan PPh 23").and("contain.text", "tanpa NPWP").and("contain.text", "Dibayarkan");
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.tax.id}/riwayat`);
      cy.contains(".timeline li", "Diperbaiki PIC").should("contain.text", "PPh 23");
    });

    // Service Lead mengonfirmasi tarif
    cy.visitAs("lead@amiga.test", "/referensi/tarif-pajak");
    cy.contains("tr", "PPh 23").contains("button", "Ubah").click();
    cy.contains(".modal label", "Sudah dikonfirmasi konsultan pajak").find("input").check();
    cy.contains(".modal button", "Simpan").click();
    cy.contains("tr", "PPh 23").should("contain.text", "sudah dikonfirmasi");
  });

  it("TS-046 Voucher reimburse yang sudah dikirim tetap tampil (tanpa cek rekening)", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.get("#type").select("Voucher Pengeluaran Reimburse");
    cy.get("main input[type=file]").selectFile("cypress/fixtures/sys_normal_b.pdf", { force: true });
    cy.contains("button", "Preview").click();
    cy.contains("button", "Kirim ke antrean").click();
    cy.contains("a", "Buka draf").click();
    submitDraft();
    waitStatus("Siap ditinjau");
    cy.reload();
    cy.contains(".section-title", "Data invoice");
    cy.contains(".tax-summary, p", /Dibayarkan|Voucher membayar/);
    cy.get(".account-check").should("not.exist");
  });

  it("TS-041 Service Lead membuat dan mengunduh rekap voucher PDF", () => {
    cy.visitAs("lead@amiga.test", "/rekap-voucher");
    cy.contains("h1", "Rekap voucher");
    cy.contains(".seg button", "30 hari").click().should("have.attr", "aria-pressed", "true");
    // Voucher dari TS-018 terbit hari ini
    cy.contains(".stat", "Jumlah voucher").find(".stat-value").invoke("text").then(Number).should("be.gte", 1);
    cy.contains(".seg button", "Kustom").click();
    cy.get("#r-from").type("2026-10-10");
    cy.get("#r-to").clear().type("2026-10-01");
    cy.contains(".alert", "tanggal mulai tidak boleh setelah");
    cy.contains("button", "Unduh rekap PDF").should("be.disabled");
    cy.contains(".seg button", "Hari ini").click();
    cy.contains("button", "Unduh rekap PDF").should("be.enabled");
    cy.token("lead@amiga.test").then((t) =>
      cy.request({ url: "/api/vouchers/report?period=7", headers: { Authorization: `Bearer ${t}` } }).then((r) => {
        expect(r.headers["content-type"]).to.eq("application/pdf");
        expect(r.headers["content-disposition"]).to.match(/rekap-voucher_\d{8}-\d{8}\.pdf/);
      }));
    // Hanya Service Lead
    cy.token("reviewer1@amiga.test").then((t) =>
      cy.request({ url: "/api/vouchers/report", headers: { Authorization: `Bearer ${t}` }, failOnStatusCode: false })
        .its("status").should("eq", 403));
  });

  it("TS-042 Label status mudah dibaca: Disetujui hijau, Siap ditinjau kuning, Ada kendala merah muda", () => {
    cy.visitAs("lead@amiga.test", "/voucher");
    cy.get(".badge.AMIGA_REVIEWED, .badge.SENT_TO_CLIENT").should("exist");
    cy.document().then((doc) => {
      const probe = (cls: string) => {
        const el = doc.createElement("span");
        el.className = `badge ${cls}`;
        doc.body.appendChild(el);
        const st = getComputedStyle(el);
        const out = [st.color, st.backgroundColor];
        el.remove();
        return out;
      };
      doc.documentElement.dataset.theme = "light";
      expect(probe("AMIGA_REVIEWED")).to.deep.eq(["rgb(17, 24, 39)", "rgb(205, 240, 214)"]);
      expect(probe("READY_FOR_REVIEW")).to.deep.eq(["rgb(17, 24, 39)", "rgb(255, 241, 166)"]);
      expect(probe("EXCEPTION")).to.deep.eq(["rgb(185, 28, 28)", "rgb(255, 225, 231)"]);
      // Mode gelap: stabilo diredam, teks tetap hitam/merah
      doc.documentElement.dataset.theme = "dark";
      expect(probe("AMIGA_REVIEWED")).to.deep.eq(["rgb(11, 18, 32)", "rgb(185, 227, 197)"]);
      expect(probe("READY_FOR_REVIEW")).to.deep.eq(["rgb(11, 18, 32)", "rgb(239, 223, 143)"]);
      expect(probe("EXCEPTION")).to.deep.eq(["rgb(161, 24, 24)", "rgb(246, 211, 218)"]);
    });
  });

  // --- Pengaturan akun (akun baru per run agar akun seed tidak berubah) ---
  const run = Date.now();
  // Email awal dipakai saat membuat akun; email baru setelah TS-034 menggantinya
  const acct = { first: `akun.${run}@amiga.test`, email: `akun2.${run}@amiga.test`, password: "AkunAwal123", next: "AkunBaru456" };
  const loginAs = (email: string, password: string) =>
    cy.request({ method: "POST", url: "/api/auth/login", form: true, body: { username: email, password } })
      .its("body.access_token");
  const visitWith = (token: string, path: string) =>
    cy.visit(path, { onBeforeLoad: (win) => win.localStorage.setItem("amiga.token", token) });

  it("TS-034 Pengguna mengubah nama dan email di Pengaturan akun", () => {
    cy.token("admin@amiga.test").then((t) =>
      cy.request({ method: "POST", url: "/api/admin/users", headers: { Authorization: `Bearer ${t}` },
                   body: { email: acct.first, full_name: "Akun Uji", password: acct.password, roles: ["SERVICE_LEAD"], client_ids: [] } }));
    loginAs(acct.first, acct.password).then((t) => visitWith(t as unknown as string, "/dashboard"));
    cy.get(".user-link").click();
    cy.location("pathname").should("eq", "/akun");
    cy.get("#p-name").clear().type("Akun Uji Diubah");
    cy.contains("button", "Simpan profil").click();
    cy.contains(".alert", "Profil disimpan");
    cy.get(".user-link").should("contain.text", "Akun Uji Diubah");
    // Ganti email wajib password saat ini
    cy.get("#p-email").clear().type(acct.email);
    cy.get("#p-current").type("salah-password1");
    cy.contains("button", "Simpan profil").click();
    cy.contains(".alert", "Password saat ini salah");
    cy.get("#p-current").clear().type(acct.password);
    cy.contains("button", "Simpan profil").click();
    cy.contains(".alert", "Gunakan email baru");
    loginAs(acct.email, acct.password).should("be.a", "string");
  });

  it("TS-035 Ganti password mengeluarkan sesi lain", () => {
    loginAs(acct.email, acct.password).then((oldToken) => {
      loginAs(acct.email, acct.password).then((t) => visitWith(t as unknown as string, "/akun"));
      cy.get("#pw-current").type(acct.password);
      cy.get("#pw-new").type("pendek");
      cy.contains("button", "Ganti password").should("be.disabled");
      cy.get("#pw-new").clear().type(acct.next);
      cy.get("#pw-confirm").type(acct.next);
      cy.get(".pw-rules li.ok").should("have.length", 4);
      cy.contains("button", "Ganti password").click();
      cy.contains(".alert", "Password diganti");
      // Sesi ini tetap jalan (token baru), sesi lama ditolak
      cy.reload();
      cy.location("pathname").should("eq", "/akun");
      cy.request({ url: "/api/auth/me", headers: { Authorization: `Bearer ${oldToken}` }, failOnStatusCode: false })
        .its("status").should("eq", 401);
      loginAs(acct.email, acct.next).should("be.a", "string");
    });
  });

  it("TS-036 Admin mereset password pengguna yang lupa", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("tr", "admin@amiga.test").contains("button", "Reset password").should("be.disabled");
    cy.contains("tr", acct.email).contains("button", "Reset password").click();
    cy.get("#r-pass").type("SementaraAja789");
    cy.contains(".modal button", "Reset password").click();
    cy.contains(".alert", "diatur ulang");
    loginAs(acct.email, "SementaraAja789").should("be.a", "string");
  });

  it("TS-037 Tema bisa dipilih dari Pengaturan akun", () => {
    cy.visitAs("reviewer1@amiga.test", "/akun");
    cy.contains(".theme-options button", "Gelap").click();
    cy.get("html").should("have.attr", "data-theme", "dark");
    cy.contains(".theme-options button", "Terang").click();
    cy.get("html").should("have.attr", "data-theme", "light");
  });

  // --- Logout ---
  it("TS-027 Logout mengakhiri sesi", () => {
    cy.visitAs("reviewer1@amiga.test", "/antrean");
    cy.get("button[aria-label=Keluar]").click();
    cy.location("pathname").should("eq", "/login");
    cy.window().its("localStorage").invoke("getItem", "amiga.token").should("be.null");
  });
});
