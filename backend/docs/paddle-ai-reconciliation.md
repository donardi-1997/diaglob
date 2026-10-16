# Paddle AI payments awaiting reconciliation

**Permanent records:** Do not delete Paddle transactions, customers, products,
prices, notification destinations, credit grants, webhook event receipts, or
pending reconciliation rows.

A verified `transaction.completed` for an AI package is independent of
subscription event ordering. New purchases carry HMAC-signed metadata. Older
unsigned purchases may be provisioned only when Paddle's customer ID is
uniquely bound to an eligible DIAGLOB organization, the package response count
matches the server catalog, and the completed transaction contains exactly
one item at the configured Paddle price.

Unresolved or malformed purchases are stored in
`paddle_ai_reconciliations` with status `pending`. A webhook response with
`pending_reconciliation: true` **does not mean credits were granted**.

For a pending purchase:
1. Review its transaction and customer in the Paddle live dashboard and the
   corresponding DIAGLOB organization association.
2. Never infer ownership from the `claimed_organization_id` or email.
3. After an independently verified customer-to-organization association exists,
   an authorized backend operator can invoke
   `reconcile_pending_ai_transaction(db, transaction_id)`. It fetches the
   transaction from Paddle using the server API key, requires `completed`,
   revalidates ownership and exact price, then grants credits idempotently.
4. If the owner remains unknown, leave the record `pending`. Escalate rather
   than attributing a payment to an unverified tenant.

This reconciliation operation is not a public route. Do not use it for
subscription changes. Keep Paddle API credentials and signing secrets only
in the server environment.
