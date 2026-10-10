# DIAGLOB infrastructure — scoped read-only evidence (2026-10-10)

**Scope:** AWS metadata read in `us-east-2` through the connected AWS account. No secret values, S3 object contents, logs, database data or PII were accessed. No mutations.

| AWS API | Verified finding | Interpretation |
|---|---|---|
| Lightsail GetInstances | `diaglob-prod` state `running` in `us-east-2` | Server exists; runtime/deployment health and private file/database footprint **not** verified |
| Lightsail GetInstanceSnapshots | Zero returned snapshots for matching `diaglob` names | Does not prove no automatic backups, disk snapshots, off-account copies or restores exist |
| S3 ListBuckets | `diaglob-knowledge-765761474007-us-east-2` present | Bucket exists; versioning, lifecycle, contents, object PII and KB links **not** reviewed |
| CloudWatch Logs DescribeLogGroups | No log group names containing `diaglob` in inspected region | Not proof of no logs; nonmatching names, other regions, Lightsail/Nginx/app files, external monitoring not checked |

Evidence gathered only from successful APIs above, with filtered non-sensitive metadata. Other AWS regions/accounts, S3 lifecycle/versioning, disk/DB backups, object-level retention, Bedrock ingestion, CDN and external third-party vendors remain unverified.

**Codex / operations next steps (read-only first):** map actual persistence volume/DB, bucket versioning and object lifecycle, Knowledge Base source and reindex behavior, Lighthouse snapshots, local/hosted logs and service retention, restoration tests, and merchant data processor inventory. No customer-data export/deletion may be marked complete based on this inspection.

Related: `docs/shopify-privacy-inventory-ownership-review-2026-10-10.md`, issue #148, PR #149.
