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
  cy.contains("button", "Kirim ke antrean").click();
  cy.contains("Terkirim ke antrean").find("b").invoke("text").then((requestId) => {
    cy.contains("a", "Lihat status dokumen").click();
    cy.location("pathname").should("match", /^\/dokumen\/[0-9a-f-]+$/).then((path) => {
      docs[key] = { id: path.split("/").pop()!, requestId };
    });
  });
}

const waitStatus = (label: string) => cy.contains(".page-head .badge", label, { timeout: 30_000 });
const meta = (label: string) => cy.contains(".meta dt", label).next("dd");
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
    cy.get(".nav").should("not.contain.text", "Dashboard Antrean").and("contain.text", "Unggah Dokumen");
    cy.get(".fab").should("not.exist"); // Asisten hanya untuk peran internal
  });

  // --- Unggah dokumen ---
  it("TS-006 Unggah invoice PDF valid", () => {
    upload("pic.alpha@amiga.test", "sys_normal_a.pdf", "a");
    cy.then(() => expect(docs.a.requestId).to.match(/^REQ-\d{8}-[0-9A-F]{6}$/));
    waitStatus("Siap ditinjau");
  });

  it("TS-007 Unggah file selain PDF ditolak", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.get("main input[type=file]").selectFile("cypress/fixtures/bukan_pdf.txt", { force: true });
    cy.contains(".alert", "File harus berformat PDF");
  });

  it("TS-008 Unggah PDF lebih dari 5 halaman ditolak", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.get("main input[type=file]").selectFile("cypress/fixtures/enam_halaman.pdf", { force: true });
    cy.contains("button", "Kirim ke antrean").click();
    cy.contains(".alert", "6 halaman").and("contain.text", "Maksimal 5 halaman");
  });

  it("TS-009 Field wajib jenis permintaan divalidasi", () => {
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.get("#type").clear();
    cy.get("main input[type=file]").selectFile("cypress/fixtures/sys_normal_b.pdf", { force: true });
    cy.contains("button", "Kirim ke antrean").click();
    cy.get("#type:invalid").should("exist");
    cy.contains("Terkirim ke antrean").should("not.exist");
  });

  // --- Dashboard antrean ---
  it("TS-010 Dashboard Antrean menampilkan semua widget", () => {
    cy.visitAs("lead@amiga.test", "/antrean");
    cy.get(".stats .stat").should("have.length", 4);
    cy.get(".status-strip button").should("have.length", 6);
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
      cy.get("#f-vendor_name").should("have.value", "PT Konsultan Prima");
      cy.get("table.compact tbody tr").should("have.length", 3);
    });
  });

  it("TS-014 Simpan & verifikasi ulang menandai kendala dan menahan persetujuan", () => {
    upload("pic.alpha@amiga.test", "sys_normal_b.pdf", "b");
    waitStatus("Siap ditinjau");
    reviewer().then((email) => {
      cy.visitAs(email, `/dokumen/${docs.b.id}`);
      cy.get("#f-total").clear().type("6000000");
      cy.contains(".decision button", "Simpan & verifikasi ulang").click();
      cy.contains(".issue", "CALCULATION_DISCREPANCY");
      cy.contains(".decision button", "Setujui").should("be.disabled");
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
    waitStatus("Siap ditinjau");
    upload("pic.alpha@amiga.test", "sys_dup_c.pdf", "c2");
    waitStatus("Ada kendala");
    cy.contains(".issue", "POSSIBLE_DUPLICATE");
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
  it("TS-022 Admin menambahkan pengguna dengan peran ganda", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("button", "Tambah pengguna").click();
    cy.get("#u-name").type("QA Tester");
    cy.get("#u-email").type(NEW_USER);
    cy.get("#u-pass").type(NEW_USER_PASSWORD, { log: false });
    cy.contains(".modal label.toggle", "Intake Support").find("input").check();
    cy.contains(".modal label.toggle", "Finance Reviewer").find("input").check();
    cy.contains(".modal label.toggle", "PT Klien Alpha").find("input").check();
    cy.contains(".modal button", "Simpan").click();
    cy.contains("tr", NEW_USER).should("contain.text", "Intake Support").and("contain.text", "Finance Reviewer");
  });

  it("TS-023 Kombinasi peran terlarang ditolak", () => {
    cy.visitAs("admin@amiga.test", "/admin/pengguna");
    cy.contains("button", "Tambah pengguna").click();
    cy.get("#u-name").type("QA Terlarang");
    cy.get("#u-email").type(`terlarang.${stamp}@amiga.test`);
    cy.get("#u-pass").type(NEW_USER_PASSWORD, { log: false });
    cy.contains(".modal label.toggle", "PIC Klien").find("input").check();
    cy.contains(".modal label.toggle", "Intake Support").find("input").check();
    cy.contains(".modal button", "Simpan").click();
    cy.contains(".modal .alert", "PIC Klien tidak boleh digabung");
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
    cy.get("main input.input").type("pt klien alpha");
    cy.contains("button", "Tambah").click();
    cy.contains(".alert", "sudah terdaftar");
  });

  // --- Fitur tambahan permintaan owner (14 Okt 2026) ---
  it("TS-029 Dashboard metrik menampilkan KPI status, tren, dan panel kinerja", () => {
    cy.visitAs("lead@amiga.test", "/dashboard");
    cy.get(".kpi-status .kpi-mini").should("have.length", 6);
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
    cy.contains("section", "Disetujui oleh").contains("button", "Tambah").click();
    cy.get("#s-name").type("Dian Pratama");
    cy.get("#s-pos").type("Bendahara");
    cy.contains(".modal button", "Simpan").click();
    cy.contains("section", "Disetujui oleh").should("contain.text", "Dian Pratama");
    cy.visitAs("pic.alpha@amiga.test", "/unggah");
    cy.contains(".signer-picker label", "Dian Pratama").find("input").should("be.checked");
  });

  it("TS-032 Penanda tangan dokumen bisa diubah sebelum voucher terbit", () => {
    cy.then(() => {
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.c1.id}`);
      cy.contains("section", "Penanda tangan voucher").within(() => {
        cy.contains("button", "Ubah").click();
        cy.contains("label", "Dian Pratama").find("input").check();
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

  // --- Logout ---
  it("TS-027 Logout mengakhiri sesi", () => {
    cy.visitAs("reviewer1@amiga.test", "/antrean");
    cy.get("button[aria-label=Keluar]").click();
    cy.location("pathname").should("eq", "/login");
    cy.window().its("localStorage").invoke("getItem", "amiga.token").should("be.null");
  });
});
