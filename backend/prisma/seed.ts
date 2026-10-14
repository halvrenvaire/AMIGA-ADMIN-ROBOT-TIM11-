import { PrismaClient, UserRole } from '@prisma/client';
import bcrypt from 'bcryptjs';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables (override process.env if set from python psycopg)
dotenv.config({ path: path.resolve(__dirname, '../.env'), override: true });

// Ensure DATABASE_URL protocol is postgresql://
if (process.env.DATABASE_URL && process.env.DATABASE_URL.startsWith('postgresql+psycopg://')) {
  process.env.DATABASE_URL = process.env.DATABASE_URL.replace('postgresql+psycopg://', 'postgresql://');
}

const prisma = new PrismaClient();

async function main() {
  console.log('🌱 Memulai proses seeding database AMIGA Robot Admin...');

  const defaultPassword = process.env.SEED_DEFAULT_PASSWORD || 'password123!';
  const salt = await bcrypt.genSalt(10);
  const passwordHash = await bcrypt.hash(defaultPassword, salt);

  // 1. Seed Organisasi Klien (DR-001, PR-004)
  console.log('📦 Membuat / memperbarui data klien...');
  const clientMain = await prisma.client.upsert({
    where: { clientCode: 'CLI-MAIN' },
    update: { clientName: 'PT Main Industri Terpadu', isActive: true },
    create: {
      clientCode: 'CLI-MAIN',
      clientName: 'PT Main Industri Terpadu',
      isActive: true,
    },
  });

  const client001 = await prisma.client.upsert({
    where: { clientCode: 'CLI-001' },
    update: { clientName: 'PT Sejahtera Mitra Abadi', isActive: true },
    create: {
      clientCode: 'CLI-001',
      clientName: 'PT Sejahtera Mitra Abadi',
      isActive: true,
    },
  });

  const client002 = await prisma.client.upsert({
    where: { clientCode: 'CLI-002' },
    update: { clientName: 'PT Nusantara Logistik Jaya', isActive: true },
    create: {
      clientCode: 'CLI-002',
      clientName: 'PT Nusantara Logistik Jaya',
      isActive: true,
    },
  });

  console.log(`   ✓ Klien dibuat: ${clientMain.clientCode}, ${client001.clientCode}, ${client002.clientCode}`);

  // 2. Seed Pengguna Multi-Peran (BR-002, PR-004, PF-003)
  console.log('👤 Membuat / memperbarui akun pengguna pengujian...');

  // 2a. System Admin
  const sysadmin = await prisma.user.upsert({
    where: { email: 'sysadmin@amiga.co.id' },
    update: {
      fullName: 'System Administrator',
      passwordHash,
      role: UserRole.SYSTEM_ADMIN,
      isActive: true,
    },
    create: {
      email: 'sysadmin@amiga.co.id',
      fullName: 'System Administrator',
      passwordHash,
      role: UserRole.SYSTEM_ADMIN,
      isActive: true,
    },
  });

  // 2b. Finance Reviewer 1 & 2 (Minimal 2 reviewer untuk penegakan SoD BR-002)
  const reviewer1 = await prisma.user.upsert({
    where: { email: 'reviewer1@amiga.co.id' },
    update: {
      fullName: 'Finance Reviewer Satu',
      passwordHash,
      role: UserRole.FINANCE_REVIEWER,
      isActive: true,
    },
    create: {
      email: 'reviewer1@amiga.co.id',
      fullName: 'Finance Reviewer Satu',
      passwordHash,
      role: UserRole.FINANCE_REVIEWER,
      isActive: true,
    },
  });

  const reviewer2 = await prisma.user.upsert({
    where: { email: 'reviewer2@amiga.co.id' },
    update: {
      fullName: 'Finance Reviewer Dua',
      passwordHash,
      role: UserRole.FINANCE_REVIEWER,
      isActive: true,
    },
    create: {
      email: 'reviewer2@amiga.co.id',
      fullName: 'Finance Reviewer Dua',
      passwordHash,
      role: UserRole.FINANCE_REVIEWER,
      isActive: true,
    },
  });

  // 2c. Service Lead (Monitoring & Rebalancing)
  const serviceLead = await prisma.user.upsert({
    where: { email: 'service_lead@amiga.co.id' },
    update: {
      fullName: 'Service Lead Operations',
      passwordHash,
      role: UserRole.SERVICE_LEAD,
      isActive: true,
    },
    create: {
      email: 'service_lead@amiga.co.id',
      fullName: 'Service Lead Operations',
      passwordHash,
      role: UserRole.SERVICE_LEAD,
      isActive: true,
    },
  });

  // 2d. PIC Klien (Pengunggah dokumen & pengunduh voucher)
  const picClient = await prisma.user.upsert({
    where: { email: 'pic_client@amiga.co.id' },
    update: {
      fullName: 'PIC Klien PT Main',
      passwordHash,
      role: UserRole.PIC_KLIEN,
      defaultClientId: clientMain.id,
      isActive: true,
    },
    create: {
      email: 'pic_client@amiga.co.id',
      fullName: 'PIC Klien PT Main',
      passwordHash,
      role: UserRole.PIC_KLIEN,
      defaultClientId: clientMain.id,
      isActive: true,
    },
  });

  // 2e. Intake Support (Delegasi operasional intake)
  const intakeSupport = await prisma.user.upsert({
    where: { email: 'intake_support@amiga.co.id' },
    update: {
      fullName: 'Intake Support Staff',
      passwordHash,
      role: UserRole.INTAKE_SUPPORT,
      defaultClientId: clientMain.id,
      isActive: true,
    },
    create: {
      email: 'intake_support@amiga.co.id',
      fullName: 'Intake Support Staff',
      passwordHash,
      role: UserRole.INTAKE_SUPPORT,
      defaultClientId: clientMain.id,
      isActive: true,
    },
  });

  console.log('   ✓ Akun pengguna dibuat:');
  console.log(`     - sysadmin:       ${sysadmin.email} (SYSTEM_ADMIN)`);
  console.log(`     - reviewer1:      ${reviewer1.email} (FINANCE_REVIEWER)`);
  console.log(`     - reviewer2:      ${reviewer2.email} (FINANCE_REVIEWER)`);
  console.log(`     - service_lead:   ${serviceLead.email} (SERVICE_LEAD)`);
  console.log(`     - pic_client:     ${picClient.email} (PIC_KLIEN -> ${clientMain.clientCode})`);
  console.log(`     - intake_support: ${intakeSupport.email} (INTAKE_SUPPORT)`);

  // 3. Seed Penugasan Klien (UserClientAssignment)
  console.log('🔗 Menghubungkan hak akses klien (UserClientAssignment)...');

  // PIC Klien -> CLI-MAIN
  await prisma.userClientAssignment.upsert({
    where: {
      userId_clientId: {
        userId: picClient.id,
        clientId: clientMain.id,
      },
    },
    update: {
      delegatedBy: sysadmin.id,
    },
    create: {
      userId: picClient.id,
      clientId: clientMain.id,
      delegatedBy: sysadmin.id,
    },
  });

  // Intake Support -> CLI-MAIN & CLI-001 (multi-client delegation)
  await prisma.userClientAssignment.upsert({
    where: {
      userId_clientId: {
        userId: intakeSupport.id,
        clientId: clientMain.id,
      },
    },
    update: {
      delegatedBy: sysadmin.id,
    },
    create: {
      userId: intakeSupport.id,
      clientId: clientMain.id,
      delegatedBy: sysadmin.id,
    },
  });

  await prisma.userClientAssignment.upsert({
    where: {
      userId_clientId: {
        userId: intakeSupport.id,
        clientId: client001.id,
      },
    },
    update: {
      delegatedBy: sysadmin.id,
    },
    create: {
      userId: intakeSupport.id,
      clientId: client001.id,
      delegatedBy: sysadmin.id,
    },
  });

  console.log('   ✓ Penugasan tenant berhasil dikonfigurasi.');
  console.log('🎉 Seeding database AMIGA Robot Admin selesai dengan sukses!');
}

main()
  .catch((e) => {
    console.error('❌ Gagal menjalankan seeder:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
