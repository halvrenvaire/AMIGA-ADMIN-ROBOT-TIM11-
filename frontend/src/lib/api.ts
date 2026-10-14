import {
  UserProfile,
  ClientItem,
  QueueResponseData,
  ReviewDataResponse,
  InvoiceStatus,
  PaymentVoucherData,
  AuditTrailResponseData,
} from './types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000';

class ApiClient {
  private token: string | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('amiga_token');
    }
  }

  setToken(token: string | null) {
    this.token = token;
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('amiga_token', token);
      } else {
        localStorage.removeItem('amiga_token');
      }
    }
  }

  getToken(): string | null {
    if (!this.token && typeof window !== 'undefined') {
      this.token = localStorage.getItem('amiga_token');
    }
    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE_URL}${endpoint}`;
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    const currentToken = this.getToken();
    if (currentToken && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${currentToken}`;
    }

    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(url, {
      ...options,
      headers,
    });

    const json = await res.json().catch(() => ({}));

    if (!res.ok) {
      const message = json?.error?.message || json?.message || `Request failed with status ${res.status}`;
      const code = json?.error?.code || 'UNKNOWN_ERROR';
      const error = new Error(message) as Error & { code?: string; statusCode?: number; details?: unknown };
      error.code = code;
      error.statusCode = res.status;
      error.details = json?.error?.details;
      throw error;
    }

    return json.data !== undefined ? json.data : json;
  }

  // Auth Endpoints
  async login(email: string, password: string = 'password123!'): Promise<{
    accessToken: string;
    expiresIn: number;
    user: UserProfile;
  }> {
    const res = await this.request<{
      accessToken: string;
      expiresIn: number;
      user: UserProfile;
    }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(res.accessToken);
    return res;
  }

  async getMe(): Promise<{ user: UserProfile }> {
    return this.request<{ user: UserProfile }>('/api/v1/auth/me');
  }

  async getClients(): Promise<ClientItem[]> {
    return this.request<ClientItem[]>('/api/v1/auth/clients');
  }

  // Queue Endpoints
  async getQueue(params: {
    clientId?: string;
    status?: InvoiceStatus;
    search?: string;
    page?: number;
    limit?: number;
  } = {}): Promise<QueueResponseData> {
    const query = new URLSearchParams();
    if (params.clientId) query.append('clientId', params.clientId);
    if (params.status) query.append('status', params.status);
    if (params.search) query.append('search', params.search);
    if (params.page) query.append('page', params.page.toString());
    if (params.limit) query.append('limit', params.limit.toString());

    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.request<QueueResponseData>(`/api/v1/invoices/queue${qs}`);
  }

  // Review & Split-Screen Endpoints
  async getReviewData(requestId: string): Promise<ReviewDataResponse> {
    return this.request<ReviewDataResponse>(`/api/v1/invoices/${requestId}/review-data`);
  }

  getPdfUrl(requestId: string): string {
    return `${API_BASE_URL}/api/v1/invoices/${requestId}/file`;
  }

  async updateLineItems(
    requestId: string,
    items: Array<{
      id?: string;
      description: string;
      quantity: number;
      unitPrice: number;
      subtotal: number;
    }>
  ) {
    return this.request(`/api/v1/invoices/${requestId}/line-items`, {
      method: 'PUT',
      body: JSON.stringify({ items }),
    });
  }

  async approveInvoice(requestId: string) {
    return this.request<{
      requestId: string;
      status: string;
      message: string;
    }>(`/api/v1/invoices/${requestId}/approve`, {
      method: 'POST',
    });
  }

  async returnInvoice(requestId: string, returnReason: string) {
    return this.request<{
      requestId: string;
      status: string;
      issueCode: string;
      message: string;
    }>(`/api/v1/invoices/${requestId}/return`, {
      method: 'POST',
      body: JSON.stringify({ returnReason }),
    });
  }

  // Intake Upload
  async uploadInvoice(formData: FormData): Promise<{
    id: string;
    requestId: string;
    status: string;
    filePageCount: number;
    originalFileName: string;
  }> {
    return this.request('/api/v1/invoices/upload', {
      method: 'POST',
      body: formData,
    });
  }

  // Correction Endpoint
  async correctInvoice(
    requestId: string,
    data: {
      paymentDetails?: {
        bankName?: string;
        accountNumber?: string;
        accountHolderName?: string;
      };
      comments?: string;
    }
  ) {
    return this.request(`/api/v1/invoices/${requestId}/correct`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // Voucher Endpoints [PR-022, PR-023, DR-004]
  async getVoucher(requestId: string): Promise<PaymentVoucherData> {
    return this.request<PaymentVoucherData>(`/api/v1/invoices/${requestId}/voucher`);
  }

  async downloadVoucherPdf(requestId: string, fallbackFileName?: string): Promise<void> {
    const url = `${API_BASE_URL}/api/v1/invoices/${requestId}/voucher/download`;
    const token = this.getToken();
    const res = await fetch(url, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      throw new Error(json?.error?.message || 'Gagal mengunduh berkas voucher resmi.');
    }

    const blob = await res.blob();
    const disposition = res.headers.get('Content-Disposition');
    let filename = fallbackFileName || `voucher-${requestId}.pdf`;
    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename="?([^"]+)"?/);
      if (match && match[1]) filename = match[1];
    }

    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(blobUrl);
  }

  // Audit Trail Endpoints [PR-025, DR-005, PF-020]
  async getAuditTrail(requestId: string): Promise<AuditTrailResponseData> {
    return this.request<AuditTrailResponseData>(`/api/v1/invoices/${requestId}/audit-trail`);
  }
}

export const api = new ApiClient();
