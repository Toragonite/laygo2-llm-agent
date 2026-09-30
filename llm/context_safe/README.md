# llm/context_safe — laygo2_safe API용 컨텍스트 (v2 계열)

`llm/context`(v1, 원본 laygo2 API)와 같은 6턴 구조(논문 Fig. 3–4)이고, 차이는 API뿐이다:
`Cell`, `nmos/pmos(ref=)`, `place_rows`, `connect(net, pins, grid)`, `port`, `check`, `export`.
컨텍스트 버전 = `git log -1 --format=%h -- llm/context_safe`. 예제 generator는 주지 않는다 (v1과 같은 선택 B).
플레이스홀더: `{{cell}}`, `{{netlist}}`, `{{netlist_path}}`(절대 경로, check용), `{{task_placement_rules}}`, `{{task_routing_rules}}`.
