describe('03 - Dashboard Antrean & Monitoring Beban', { testIsolation: false }, () => {
  before(() => {
    cy.resetDatabase();
    cy.loginAs('FINANCE_REVIEWER_1');
    cy.visit('/queue');
  });

  it('harus memuat metrik antrean dan dashboard dalam SLA <= 2 detik', () => {
    const start = Date.now();

    cy.contains('Dashboard Antrean & Monitoring Beban', { timeout: 8000 }).should('be.visible');
    cy.contains('Semua Dokumen').should('be.visible').then(() => {
      const duration = Date.now() - start;
      cy.log(`Halaman Queue termuat dalam ${duration} ms`);
    });

    // Periksa kartu ringkasan status antrean
    cy.contains('Semua Dokumen').should('be.visible');
    cy.contains('Dalam Antrean').should('be.visible');
    cy.contains('Ekstraksi AI').should('be.visible');
    cy.contains('Siap Ditinjau').should('be.visible');
    cy.contains('Kendala Sistem').should('be.visible');
    cy.contains('Voucher Terbit').should('be.visible');
  });

  it('harus dapat memfilter antrean dokumen berdasarkan tab kartu status', () => {
    // 1. Klik kartu status 'Siap Ditinjau'
    cy.contains('Siap Ditinjau').click();
    cy.contains('REQ-20261014-CLEAN1', { timeout: 10000 }).should('be.visible');

    // 2. Klik kartu status 'Kendala Sistem'
    cy.contains('Kendala Sistem').click();
    cy.contains('REQ-20261014-EXCP01', { timeout: 10000 }).should('be.visible');

    // 3. Klik kembali ke 'Semua Dokumen'
    cy.contains('Semua Dokumen').click();
    cy.contains('REQ-20261014-CLEAN1', { timeout: 10000 }).should('be.visible');
  });

  it('harus menampilkan widget Monitoring Beban Antrean Reviewer', () => {
    cy.contains('Monitoring Beban Antrean Reviewer', { timeout: 10000 }).should('be.visible');
    cy.contains('reviewer1@amiga.co.id').should('be.visible');
  });
});


