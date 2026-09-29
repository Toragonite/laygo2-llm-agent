# paper_notes — arXiv:2408.07279 재현 노트

## 논문 요약
- (Phase 3-1에서 작성)

## 우리 선택 (논문에 없는 결정과 이유)

| 날짜 | 항목 | 선택 | 이유 |
|---|---|---|---|
| 2026-09-29 | LVS 기준 netlist 크기 | 템플릿이 실제 그리는 W (nfet 0.5, pfet 1.0, L=0.15, `m=2`) | `lvs_example`의 W=1.2/2.4는 laygo2 템플릿이 그리지 않는 값 → property_errors |
| 2026-09-29 | LVS 통과 조건 | "Circuits match uniquely" + 핀 표 `**Mismatch**` 없음 + "Property errors" 없음 | netgen 1.5.133은 W 오류·핀 뒤바뀜에도 "match uniquely"를 출력 |
| 2026-09-29 | DRC 개수 | 평탄화한 top cell 복사본, `drc(full)` | 계층 그대로 세면 via·템플릿 단독 에러가 섞임, rc 기본은 `drc(fast)` |
| 2026-09-29 | DRC>0일 때 | LVS까지 계속 진행, 둘 다 기록 | 실패 유형을 DRC×LVS 2×2로 구분하기 위해 (사용자 결정) |
| 2026-09-29 | `area_um2` 정의 | 셀 경계 bbox (inv 11.29 µm²) | 배치할 때 실제 차지하는 크기. 도형만 bbox면 9.85 µm² (사용자 결정) |
| 2026-09-29 | tech | `sky130A` 고정 | `laygo2_tech.name`은 `sky130B`. 설치 PDK·기준은 sky130A |
