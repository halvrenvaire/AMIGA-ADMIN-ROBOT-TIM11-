export {};

/**
 * 8 skenario uji penerimaan (PRD bagian 8) lewat UI, dengan ekstraksi Nova sungguhan,
 * plus target waktu (PRD bagian 7). Skenario berurutan dan saling memakai dokumen.
 */

const REVIEWER_EMAIL: Record<string, string> = {
  "Dewi (Finance Reviewer)": "reviewer1@amiga.test",
  "Agus (Finance Reviewer)": "reviewer2@amiga.test",
  "Yoga (Intake + Reviewer)": "multi@amiga.test",
};

interface Doc { id: string; requestId: string }
const docs: Record<string, Doc> = {};

/** Unggah lewat Layar 02 lalu buka halaman dokumennya. */
/** Skenario uji lama memakai mode rincian barang/jasa dan rekening tujuan (bawaan Tahap 14: total saja, tanpa rekening). */
function itemizedWithAccount() {
  cy.contains(".mode-card", "Rincian barang/jasa").click();
  cy.contains("details.extras summary", "Fitur tambahan").click();
  cy.contains(".extras label", "Perlu input rekening").find("input").check();
}

/** Simpan draf lalu catat ID dokumen dan Request ID dari halaman detail. */
function saveDraft(key: string) {
  cy.contains("button", "Simpan draf & lanjutkan").click();
  cy.location("pathname", { timeout: 30_000 }).should("match", /^\/dokumen\/[0-9a-f-]+$/).then((path) => {
    cy.get(".page-head h1 .mono").invoke("text").then((requestId) => {
      docs[key] = { id: path.split("/").pop()!, requestId };
    });
  });
}

function upload(email: string, file: string, key: string) {
  cy.visitAs(email, "/unggah");
  itemizedWithAccount();
  cy.get("main input[type=file]").selectFile(`../samples/invoices/${file}`, { force: true });
  saveDraft(key);
}

const badge = () => cy.get(".page-head .badge");
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
  cy.contains(".decision button", "Ajukan untuk Direview").click();
  cy.contains(".alert", "Diajukan ke Finance Reviewer");
}

function reviewerOf() {
  return meta("Finance Reviewer").invoke("text").then((name) => {
    expect(REVIEWER_EMAIL, `reviewer ${name}`).to.have.property(name);
    return REVIEWER_EMAIL[name];
  });
}

