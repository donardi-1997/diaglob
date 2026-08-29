-- ============================================================
-- MIGRATION: Shopify Draft Orders support
-- Date: 2026-08-29
-- Description: Add Order fields for Shopify Draft Orders + OrderItem table
--              + external_creation_status for DraftOrder lifecycle tracking
--
-- IDEMPOTENT: Safe to run multiple times.
--   - ADD COLUMN IF NOT EXISTS for all columns
--   - DO $$ block for CHECK constraint (pg_constraint lookup)
--   - CREATE UNIQUE INDEX IF NOT EXISTS for partial indexes
--   - CREATE TABLE IF NOT EXISTS for order_items
-- ============================================================

BEGIN;

-- ============================================================
-- 1. NEW COLUMNS ON orders TABLE
-- ============================================================

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS note TEXT DEFAULT NULL;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT NULL;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS invoice_url TEXT DEFAULT NULL;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS shopify_draft_order_id VARCHAR(255) DEFAULT NULL;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(100) DEFAULT NULL;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS external_creation_status VARCHAR(30) DEFAULT NULL;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS external_last_error TEXT DEFAULT NULL;


-- ============================================================
-- 2. CHECK CONSTRAINT for external_creation_status
--    PostgreSQL does not support ADD CONSTRAINT IF NOT EXISTS.
--    Use DO $$ block with pg_constraint lookup for idempotency.
--
--    NULL = historical orders or orders not via Shopify Draft API
--    pending = local order created, Shopify mutation not yet confirmed
--    created = Shopify returned DraftOrder ID, persisted
--    failed = deterministic failure, Shopify did NOT create DraftOrder
--    unknown = ambiguous failure (timeout/5xx), may have created DraftOrder
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_orders_external_creation_status'
    ) THEN
        ALTER TABLE orders
        ADD CONSTRAINT chk_orders_external_creation_status
        CHECK (
            external_creation_status IS NULL
            OR external_creation_status IN (
                'pending',
                'created',
                'failed',
                'unknown'
            )
        );
    END IF;
END
$$;


-- ============================================================
-- 3. UNIQUE CONSTRAINTS ON orders (STORE-SCOPED)
--    In multi-store architecture, idempotency and draft order IDs
--    must be unique WITHIN a store, not globally.
--    PostgreSQL NULLs are NOT equal, so partial UNIQUE allows
--    multiple NULLs safely.
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_order_store_idempotency_key
    ON orders (store_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_order_store_shopify_draft_order_id
    ON orders (store_id, shopify_draft_order_id)
    WHERE shopify_draft_order_id IS NOT NULL;


-- ============================================================
-- 4. NEW TABLE: order_items
-- ============================================================

CREATE TABLE IF NOT EXISTS order_items (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL
                        REFERENCES orders(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL
                        REFERENCES organizations(id) ON DELETE CASCADE,
    store_id        INTEGER NOT NULL
                        REFERENCES stores(id) ON DELETE CASCADE,
    product_id      INTEGER NULL
                        REFERENCES products(id) ON DELETE SET NULL,
    variant_id      INTEGER NULL
                        REFERENCES product_variants(id) ON DELETE SET NULL,
    shopify_variant_id VARCHAR(255) DEFAULT NULL,
    title           VARCHAR(255) NOT NULL,
    sku             VARCHAR(255) DEFAULT NULL,
    quantity        INTEGER NOT NULL,
    unit_price      NUMERIC(18,4) NOT NULL,
    currency        VARCHAR(3) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_order_items_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT chk_order_items_unit_price_non_negative
        CHECK (unit_price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON order_items (order_id);

CREATE INDEX IF NOT EXISTS idx_order_items_organization_id
    ON order_items (organization_id);

CREATE INDEX IF NOT EXISTS idx_order_items_store_id
    ON order_items (store_id);


COMMIT;
