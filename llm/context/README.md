# llm/context — LLM에게 주는 컨텍스트 (실험 변수)

이 폴더의 파일 하나라도 바꾸면 **다른 실험 조건**이다. 결과에는 컨텍스트 버전을 함께 기록한다:
`git log -1 --format=%h -- llm/context`

## 사용자 선택 (2026-09-29)
| 질문 | 선택 | 뜻 |
|---|---|---|
| 규칙 전달 | **A. 여러 턴** | 논문 Fig. 3–4 순서대로 규칙 → 전략 → 실행을 대화로 |
| 예제 코드 | **B. 없음** | golden generator를 보여주지 않고 API 설명만 |
| netmap 단계 | **A. 유지** | 첫 턴에서 LLM이 넷리스트를 dict로 변환 (논문 Fig. 2 ①) |

## 구성
`system.md`는 시스템 프롬프트, `turns/`는 순서대로 보내는 사용자 메시지다.

| 턴 | 파일 | 논문 대응 | LLM 응답 |
|---|---|---|---|
| — | `system.md` | 프레임워크 소개 + 출력 규약 | — |
| 1 | `turns/01_netmap.md` | Fig. 3 ① netlist → netmap dict | dict + `ports` |
| 2 | `turns/02_placement_rules.md` | Fig. 3 ② 기본 배치 규칙, ③ 정렬 전략 | 확인만 |
| 3 | `turns/03_place.md` | Fig. 3 ④ 설계별 규칙, ⑤ 배치 | 배치 코드 |
| 4 | `turns/04_routing_commands.md` | Fig. 4 ① 기본 배선 규칙과 명령 | 확인만 |
| 5 | `turns/05_track_strategy.md` | Fig. 4 ② 핀 접근 함수, ③ track 배선 전략 | 확인만 |
| 6 | `turns/06_route_and_finish.md` | Fig. 4 ④ 배선 + 핀 + 전체 스크립트 | 완성 스크립트 |

- 기본 턴 수는 배치 3 + 배선 3 = 6. 논문 Table II의 NAND(3+3)와 같은 수로 맞췄다.
  논문은 턴을 어떻게 나눴는지 밝히지 않았으므로 이 분할은 우리 추정이다.
- 결과를 보고 사람이 수정 지시를 보내는 턴(Fig. 3–4의 "Describe Modification Instructions")은
  여기 없고, `llm/chat.py`에서 사람이 입력한다. 그 턴 수는 따로 센다.

## 플레이스홀더
`{{이름}}` 형식이고 단순 문자열 치환이다. 파이썬 `str.format`은 dict의 중괄호와 충돌하므로 쓰지 않는다.

| 플레이스홀더 | 채우는 값 |
|---|---|
| `{{cell}}` | 셀 이름 (예: `nand_2x`) |
| `{{netlist}}` | `ref/netlist/<셀>.spice`에서 `*` 주석 줄을 뺀 것 (주석에 배치 힌트가 있어서) |
| `{{task_placement_rules}}`, `{{task_routing_rules}}` | `bench/tasks.yaml`의 과제별 규칙 (Phase 3-5에서 설계) |

## API 설명의 출처
`third_party/laygo2` @ cc6276a와 워크스페이스 `laygo2_tech`에서 실제로 실행해 확인한 것만 적었다
(템플릿 이름·파라미터, 핀 이름, grid 이름·층, `route`/`route_via_track`의 반환값, 2D `place`).
