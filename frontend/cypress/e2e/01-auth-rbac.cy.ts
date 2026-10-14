describe('01 - Authentication & RBAC Access Control', { testIsolation: false }, () => {
  before(() => {
    cy.resetDatabase();
    cy.loginAs('PIC_KLIEN');
    cy.visit('/queue');
  });

  it('harus dapat beralih peran pengguna via demo switcher di navbar', () => {

    // 1. Periksa default user atau navbar
    cy.get('header').should('be.visible');
    cy.contains('AMIGA Robot Admin').should('be.visible');

    // 2. Buka dropdown Demo Switcher
    cy.contains('Peran Demo:').click();
    cy.contains('Ganti Peran Pengguna (SoD Demo)').should('be.visible');

    // 3. Ganti ke PIC Klien
    cy.contains('PIC Klien (Client)').click();
    cy.contains('PIC_KLIEN', { timeout: 10000 }).should('be.visible');

    // 4. Buka dropdown lagi dan ganti ke Finance Reviewer 1
    cy.contains('Peran Demo:').click();
    cy.contains('Reviewer 1 (AMIGA)').click();
    cy.contains('FINANCE_REVIEWER', { timeout: 10000 }).should('be.visible');
  });

  it('harus memvalidasi akses rute berdasarkan hak peran pengguna', () => {
    // PIC Klien melihat menu Antrean Dokumen dan Unggah Invoice
    cy.contains('Antrean Dokumen').should('be.visible');
    cy.contains('Unggah Invoice').should('be.visible');
  });
});
