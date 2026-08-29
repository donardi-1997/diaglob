import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  Check,
  ExternalLink,
  Loader2,
  ShoppingBag,
  X,
} from "lucide-react";
import {
  createShopifyOrder,
  listShopifyOrders,
  type Order,
  type OrderItem,
} from "../services/integrations";


interface ShopifyOrdersProps {
  storeId: number;
  canWrite: boolean;
  shopConnected: boolean;
  syncedProducts: OrderItem[];
}


interface CartItem {
  variant_local_id: number;
  title: string;
  sku: string | null;
  price: number;
  currency: string;
  quantity: number;
}


export default function ShopifyOrders({
  storeId,
  canWrite,
  shopConnected,
}: ShopifyOrdersProps) {
  const { t } = useTranslation();

  const [orders, setOrders] =
    useState<Order[]>([]);

  const [loading, setLoading] =
    useState(false);

  const [creating, setCreating] =
    useState(false);

  const [error, setError] = useState("");

  const [success, setSuccess] =
    useState("");

  const [cart, setCart] = useState<
    CartItem[]
  >([]);

  const [searchQuery, setSearchQuery] =
    useState("");

  const [searchResults, setSearchResults] =
    useState<any[]>([]);

  const [searching, setSearching] =
    useState(false);


  async function loadOrders() {
    try {
      setLoading(true);
      const data =
        await listShopifyOrders(storeId);
      setOrders(data.items);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    if (shopConnected) {
      loadOrders();
    }
  }, [storeId, shopConnected]);


  async function handleSearch() {
    if (!searchQuery.trim()) return;

    try {
      setSearching(true);
      const response = await fetch(
        `/api/commerce/products?q=${encodeURIComponent(
          searchQuery,
        )}&store_id=${storeId}`,
        {
          credentials: "include",
        },
      );

      if (response.ok) {
        const data = await response.json();
        const results: any[] = [];
        for (const p of data.items || []) {
          for (const v of p.variants || []) {
            results.push({
              variant_local_id: v.id,
              title: `${p.title} — ${v.title}`,
              sku: v.sku,
              price: v.price,
              currency: v.currency,
            });
          }
        }
        setSearchResults(results);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  }


  function addToCart(item: any) {
    setCart((prev) => {
      const exists = prev.find(
        (c) =>
          c.variant_local_id ===
          item.variant_local_id,
      );

      if (exists) {
        return prev.map((c) =>
          c.variant_local_id ===
          item.variant_local_id
            ? {
                ...c,
                quantity: c.quantity + 1,
              }
            : c,
        );
      }

      return [...prev, { ...item, quantity: 1 }];
    });
  }


  function removeFromCart(
    variant_local_id: number,
  ) {
    setCart((prev) =>
      prev.filter(
        (c) =>
          c.variant_local_id !==
          variant_local_id,
      ),
    );
  }


  function updateQuantity(
    variant_local_id: number,
    quantity: number,
  ) {
    if (quantity < 1) return;

    setCart((prev) =>
      prev.map((c) =>
        c.variant_local_id ===
        variant_local_id
          ? { ...c, quantity }
          : c,
      ),
    );
  }


  const cartTotal = cart.reduce(
    (sum, item) =>
      sum + item.price * item.quantity,
    0,
  );


  async function handleCreateOrder() {
    if (cart.length === 0) return;

    try {
      setCreating(true);
      setError("");
      setSuccess("");

      const idempotency_key =
        crypto.randomUUID();

      const result =
        await createShopifyOrder(
          storeId,
          cart.map((c) => ({
            variant_local_id:
              c.variant_local_id,
            quantity: c.quantity,
          })),
          {
            idempotency_key,
            note: "Created from DIAGLOB",
          },
        );

      if (result.ok) {
        setSuccess(
          t(
            "integrationsShopifyOrderCreateOk",
          ),
        );
        setCart([]);

        if (result.invoice_url) {
          window.open(
            result.invoice_url,
            "_blank",
            "noopener,noreferrer",
          );
        }

        await loadOrders();
      }
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail;

      setError(
        (typeof detail === "string"
          ? detail
          : detail?.message) ||
          t(
            "integrationsShopifyOrderCreateError",
          ),
      );
    } finally {
      setCreating(false);
    }
  }


  if (!shopConnected) return null;


  return (
    <div className="store-integration-block shopify-orders">
      <div className="store-integration-header">
        <div className="store-integration-title">
          <ShoppingBag size={17} />

          <strong>
            {t(
              "integrationsShopifyOrdersTitle",
            )}
          </strong>
        </div>
      </div>

      {error && (
        <div className="stores-alert error">
          {error}
        </div>
      )}

      {success && (
        <div className="stores-alert success">
          <Check size={15} />
          {success}
        </div>
      )}

      {canWrite && (
        <div className="shopify-order-cart">
          <div className="shopify-order-search">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) =>
                setSearchQuery(
                  e.target.value,
                )
              }
              onKeyDown={(e) =>
                e.key === "Enter" &&
                handleSearch()
              }
              placeholder={t(
                "integrationsShopifyOrderSearch",
              )}
              autoComplete="off"
            />

            <button
              type="button"
              className="store-integration-button secondary"
              onClick={handleSearch}
              disabled={searching}
            >
              {searching ? (
                <Loader2
                  className="spin"
                  size={14}
                />
              ) : null}
              {t("integrationsShopifyTest")}
            </button>
          </div>

          {searchResults.length > 0 && (
            <div className="shopify-order-search-results">
              {searchResults.map((r) => (
                <div
                  key={r.variant_local_id}
                  className="shopify-order-search-item"
                >
                  <span>
                    {r.title}
                    {r.sku
                      ? ` (${r.sku})`
                      : ""}
                    {" — "}
                    {r.price} {r.currency}
                  </span>

                  <button
                    type="button"
                    className="store-integration-button secondary"
                    onClick={() =>
                      addToCart(r)
                    }
                  >
                    +
                  </button>
                </div>
              ))}
            </div>
          )}

          {cart.length > 0 && (
            <div className="shopify-order-cart-items">
              {cart.map((item) => (
                <div
                  key={
                    item.variant_local_id
                  }
                  className="shopify-order-cart-item"
                >
                  <span className="cart-item-title">
                    {item.title}
                  </span>

                  <div className="cart-item-controls">
                    <button
                      type="button"
                      onClick={() =>
                        updateQuantity(
                          item.variant_local_id,
                          item.quantity - 1,
                        )
                      }
                    >
                      -
                    </button>

                    <span>
                      {item.quantity}
                    </span>

                    <button
                      type="button"
                      onClick={() =>
                        updateQuantity(
                          item.variant_local_id,
                          item.quantity + 1,
                        )
                      }
                    >
                      +
                    </button>

                    <button
                      type="button"
                      className="cart-item-remove"
                      onClick={() =>
                        removeFromCart(
                          item.variant_local_id,
                        )
                      }
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ))}

              <div className="shopify-order-cart-total">
                <strong>
                  Total: {cartTotal.toFixed(2)}{" "}
                  {cart[0]?.currency}
                </strong>
              </div>

              <button
                type="button"
                className="store-integration-button primary"
                onClick={handleCreateOrder}
                disabled={creating}
              >
                {creating ? (
                  <Loader2
                    className="spin"
                    size={14}
                  />
                ) : (
                  <ShoppingBag size={14} />
                )}

                {t(
                  "integrationsShopifyOrderCreate",
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {loading ? (
        <Loader2
          className="spin"
          size={16}
        />
      ) : orders.length === 0 ? (
        <div className="shopify-order-empty">
          {t(
            "integrationsShopifyOrderEmpty",
          )}
        </div>
      ) : (
        <div className="shopify-order-list">
          {orders.map((order) => (
            <div
              key={order.id}
              className="shopify-order-row"
            >
              <span className="order-number">
                {order.order_number}
              </span>

              <span className="order-status">
                {order.financial_status}
              </span>

              <span className="order-total">
                {order.total_amount}{" "}
                {order.currency}
              </span>

              {order.invoice_url && (
                <a
                  href={order.invoice_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="order-invoice-link"
                >
                  <ExternalLink size={14} />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
