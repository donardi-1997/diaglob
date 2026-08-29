import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import {
  LoaderCircle,
  Search,
} from "lucide-react";
import {
  listCommerceProducts,
  type CommerceProduct,
} from "../services/integrations";


interface CommerceProductsProps {
  storeId: number;
  canWrite: boolean;
}


export default function CommerceProducts({
  storeId,
  canWrite: _canWrite,
}: CommerceProductsProps) {
  const { t } = useTranslation();

  const [products, setProducts] =
    useState<CommerceProduct[]>([]);

  const [total, setTotal] = useState(0);

  const [searchQuery, setSearchQuery] =
    useState("");

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");


  useEffect(() => {
    loadProducts();
  }, [storeId]);


  async function loadProducts(
    query?: string,
  ) {
    try {
      setLoading(true);
      setError("");

      const data =
        await listCommerceProducts(
          storeId,
          query,
        );

      setProducts(data.items);
      setTotal(data.total);
    } catch {
      setError(
        t("commerceProductsError"),
      );
    } finally {
      setLoading(false);
    }
  }


  function handleSearch(
    e: React.FormEvent,
  ) {
    e.preventDefault();

    loadProducts(
      searchQuery.trim() || undefined,
    );
  }


  function formatPrice(
    price: number,
    currency: string,
  ) {
    return `${currency} ${price.toFixed(2)}`;
  }


  if (loading && products.length === 0) {
    return (
      <div className="commerce-loading">
        <LoaderCircle
          className="spin"
          size={24}
        />
      </div>
    );
  }


  return (
    <div className="commerce-products">
      <form
        className="commerce-search-bar"
        onSubmit={handleSearch}
      >
        <Search size={16} />

        <input
          type="text"
          placeholder={t(
            "commerceProductsSearch",
          )}
          value={searchQuery}
          onChange={(e) =>
            setSearchQuery(e.target.value)
          }
        />

        <button type="submit">
          {t("commerceSearch")}
        </button>
      </form>

      {error && (
        <div className="commerce-error">
          {error}
        </div>
      )}

      {!error && products.length === 0 && (
        <div className="commerce-empty">
          <p>{t("commerceNoProducts")}</p>
        </div>
      )}

      {products.length > 0 && (
        <>
          <div className="commerce-count">
            {t("commerceResultsCount", {
              count: total,
            })}
          </div>

          <div className="commerce-product-grid">
            {products.map((product) => (
              <div
                key={product.id}
                className="commerce-product-card"
              >
                <div className="commerce-product-image">
                  {product.image_url ? (
                    <img
                      src={
                        product.image_url
                      }
                      alt={product.title}
                    />
                  ) : (
                    <div className="commerce-product-placeholder">
                      {product.title.charAt(
                        0,
                      )}
                    </div>
                  )}
                </div>

                <div className="commerce-product-info">
                  <h4>
                    {product.title}
                  </h4>

                  <p className="commerce-product-vendor">
                    {product.vendor
                      ?? product.product_type
                      ?? "—"}
                  </p>

                  <div className="commerce-product-variants">
                    {product.variants
                      .slice(0, 3)
                      .map((variant) => (
                        <div
                          key={
                            variant.id
                          }
                          className="commerce-product-variant"
                        >
                          <span>
                            {variant.title}
                          </span>

                          <span className="commerce-variant-price">
                            {formatPrice(
                              variant.price,
                              product.store
                                ?.currency
                                ?? "USD",
                            )}
                          </span>
                        </div>
                      ))}

                    {product.variants
                      .length >
                      3 && (
                      <span className="commerce-variant-more">
                        +
                        {product.variants
                          .length -
                          3}{" "}
                        {t(
                          "commerceMore",
                        )}
                      </span>
                    )}
                  </div>

                  {product.active && (
                    <span className="commerce-badge created">
                      {t(
                        "commerceActive",
                      )}
                    </span>
                  )}

                  {!product.active && (
                    <span className="commerce-badge failed">
                      {t(
                        "commerceInactive",
                      )}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
