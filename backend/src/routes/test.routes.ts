import { FastifyInstance, FastifyPluginAsync } from 'fastify';
import { Type } from '@sinclair/typebox';
import bcrypt from 'bcryptjs';
import { UserRole, InvoiceStatus } from '@prisma/client';

export const testRoutes: FastifyPluginAsync = async (fastify: FastifyInstance) => {
  // Hanya aktif di environment non-production
  if (process.env.NODE_ENV === 'production') {
    return;
  }

  fastify.post(
    '/reset-seed',
    {
      schema: {
        description: 'Endpoint khusus dev/testing untuk mereset database ke status seed bersih',
        tags: ['Testing'],
        response: {
          200: Type.Object({
            success: Type.Boolean(),
            message: Type.String(),
            timestamp: Type.String(),
          }),
        },
      },
    },
    async (_request, reply) => {
      const prisma = fastify.prisma;

      // 1. Bersihkan transaksi invoice dan riwayat audit
      await prisma.paymentVoucher.deleteMany();
      await prisma.verificationIssue.deleteMany();
      await prisma.invoiceLineItem.deleteMany();
      await prisma.invoicePaymentDetail.deleteMany();
      await prisma.reviewerAssignment.deleteMany();
      await prisma.auditLog.deleteMany();
      await prisma.invoiceRequest.deleteMany();

      // 2. Pastikan data akun standar tersedia
      const defaultPassword = process.env.SEED_DEFAULT_PASSWORD || 'password123!';
      const salt = await bcrypt.genSalt(10);
      const passwordHash = await bcrypt.hash(defaultPassword, salt);

      const clientMain = await prisma.client.upsert({
        where: { clientCode: 'CLI-MAIN' },
        update: { clientName: 'PT Main Industri Terpadu', isActive: true },
        create: { clientCode: 'CLI-MAIN', clientName: 'PT Main Industri Terpadu', isActive: true },
      });

      const client001 = await prisma.client.upsert({
        where: { clientCode: 'CLI-001' },
        update: { clientName: 'PT Sejahtera Mitra Abadi', isActive: true },
        create: { clientCode: 'CLI-001', clientName: 'PT Sejahtera Mitra Abadi', isActive: true },
      });

      const client002 = await prisma.client.upsert({
        where: { clientCode: 'CLI-002' },
        update: { clientName: 'PT Nusantara Logistik Jaya', isActive: true },
        create: { clientCode: 'CLI-002', clientName: 'PT Nusantara Logistik Jaya', isActive: true },
      });

      const sysadmin = await prisma.user.upsert({
        where: { email: 'sysadmin@amiga.co.id' },
        update: { fullName: 'System Administrator', passwordHash, role: UserRole.SYSTEM_ADMIN, isActive: true },
        create: { email: 'sysadmin@amiga.co.id', fullName: 'System Administrator', passwordHash, role: UserRole.SYSTEM_ADMIN, isActive: true },
      });

      const reviewer1 = await prisma.user.upsert({
        where: { email: 'reviewer1@amiga.co.id' },
        update: { fullName: 'Finance Reviewer Satu', passwordHash, role: UserRole.FINANCE_REVIEWER, isActive: true },
        create: { email: 'reviewer1@amiga.co.id', fullName: 'Finance Reviewer Satu', passwordHash, role: UserRole.FINANCE_REVIEWER, isActive: true },
      });

      const reviewer2 = await prisma.user.upsert({
        where: { email: 'reviewer2@amiga.co.id' },
        update: { fullName: 'Finance Reviewer Dua', passwordHash, role: UserRole.FINANCE_REVIEWER, isActive: true },
        create: { email: 'reviewer2@amiga.co.id', fullName: 'Finance Reviewer Dua', passwordHash, role: UserRole.FINANCE_REVIEWER, isActive: true },
      });

      const picClient = await prisma.user.upsert({
        where: { email: 'pic_client@amiga.co.id' },
        update: { fullName: 'PIC Klien Utama', passwordHash, role: UserRole.PIC_KLIEN, isActive: true },
        create: { email: 'pic_client@amiga.co.id', fullName: 'PIC Klien Utama', passwordHash, role: UserRole.PIC_KLIEN, isActive: true },
      });

      const intakeSupport = await prisma.user.upsert({
        where: { email: 'intake_support@amiga.co.id' },
        update: { fullName: 'Intake Support Staff', passwordHash, role: UserRole.INTAKE_SUPPORT, isActive: true },
        create: { email: 'intake_support@amiga.co.id', fullName: 'Intake Support Staff', passwordHash, role: UserRole.INTAKE_SUPPORT, isActive: true },
      });

      const serviceLead = await prisma.user.upsert({
        where: { email: 'service_lead@amiga.co.id' },
        update: { fullName: 'Service Operations Lead', passwordHash, role: UserRole.SERVICE_LEAD, isActive: true },
        create: { email: 'service_lead@amiga.co.id', fullName: 'Service Operations Lead', passwordHash, role: UserRole.SERVICE_LEAD, isActive: true },
      });

      // Assignments
      for (const client of [clientMain, client001, client002]) {
        await prisma.userClientAssignment.upsert({
          where: { userId_clientId: { userId: reviewer1.id, clientId: client.id } },
          update: { delegatedBy: sysadmin.id },
          create: { userId: reviewer1.id, clientId: client.id, delegatedBy: sysadmin.id },
        });
        await prisma.userClientAssignment.upsert({
          where: { userId_clientId: { userId: reviewer2.id, clientId: client.id } },
          update: { delegatedBy: sysadmin.id },
          create: { userId: reviewer2.id, clientId: client.id, delegatedBy: sysadmin.id },
        });
        await prisma.userClientAssignment.upsert({
          where: { userId_clientId: { userId: serviceLead.id, clientId: client.id } },
          update: { delegatedBy: sysadmin.id },
          create: { userId: serviceLead.id, clientId: client.id, delegatedBy: sysadmin.id },
        });
      }

      await prisma.userClientAssignment.upsert({
        where: { userId_clientId: { userId: picClient.id, clientId: clientMain.id } },
        update: { delegatedBy: sysadmin.id },
        create: { userId: picClient.id, clientId: clientMain.id, delegatedBy: sysadmin.id },
      });

      await prisma.userClientAssignment.upsert({
        where: { userId_clientId: { userId: intakeSupport.id, clientId: clientMain.id } },
        update: { delegatedBy: sysadmin.id },
        create: { userId: intakeSupport.id, clientId: clientMain.id, delegatedBy: sysadmin.id },
      });

      // 3. Seed Sample Invoices for UI/E2E deterministic tests
      // A. Invoice 1: READY_FOR_REVIEW (clean)
      await prisma.invoiceRequest.create({
        data: {
          requestId: 'REQ-20261014-CLEAN1',
          clientId: clientMain.id,
          uploaderId: picClient.id,
          currentReviewerId: reviewer1.id,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date('2026-10-14'),
          originalFileName: 'clean-invoice.pdf',
          storageFilePath: 'invoices/clean-invoice.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Nusantara Solusi Digital',
          vendorNameNormalized: 'pt nusantara solusi digital',
          invoiceNumber: 'INV-2026-001',
          invoiceNumberNormalized: 'inv2026001',
          invoiceDate: new Date('2026-10-14'),
          subtotalAmount: 15000000,
          taxAmount: 0,
          totalAmount: 15000000,
          lineItems: {
            create: [
              {
                itemIndex: 1,
                description: 'Jasa Konsultasi TI & Cloud Infrastructure',
                quantity: 1,
                unitPrice: 15000000,
                subtotal: 15000000,
              },
            ],
          },
          paymentDetails: {
            create: {
              bankName: 'Bank Central Asia (BCA)',
              accountNumber: '8820192831',
              accountHolderName: 'PT Nusantara Solusi Digital',
            },
          },
          assignments: {
            create: {
              assignedReviewerId: reviewer1.id,
              triggerReason: 'INITIAL_ASSIGNMENT',
              reasonNotes: 'Penugasan otomatis sistem initial assignment',
            },
          },
        },
      });

      // B. Invoice 2: EXCEPTION (missing evidence)
      await prisma.invoiceRequest.create({
        data: {
          requestId: 'REQ-20261014-EXCP01',
          clientId: clientMain.id,
          uploaderId: picClient.id,
          currentReviewerId: reviewer1.id,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date('2026-10-14'),
          originalFileName: 'missing-evidence.pdf',
          storageFilePath: 'invoices/clean-invoice.pdf',
          filePageCount: 1,
          status: InvoiceStatus.EXCEPTION,
          vendorName: 'CV Mitra Mandiri',
          vendorNameNormalized: 'cv mitra mandiri',
          invoiceNumber: 'INV-2026-002',
          invoiceNumberNormalized: 'inv2026002',
          invoiceDate: new Date('2026-10-14'),
          subtotalAmount: 7500000,
          taxAmount: 0,
          totalAmount: 7500000,
          lineItems: {
            create: [
              {
                itemIndex: 1,
                description: 'Jasa Desain Grafis & Percetakan',
                quantity: 1,
                unitPrice: 7500000,
                subtotal: 7500000,
              },
            ],
          },
          issues: {
            create: [
              {
                issueCode: 'MISSING_EVIDENCE',
                issueCategory: 'COMPLETENESS',
                messageId: 'Nomor rekening atau nama bank tujuan transfer tidak terdeteksi pada berkas invoice.',
              },
            ],
          },
        },
      });

      // C. Invoice 3: AMIGA_REVIEWED (reviewed & voucher generated)
      await prisma.invoiceRequest.create({
        data: {
          requestId: 'REQ-20261014-APPR01',
          clientId: clientMain.id,
          uploaderId: picClient.id,
          currentReviewerId: reviewer1.id,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date('2026-10-14'),
          originalFileName: 'clean-invoice.pdf',
          storageFilePath: 'invoices/clean-invoice.pdf',
          filePageCount: 1,
          status: InvoiceStatus.AMIGA_REVIEWED,
          vendorName: 'PT Global Solusi Logistik',
          vendorNameNormalized: 'pt global solusi logistik',
          invoiceNumber: 'INV-2026-003',
          invoiceNumberNormalized: 'inv2026003',
          invoiceDate: new Date('2026-10-14'),
          subtotalAmount: 20000000,
          taxAmount: 0,
          totalAmount: 20000000,
          lineItems: {
            create: [
              {
                itemIndex: 1,
                description: 'Pengiriman Kargo Laut Kontainer 20ft',
                quantity: 1,
                unitPrice: 20000000,
                subtotal: 20000000,
              },
            ],
          },
          paymentDetails: {
            create: {
              bankName: 'Bank Mandiri',
              accountNumber: '1420009988776',
              accountHolderName: 'PT Global Solusi Logistik',
            },
          },
          paymentVoucher: {
            create: {
              voucherNumber: 'VCH/202610/CLI-MAIN/00001',
              voucherFilePath: 'vouchers/VCH_202610_CLI-MAIN_00001.pdf',
              authorizationBoundaryText: 'BATAS OTORISASI PEMBAYARAN LEGAL: Voucher ini diterbitkan secara otomatis oleh AMIGA Robot Admin untuk otorisasi verifikasi finansial.',
              generatedBy: reviewer1.id,
            },
          },
          auditLogs: {
            create: [
              {
                actorId: picClient.id,
                actorName: picClient.fullName,
                actorRole: 'PIC_KLIEN',
                actionType: 'INVOICE_UPLOADED',
                newStatus: 'QUEUED',
              },
              {
                actorName: 'AI Engine',
                actorRole: 'AI_ENGINE',
                actionType: 'EXTRACTION_SUCCEEDED',
                previousStatus: 'PROCESSING',
                newStatus: 'READY_FOR_REVIEW',
              },
              {
                actorId: reviewer1.id,
                actorName: reviewer1.fullName,
                actorRole: 'FINANCE_REVIEWER',
                actionType: 'REVIEW_APPROVED',
                previousStatus: 'READY_FOR_REVIEW',
                newStatus: 'AMIGA_REVIEWED',
              },
            ],
          },
        },
      });

      // D. Invoice 4: READY_FOR_REVIEW with SoD conflict (uploader == reviewer1)
      await prisma.invoiceRequest.create({
        data: {
          requestId: 'REQ-20261014-SOD001',
          clientId: clientMain.id,
          uploaderId: reviewer1.id,
          currentReviewerId: reviewer1.id,
          requestType: 'Standard Vendor Invoice',
          submissionChannel: 'Portal',
          submissionDate: new Date('2026-10-14'),
          originalFileName: 'clean-invoice.pdf',
          storageFilePath: 'invoices/clean-invoice.pdf',
          filePageCount: 1,
          status: InvoiceStatus.READY_FOR_REVIEW,
          vendorName: 'PT Cipta Kreasi Sejahtera',
          vendorNameNormalized: 'pt cipta kreasi sejahtera',
          invoiceNumber: 'INV-2026-SOD01',
          invoiceNumberNormalized: 'inv2026sod01',
          invoiceDate: new Date('2026-10-14'),
          subtotalAmount: 10000000,
          taxAmount: 0,
          totalAmount: 10000000,
          lineItems: {
            create: [
              {
                itemIndex: 1,
                description: 'Pengadaan Server Rack & Network Hub',
                quantity: 1,
                unitPrice: 10000000,
                subtotal: 10000000,
              },
            ],
          },
          paymentDetails: {
            create: {
              bankName: 'Bank Mandiri',
              accountNumber: '1234567890',
              accountHolderName: 'PT Cipta Kreasi Sejahtera',
            },
          },
          assignments: {
            create: {
              assignedReviewerId: reviewer1.id,
              triggerReason: 'INITIAL_ASSIGNMENT',
              reasonNotes: 'Penugasan otomatis awal untuk simulasi SoD',
            },
          },
        },
      });

      return reply.send({
        success: true,
        message: 'Database berhasil di-reset ke kondisi awal pengujian.',
        timestamp: new Date().toISOString(),
      });
    }
  );
};
