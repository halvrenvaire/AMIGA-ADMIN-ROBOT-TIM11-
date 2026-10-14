export type UserRole =
  | 'PIC_KLIEN'
  | 'INTAKE_SUPPORT'
  | 'FINANCE_REVIEWER'
  | 'SERVICE_LEAD'
  | 'SYSTEM_ADMIN';

export type InvoiceStatus =
  | 'QUEUED'
  | 'PROCESSING'
  | 'READY_FOR_REVIEW'
  | 'EXCEPTION'
  | 'AMIGA_REVIEWED'
  | 'SENT_TO_CLIENT';

export interface UserProfile {
  id: string;
  email: string;
  fullName: string;
  role: UserRole;
  defaultClientId: string | null;
  assignedClientIds: string[];
}

export interface ClientItem {
  id: string;
  clientCode: string;
  clientName: string;
}

export interface InvoiceSummaryItem {
  id: string;
  requestId: string;
  clientId: string;
  clientName: string;
  clientCode: string;
  vendorName: string | null;
  invoiceNumber: string | null;
  invoiceDate: string | null;
  totalAmount: number | null;
  subtotalAmount: number | null;
  taxAmount: number | null;
  status: InvoiceStatus;
  requestType: string;
  submissionChannel: string;
  submissionDate: string;
  originalFileName: string;
  filePageCount: number;
  uploaderId: string;
  uploaderName: string;
  currentReviewerId: string | null;
  currentReviewerName: string | null;
  activeIssuesCount: number;
  createdAt: string;
}

export interface ReviewerWorkload {
  id: string;
  fullName: string;
  email: string;
  activeCount: number;
  isOverloaded: boolean;
}

export interface QueueResponseData {
  items: InvoiceSummaryItem[];
  totalCount: number;
  page: number;
  limit: number;
  totalPages: number;
  statusCounts: {
    QUEUED: number;
    PROCESSING: number;
    READY_FOR_REVIEW: number;
    EXCEPTION: number;
    AMIGA_REVIEWED: number;
    SENT_TO_CLIENT: number;
    ALL: number;
  };
  reviewerWorkloads: ReviewerWorkload[];
}

export interface VerificationIssueItem {
  id: string;
  issueCode: 'MISSING_EVIDENCE' | 'POSSIBLE_DUPLICATE' | 'CALCULATION_DISCREPANCY' | 'REVIEWER_RETURNED';
  issueCategory: 'COMPLETENESS' | 'INTEGRITY' | 'ARITHMETIC' | 'MANUAL_REVIEW';
  messageId: string;
  detectedAt: string;
}

export interface LineItemDetail {
  id: string;
  itemIndex: number;
  description: string;
  quantity: number;
  unitPrice: number;
  subtotal: number;
  isManuallyEdited: boolean;
}

export interface PaymentDetailsItem {
  id: string;
  bankName: string | null;
  accountNumber: string | null;
  accountHolderName: string | null;
  isManuallyEdited: boolean;
}

export interface ReviewDataResponse {
  invoice: {
    id: string;
    requestId: string;
    clientId: string;
    clientName: string;
    clientCode: string;
    vendorName: string | null;
    invoiceNumber: string | null;
    invoiceDate: string | null;
    subtotalAmount: number;
    taxAmount: number;
    totalAmount: number;
    status: InvoiceStatus;
    originalFileName: string;
    filePageCount: number;
    submissionDate: string;
    uploader: { id: string; fullName: string; email: string; role: string };
    currentReviewer: { id: string; fullName: string; email: string; role: string } | null;
  };
  lineItems: LineItemDetail[];
  paymentDetails: PaymentDetailsItem | null;
  issues: VerificationIssueItem[];
  pdfStreamUrl: string;
  isUploader: boolean;
  canApprove: boolean;
  sodWarning: string | null;
}

export interface PaymentVoucherData {
  id: string;
  requestId: string;
  voucherNumber: string;
  voucherFilePath: string;
  authorizationBoundaryText: string;
  generatedAt: string;
  invoiceRequest: {
    id: string;
    requestId: string;
    clientId: string;
    vendorName: string | null;
    invoiceNumber: string | null;
    invoiceDate: string | null;
    subtotalAmount: number;
    taxAmount: number;
    totalAmount: number;
    status: InvoiceStatus;
    submissionDate: string;
    client: {
      id: string;
      clientCode: string;
      clientName: string;
    };
    uploader: {
      id: string;
      fullName: string;
      email: string;
    };
    currentReviewer?: {
      id: string;
      fullName: string;
      email: string;
    } | null;
    paymentDetails: PaymentDetailsItem | null;
    lineItems: LineItemDetail[];
  };
  generator: {
    id: string;
    fullName: string;
    email: string;
    role: string;
  };
}

export interface AuditLogItem {
  id: string;
  requestId: string;
  actorId: string | null;
  actorName: string;
  actorRole: string;
  actionType: string;
  previousStatus: InvoiceStatus | string | null;
  newStatus: InvoiceStatus | string | null;
  changeDiff: Record<string, any> | null;
  ipAddress: string | null;
  createdAt: string;
  actor?: {
    id: string;
    fullName: string;
    email: string;
    role: string;
  } | null;
}

export interface AuditTrailResponseData {
  invoice: {
    id: string;
    requestId: string;
    clientId: string;
    clientName: string;
    clientCode: string;
    vendorName: string | null;
    invoiceNumber: string | null;
    status: InvoiceStatus;
    submissionDate: string;
  };
  auditLogs: AuditLogItem[];
}
