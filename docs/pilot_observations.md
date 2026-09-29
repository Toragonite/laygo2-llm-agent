# 파일럿 관찰 기록 (2026-09-29)

조건: gpt-4o-2024-05-13, temperature 기본값, context `c5af175`, 셀마다 시도 1회.
수정 지시는 Claude(claude-fable-5-1)가 설계자 역할로 작성했고, 셀당 최대 8개로 제한했다.
결과 표: `results/pilot_2026-09-29.csv`. 실행 산출물: `runs/llm/{smoke,pilot}/` (git에 올리지 않음).

아래 표는 **분류하지 않은 원자료**다. 실패 유형 분류는 사용자가 한다 (CLAUDE.md).
"원인"은 생성된 코드와 추출 netlist에서 직접 확인한 사실만 적었다.

| 셀 | 라운드 | 도구가 보인 증상 | 코드에서 확인한 원인 |
|---|---|---|---|
| nand | 초기 | gen 실패 `KeyError: 'D'` | 드레인이 OUT인 MN0에 `tie='D'` (규칙 2 위반), 없는 D 핀 참조 |
| nand | 초기 | (실행 전) | 게이트 A를 쓰는 MN0·MP1이 다른 열 (규칙 3 위반) |
| nand | 1 | gen 실패 `TypeError` (pin bbox) | `via_tag=[True,True]` route의 반환 리스트 전체를 `bbox`에 넣음, 같은 배선을 두 번 그림 |
| nand | 1 | (실행 전) | OUT에 MP1 드레인 누락, 레일 좌표에 placement grid와 r12 grid를 섞음 |
| nand | 2 | gen 실패 `ValueError: too many values to unpack` | `route_via_track` 반환 리스트를 3개로 풂 (마지막 요소가 track) |
| nand | 3 | DRC 0, LVS mismatch (net 4/6) | A 배선과 OUT track이 같은 r23 열 (G·D 핀이 같은 열) → A·net1·VSS가 OUT과 short. MP1 소스 미tie → floating |
| nand | 4 | DRC 0, LVS mismatch (net 4/6) | 서로 다른 행의 두 점을 `route()` 한 번으로 연결 → 두 점 사이 전체를 채운 locali 사각형이 OUT·VSS를 덮음 |
| nand | 5 | DRC 0, LVS mismatch (net 5/6) | net1 가로 track이 MN0 소스 행 = MN1의 VSS tie 소스 위를 지남 → net1·VSS short |
| nand | 6 | **DRC 2 (li.3 간격)**, LVS match | net1 세로 track이 MN0 드레인(OUT) 바로 옆 열 |
| nand | 7 | DRC 0, LVS mismatch | track 열을 `max(드레인 열)+1` = 7로 계산 → MN1 소스(VSS) 위 |
| nand | 8 | **통과** | 두 nfet 경계 열(MN0 RAIL 오른쪽 끝) 사용 |
| inv | 초기 | gen 실패 (route 내부) | 핀에 `r12.mn.bottom_left(...)[0]` 사용 → 점이 아니라 숫자 |
| inv | 1 | DRC 0, LVS mismatch (net 3/4) | I와 O 세로 배선이 같은 열 → I·O short |
| inv | 2 | DRC 0, LVS mismatch (net 3/4) | `route_via_track` 대신 게이트 핀 위에 via를 직접 놓음 (O 열 위) + 길이 0 배선 |
| inv | 3 | **통과** | 게이트 열 −1에 `route_via_track` |
| nor | 초기 | gen 실패 (route 내부) | 핀에 `pg.mn.bottom_left(...)[0]` 사용 (placement grid 헬퍼를 핀에) |
| nor | 초기 | (실행 전) | 드레인이 OUT인 MP0에 `tie='D'` |
| nor | 1 | gen 실패 `KeyError: 'S'` | tie된 MP1의 S 핀 참조. A/B/OUT/net1 모두 다른 트랜지스터에 연결 (dict와 인스턴스 대응 혼동) |
| nor | 2 | gen 실패 `TypeError: cannot unpack` | `via_tag=[False,False]` route 반환(Rect 1개)을 3개로 풂 |
| nor | 3 | DRC 0, LVS mismatch (net 4/6) | OUT track이 MN0 게이트 열(B) 위, net1 점은 r12로 구하고 r23에 배선 |
| nor | 4 | DRC 0, LVS mismatch (net 5/6) | OUT·net1의 가로 stub이 같은 pfet 드레인 행에서 겹침 |
| nor | 5 | DRC 0, LVS mismatch (net 5/6) | net1 stub이 MP1의 VDD tie 소스 행 위를 지남 |
| nor | 6 | **통과** | 설계자가 배선 계획(4단계)을 직접 제시 |

- netmap(1턴)은 세 셀 모두 정확했다.
- 세 셀 모두 초기 6턴 결과는 gen 실패였다.
- **프로토콜 이탈 1건:** `nor_2x_1`의 6번째 지시가 `chat.py` 스크립트 모드 버그로 6개 메시지로 쪼개져 전송됨.
  원본은 그대로 두고, 5라운드 직후 상태에서 분기한 `nor_2x_1b`로 같은 지시를 한 메시지로 다시 보냄. 표와 CSV는 `nor_2x_1b` 기준.
