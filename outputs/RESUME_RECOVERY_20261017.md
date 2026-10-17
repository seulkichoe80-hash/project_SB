# 2026-10-17 재개 기준 회복

최초 기존67개 시험은55 PASS/12 FAIL이었다. 원인은 tests/fixtures/synthetic/procedure-v1.hwpx와 procedure-v2.hwpx 누락이며 발생 경위는 미검증이다. 코드를 초기화하거나 과거 PASS 기록을 수정하지 않았다. 원문 증거 ZIP에도 두 fixture는 없었다.

정상 v2는 work/phase2b/evidence-runtime/originals의 불변 저장본에서 발견했다. SHA-256 `47d7867e3a366d6a04e18b338785f712819b10f8e0a236d9b9c90fa2292a9226`가 과거 manifest와 일치하므로 누락 경로에 바이트 동일 복사했다. 원본 저장본은 변경하지 않았다.

과거 v1은 정확한 저장본을 찾지 못했다. 해당 manifest와 과거 증거는 보존하며 복원했다고 주장하지 않는다. 정상 v2의 PNG IDAT CRC 한 비트만 바꾼 새로운 `procedure-recovery-invalid.hwpx`를 만들고 ZIP CRC는 정상으로 유지했다. SHA-256은 `b3764a641e35dc575772b166d8183807aef53e2c7ba744ee0dce38c6ef85f9a0`이다. 기존 부정 계약 시험 한 곳을 새 fixture로 연결했다. 의미상 동일한 PNG 손상 거부 계약이지만 옛 v1 파일 자체의 재시험은 아니다.

재현용 합성 바이트를 hwpx-recovery.json(base64+hash)에 보존하고 `python scripts/validation/restore_synthetic_fixtures.py --restore-missing`으로 복구한다. 다른 기존 파일은 덮어쓰지 않는다. 실제 비공개 자료/사용자 원본은 사용하지 않았다.

복구 후 `work/phase2b/venv/Scripts/python.exe scripts/validation/run_phase2b_checks.py --output outputs/phase2c/BASELINE_RECOVERED_67.json` 실행:67 PASS/0 FAIL/0 SKIP/0 BLOCKED. 최초 실패는 BASELINE_67.json에 별도 보존했다.

이후 최신 사용자 지시로 Phase 2C-1 구조 청킹/EvidenceRef/SQLite 키워드 검색과 초기 로컬 커밋이 승인되었다. 실제 LLM/유료 호출·OCR/UI·클라우드·push는 제외한다.
