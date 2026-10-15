# DIAGLOB Lightsail — blue/green preflight (read-only)

Current AWS evidence (14 Oct 2026, us-east-2): instance `diaglob-prod` is running; 2 vCPU, 2 GiB RAM, 60 GiB disk, one public static IPv4. Last 24h CPU averaged ~3.05% with a maximum observed of ~53.4%; burst capacity stayed near 100%. These observations **do not establish available memory or free disk**.

Security/recovery findings: inbound SSH TCP/22 is open to `0.0.0.0/0` and `::/0`. Lightsail reports **zero automatic and zero manual instance snapshots**. No RDS or Lightsail managed database was found in us-east-2; the application's database location and recovery plan are still unknown. Other backups may exist and require independent verification.

## Run only after confirming access; no writes

```bash
cd /opt/diaglob/app/backend
.venv/bin/python -m tools.bluegreen_preflight
```

The command observes `/proc/meminfo`, free disk, CPU count, systemd state, Uvicorn's loopback binding, Nginx validation and listening ports. It does not alter services, files, backups, ports, resources or the database. It fails on insufficient available RAM (less than 768 MiB), free disk (less than 1 GiB), missing loopback listener on 8000, or an occupied standby port 8001.

**A passing preflight never authorizes cutover.** Backup/recovery, Nginx routing, rollback and in-flight request draining remain manual blockers. The new port must bind only to `127.0.0.1`; do not add public firewall ports.

## Proposed phase-two architecture (not implemented)

Keep FastAPI on one Lightsail instance, with independent blue and green systemd services on loopback ports 8000 and 8001. Build and verify the standby using a local health probe; switch Nginx only after successful startup and `nginx -t`; drain in-flight requests, then release the old process. Restore the previous upstream immediately on failed post-cutover health. Verify compatibility of migrations and the previous binary **before** switching.

On 2 GiB RAM, inspect the measured memory footprint under realistic load before provisioning both variants simultaneously; adding a second instance or upgrading RAM may be required. Review the existing unmanaged `/opt/diaglob/scripts/deploy.sh`, `/etc/nginx` and systemd units before implementing modifications.

Do not merge to `main` while unsupervised production deploy is enabled; GitHub push to main starts production workflow. Prepare and test code in pull requests.
