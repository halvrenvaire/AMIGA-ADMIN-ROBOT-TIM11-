export {};

declare global {
  namespace Cypress {
    interface Chainable {
      /**
       * Reset database ke kondisi awal (seeder) via endpoint dev/test backend
       */
      resetDatabase(): Chainable<void>;

      /**
       * Login sebagai peran tertentu dan simpan token di localStorage
       */
      loginAs(role: 'PIC_KLIEN' | 'FINANCE_REVIEWER_1' | 'FINANCE_REVIEWER_2' | 'SERVICE_LEAD' | 'SYSTEM_ADMIN'): Chainable<any>;

      /**
       * Unggah invoice melalui formulir /upload
       */
      uploadInvoiceForm(
        fixtureFilename: string,
        clientCode?: string,
        channel?: string
      ): Chainable<string>;
    }
  }
}

let activeToken: string | null = null;

export function getActiveToken(): string | null {
  return activeToken;
}

export function setActiveToken(token: string | null) {
  activeToken = token;
}

const USERS = {
  PIC_KLIEN: { email: 'pic_client@amiga.co.id', password: 'password123!' },
  FINANCE_REVIEWER_1: { email: 'reviewer1@amiga.co.id', password: 'password123!' },
  FINANCE_REVIEWER_2: { email: 'reviewer2@amiga.co.id', password: 'password123!' },
  SERVICE_LEAD: { email: 'service_lead@amiga.co.id', password: 'password123!' },
  SYSTEM_ADMIN: { email: 'sysadmin@amiga.co.id', password: 'password123!' },
};

Cypress.Commands.add('resetDatabase', () => {
  activeToken = null;
  cy.request({
    method: 'POST',
    url: 'http://localhost:4000/api/v1/test/reset-seed',
    failOnStatusCode: false,
  }).then((res) => {
    expect(res.status).to.be.oneOf([200, 404]); // 200 in dev
  });
});

Cypress.Commands.add('loginAs', (role) => {
  const user = USERS[role];
  return cy.request({
    method: 'POST',
    url: 'http://localhost:4000/api/v1/auth/login',
    body: {
      email: user.email,
      password: user.password,
    },
  }).then((res) => {
    expect(res.status).to.eq(200);
    const token = res.body.data.accessToken;
    activeToken = token;
    return res.body.data;
  });
});

Cypress.Commands.add('uploadInvoiceForm', (fixtureFilename, clientCode = 'CLI-MAIN', channel = 'Portal') => {
  cy.visit('/upload');

  // Tunggu dropdown klien terisi opsi dari backend
  cy.get('select#client-select option', { timeout: 10000 }).should('have.length.greaterThan', 1);

  // Pilih Klien
  cy.get('select#client-select option').then(($options) => {
    const matchingOption = Array.from($options).find((opt) => (opt as HTMLOptionElement).text.includes(clientCode)) as HTMLOptionElement | undefined;
    if (matchingOption) {
      cy.get('select#client-select').select(matchingOption.value);
    } else {
      cy.get('select#client-select').select(1);
    }
  });

  // Pilih Saluran
  cy.get('select#submission-channel').select(channel);

  // Upload berkas via input file
  cy.get('input#invoice-file-upload').selectFile(
    `cypress/fixtures/invoices/${fixtureFilename}`,
    { force: true }
  );

  // Klik tombol submit
  cy.get('button[type="submit"]').should('not.be.disabled').click();

  // Validasi modal sukses dan ambil Request ID
  return cy.contains('Request ID:', { timeout: 15000 })
    .invoke('text')
    .then((text) => {
      const match = text.match(/REQ-[\w-]+/);
      const reqId = match ? match[0] : '';
      expect(reqId).to.not.be.empty;
      return reqId;
    });
});
