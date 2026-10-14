// ***********************************************************
// This support/e2e.ts file is processed and loaded automatically before your test files.
// ***********************************************************

import './commands';
import { getActiveToken } from './commands';

// Set authentication token in localStorage before any window loads
Cypress.on('window:before:load', (win) => {
  const token = getActiveToken();
  if (token) {
    win.localStorage.setItem('amiga_token', token);
  }
});

// Ignore benign uncaught exceptions (e.g. Next.js hydration or third-party library warnings)
Cypress.on('uncaught:exception', (err) => {
  // Return false to prevent Cypress from failing the test
  if (
    err.message.includes('Hydration failed') ||
    err.message.includes('NEXT_REDIRECT') ||
    err.message.includes('ResizeObserver')
  ) {
    return false;
  }
  return true;
});
