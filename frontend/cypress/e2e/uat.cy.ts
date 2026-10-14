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
function upload(email: string, file: string, key: string) {
  cy.visitAs(email, "/unggah");
  cy.get("main input[type=file]").selectFile(`../samples/invoices/${file}`, { force: true });
  cy.contains("button", "Kirim ke antrean").click();
  cy.contains("Terkirim ke antrean").find("b").invoke("text").then((requestId) => {
    cy.contains("a", "Lihat status dokumen").click();
    cy.location("pathname").should("match", /^\/dokumen\/[0-9a-f-]+$/).then((path) => {
      docs[key] = { id: path.split("/").pop()!, requestId };
    });
  });
}

const badge = () => cy.get(".page-head .badge");
const waitStatus = (label: string) => cy.contains(".page-head .badge", label, { timeout: 30_000 });
const meta = (label: string) => cy.contains(".meta dt", label).next("dd");

function reviewerOf() {
  return meta("Finance Reviewer").invoke("text").then((name) => {
    expect(REVIEWER_EMAIL, `reviewer ${name}`).to.have.property(name);
    return REVIEWER_EMAIL[name];
  });
}

describe("UAT AMIGA Robot Admin", () => {
  it("UAT 1 — alur normal: unggah → ekstraksi → disetujui → voucher diunduh (SENT_TO_CLIENT)", () => {
    upload("pic.alpha@amiga.test", "01_normal_3_baris.pdf", "normal");
    waitStatus("Siap ditinjau");
    // Target ekstraksi <= 15 detik (FR-2.3)
    meta("Dibaca AI").invoke("text").then((t) => expect(parseFloat(t)).to.be.at.most(15));

    reviewerOf().then((reviewer) => {
      cy.visitAs(reviewer, `/dokumen/${docs.normal.id}`);
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
    waitStatus("Ada kendala");
    cy.contains(".issue", "POSSIBLE_DUPLICATE").should("contain.text", docs.normal.requestId);
  });

  it("UAT 3 — missing evidence: tanpa nomor rekening → MISSING_EVIDENCE, EXCEPTION", () => {
    upload("pic.alpha@amiga.test", "02_tanpa_rekening.pdf", "missing");
    waitStatus("Ada kendala");
    cy.contains(".issue", "MISSING_EVIDENCE").should("contain.text", "Nomor rekening");
  });

  it("UAT 8 — perbaikan PIC: kembali ke ekstraksi dengan Request ID sama → READY_FOR_REVIEW", () => {
    cy.visitAs("pic.alpha@amiga.test", `/dokumen/${docs.missing.id}`);
    cy.get("#fix-account_no").type("8890012345");
    cy.get("#fix-note").type("Nomor rekening dikonfirmasi vendor via email.");
    cy.contains("button", "Kirim perbaikan").click();
    waitStatus("Siap ditinjau");
    cy.get(".page-head h1 .mono").should("have.text", docs.missing.requestId);
    meta("Nomor rekening").should("contain.text", "8890012345").and("contain.text", "diisi PIC");
  });

  it("UAT 5 — Segregation of Duties: pengunggah tidak bisa menyetujui, dialihkan otomatis", () => {
    upload("multi@amiga.test", "05_normal_jasa.pdf", "sod");
    waitStatus("Siap ditinjau");
    cy.contains(".decision button", "Setujui").click();
    cy.contains(".alert", "Segregation of Duties").should("contain.text", "dialihkan");
    badge().should("have.text", "Siap ditinjau");
    meta("Finance Reviewer").should("not.contain.text", "Yoga");
  });

  it("UAT 7 — jejak audit: reviewer mengubah nominal → nilai awal, nilai baru, nama, waktu", () => {
    cy.visitAs("multi@amiga.test", `/dokumen/${docs.sod.id}`);
    reviewerOf().then((reviewer) => {
      cy.visitAs(reviewer, `/dokumen/${docs.sod.id}`);
      cy.get("#f-total").clear().type("11000000");
      cy.contains(".decision button", "Simpan & verifikasi ulang").click();
      cy.contains(".alert", "Tersimpan");
      cy.contains(".issue", "CALCULATION_DISCREPANCY");
      cy.contains(".decision button", "Setujui").should("be.disabled");

      cy.visitAs(reviewer, `/dokumen/${docs.sod.id}/riwayat`);
      cy.contains(".timeline li", "Dikoreksi reviewer").within(() => {
        cy.get("del").should("contain.text", "11050000");
        cy.get("ins").should("have.text", "11000000");
        cy.contains(reviewer);
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
