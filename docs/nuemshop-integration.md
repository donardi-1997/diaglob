# Nuvemshop Integration

## Architecture

```
Frontend → Diaglob API → Nuvemshop Service → Nuvemshop Client → Nuvemshop API
                                    ↓
                              Commerce Data (Products, Customers, Orders)
                                    ↓
                              Canonical Diaglob Models
```

## OAuth Flow

1. Frontend requests OAuth URL from `nuvemshop_service.get_oauth_url()`
2. User authorizes in Nuvemshop
3. Nuvemshop redirects to callback with code
4. Backend exchanges code for access token
5. Backend retrieves store info
6. Backend encrypts and stores token

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NUVEMSHOP_CLIENT_ID` | Nuvemshop App Client ID |
| `NUVEMSHOP_CLIENT_SECRET` | Nuvemshop App Client Secret |
| `NUVEMSHOP_REDIRECT_URI` | OAuth callback URL |
| `NUVEMSHOP_ENCRYPTION_KEY` | Fernet encryption key for tokens |
| `NUVEMSHOP_API_VERSION` | API version (default: 2025-03-01) |
| `NUVEMSHOP_BASE_URL` | API base URL (default: https://api.tiendanube.com/v1) |

## PIX Support

PIX is recognized as a payment method when Nuvemshop exposes it in order data.

### What PIX Support Means

**SUPPORTED:**
- Identify PIX as payment method from provider data
- Display PIX as payment method
- Know whether order/payment is pending/paid/cancelled
- PIX pending reminder automation template
- Portuguese merchant-facing copy

**NOT SUPPORTED:**
- Generating PIX keys
- Creating PIX QR codes
- Creating payment charges
- Polling Brazilian banks
- PIX refunds through Diaglob
- BRL subscription billing for Diaglob

## Order Model Fields

| Field | Description |
|-------|-------------|
| `external_order_id` | Nuvemshop order ID |
| `payment_method` | PIX, CREDIT_CARD, BOLETO, OTHER, UNKNOWN |
| `payment_status` | PENDING, PAID, REFUNDED, CANCELLED, UNKNOWN |

## Tenant Isolation

- Organization → Store → Commerce Connection
- All Nuvemshop operations scoped to organization/store
- No cross-store product collision
- No cross-tenant access

## Security

- Access tokens encrypted with Fernet
- OAuth state validated
- No raw tokens in frontend/logs
- No customer PII in analytics

## Supported Resources

- Products (sync)
- Customers (sync)
- Orders (sync)
- Store info (connection)

## Unsupported Resources

- Webhooks (not yet implemented)
- Fulfillment management
- Inventory updates
- Product creation
- Order management

## Migration

**Current Alembic revision:** `f6f002b05545`
**Parent revision:** `e63418b90903` (canonical initial schema)

### What This Migration Adds

Three columns to the `orders` table:
- `external_order_id` (String(255), nullable, indexed)
- `payment_method` (String(50), nullable, indexed)
- `payment_status` (String(50), nullable, indexed)

### Upgrade Path

```bash
cd backend && alembic upgrade head
```

The migration uses schema-aware idempotent guards: it inspects the physical database
before adding columns/indexes, so it is safe to run against databases that may already
have these fields.

### Stamped-But-Missing Recovery

**WARNING:** `alembic stamp` does NOT execute migrations. It only records the revision
in `alembic_version`. If you stamped a database without running the migration, the
physical schema may be missing the Nuvemshop fields.

To check:
```sql
SELECT version_num FROM alembic_version;
PRAGMA table_info(orders);  -- SQLite
SELECT column_name FROM information_schema.columns WHERE table_name = 'orders';  -- PostgreSQL
```

Recovery:
1. If `version_num = f6f002b05545` but columns are missing:
   ```bash
   cd backend && alembic downgrade e63418b90903
   cd backend && alembic upgrade head
   ```
   This re-runs the migration and adds the missing columns.

2. If `version_num = e63418b90903`:
   ```bash
   cd backend && alembic upgrade head
   ```

3. If `version_num = f6f002b05545` and columns exist:
   No action needed. The migration is already applied.

### Schema Verification

```python
from sqlalchemy import inspect, create_engine
engine = create_engine("postgresql://...")
inspector = inspect(engine)
cols = {c["name"] for c in inspector.get_columns("orders")}
assert "external_order_id" in cols
assert "payment_method" in cols
assert "payment_status" in cols
```
