describe('06 - Pratinjau Voucher Resmi & Alur Unduh Berkas (UAT-1)', { testIsolation: false }, () => {
  const reqId = 'REQ-20261014-APPR01';

  before(() => {
    cy.resetDatabase();
    cy.loginAs('PIC_KLIEN');
    cy.visit(`/voucher/${reqId}`);
  });

  it('harus menampilkan pratinjau voucher pembayaran resmi dengan nomor unik dan teks legalitas', () => {
    // Verifikasi judul voucher dan nomor voucher format VCH/YYYYMM/CLI/XXXXX
    cy.contains(/PAYMENT VOUCHER|Pratinjau Voucher/i, { timeout: 15000 }).should('be.visible');
    cy.contains(/VCH\/202610\/CLI-MAIN\/\d{5}/).should('be.visible');

    // Verifikasi teks batas otorisasi legal tertera
    cy.contains('BATAS OTORISASI PEMBAYARAN LEGAL').should('be.visible');
    cy.contains('Voucher ini diterbitkan secara otomatis oleh AMIGA Robot Admin').should('be.visible');
  });

  it('harus memicu pengunduhan berkas voucher PDF resmi saat tombol unduh ditekan', () => {
    // Klik tombol unduh berkas
    cy.contains('button', /Unduh Voucher PDF Resmi/i, { timeout: 10000 })
      .should('not.be.disabled')
      .click();

    // Verifikasi pesan sukses unduh tampil
    cy.contains('Berkas voucher resmi berhasil diunduh ke perangkat Anda.', { timeout: 10000 }).should('be.visible');
  });
});

