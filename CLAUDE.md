# 회의록 자동화 — 1차시 시연

녹취록을 `inbox/` 에 넣으면 회의록과 검사 보고가 나온다. 이 폴더에서 대화 창을 열거나 `scripts/request.sh` 로 실행한다
— Claude Code 는 연 폴더의 `.claude/` 만 읽는다.

## 이 프로젝트의 선언

| 업무 말 | 이름 | 이 프로젝트에서 |
|---|---|---|
| 요청 | `request` | `scripts/watch.sh` 가 `inbox/` 를 5초마다 보고 새 녹취록마다 `scripts/request.sh` 를 부른다. 요청 id 는 `inbox-<내용 지문 12자리>`, 요청 폴더 `requests/<요청 id>/` |
| 수집 | `collect` | `scripts/collect.py` — 발화자와 발화 줄, 머리줄(회의·일시·참석), 같은 회의 폴더의 지난 회의록 열린 할 일 → `collected.json`. 모델 없음 |
| 작성 | `draft` | 하위 에이전트 `drafter`(`.claude/agents/drafter.md`, 도구 Read·Write) 가 `requests/<id>/draft.json` 을 쓴다 |
| 검수 | `review` | `review.py` — M1 할 일 완결 · M2 결정사항·미결사항 근거 · M3 참석자 실재(명단 포함) · M4 지난 할 일 대조(지난 회의록이 있을 때). 모델 없음 |
| 승인 | `approve` | 없음. 검수를 세 번 통과하지 못한 회의록만 사람에게(`needs_human`) |
| 전달 | `deliver` | `scripts/deliver.py` — `minutes/<회의 이름>/<날짜>_<id>.md` · `.report.json` · `.minutes.json`(다음 회의가 읽는 열린 할 일). 모델 없음 |

- 명령: `/handle-request <요청 id 또는 녹취록 경로>`
- 차단 장치(`.claude/settings.json` 에 등록): `guard.py`(막기) · `protect_sources.py`(원문 보호) · `run_review.py`(초안이 쓰이면 검수) · `next_step.py`(멈추려 할 때 다음 단계) · `show_status.py`(새 세션에 진행표)
- 흐름도 `graph.yaml`, 정책 `policies.yaml`

## 지킬 것

- 회의록 초안은 drafter 만 쓴다. 본 세션은 진행만 맡는다.
- `inbox/`·`samples/`·요청 폴더의 `transcript.txt` 는 원문이라 고치지 않는다.
- `state.json`·`events.jsonl`·`STATUS.md` 는 차단 장치가 쓴다. 고치지 않는다.
