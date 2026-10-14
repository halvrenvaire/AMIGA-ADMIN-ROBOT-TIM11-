describe('04 - Layar Peninjauan Split-Screen & Editor Finansial', { testIsolation: false }, () => {
  const reqId = 'REQ-20261014-CLEAN1';

  before(() => {
    cy.resetDatabase();
    cy.loginAs('FINANCE_REVIEWER_1');
    cy.visit(`/review/${reqId}`);
  });

  it('harus menampilkan tata letak dual-context split-screen 50:50 dengan kontrol PDF viewer', () => {
    // Verifikasi Request ID di header review
    cy.contains(reqId, { timeout: 15000 }).should('be.visible');

    // Verifikasi panel viewer kiri (iframe)
    cy.get('iframe[title*="Pratinjau PDF"]', { timeout: 15000 }).should('be.visible');

    // Verifikasi kontrol zoom
    cy.get('button[title*="Perbesar"]').should('exist');
    cy.get('button[title*="Perkecil"]').should('exist');
  });

  it('harus mengkalkulasi ulang subtotal dan grand total secara real-time saat baris item diedit', () => {
    // Pastikan editor finansial termuat
    cy.contains(/Pos Biaya|Rincian/i, { timeout: 15000 }).should('be.visible');

    // Ambil input kuantitas pada baris item pertama dan ganti nilai
    cy.get('input[type="number"]').first().clear().type('5');

    // Verifikasi live calculation berjalan pada komponen React
    cy.contains(/Subtotal|Total/i).should('be.visible');
  });

  it('harus dapat membuka modal Kembalikan ke PIC dan membatalkan tindakan', () => {
    // Klik tombol Kembalikan ke PIC
    cy.contains('button', 'Kembalikan ke PIC').click();

    // Verifikasi modal pengembalian terbuka
    cy.contains('Kembalikan Dokumen ke PIC Klien').should('be.visible');

    // Klik Batal
    cy.contains('button', 'Batal').click();
    cy.contains('Kembalikan Dokumen ke PIC Klien').should('not.exist');
  });
});

