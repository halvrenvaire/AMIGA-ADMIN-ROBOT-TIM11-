-- CreateEnum
CREATE TYPE "UserRole" AS ENUM ('PIC_KLIEN', 'INTAKE_SUPPORT', 'FINANCE_REVIEWER', 'SERVICE_LEAD', 'SYSTEM_ADMIN');

-- CreateEnum
CREATE TYPE "InvoiceStatus" AS ENUM ('QUEUED', 'PROCESSING', 'READY_FOR_REVIEW', 'EXCEPTION', 'AMIGA_REVIEWED', 'SENT_TO_CLIENT');

-- CreateEnum
CREATE TYPE "IssueCode" AS ENUM ('MISSING_EVIDENCE', 'POSSIBLE_DUPLICATE', 'CALCULATION_DISCREPANCY', 'REVIEWER_RETURNED');

-- CreateEnum
CREATE TYPE "IssueCategory" AS ENUM ('COMPLETENESS', 'INTEGRITY', 'ARITHMETIC', 'MANUAL_REVIEW');

-- CreateEnum
CREATE TYPE "AssignmentTriggerReason" AS ENUM ('INITIAL_ASSIGNMENT', 'SOD_AUTO_REASSIGN', 'WORKLOAD_REBALANCE_LEAD');

-- CreateTable
CREATE TABLE "clients" (
    "id" UUID NOT NULL,
    "client_code" VARCHAR(20) NOT NULL,
    "client_name" VARCHAR(150) NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "clients_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "users" (
    "id" UUID NOT NULL,
    "email" VARCHAR(120) NOT NULL,
    "full_name" VARCHAR(150) NOT NULL,
    "password_hash" VARCHAR(255) NOT NULL,
    "role" "UserRole" NOT NULL,
    "default_client_id" UUID,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_client_assignments" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "client_id" UUID NOT NULL,
    "delegated_by" UUID NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "user_client_assignments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invoice_requests" (
    "id" UUID NOT NULL,
    "request_id" VARCHAR(30) NOT NULL,
    "client_id" UUID NOT NULL,
    "uploader_id" UUID NOT NULL,
    "current_reviewer_id" UUID,
    "request_type" VARCHAR(50) NOT NULL,
    "submission_channel" VARCHAR(50) NOT NULL,
    "submission_date" DATE NOT NULL,
    "original_file_name" VARCHAR(255) NOT NULL,
    "storage_file_path" VARCHAR(500) NOT NULL,
    "file_page_count" INTEGER NOT NULL,
    "status" "InvoiceStatus" NOT NULL DEFAULT 'QUEUED',
    "vendor_name" VARCHAR(150),
    "vendor_name_normalized" VARCHAR(150),
    "invoice_number" VARCHAR(80),
    "invoice_number_normalized" VARCHAR(80),
    "invoice_date" DATE,
    "subtotal_amount" DECIMAL(15,2),
    "tax_amount" DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    "total_amount" DECIMAL(15,2),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "invoice_requests_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invoice_line_items" (
    "id" UUID NOT NULL,
    "request_id" UUID NOT NULL,
    "item_index" INTEGER NOT NULL,
    "description" TEXT NOT NULL,
    "quantity" DECIMAL(12,4) NOT NULL,
    "unit_price" DECIMAL(15,2) NOT NULL,
    "subtotal" DECIMAL(15,2) NOT NULL,
    "is_manually_edited" BOOLEAN NOT NULL DEFAULT false,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "invoice_line_items_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invoice_payment_details" (
    "id" UUID NOT NULL,
    "request_id" UUID NOT NULL,
    "bank_name" VARCHAR(100),
    "account_number" VARCHAR(50),
    "account_holder_name" VARCHAR(150),
    "is_manually_edited" BOOLEAN NOT NULL DEFAULT false,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "invoice_payment_details_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "verification_issues" (
    "id" UUID NOT NULL,
    "request_id" UUID NOT NULL,
    "issue_code" "IssueCode" NOT NULL,
    "issue_category" "IssueCategory" NOT NULL,
    "message_id" TEXT NOT NULL,
    "is_resolved" BOOLEAN NOT NULL DEFAULT false,
    "detected_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolved_at" TIMESTAMPTZ,

    CONSTRAINT "verification_issues_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "reviewer_assignments" (
    "id" UUID NOT NULL,
    "request_id" UUID NOT NULL,
    "previous_reviewer_id" UUID,
    "assigned_reviewer_id" UUID NOT NULL,
    "assigned_by_user_id" UUID,
    "trigger_reason" "AssignmentTriggerReason" NOT NULL,
    "reason_notes" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "reviewer_assignments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "payment_vouchers" (
    "id" UUID NOT NULL,
    "request_id" UUID NOT NULL,
    "voucher_number" VARCHAR(50) NOT NULL,
    "voucher_file_path" VARCHAR(500) NOT NULL,
    "authorization_boundary_text" TEXT NOT NULL,
    "generated_by" UUID NOT NULL,
    "generated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "payment_vouchers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_logs" (
    "id" BIGSERIAL NOT NULL,
    "request_id" UUID NOT NULL,
    "actor_id" UUID,
    "actor_name" VARCHAR(150) NOT NULL,
    "actor_role" VARCHAR(50) NOT NULL,
    "action_type" VARCHAR(50) NOT NULL,
    "previous_status" VARCHAR(30),
    "new_status" VARCHAR(30),
    "change_diff" JSONB,
    "ip_address" VARCHAR(45),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "clients_client_code_key" ON "clients"("client_code");

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "user_client_assignments_user_id_client_id_key" ON "user_client_assignments"("user_id", "client_id");

-- CreateIndex
CREATE UNIQUE INDEX "invoice_requests_request_id_key" ON "invoice_requests"("request_id");

-- CreateIndex
CREATE INDEX "idx_invoice_client_status" ON "invoice_requests"("client_id", "status");

-- CreateIndex
CREATE INDEX "idx_invoice_duplicate_lookup" ON "invoice_requests"("client_id", "vendor_name_normalized", "invoice_number_normalized");

-- CreateIndex
CREATE INDEX "invoice_line_items_request_id_idx" ON "invoice_line_items"("request_id");

-- CreateIndex
CREATE UNIQUE INDEX "invoice_payment_details_request_id_key" ON "invoice_payment_details"("request_id");

-- CreateIndex
CREATE INDEX "verification_issues_request_id_idx" ON "verification_issues"("request_id");

-- CreateIndex
CREATE INDEX "reviewer_assignments_request_id_idx" ON "reviewer_assignments"("request_id");

-- CreateIndex
CREATE UNIQUE INDEX "payment_vouchers_request_id_key" ON "payment_vouchers"("request_id");

-- CreateIndex
CREATE UNIQUE INDEX "payment_vouchers_voucher_number_key" ON "payment_vouchers"("voucher_number");

-- CreateIndex
CREATE INDEX "idx_audit_logs_request" ON "audit_logs"("request_id", "created_at" ASC);

-- AddForeignKey
ALTER TABLE "users" ADD CONSTRAINT "users_default_client_id_fkey" FOREIGN KEY ("default_client_id") REFERENCES "clients"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_client_assignments" ADD CONSTRAINT "user_client_assignments_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_client_assignments" ADD CONSTRAINT "user_client_assignments_client_id_fkey" FOREIGN KEY ("client_id") REFERENCES "clients"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_client_assignments" ADD CONSTRAINT "user_client_assignments_delegated_by_fkey" FOREIGN KEY ("delegated_by") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoice_requests" ADD CONSTRAINT "invoice_requests_client_id_fkey" FOREIGN KEY ("client_id") REFERENCES "clients"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoice_requests" ADD CONSTRAINT "invoice_requests_uploader_id_fkey" FOREIGN KEY ("uploader_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoice_requests" ADD CONSTRAINT "invoice_requests_current_reviewer_id_fkey" FOREIGN KEY ("current_reviewer_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoice_line_items" ADD CONSTRAINT "invoice_line_items_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "invoice_requests"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoice_payment_details" ADD CONSTRAINT "invoice_payment_details_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "invoice_requests"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "verification_issues" ADD CONSTRAINT "verification_issues_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "invoice_requests"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "reviewer_assignments" ADD CONSTRAINT "reviewer_assignments_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "invoice_requests"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "reviewer_assignments" ADD CONSTRAINT "reviewer_assignments_previous_reviewer_id_fkey" FOREIGN KEY ("previous_reviewer_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "reviewer_assignments" ADD CONSTRAINT "reviewer_assignments_assigned_reviewer_id_fkey" FOREIGN KEY ("assigned_reviewer_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "reviewer_assignments" ADD CONSTRAINT "reviewer_assignments_assigned_by_user_id_fkey" FOREIGN KEY ("assigned_by_user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payment_vouchers" ADD CONSTRAINT "payment_vouchers_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "invoice_requests"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payment_vouchers" ADD CONSTRAINT "payment_vouchers_generated_by_fkey" FOREIGN KEY ("generated_by") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "invoice_requests"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_actor_id_fkey" FOREIGN KEY ("actor_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;
