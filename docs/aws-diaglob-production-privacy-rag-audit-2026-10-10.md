# DIAGLOB — AWS production privacy, backup and Bedrock RAG audit

**Date:** 2026-10-10. **Scope:** connected AWS account; region `us-east-2`, plus S3 bucket metadata. **Type:** read-only evidence, not an availability penetration test, restored-backup proof or Shopify privacy compliance. **No customer files, object keys, message bodies, secrets or vector values were accessed.**

## 1. Direct AWS evidence

| Resource | AWS API evidence | Verified state | Risk / limitation |
|---|---|---|---|
| Lightsail `diaglob-prod` | `GetInstance` + `GetAutoSnapshots` + `GetInstanceSnapshots` | Instance **running**, 60 GiB system disk, **no instance add-ons**, zero automatic snapshots, zero manual instance snapshots | **P0 backup recovery gap** for the live instance; off-instance backup arrangements not verified |
| Lightsail additional disk snapshots | `GetDisks` + `GetDiskSnapshots` | No separately listed disks or disk snapshots | Integrated 60 GiB system disk exists; not a separate disk snapshot |
| AWS Backup | `ListProtectedResources`, `ListBackupVaults`, `ListBackupPlans` | **Zero protected resources**; only automatic EFS plan/vault (0 recovery points) | No AWS Backup recovery path confirmed for Diaglob; external backups not ruled out |
| S3 object bucket `diaglob-knowledge-765761474007-us-east-2` | `GetBucketVersioning` | **Enabled** | A normal unversioned delete can leave older data recoverable |
| S3 lifecycle | `GetBucketLifecycleConfiguration` | `NoSuchLifecycleConfiguration` | **P1 retention gap**; no automatic noncurrent-version expiration |
| S3 object inventory | `ListObjectsV2` + `ListObjectVersions` (untruncated) | **0 current objects**, **2 noncurrent versions**, **2 delete markers**, 502 bytes across noncurrent versions | Not safe to assume old versions were permanently deleted; no object content inspected |
| S3 encryption | `GetBucketEncryption` | SSE-S3 (`AES256`) enabled | Encryption protects at rest, not deletion or tenant isolation |
| S3 public access | `GetPublicAccessBlock` | All four public-block switches **true** | Good baseline; IAM and object-level policies not audited |
| S3 replication / notifications | `GetBucketReplication`, `GetBucketNotificationConfiguration` | No replication configuration; no Lambda/SNS/SQS bucket notifications | Ingest may depend on explicit sync, not event notification |
| S3 object lock | `GetObjectLockConfiguration` | No Object Lock configuration | Do not infer legally approved retention/hold logic from AWS object lock |
| S3 bucket logging/inventory | `GetBucketLogging`, `ListBucketInventoryConfigurations` | Logging **off**; no inventory configurations | Need alternate audit evidence (e.g. CloudTrail/Lightsail logs) and coverage |
| S3 bucket policy | `GetBucketPolicyStatus` | No bucket policy | Block Public Access remains enabled; full identity policy/ACL review still pending |
| CloudWatch Logs | `DescribeLogGroups` | One group `/aws/lambda/ai-recruiter-chat`, no `diaglob`-named group | DIAGLOB may log to Nginx/systemd/files, Sentry or other regions; **not proof of no logs** |

### 2. Bedrock Knowledge Bases and vector storage

All five KBs are `ACTIVE`, vector-based, with `S3_VECTORS` storage. Their vector bucket is `diaglob-vectors-765761474007-us-east-2`.

| Knowledge Base name | KB ID | Data source / S3 prefix | Active source | Ingestion jobs returned | Indexed vectors |
|---|---|---|---|---:|---:|
| `diaglob-knowledge-main` | `RDAQY1JNQ8` | No data source | No | N/A | **0** |
| `diaglob-prod-org-1-kb-8` | `I7I4UMMTKQ` | `organizations/1/knowledge-bases/8/documents/` | Yes, AVAILABLE | 0 | **0** |
| `diaglob-prod-org-1-kb-9` | `GMWILSCNUV` | `organizations/1/knowledge-bases/9/documents/` | Yes, AVAILABLE | 0 | **0** |
| `diaglob-prod-org-1-kb-12` | `OTTG8ZZICZ` | `organizations/1/knowledge-bases/12/documents/` | Yes, AVAILABLE | 0 | **0** |
| `diaglob-prod-org-1-kb-13` | `TJPCCGWWOI` | `organizations/1/knowledge-bases/13/documents/` | Yes, AVAILABLE | 0 | **0** |

