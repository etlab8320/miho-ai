"""pacapro 학원 API 지도 생성 — 미호가 전체 API를 적재적소에 쓰게 하는 카탈로그.

미호는 그동안 AcademyApiClient에 수동 매핑된 ~20개 메서드만 썼다(전체 261
엔드포인트의 ~7%). 이 지도는 백엔드 코드에서 추출한 라우트 전수와 pacapro
API-SPEC.md의 모듈·엔드포인트 설명을 합쳐, academy_api_query의 map_search/
call 모드가 쓰는 화이트리스트 겸 사용 설명서가 된다.

접근 정책 (사장님 2026-06-13 승인):
- 읽기(GET): 전 모듈 허용 — 급여·결제·지출 등 돈 관련 포함.
- 쓰기(POST/PUT/PATCH/DELETE): expenses(지출)만.
- 제외: auth(인증), onboarding, users(계정), push(브라우저 구독),
  peakSso(SSO 토큰), public(외부 신청 폼) — 미호가 부를 이유가 없고
  부르면 사고인 시스템성 모듈.

입력:
  routes JSON — n100 backend/routes에서 추출한 [{file, method, path, comment}]
  API-SPEC.md — 모듈 설명 표 + 상세 엔드포인트 표

사용:
  python3 scripts/build_academy_api_map.py /tmp/paca_routes.json \
      /tmp/paca_api_spec.md ~/.miho/academy_ops/academy_api_map.json
"""

from __future__ import annotations

import json
import os
import re
import sys

EXCLUDED_MODULES = {"auth", "onboarding", "users", "push", "peakSso", "public", "classes"}
WRITE_ALLOWED_MODULES = {"expenses"}


def _kebab(name: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name).lower()


def _module_of(file_path: str) -> str:
    return file_path.split("/")[0].removesuffix(".js")


def parse_spec(spec_text: str) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """모듈 설명과 (METHOD, full_path) → 설명 매핑을 SPEC 표에서 파싱."""
    module_desc: dict[str, str] = {}
    for m in re.finditer(r"\|\s*`([a-zA-Z-]+)(?:\.js|/)?`\s*\|\s*`(/paca/[a-z-]+)`\s*\|\s*([^|]+)\|", spec_text):
        module_desc[m.group(2)] = m.group(3).strip()

    endpoint_desc: dict[tuple[str, str], str] = {}
    current_prefix = None
    for line in spec_text.splitlines():
        h = re.match(r"###\s+.*\(`(/paca/[a-z-]+)`\)", line)
        if h:
            current_prefix = h.group(1)
            continue
        row = re.match(r"\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|", line)
        if row and current_prefix:
            full = current_prefix + (row.group(2) if row.group(2) != "/" else "")
            endpoint_desc[(row.group(1), full)] = row.group(3).strip()
    return module_desc, endpoint_desc


def build(routes: list[dict], spec_text: str) -> dict:
    module_desc, endpoint_desc = parse_spec(spec_text)
    modules: dict[str, dict] = {}
    for r in routes:
        module = _module_of(r["file"])
        if module in EXCLUDED_MODULES:
            continue
        prefix = f"/paca/{_kebab(module)}"
        sub = r["path"]
        full_path = prefix + ("" if sub == "/" else sub)
        method = r["method"]
        write = method != "GET"
        if write and module not in WRITE_ALLOWED_MODULES:
            continue
        desc = endpoint_desc.get((method, full_path)) or r.get("comment") or ""
        mod = modules.setdefault(module, {
            "prefix": prefix,
            "desc": module_desc.get(prefix, ""),
            "endpoints": [],
        })
        mod["endpoints"].append({
            "method": method,
            "path": full_path,
            "desc": desc,
            "write": write,
        })
    for mod in modules.values():
        mod["endpoints"].sort(key=lambda e: (e["path"], e["method"]))
    return {
        "source": "pacapro backend/routes + API-SPEC.md",
        "policy": "GET 전 모듈 허용(시스템성 모듈 제외), 쓰기는 expenses만 (사장님 승인 2026-06-13)",
        "modules": modules,
    }


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    routes = json.load(open(sys.argv[1], encoding="utf-8"))
    spec = open(sys.argv[2], encoding="utf-8").read()
    result = build(routes, spec)
    dest = os.path.expanduser(sys.argv[3])
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    n = sum(len(m["endpoints"]) for m in result["modules"].values())
    writes = sum(1 for m in result["modules"].values() for e in m["endpoints"] if e["write"])
    described = sum(1 for m in result["modules"].values() for e in m["endpoints"] if e["desc"])
    print(f"{len(result['modules'])}모듈 {n}엔드포인트 (쓰기 {writes}, 설명 보유 {described}) → {dest}")


if __name__ == "__main__":
    main()
