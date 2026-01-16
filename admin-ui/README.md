## Unified Adapter Admin UI

Static admin dashboard for managing adapter tool metadata. This lives inside the
adapter repo but is decoupled from Automatos UI.

### Run locally

```bash
cd automatos-unified-adapter/admin-ui
python -m http.server 5173
```

Open `http://localhost:5173`, set:

- `API Base URL` → `http://localhost:8000`
- `Admin Token` → value of `ADAPTER_AUTH_TOKEN`

### Notes

- Uses the adapter admin API (`/admin/tools`) for CRUD.
- Tool changes require adapter restart to reload the tool registry.
