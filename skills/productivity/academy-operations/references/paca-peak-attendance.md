# PACA/Peak attendance retrieval notes

Session learning: a Discord user asked whether PACA/Peak was linked and requested today's attendance. The login binding was present, but the academy operation catalog tool wrapper initially failed because the dispatcher supplied extra metadata. The durable operating lesson is to verify binding and then call the read API directly if a wrapper fails.

## Binding location

Local Miho home:

```text
~/.miho/academy_ops/bindings.json
~/.miho/academy_ops/secret.key
```

Use the plugin's store helpers rather than reading/decrypting manually:

```python
from plugins.academy_ops.auth_store import load_bindings, decrypt_token
bindings = load_bindings()
binding = next(iter(bindings.values()))
token = decrypt_token(binding.token_ciphertext)
```

Do not print or send the token.

## Verified endpoint

Base URL comes from `plugins.academy_ops.paca_config.resolve_paca_base_url()`, which honors `MIHO_ACADEMY_PACA_BASE_URL` first and then `academy_ops.paca_base_url` in `~/.miho/config.yaml`.

```python
import datetime, httpx
from plugins.academy_ops.paca_config import resolve_paca_base_url

base = resolve_paca_base_url()
date = datetime.date.today().isoformat()
response = httpx.get(
    f"{base}/peak/attendance/students",
    params={"date": date},
    headers={"Authorization": f"Bearer {token}"},
    timeout=12,
    follow_redirects=True,
)
response.raise_for_status()
payload = response.json()
```

Observed working auth header:

```text
Authorization: Bearer <token>
```

Observed non-working header in this flow:

```text
x-access-token: <token>
```

## Response shaping

The endpoint returned:

```text
payload.date
payload.slots.morning[]
payload.slots.afternoon[]
payload.slots.evening[]
```

Rows included fields like:

```text
student_id, student_name, gender, school, grade, attendance_status
```

For Discord, group by normalized status and avoid unnecessary PII:

```text
오늘 출석 현황 — YYYY-MM-DD
- 오전: N명
- 오후: N명
- 저녁: N명
- 출석: N명
- 지각: N명
- 결석: N명

출석: 이름, 이름...
지각: 이름...
결석: 이름...
```

## Related plugin-tool pitfall

If a Miho plugin tool handler is called through the dispatcher, it may receive extra keyword metadata such as `task_id`. Handler signatures should tolerate extra kwargs:

```python
def _catalog_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    return json.dumps(operations_payload(), ensure_ascii=False)
```

This is a coding fix, not a reason to tell the user the academy integration is missing.
