# paper_notes — arXiv:2408.07279 재현 노트

## 논문 요약
- 상세 분석(배경 지식 포함): https://claude.ai/artifact/84su77Bz4NraGJjRYQGVNp (비공개 아티팩트, 2026-09-29)
- 방법: SPICE netlist → (LLM) netmap dict → 배치 명령 → net별 배선 명령 → 실행. 단계마다 규칙을 대화로 설명하고 사람이 결과를 보고 수정 지시 (Fig. 2–5). 모델은 ChatGPT-4 웹 채팅.
- 결과: 13개 설계 모두 DRC/LVS 통과. 프롬프트 수 합계 배치 62, 배선 131 (Table II). NAND 3+3, NOR 3+2.
  게이트 수준 배치 순서 최적화로 배선 길이 18.6% 감소 (Fig. 8). 32 Gb/s serializer post-layout 확인 (Fig. 11).
- 저자 평가 (Table I): 상호작용 배치/배선 Good, 최적화 배치 Normal, 배선 Bad.
- 빈칸: 프롬프트 로그 [16] 링크 만료(`repository_expired`, 2026-09-29 확인), 공정 미명시, 성공률·반복성·temperature 없음,
  level shifter는 사람이 배치를 수동 조정, Fig. 2의 `laygo.place/route`는 공개판과 표기 다름
  (2D `dsn.place(inst=[[...]])`는 공개판 cc6276a에도 있음, route는 grid·핀 변환을 직접 써야 함).

## 우리 선택 (논문에 없는 결정과 이유)

| 날짜 | 항목 | 선택 | 이유 |
|---|---|---|---|
| 2026-09-29 | LVS 기준 netlist 크기 | 템플릿이 실제 그리는 W (nfet 0.5, pfet 1.0, L=0.15, `m=2`) | `lvs_example`의 W=1.2/2.4는 laygo2 템플릿이 그리지 않는 값 → property_errors |
| 2026-09-29 | LVS 통과 조건 | "Circuits match uniquely" + 핀 표 `**Mismatch**` 없음 + "Property errors" 없음 | netgen 1.5.133은 W 오류·핀 뒤바뀜에도 "match uniquely"를 출력 |
| 2026-09-29 | DRC 개수 | 평탄화한 top cell 복사본, `drc(full)` | 계층 그대로 세면 via·템플릿 단독 에러가 섞임, rc 기본은 `drc(fast)` |
| 2026-09-29 | DRC>0일 때 | LVS까지 계속 진행, 둘 다 기록 | 실패 유형을 DRC×LVS 2×2로 구분하기 위해 (사용자 결정) |
| 2026-09-29 | `area_um2` 정의 | 셀 경계 bbox (inv 11.29 µm²) | 배치할 때 실제 차지하는 크기. 도형만 bbox면 9.85 µm² (사용자 결정) |
| 2026-09-29 | tech | `sky130A` 고정 | `laygo2_tech.name`은 `sky130B`. 설치 PDK·기준은 sky130A |
| 2026-09-29 | 컨텍스트 전달 방식 | 여러 턴: `system.md` + 6턴 (배치 3 + 배선 3), Fig. 3–4 순서 | 사용자 결정 A. 논문 절차에 충실. 턴 분할은 논문에 없어서 NAND(3+3)에 맞춘 추정 |
| 2026-09-29 | 예제 코드 | 제공 안 함, API 설명만 | 사용자 결정 B. golden을 보여주면 NAND/NOR가 베끼기 과제가 됨 |
| 2026-09-29 | netmap 단계 | 유지, LLM이 dict 생성. 논문의 D/G/S에 `m`(핑거 수) 키 추가 | 사용자 결정 A. 크기 정보가 없으면 `nf`를 정할 수 없음 |
| 2026-09-29 | 출력 skeleton | import·LAYOUT_OUT_DIR·export 줄은 고정 코드로 제공 | `check_cell.py` 출력 규약 때문. 배치·배선 내용은 없음 |
| 2026-09-29 | 넷리스트 입력 | `*` 주석 줄 제거 후 입력 | `ref/netlist` 주석에 배치 힌트(직렬 순서, 소자 이름)가 있음 |
| 2026-09-29 | 컨텍스트 세부 3항목 | 고정 skeleton 제공, 배치 규칙 4개(NMOS 아래 / 레일 tie / 같은 게이트 같은 열 / 직렬 인접), 배선 충돌 시 옆 열 우회 규칙 — 모두 유지 | 사용자 결정. 재현 조건으로 기록만 함 |
| 2026-09-29 | LLM 호출 | OpenAI GPT (Chat Completions API), 턴마다 전체 대화 재전송, temperature 미지정 시 제공자 기본값 | 사용자 결정: 논문(ChatGPT-4 웹 채팅)과 같은 계열. 모델 id는 API key 받은 뒤 결정 |
| 2026-09-29 | 판정 | 마지막 응답의 마지막 ```python 블록을 `check_cell.py`로 1회 판정, 실패는 기록만 | 자동 피드백은 범위 밖 |
| 2026-09-29 | 모델 | `gpt-4o-2024-05-13`, max_completion_tokens 4096(이 모델의 상한) | 사용자 결정. 논문 시기(2024 상반기) ChatGPT-4에 가장 가까운 고정 버전 |
| 2026-09-29 | 사람 수정 지시 | `llm/chat.py`, 지시마다 `p:`(배치)/`r:`(배선) 태그로 Table II처럼 셈. 도구가 DRC/LVS 결과를 자동으로 대화에 넣지 않음 | 논문의 사람이 닫는 루프를 재현. 자동 피드백은 범위 밖 |
| 2026-09-29 | 파일럿의 수정 지시 작성자 | Claude(claude-fable-5-1)가 설계자 역할, 셀당 최대 8개, 자연어만(코드 블록·golden 코드 없음) | 사용자 요청. 논문은 사람 설계자. 지시의 질이 결과에 영향 → `chat.json`의 `instructor`로 기록 |
| 2026-09-29 | 프롬프트 수 세는 법 | 총 = 초기 턴(배치 3 + 배선 3) + 수정 지시(p:/r: 태그) | 논문 Table II는 셀 방법이 명시되지 않음. 논문 숫자와 직접 비교할 때 이 차이를 밝힐 것 |
| 2026-09-30 | 수정 지시 수준 상한 | L3 (방향까지, 구체 값·배선 계획 없음). 지시마다 수준 기록 | 사용자 결정. 구체적 지시(L4)는 LLM 능력이 아니라 지시자 능력을 재게 됨. 정의는 `docs/protocol.md` |
| 2026-09-30 | 실패 유형 | A API 오용 / B 회로 해석 / C 배선 충돌 / D 기하 오해 / E 간격 위반, 다중 라벨 | 사용자 결정. 파일럿 22건에서 도출 |
| 2026-09-30 | baseline 과제 조건 | 셀당 5회, temperature 기본값, 수정 지시는 Claude(L3 상한), 셀별 추가 규칙 없음(`(none)`) | 사용자 결정 |
| 2026-09-30 | 과제 셀 확장 | INV·NAND·NOR + MUX2·NAND3·TINV(트랜지스터 수준) + latch·D-FF(게이트 수준) + 고속 회로 | 사용자 결정. 추가 셀은 golden DRC/LVS 통과 확인 후 과제에 넣음. 단계적으로 진행 |
