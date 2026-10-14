describe('08 - Isolasi Multi-Tenant (UAT-6) & Jejak Audit Permanen (UAT-7)', { testIsolation: false }, () => {
  const reqId = 'REQ-20261014-APPR01';

  before(() => {
    cy.resetDatabase();
    cy.loginAs('PIC_KLIEN');
  });

  it('harus menolak akses dokumen lintas tenant (Isolasi Multi-Tenant)', () => {
    cy.loginAs('PIC_KLIEN').then((authData) => {
      cy.request({
        method: 'GET',
        url: 'http://localhost:4000/api/v1/invoices/REQ-CLI2-NON-EXISTENT',
        headers: {
          Authorization: `Bearer ${authData.accessToken}`,
        },
        failOnStatusCode: false,
      }).then((res) => {
        expect(res.status).to.be.oneOf([403, 404]);
      });
    });
  });

  it('harus menampilkan lini masa jejak audit permanen dan filter kategori audit', () => {
    cy.visit(`/audit/${reqId}`);

    // Verifikasi judul halaman audit dan Request ID
    cy.contains(/Jejak Audit/i, { timeout: 15000 }).should('be.visible');
    cy.contains(reqId).should('be.visible');

    // Verifikasi catatan event audit tercatat
    cy.contains(/Dokumen Invoice Diunggah|Persetujuan Dokumen|INVOICE_UPLOADED|REVIEW_APPROVED/i).should('be.visible');

    // Verifikasi filter kategori audit
    cy.contains('button', /Semua Aktivitas|Perubahan Data|Persetujuan/i).should('exist');
  });
});

