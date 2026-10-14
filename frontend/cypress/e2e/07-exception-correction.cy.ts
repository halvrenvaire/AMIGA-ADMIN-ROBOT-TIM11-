describe('07 - Penanganan Kendala Rekening (UAT-3) & Siklus Koreksi EXCEPTION (UAT-8)', { testIsolation: false }, () => {
  const reqId = 'REQ-20261014-EXCP01';

  before(() => {
    cy.resetDatabase();
    cy.loginAs('PIC_KLIEN');
    cy.visit('/queue');
  });

  it('harus mendeteksi ketiadaan rekening dan menandai dokumen sebagai EXCEPTION', () => {
    // Cari baris dokumen di tabel antrean
    cy.contains(reqId, { timeout: 15000 }).should('be.visible');

    // Status harus EXCEPTION dengan indikator kendala aktif
    cy.contains(reqId)
      .parents('tr')
      .within(() => {
        cy.contains(/EXCEPTION|Kendala/i).should('be.visible');
        cy.contains('button', 'Koreksi').should('be.visible');
      });
  });

  it('harus dapat mengoreksi rekening via modal perbaikan dan mempertahankan Request ID identik', () => {
    // Klik tombol Koreksi pada baris dokumen
    cy.contains(reqId)
      .parents('tr')
      .within(() => {
        cy.contains('button', 'Koreksi', { timeout: 15000 }).click();
      });

    // Verifikasi modal koreksi terbuka dengan Request ID yang sama
    cy.contains('Koreksi Dokumen EXCEPTION').should('be.visible');
    cy.contains(`Request ID: ${reqId}`).should('be.visible');

    // Isi formulir data rekening bank yang benar
    cy.get('input[placeholder*="BCA"]').clear().type('Bank Central Asia (BCA)');
    cy.get('input[placeholder*="8820"]').clear().type('5410982711');

    // Kirim koreksi
    cy.contains('button', 'Kirim Koreksi Dokumen').click();

    // Verifikasi modal tertutup dan Request ID tetap sama pada tabel
    cy.contains('Koreksi Dokumen EXCEPTION').should('not.exist');
    cy.contains(reqId).should('be.visible');
  });
});

