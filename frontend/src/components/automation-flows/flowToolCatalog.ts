import type { FlowToolName } from "./flowGraphUtils";

export type FlowToolFieldType = "text" | "number" | "json";

export interface FlowToolField {
  key: string;
  label: string;
  type: FlowToolFieldType;
  placeholder?: string;
  min?: number;
  max?: number;
}

export interface FlowToolCatalogItem {
  name: FlowToolName;
  title: string;
  description: string;
  group: "Pedidos" | "Productos" | "Clientes" | "Proveedores" | "Analytics";
  defaultArguments: Record<string, unknown>;
  fields: FlowToolField[];
}

export const FLOW_TOOL_CATALOG: FlowToolCatalogItem[] = [
  {
    name: "orders.list",
    title: "Listar pedidos",
    description: "Consulta pedidos de la tienda y opcionalmente filtra por estado.",
    group: "Pedidos",
    defaultArguments: { limit: 20 },
    fields: [
      {
        key: "status",
        label: "Estado",
        type: "text",
        placeholder: "paid, pending, fulfilled...",
      },
      {
        key: "limit",
        label: "Límite",
        type: "number",
        min: 1,
        max: 100,
      },
    ],
  },
  {
    name: "orders.get",
    title: "Consultar pedido",
    description: "Obtiene el detalle de un pedido concreto de la tienda.",
    group: "Pedidos",
    defaultArguments: { order_id: 1 },
    fields: [
      {
        key: "order_id",
        label: "ID del pedido",
        type: "number",
        min: 1,
      },
    ],
  },
  {
    name: "products.list",
    title: "Buscar productos",
    description: "Busca productos y variantes disponibles en la tienda.",
    group: "Productos",
    defaultArguments: { query: "", limit: 20 },
    fields: [
      {
        key: "query",
        label: "Búsqueda",
        type: "text",
        placeholder: "Nombre, handle o proveedor",
      },
      {
        key: "limit",
        label: "Límite",
        type: "number",
        min: 1,
        max: 100,
      },
    ],
  },
  {
    name: "customers.search",
    title: "Buscar cliente",
    description: "Busca clientes; admite variables del destinatario actual.",
    group: "Clientes",
    defaultArguments: { query: "{{customer.name}}", limit: 10 },
    fields: [
      {
        key: "query",
        label: "Búsqueda",
        type: "text",
        placeholder: "{{customer.name}}",
      },
      {
        key: "limit",
        label: "Límite",
        type: "number",
        min: 1,
        max: 100,
      },
    ],
  },
  {
    name: "tracking.get",
    title: "Consultar tracking",
    description: "Consulta shipment y tracking de una orden de proveedor.",
    group: "Pedidos",
    defaultArguments: { supplier_order_id: 1 },
    fields: [
      {
        key: "supplier_order_id",
        label: "ID orden proveedor",
        type: "number",
        min: 1,
      },
    ],
  },
  {
    name: "suppliers.cj.search",
    title: "Buscar en CJ",
    description: "Consulta el catálogo de CJ Dropshipping sin crear órdenes.",
    group: "Proveedores",
    defaultArguments: { query: "", limit: 20, page: 1 },
    fields: [
      {
        key: "query",
        label: "Búsqueda",
        type: "text",
        placeholder: "Producto en CJ",
      },
      {
        key: "limit",
        label: "Límite",
        type: "number",
        min: 1,
        max: 100,
      },
      {
        key: "page",
        label: "Página",
        type: "number",
        min: 1,
      },
    ],
  },
  {
    name: "suppliers.cj.quote",
    title: "Cotizar envío CJ",
    description: "Cotiza opciones de envío de CJ sin comprar ni hacer fulfillment.",
    group: "Proveedores",
    defaultArguments: {
      start_country_code: "CN",
      end_country_code: "CO",
      items: [{ variant_id: "", quantity: 1 }],
    },
    fields: [
      {
        key: "start_country_code",
        label: "País origen",
        type: "text",
        placeholder: "CN",
      },
      {
        key: "end_country_code",
        label: "País destino",
        type: "text",
        placeholder: "CO",
      },
      {
        key: "zip_code",
        label: "Código postal",
        type: "text",
      },
      {
        key: "items",
        label: "Items JSON",
        type: "json",
        placeholder: '[{"variant_id":"...","quantity":1}]',
      },
    ],
  },
  {
    name: "fulfillment.enqueue_trigger_order",
    title: "Enviar pedido confirmado a fulfillment",
    description: "Encola únicamente el pedido que disparó el flujo y que ya fue confirmado por voz.",
    group: "Pedidos",
    defaultArguments: {},
    fields: [],
  },
  {
    name: "analytics.summary",
    title: "Resumen operativo",
    description: "Consulta pedidos pagados y valor agregado de órdenes de la tienda.",
    group: "Analytics",
    defaultArguments: {},
    fields: [],
  },
];

export function getFlowToolCatalogItem(
  name: FlowToolName | string | undefined,
) {
  return FLOW_TOOL_CATALOG.find((item) => item.name === name);
}

export const FLOW_RUNTIME_VARIABLES = [
  "{{customer.id}}",
  "{{customer.name}}",
  "{{customer.email}}",
  "{{customer.phone}}",
  "{{customer.country}}",
  "{{store.name}}",
  "{{order.id}}",
  "{{order.number}}",
  "{{order.total}}",
  "{{order.currency}}",
  "{{order.payment_method}}",
  "{{order.payment_status}}",
  "{{order.is_cod}}",
  "{{order.shipping.city}}",
  "{{order.shipping.province}}",
  "{{order.shipping.country}}",
  "{{order.shipping.address1}}",
  "{{order.shipping.zip}}",
  "{{order.items_summary}}",
];
