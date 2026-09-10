import { getAgents } from "./agents";
import { listAutomations } from "./automations";
import { getConversations } from "./conversations";
import { getCustomerList } from "./customers";
import {
  globalSearchMatches,
  normalizeGlobalSearchQuery,
} from "./globalSearchHelpers";
import {
  listCommerceOrders,
  listCommerceProducts,
} from "./integrations";
import { getKnowledgeBases } from "./knowledgeBases";


export type GlobalSearchResultKind =
  | "navigation"
  | "conversation"
  | "customer"
  | "product"
  | "order"
  | "automation"
  | "agent"
  | "knowledge"
  | "store";


export interface GlobalSearchResult {
  key: string;
  kind: GlobalSearchResultKind;
  title: string;
  subtitle: string;
  page: string;
  entityId?: number;
  storeId?: number;
  query?: string;
}


export interface GlobalSearchCategories {
  conversations: boolean;
  customers: boolean;
  commerce: boolean;
  automations: boolean;
  agents: boolean;
  knowledge: boolean;
}


interface SearchWorkspaceOptions {
  query: string;
  storeId?: number;
  categories: GlobalSearchCategories;
}


async function safeSearch(
  task: () => Promise<GlobalSearchResult[]>,
): Promise<GlobalSearchResult[]> {
  try {
    return await task();
  } catch {
    return [];
  }
}


export async function searchWorkspace({
  query,
  storeId,
  categories,
}: SearchWorkspaceOptions): Promise<GlobalSearchResult[]> {
  const normalized = normalizeGlobalSearchQuery(query);

  if (normalized.length < 2) {
    return [];
  }

  const tasks: Promise<GlobalSearchResult[]>[] = [];

  if (categories.customers) {
    tasks.push(
      safeSearch(async () => {
        const data = await getCustomerList({
          storeId,
          search: query.trim(),
          page: 1,
          pageSize: 6,
        });

        return data.items.slice(0, 6).map((customer) => ({
          key: `customer:${customer.id}`,
          kind: "customer" as const,
          title: customer.name,
          subtitle: [customer.phone, customer.email]
            .filter(Boolean)
            .join(" · "),
          page: "customers",
          entityId: customer.id,
          storeId: customer.store_id ?? storeId,
          query: customer.name,
        }));
      }),
    );
  }

  if (categories.conversations) {
    tasks.push(
      safeSearch(async () => {
        const data = await getConversations(storeId);

        return data.items
          .filter((conversation) =>
            globalSearchMatches(normalized, [
              conversation.name,
              conversation.phone,
              conversation.email,
              conversation.preview,
              conversation.channel,
              ...conversation.tags,
            ]),
          )
          .slice(0, 6)
          .map((conversation) => ({
            key: `conversation:${conversation.id}`,
            kind: "conversation" as const,
            title: conversation.name || conversation.phone,
            subtitle: conversation.preview || conversation.channel,
            page: "conversations",
            entityId: conversation.id,
            storeId: conversation.store?.id ?? storeId,
            query: conversation.name || conversation.phone,
          }));
      }),
    );
  }

  if (categories.commerce && storeId) {
    tasks.push(
      safeSearch(async () => {
        const data = await listCommerceProducts(storeId, query.trim());

        return data.items.slice(0, 6).map((product) => {
          const sku = product.variants.find((variant) => variant.sku)?.sku;
          const variant = product.variants[0];
          const price = variant
            ? `${variant.currency} ${variant.price.toLocaleString()}`
            : "";

          return {
            key: `product:${product.id}`,
            kind: "product" as const,
            title: product.title,
            subtitle: [sku, product.vendor, price].filter(Boolean).join(" · "),
            page: "commerce",
            entityId: product.id,
            storeId,
            query: product.title,
          };
        });
      }),
    );

    tasks.push(
      safeSearch(async () => {
        const data = await listCommerceOrders(storeId);

        return data.items
          .filter((order) =>
            globalSearchMatches(normalized, [
              order.order_number,
              order.source,
              order.note,
              ...order.items.flatMap((item) => [item.title, item.sku]),
            ]),
          )
          .slice(0, 6)
          .map((order) => ({
            key: `order:${order.id}`,
            kind: "order" as const,
            title: `#${order.order_number}`,
            subtitle: `${order.currency} ${order.total_amount.toLocaleString()}${order.items[0] ? ` · ${order.items[0].title}` : ""}`,
            page: "commerce",
            entityId: order.id,
            storeId,
            query: order.order_number,
          }));
      }),
    );
  }

  if (categories.automations && storeId) {
    tasks.push(
      safeSearch(async () => {
        const data = await listAutomations(storeId);

        return data.items
          .filter((automation) =>
            globalSearchMatches(normalized, [
              automation.name,
              automation.description,
              automation.trigger_type,
            ]),
          )
          .slice(0, 6)
          .map((automation) => ({
            key: `automation:${automation.id}`,
            kind: "automation" as const,
            title: automation.name,
            subtitle: automation.description || automation.trigger_type,
            page: "automations",
            entityId: automation.id,
            storeId: automation.store_id ?? storeId,
            query: automation.name,
          }));
      }),
    );
  }

  if (categories.agents) {
    tasks.push(
      safeSearch(async () => {
        const data = await getAgents();

        return data.items
          .filter((agent) => {
            const belongsToStore =
              !storeId || agent.stores.some((store) => store.id === storeId);

            return belongsToStore && globalSearchMatches(normalized, [
              agent.name,
              agent.role,
            ]);
          })
          .slice(0, 6)
          .map((agent) => ({
            key: `agent:${agent.id}`,
            kind: "agent" as const,
            title: agent.name,
            subtitle: agent.role,
            page: "agents",
            entityId: agent.id,
            storeId,
            query: agent.name,
          }));
      }),
    );
  }

  if (categories.knowledge) {
    tasks.push(
      safeSearch(async () => {
        const data = await getKnowledgeBases();

        return data.items
          .filter((knowledgeBase) => {
            const belongsToStore =
              !storeId
              || knowledgeBase.scope === "organization"
              || knowledgeBase.stores.some((store) => store.id === storeId);

            return belongsToStore && globalSearchMatches(normalized, [
              knowledgeBase.name,
              knowledgeBase.scope,
              knowledgeBase.external_status,
            ]);
          })
          .slice(0, 6)
          .map((knowledgeBase) => ({
            key: `knowledge:${knowledgeBase.id}`,
            kind: "knowledge" as const,
            title: knowledgeBase.name,
            subtitle: knowledgeBase.external_status,
            page: "knowledge",
            entityId: knowledgeBase.id,
            storeId,
            query: knowledgeBase.name,
          }));
      }),
    );
  }

  const groups = await Promise.all(tasks);
  return groups.flat().slice(0, 30);
}
