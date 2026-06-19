# Local YAML registry

Used when `config.yml` sets `backend.mode: yaml`. These files replace the
`datalake_config` (MySQL) tables so the tools run with **no database**.

Each file is a list of row dicts. The code reads/writes the `*.yml` files; the
`*.example.yml` files here show the shape — copy one to drop the `.example`:

```bash
cp rds_endpoints.example.yml rds_endpoints.yml
```

| File | Written by | Replaces |
|---|---|---|
| `rds_endpoints.yml` | dms_automation (insert), read by transactional | `datalake_config.rds_endpoints` |
| `gsheet_targets.yml` | gsheet_onboarding | tracks each sheet→Redshift load |
| `transformation_master.yml` | transactional | `datalake_config.transformation_master` |
| `watermark.yml` | transactional | `datalake_config.watermark` |

Files are created automatically on first write if absent. `registry_dir` (in
`config.yml` `backend.registry_dir`) controls the location.
