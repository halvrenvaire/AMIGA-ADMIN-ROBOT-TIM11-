describe('05A - Penegakan Segregation of Duties (SoD) oleh Pengunggah', { testIsolation: false }, () => {
  const reqId = 'REQ-20261014-SOD001';

  before(() => {
    cy.resetDatabase();
    cy.loginAs('FINANCE_REVIEWER_1');
    cy.visit(`/review/${reqId}`);
  });

  it('harus mendeteksi uploader_id == reviewer_id dan menampilkan banner peringatan SoD serta mendisabel persetujuan', () => {
    cy.contains('Pemberitahuan Segregation of Duties (SoD)', { timeout: 15000 }).should('be.visible');
    cy.contains('Anda terdaftar sebagai pengunggah dokumen ini').should('be.visible');
    cy.contains('button', 'Setujui Voucher').should('be.disabled');
  });
});

describe('05B - Persetujuan Voucher oleh Reviewer Independen', { testIsolation: false }, () => {
  const reqId = 'REQ-20261014-CLEAN1';

  before(() => {
    cy.loginAs('FINANCE_REVIEWER_2');
    cy.visit(`/review/${reqId}`);
  });

  it('harus mengizinkan Finance Reviewer 2 menyetujui dokumen dan menerbitkan voucher resmi', () => {
    cy.contains('Anda terdaftar sebagai pengunggah dokumen ini').should('not.exist');
    cy.contains('button', 'Setujui Voucher', { timeout: 15000 })
      .should('not.be.disabled')
      .click();
    cy.contains(/Dokumen Telah Disetujui/i, { timeout: 15000 }).should('be.visible');
  });
});


