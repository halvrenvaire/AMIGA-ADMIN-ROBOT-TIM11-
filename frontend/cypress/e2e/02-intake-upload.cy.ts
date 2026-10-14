describe('02 - Intake & Formulir Pengunggahan Invoice', { testIsolation: false }, () => {
  before(() => {
    cy.resetDatabase();
    cy.loginAs('PIC_KLIEN');
    cy.visit('/upload');
    cy.get('select#client-select option', { timeout: 10000 }).should('have.length.greaterThan', 1);
  });

  it('harus menolak unggahan berkas non-PDF pada validasi client-side', () => {
    // Buat file non-PDF dummy dan drag-drop ke dropzone
    cy.get('#invoice-dropzone').selectFile(
      {
        contents: Cypress.Buffer.from('Fake image content'),
        fileName: 'sample_photo.png',
        mimeType: 'image/png',
      },
      { action: 'drag-drop' }
    );

    // Verifikasi pesan peringatan muncul
    cy.contains('Berkas wajib berformat PDF digital (.pdf).').should('be.visible');
    cy.get('button[type="submit"]').should('be.disabled');
  });

  it('harus menolak berkas PDF lebih dari 5 halaman dari server (PAGE_LIMIT_EXCEEDED)', () => {
    // Pilih klien
    cy.get('select#client-select').select(1);

    // Unggah file 6 halaman
    cy.get('input#invoice-file-upload').selectFile(
      'cypress/fixtures/invoices/invalid-6-pages.pdf',
      { force: true }
    );

    cy.get('button[type="submit"]').click();

    // Verifikasi pesan penolakan dari server
    cy.contains(/melebihi batas maksimum 5 halaman|PAGE_LIMIT_EXCEEDED/i, { timeout: 15000 }).should('be.visible');
  });

  it('harus menolak berkas dengan magic bytes palsu (INVALID_FILE_TYPE)', () => {
    // Unggah binary .exe yang diberi nama .pdf
    cy.get('input#invoice-file-upload').selectFile(
      'cypress/fixtures/invoices/fake-file.pdf',
      { force: true }
    );

    cy.get('button[type="submit"]').click();

    // Verifikasi penolakan magic bytes
    cy.contains(/bukan PDF digital yang valid|magic bytes mismatch|INVALID_FILE_TYPE/i, { timeout: 15000 }).should('be.visible');
  });

  it('harus berhasil mengunggah PDF valid dan menerbitkan Request ID unik (QUEUED)', () => {
    // Unggah file PDF bersih valid
    cy.get('input#invoice-file-upload').selectFile(
      'cypress/fixtures/invoices/clean-invoice.pdf',
      { force: true }
    );

    cy.get('button[type="submit"]').should('not.be.disabled').click();

    // Validasi modal sukses dan ambil Request ID
    cy.contains('Request ID:', { timeout: 15000 })
      .invoke('text')
      .then((text) => {
        const match = text.match(/REQ-[\w-]+/);
        const reqId = match ? match[0] : '';
        expect(reqId).to.match(/^REQ-\d{8}-[A-Za-z0-9]+$/);

        // Verifikasi teks sukses dan navigasi antrean
        cy.contains('Unggahan Berhasil Diterima').should('be.visible');
        cy.contains('Buka Antrean & Pantau Dokumen').click();

        cy.url().should('include', '/queue');
        cy.contains(reqId, { timeout: 10000 }).should('be.visible');
      });
  });
});