The four sources point to the S3 bucket above. `GetDataSource` returns `dataDeletionPolicy=DELETE` for each, but that applies to **source/KB deletion of indexed data**, not blanket expiration of all versioned S3 objects. The vector bucket and indexes are separate resources and are not automatically deleted with the KB. All five indexes were listed by `ListIndexes`. `ListVectors` returned **zero vectors and no next page** for every index. The bucket currently has **zero active documents**; all four source prefixes had zero current objects.

**Consequence:** the knowledge-backed RAG retrieval path for these five KBs currently has no indexed content. This does not prove the general LLM assistant or its other data integrations are down. No documents should be restored/uploaded automatically without provenance, tenant authorization and user-approved source selection.

Official AWS references:
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-ds-update.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-ds-delete.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html

## 3. Prioritized implementation plan

**P0: backups and restore verification (owner approval needed for billing/config changes).** Select a Lightsail automatic snapshot time and enable the built-in daily snapshots for `diaglob-prod`, then verify one real recovery point and a controlled restoration drill into a separate, isolated test target. AWS stores up to seven recent auto snapshots; storage is billed. A snapshot **is not** a substitute for database application-consistent backups and off-instance disaster recovery. Before enabling, agree on RPO/RTO, data recovery scope (SQLite/Postgres, file uploads, app secrets, nginx configs) and cost ceiling. Do not automatically reboot or mutate the production instance.

**P0: restore knowledge ingestion from authorized sources.** Verify which DIAGLOB KnowledgeBase rows are supposed to have content and their source ownership/consent. Exercise the existing application upload/sync flows (see `backend/app/services/knowledge_source_lifecycle.py`, `knowledge_ingestion.py` and `bedrock_ingestion.py`) with **synthetic tenant-owned documents**. Confirm the S3 prefix has a current object, Bedrock ingestion job is `COMPLETE`, vector count becomes greater than zero, and an authorized retrieval query returns only the expected store/org document. No need to run an empty ingestion job over empty S3.

**P1: S3 lifecycle and privacy deletion design (legal/owner decision required).** Define per-prefix retention and hold rules first. For versioned S3, ordinary object deletion creates a **delete marker**; noncurrent versions require explicit lifecycle expiration or version-ID deletion. A blanket bucket lifecycle rule risks permanently deleting lawful records and therefore is **NOT applied here**. Verify processor copies, backups, vector indexes and restore/reingestion suppression. Consider noncurrent-version expiration, expired delete-marker cleanup, aborted multipart cleanup, object inventory and CloudTrail data events after exact approval of time windows and cost.

**P1: observability.** Determine where the FastAPI backend and reverse proxy persist logs on Lightsail and whether the data is redacted, rotated and shipped to a retained central store. Confirm Sentry integration and retention. Add alerting for failed KB ingestion, orphaned indexed vectors, failed backups, S3 public access regression and privacy queue cases older than 23/30 days.

**P2: recurring audit.** Implement or schedule a read-only inventory that checks the above metadata, per-prefix live object counts and vector counts without printing document keys, customer selectors or vector data. Keep its output restricted to operations/admin users.

## 4. Change-control boundary and open evidence

No AWS settings, AWS resource lifecycle, instance backups, object versions, vector stores, IAM policies or API keys were changed as part of this inspection. CloudFront, external data processors, the live application DB and log files, private snapshots in other accounts, legal hold decisions and tenant-facing authorization **remain unverified**.

**Release assessment: BLOCK** for Shopify App Store real privacy fulfillment until a signed retention policy, legitimate subject provenance and complete disposal/recovery coverage exist. RAG retrieval also needs an end-to-end functional proof after documents are intentionally seeded.

Official references:
- https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-configuring-automatic-snapshots.html
- https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-snapshots.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/troubleshooting-versioning.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html

**Tracking:** issue #148 / draft PR #149. This document supersedes the narrower `docs/shopify-privacy-aws-infrastructure-evidence-2026-10-10.md` inventory.
