// Login lewat API (password akun dummy dari SEED_DEFAULT_PASSWORD, diberikan oleh scripts/run_e2e.sh)

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Cypress {
    interface Chainable {
      /** Token login untuk akun hasil seed.py. */
      token(email: string): Chainable<string>;
      /** Buka halaman sebagai pengguna tertentu. */
      visitAs(email: string, path: string): Chainable<void>;
    }
  }
}

const tokens: Record<string, string> = {};

Cypress.Commands.add("token", (email: string) => {
  if (tokens[email]) return cy.wrap(tokens[email], { log: false });
  return cy
    .env(["SEED_PASSWORD"], { log: false })
    .then(({ SEED_PASSWORD }) =>
      cy.request({
        method: "POST",
        url: "/api/auth/login",
        form: true,
        body: { username: email, password: SEED_PASSWORD },
        log: false,
      }))
    .then((res) => {
      tokens[email] = res.body.access_token;
      return tokens[email];
    });
});

Cypress.Commands.add("visitAs", (email: string, path: string) => {
  cy.token(email).then((t) => {
    cy.visit(path, { onBeforeLoad: (win) => win.localStorage.setItem("amiga.token", t) });
  });
});

export {};
