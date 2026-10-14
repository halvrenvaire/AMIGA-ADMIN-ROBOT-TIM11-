import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { FastifyInstance } from 'fastify';
import { UserRole } from '@prisma/client';
import { buildApp } from '../../app.js';
import { requireRoles, requireTenantAccess } from '../../plugins/rbac.plugin.js';

describe('T-004: Auth & RBAC Guard Integration Tests', () => {
  let app: FastifyInstance;
  let picToken: string;
  let reviewerToken: string;
  let picAssignedClientId: string;

  beforeAll(async () => {
    app = buildApp();

    // Register dummy protected routes within app.register so decorators (app.authenticate) are available
    await app.register(async (scopedApp) => {
      scopedApp.get(
        '/api/v1/test/reviewer-only',
        {
          preHandler: [scopedApp.authenticate, requireRoles([UserRole.FINANCE_REVIEWER])],
        },
        async () => ({ success: true, message: 'Reviewer access granted' })
      );

      scopedApp.get(
        '/api/v1/test/tenant-protected/:clientId',
        {
          preHandler: [
            scopedApp.authenticate,
            requireTenantAccess((req) => (req.params as { clientId: string }).clientId),
          ],
        },
        async () => ({ success: true, message: 'Tenant access granted' })
      );
    });

    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  describe('POST /api/v1/auth/login', () => {
    it('harus berhasil login dengan kredensial valid (PIC Klien) dan mengembalikan JWT', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/auth/login',
        payload: {
          email: 'pic_client@amiga.co.id',
          password: 'password123!',
        },
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      expect(body.data.accessToken).toBeDefined();
      expect(body.data.user.email).toBe('pic_client@amiga.co.id');
      expect(body.data.user.role).toBe('PIC_KLIEN');
      expect(body.data.user.assignedClientIds.length).toBeGreaterThan(0);

      picToken = body.data.accessToken;
      picAssignedClientId = body.data.user.assignedClientIds[0];
    });

    it('harus berhasil login untuk Finance Reviewer dan mengembalikan JWT', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/auth/login',
        payload: {
          email: 'reviewer1@amiga.co.id',
          password: 'password123!',
        },
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      expect(body.data.user.role).toBe('FINANCE_REVIEWER');

      reviewerToken = body.data.accessToken;
    });

    it('harus menolak login jika password salah dengan format RFC 7807 (401)', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/auth/login',
        payload: {
          email: 'pic_client@amiga.co.id',
          password: 'wrong_password_amiga',
        },
      });

      expect(response.statusCode).toBe(401);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('AUTH_INVALID_CREDENTIALS');
      expect(body.error.message).toContain('tidak valid');
    });

    it('harus menolak login jika email tidak terdaftar dengan format RFC 7807 (401)', async () => {
      const response = await app.inject({
        method: 'POST',
        url: '/api/v1/auth/login',
        payload: {
          email: 'unknown_user_99@amiga.co.id',
          password: 'password123!',
        },
      });

      expect(response.statusCode).toBe(401);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('AUTH_INVALID_CREDENTIALS');
    });
  });

  describe('GET /api/v1/auth/me', () => {
    it('harus menolak request tanpa token dengan RFC 7807 (401)', async () => {
      const response = await app.inject({
        method: 'GET',
        url: '/api/v1/auth/me',
      });

      expect(response.statusCode).toBe(401);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('AUTH_UNAUTHORIZED');
    });

    it('harus mengembalikan profil pengguna jika token Bearer valid (200)', async () => {
      const response = await app.inject({
        method: 'GET',
        url: '/api/v1/auth/me',
        headers: {
          authorization: `Bearer ${picToken}`,
        },
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      expect(body.data.user.email).toBe('pic_client@amiga.co.id');
      expect(body.data.user.role).toBe('PIC_KLIEN');
    });
  });

  describe('RBAC Guard & Tenant Boundary Enforcement', () => {
    it('harus menolak PIC Klien (403 FORBIDDEN_ROLE) saat mengakses route khusus Reviewer', async () => {
      const response = await app.inject({
        method: 'GET',
        url: '/api/v1/test/reviewer-only',
        headers: {
          authorization: `Bearer ${picToken}`,
        },
      });

      expect(response.statusCode).toBe(403);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('FORBIDDEN_ROLE');
      expect(body.error.details.userRole).toBe('PIC_KLIEN');
    });

    it('harus mengizinkan Finance Reviewer (200 OK) mengakses route khusus Reviewer', async () => {
      const response = await app.inject({
        method: 'GET',
        url: '/api/v1/test/reviewer-only',
        headers: {
          authorization: `Bearer ${reviewerToken}`,
        },
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
    });

    it('harus mengizinkan PIC Klien mengakses klien yang ditugaskan kepadanya (200 OK)', async () => {
      const response = await app.inject({
        method: 'GET',
        url: `/api/v1/test/tenant-protected/${picAssignedClientId}`,
        headers: {
          authorization: `Bearer ${picToken}`,
        },
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
    });

    it('harus menolak PIC Klien (403 TENANT_FORBIDDEN) saat mencoba mengakses clientId lain', async () => {
      const fakeUnassignedClientId = '00000000-0000-0000-0000-000000000999';
      const response = await app.inject({
        method: 'GET',
        url: `/api/v1/test/tenant-protected/${fakeUnassignedClientId}`,
        headers: {
          authorization: `Bearer ${picToken}`,
        },
      });

      expect(response.statusCode).toBe(403);
      const body = JSON.parse(response.body);
      expect(body.success).toBe(false);
      expect(body.error.code).toBe('TENANT_FORBIDDEN');
    });
  });
});