describe("UAT AMIGA Robot Admin", () => {
  it("UAT 1 — alur normal: unggah → ekstraksi → disetujui → voucher diunduh (SENT_TO_CLIENT)", () => {
    upload("pic.alpha@amiga.test", "01_normal_3_baris.pdf", "normal");
    submitDraft();
    waitStatus("Siap ditinjau");
    // Target ekstraksi <= 15 detik (FR-2.3)
    meta("Dibaca AI").invoke("text").then((t) => expect(parseFloat(t)).to.be.at.most(15));

    reviewerOf().then((reviewer) => {
      cy.visitAs(reviewer, `/dokumen/${docs.normal.id}`);
      // Rekening vendor belum terverifikasi di data E2E: reviewer wajib mengonfirmasi pengecekan
      cy.get(".account-confirm input[type=checkbox]").check();
      cy.contains(".decision button", "Setujui").click();
      cy.contains(".alert", "Disetujui. Voucher");
      badge().should("have.text", "Disetujui");
    });

    // docs.normal baru terisi setelah unggahan selesai, jadi dibaca di dalam cy.then
    cy.then(() => {
      // Target voucher <= 3 detik (FR-5.1), dicatat sistem di jejak audit
      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.normal.id}/riwayat`);
      cy.contains(".tl-body", "Voucher dibuat").invoke("text").then((t) => {
        expect(Number(/Dibuat dalam (\d+) ms/.exec(t)![1])).to.be.at.most(3000);
      });

      cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.normal.id}/voucher`);
      cy.contains("button", "Unduh voucher PDF").click();
      cy.contains(".alert", "SENT_TO_CLIENT");
      badge().should("have.text", "Diserahkan");
    });
  });

  it("UAT 2 — multi-line item: semua baris terbaca, total benar", () => {
    cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.normal.id}`);
    cy.get("table.compact tbody tr").should("have.length", 4); // 3 baris + jumlah rincian
    cy.contains("tr", "Kertas HVS A4");
    cy.contains("tr", "Tinta printer hitam");
    cy.contains("tr", "Map plastik bening");
    cy.contains(".chip", "= total");
  });

  it("UAT 4 — duplikasi: nomor & vendor sama (format berbeda) → POSSIBLE_DUPLICATE", () => {
    upload("pic.alpha@amiga.test", "03_duplikat_dari_01.pdf", "duplicate");
    waitStatus("Draf"); // kemungkinan duplikat diputuskan reviewer, tidak menahan pengiriman
    cy.contains(".issue", "POSSIBLE_DUPLICATE").should("contain.text", docs.normal.requestId);
  });

  it("UAT 3 — tanpa nomor rekening tetap Draf: rekening opsional (feedback 21 Okt 2026)", () => {
    upload("pic.alpha@amiga.test", "02_tanpa_rekening.pdf", "missing");
    waitStatus("Draf");
    cy.contains(".section-title", "Rekening tujuan");
    cy.contains("label", "Nomor rekening").next("input").should("have.value", "");
    cy.contains(".issue", "Nomor rekening").should("not.exist");
  });

  it("UAT 8 — perbaikan PIC: ubah data di draf dengan Request ID sama → READY_FOR_REVIEW", () => {
    cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.missing.id}`);
    // Halaman memuat data vendor & penanda tangan secara asinkron: tunggu field siap sebelum mengetik
    cy.contains("section", "Penanda tangan voucher");
    cy.get("#f-account_no").should("be.enabled").click().type("8890012345");
    cy.contains(".unsaved-hint", "Ada perubahan yang belum disimpan");
    cy.contains(".decision button", "Simpan bukti 1").should("have.class", "primary").click();
    cy.contains(".alert", "Tersimpan dan lolos verifikasi ulang");
    submitDraft();
    waitStatus("Siap ditinjau");
    cy.get(".page-head h1 .mono").should("have.text", docs.missing.requestId);
    meta("Nomor rekening").should("contain.text", "8890012345").and("contain.text", "diisi PIC");
  });

  it("UAT 5 — Segregation of Duties: pengunggah tidak bisa menyetujui, dialihkan otomatis", () => {
    upload("multi@amiga.test", "05_normal_jasa.pdf", "sod");
    submitDraft();
    waitStatus("Siap ditinjau");
    // Rekening vendor belum terverifikasi di data E2E: reviewer wajib mengonfirmasi pengecekan
    cy.get(".account-confirm input[type=checkbox]").check();
    cy.contains(".decision button", "Setujui").click();
    cy.contains(".alert", "Segregation of Duties").should("contain.text", "dialihkan");
    badge().should("have.text", "Siap ditinjau");
    meta("Finance Reviewer").should("not.contain.text", "Yoga");
  });

  it("UAT 7 — jejak audit: reviewer tidak mengedit; PIC mengubah nominal → nilai awal, nilai baru, nama, waktu", () => {
    cy.visitAs("multi@amiga.test", `/dokumen/${docs.sod.id}`);
    reviewerOf().then((reviewer) => {
      // Finance Reviewer hanya menyetujui atau mengembalikan, tanpa kolom edit
      cy.visitAs(reviewer, `/dokumen/${docs.sod.id}`);
      cy.get("#f-total").should("not.exist");
      cy.contains(".decision button", "Kembalikan ke PIC").click();
      cy.get("#reason").type("Total seharusnya 11.000.000 sesuai PO.");
      cy.contains(".modal button", "Kembalikan").click();
      cy.contains(".page-head .badge", "Ada kendala");

      // PIC (Yoga sebagai pengaju) mengubah nominal di editor per invoice
      cy.visitAs("multi@amiga.test", `/dokumen/${docs.sod.id}`);
      cy.get("#f-total").should("be.enabled").clear().type("11000000");
      cy.contains(".decision button", "Simpan bukti 1").click();
      cy.contains(".alert", "Tersimpan");
      cy.contains(".issue", "CALCULATION_DISCREPANCY");
      cy.contains(".decision button", "Ajukan untuk Direview").should("be.disabled");

      cy.visitAs("multi@amiga.test", `/dokumen/${docs.sod.id}/riwayat`);
      // Entri perubahan nominal (entri "Diperbaiki PIC" lain: pilihan pajak saat draf dikirim)
      cy.contains(".timeline li", "Diperbaiki PIC").should("exist");
      cy.get(".timeline li").filter(':contains("Diperbaiki PIC")').filter(':contains("11050000")').within(() => {
        cy.get("del").should("contain.text", "11050000");
        cy.get("ins").should("have.text", "11000000");
        cy.contains("Yoga");
        cy.get(".tl-time").invoke("text").should("match", /\d{2}\.\d{2}/);
      });
    });
  });

  it("UAT 6 — isolasi klien: user klien B tidak bisa membuka dokumen klien A", () => {
    cy.visitAs("pic.beta@amiga.test", `/dokumen/${docs.normal.id}`);
    cy.contains(".alert", "Akses ditolak");
    cy.visitAs("pic.beta@amiga.test", "/pengajuan");
    cy.contains("Daftar pengajuan");
    cy.contains(docs.normal.requestId).should("not.exist");
  });

  it("Target waktu: antrean dan layar review termuat <= 2 detik", () => {
    cy.token("lead@amiga.test").then((t) => {
      const auth = { Authorization: `Bearer ${t}` };
      for (const url of ["/api/dashboard/summary", "/api/documents?sort=tenggat", `/api/documents/${docs.sod.id}`]) {
        cy.request({ url, headers: auth }).its("duration").should("be.at.most", 2000);
      }
    });
  });
});
