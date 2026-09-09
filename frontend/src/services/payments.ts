import { api } from "./api";

export interface PaymentProviderInfo {
  code: string;
  name: string;
  payment_methods: string[];
  supports_webhooks: boolean;
  supports_reversals: boolean;
}

export interface PaymentConnectionStatus {
  connected: boolean;
  provider: string;
  status: string;
  environment: string | null;
  merchant_reference: string | null;
  connected_at: string | null;
  last_error: string | null;
}

export interface PaymentActionData {
  qr_code?: string;
  qr_code_base64?: string;
  ticket_url?: string;
}

export interface PaymentTransaction {
  id: number;
  provider: string;
  status: string;
  amount: string;
  currency: string;
  payment_method: string;
  provider_transaction_id: string | null;
  order_id: number | null;
  customer_phone: string | null;
  provider_status: string | null;
  expires_at: string | null;
  paid_at: string | null;
  created_at: string | null;
  action_data: PaymentActionData | null;
}

export async function getPaymentProviders(storeId: number) {
  const response = await api.get<{
    store_id: number;
    providers: PaymentProviderInfo[];
  }>(`/api/stores/${storeId}/payments/providers`);
  return response.data;
}

export async function getPaymentStatus(
  storeId: number,
  provider: string,
) {
  const response = await api.get<PaymentConnectionStatus>(
    `/api/stores/${storeId}/payments/${provider}/status`,
  );
  return response.data;
}

export async function connectMercadoPagoPix(
  storeId: number,
  accessToken: string,
  environment: "sandbox" | "production" = "sandbox",
) {
  const response = await api.post(
    `/api/stores/${storeId}/payments/mercado_pago/connect`,
    {
      provider: "mercado_pago",
      environment,
      access_token: accessToken,
    },
  );
  return response.data;
}

export async function disconnectMercadoPagoPix(storeId: number) {
  const response = await api.delete(
    `/api/stores/${storeId}/payments/mercado_pago/disconnect`,
  );
  return response.data;
}

export async function createPixPayment(
  storeId: number,
  data: {
    amount: number;
    customer_phone: string;
    customer_email: string;
    customer_document: string;
    order_id?: number;
    idempotency_key?: string;
  },
) {
  const response = await api.post<PaymentTransaction>(
    `/api/stores/${storeId}/payments`,
    {
      provider: "mercado_pago",
      payment_method: "pix",
      currency: "BRL",
      customer_document_type: "CPF",
      ...data,
    },
  );
  return response.data;
}

export async function reconcilePayment(
  storeId: number,
  paymentId: number,
) {
  const response = await api.post<PaymentTransaction>(
    `/api/stores/${storeId}/payments/${paymentId}/reconcile`,
  );
  return response.data;
}

export async function cancelPayment(
  storeId: number,
  paymentId: number,
) {
  const response = await api.post<PaymentTransaction>(
    `/api/stores/${storeId}/payments/${paymentId}/cancel`,
  );
  return response.data;
}

export async function reversePayment(
  storeId: number,
  paymentId: number,
  reason = "Merchant requested reversal",
) {
  const response = await api.post<PaymentTransaction>(
    `/api/stores/${storeId}/payments/${paymentId}/reverse`,
    { reason },
  );
  return response.data;
}
