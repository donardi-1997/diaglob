import { api } from "./api";

export interface CarrierDefinition {
  key: string;
  name: string;
  countries: string[];
  integration_modes: string[];
  tracking_page_url: string | null;
  supports_push_webhook: boolean;
  supports_direct_sync: boolean;
  documented_api: boolean;
}

export interface CarrierConnection {
  id: number;
  carrier_key: string;
  integration_mode: string;
  status: string;
  external_account_id: string | null;
  provider_config: Record<string, unknown>;
  last_sync_at: string | null;
  last_error: string | null;
  connected_at: string;
}

export interface StoreCarrierItem extends CarrierDefinition {
  connection: CarrierConnection | null;
}

export interface CarrierConnectResult {
  ok: boolean;
  carrier: CarrierDefinition;
  connection: CarrierConnection;
  webhook_token: string;
  callback_url: string;
}

export interface ShipmentTrackingEvent {
  id: number;
  status: string;
  provider_status_code: number | null;
  description: string | null;
  location: string | null;
  event_at: string;
}

export interface Shipment {
  id: number;
  provider: string;
  order_id: number | null;
  supplier_order_id: number | null;
  tracking_number: string;
  logistic_name: string | null;
  tracking_provider: string | null;
  tracking_url: string | null;
  origin_country_code: string | null;
  destination_country_code: string | null;
  last_mile_carrier: string | null;
  last_mile_tracking_number: string | null;
  status: string;
  provider_status_code: number | null;
  provider_status_label: string | null;
  delivery_days: string | null;
  delivery_time: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  last_event_at: string | null;
  last_synced_at: string | null;
  events: ShipmentTrackingEvent[];
}

export async function getStoreCarriers(storeId: number) {
  const response = await api.get<{
    store_id: number;
    country_code: string;
    items: StoreCarrierItem[];
  }>(`/api/stores/${storeId}/carriers`);
  return response.data;
}

export async function connectCarrier(
  storeId: number,
  carrierKey: string,
) {
  const response = await api.post<CarrierConnectResult>(
    `/api/stores/${storeId}/carriers/${carrierKey}/connect`,
    { integration_mode: "webhook" },
  );
  return response.data;
}

export async function disconnectCarrier(
  storeId: number,
  carrierKey: string,
) {
  const response = await api.delete<{
    ok: boolean;
    carrier_key: string;
    status: string;
  }>(`/api/stores/${storeId}/carriers/${carrierKey}`);
  return response.data;
}

export async function listShipments(
  storeId: number,
  options?: {
    status?: string;
    carrierKey?: string;
    limit?: number;
  },
) {
  const params = new URLSearchParams();
  if (options?.status) params.set("status", options.status);
  if (options?.carrierKey) params.set("carrier_key", options.carrierKey);
  if (options?.limit) params.set("limit", String(options.limit));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await api.get<{
    items: Shipment[];
    total: number;
  }>(`/api/stores/${storeId}/shipments${suffix}`);
  return response.data;
}

export async function registerShipment(
  storeId: number,
  payload: {
    carrier_key: string;
    tracking_number: string;
    order_id?: number;
    tracking_url?: string;
    source_provider?: string;
  },
) {
  const response = await api.post<{
    created: boolean;
    shipment: Shipment;
  }>(`/api/stores/${storeId}/shipments`, payload);
  return response.data;
}

export async function syncShipment(
  storeId: number,
  shipmentId: number,
) {
  const response = await api.post(
    `/api/stores/${storeId}/shipments/${shipmentId}/sync`,
  );
  return response.data;
}
