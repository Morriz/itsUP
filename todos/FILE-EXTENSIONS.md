# File Extension Strategy

**Simple rule: `.j2` only for files with Jinja2 control flow**

---

## When to Use `.j2`

**Only when file contains Jinja2 control flow:**

```jinja2
{% for item in list %}
  - {{ item }}
{% endfor %}

{% if condition %}
  enabled: true
{% endif %}
```

**Files:**
- `tpl/proxy/docker-compose.yml.j2`
- `tpl/proxy/traefik.yml.j2`
- `tpl/proxy/routers-*.yml.j2`

These files are **rendered once** to generate artifacts.

---

## When NOT to Use `.j2`

**Files with just `${VAR}` placeholders:**

```yaml
# This is plain YAML
letsencrypt:
  email: ${LETSENCRYPT_EMAIL}

traefik:
  dashboard_auth: ${TRAEFIK_ADMIN}
```

**Files:**
- `samples/traefik.yml` (has `${VARS}`, no control flow)
- `samples/example-project/docker-compose.yml` (has `${VARS}`, no control flow)
- `samples/example-project/traefik.yml` (plain YAML)
- `projects/traefik.yml` (has `${VARS}`, committed to git)
- `projects/*/docker-compose.yml` (has `${VARS}`, committed to git)
- `projects/*/traefik.yml` (plain YAML)

These files are:
- ✅ Valid YAML (syntax highlighting works)
- ✅ Docker Compose compatible (`docker compose config` works)
- ✅ Expanded at runtime (not rendered)

---

## Why This Matters

### Editor Support

**`.yml` files:**
```yaml
# Syntax highlighting works
# YAML validation works
# Docker Compose extension understands it
```

**`.j2` files:**
```jinja2
# Need Jinja2-YAML mode
# Standard YAML tools don't understand
```

### Docker Tooling

```bash
# This works:
docker compose -f projects/my-app/docker-compose.yml config

# This wouldn't work:
docker compose -f projects/my-app/docker-compose.yml.j2 config
# Error: invalid file extension
```

### Mental Model

**`.j2` = Template (build-time rendering)**
- Contains control flow
- Rendered to generate final files
- Lives in `tpl/` directory

**`.yml` = Config (runtime expansion)**
- Plain YAML structure
- May contain `${VARS}`
- Variables expanded at deployment
- Lives in `samples/` or `projects/`

---

## Summary

| Location | Extension | Contains | Used For |
|----------|-----------|----------|----------|
| `tpl/proxy/*.j2` | `.j2` | Jinja2 control flow | Generate proxy configs |
| `samples/env` | none | Plain text env vars | Copy to .env |
| `samples/*.yml` | `.yml` | Plain YAML + `${VARS}` | Copy to projects/ |
| `samples/secrets/*.txt` | `.txt` | Plain text examples | Copy to secrets/ |
| `projects/*.yml` | `.yml` | Plain YAML + `${VARS}` | Committed config |

**Bottom line:** If it doesn't have `{% for %}` or `{% if %}`, it doesn't need `.j2`.
