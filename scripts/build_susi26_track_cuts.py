"""26 수시 확정 합격자 → 트랙별 컷 캐시 생성.

한 전형 안에서 실기 트랙(예: 수원대 전공/기초체력)이 갈리면 합격자
기록 슬롯 패턴(점수1~7 중 어느 슬롯이 채워졌는가)으로 코호트를 분리해
트랙별 최초/최종 컷을 산출한다. recommend_candidates가 이 캐시로
혼합 컷 왜곡을 방지한다 (수원대 실사고: 전공 트랙 564가 전체 컷으로 둔갑).

합격 판정은 정확히 '합격' 일치만 — substring 매칭은 '불합격'을 삼킨다
(2026-06-12 실사고: 불합격자 84명의 최소점 835가 컷으로 둔갑, 실제 최종컷 978).
'1차합격'은 1단계 통과일 뿐 최초합이 아니고, '예비N'은 충원 안 된 상태다
(충원합격자는 최종합여부가 '합격'으로 바뀐다).

입력 TSV는 Vultr 26susi에서 추출:
  confirmed: SELECT 대학ID, 실기ID, 점수1..점수7, 합산점수, 최초합여부, 최종합여부
             FROM 확정대학정보  (12열, 헤더 없음)
  events:    SELECT 실기ID, 종목명, MIN(id) FROM 26수시실기배점
             GROUP BY 실기ID, 종목명  (슬롯 순서 = MIN(id) 오름차순 휴리스틱)

사용:
  python3 scripts/build_susi26_track_cuts.py /tmp/susi26_confirmed.tsv \
      /tmp/susi26_events.tsv ~/.miho/academy_ops/susi26_track_cuts.json
"""

from __future__ import annotations

import collections
import json
import os
import sys


def _num(x: str) -> float:
    try:
        return float(x)
    except ValueError:
        return 0.0


def build(confirmed_path: str, events_path: str) -> dict[str, list[dict]]:
    events: dict[str, list[tuple[int, str]]] = collections.defaultdict(list)
    with open(events_path, encoding="utf-8") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) >= 3:
                events[f[0]].append((int(f[2]), f[1]))
    event_order = {k: [name for _, name in sorted(v)] for k, v in events.items()}

    cohorts: dict[tuple, dict] = {}
    with open(confirmed_path, encoding="utf-8") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) != 12:
                continue
            uid, pid = f[0], f[1]
            slots = tuple(i for i in range(7) if _num(f[2 + i]) > 0)
            total = _num(f[9])
            if not slots or total <= 0:
                continue
            c = cohorts.setdefault((uid, pid, slots), {"n": 0, "first": [], "final": []})
            c["n"] += 1
            if f[10].strip() == "합격":
                c["first"].append(total)
            if f[11].strip() == "합격":
                c["final"].append(total)

    out: dict[str, list[dict]] = collections.defaultdict(list)
    for (uid, pid, slots), c in cohorts.items():
        names = event_order.get(pid, [])
        out[uid].append({
            "events": [names[i] if i < len(names) else f"종목{i + 1}" for i in slots],
            "slot_count": len(slots),
            "n_students": c["n"],
            "n_first_winners": len(c["first"]),
            "n_final_winners": len(c["final"]),
            "first_cut_total": min(c["first"]) if c["first"] else None,
            "final_cut_total": min(c["final"]) if c["final"] else None,
        })
    for uid in out:
        out[uid].sort(key=lambda t: (-t["slot_count"], -t["n_students"]))
    return dict(out)


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    result = build(sys.argv[1], sys.argv[2])
    dest = os.path.expanduser(sys.argv[3])
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    multi = sum(1 for v in result.values() if len(v) > 1)
    print(f"{len(result)}개교, 다중트랙 {multi}개교 → {dest}")


if __name__ == "__main__":
    main()
