# React Flow 브라우저 검증 준비

상태: 기존 설치/빌드 PASS 재사용, 실제 browser UI 시험은 BLOCKED/미검증이다. 이번에는 전체 프런트 앱을 생성하지 않는다. 이전 work/phase1/frontend의 합성2노드/1간선 스파이크·package-lock·빌드 로그를 보존했다.

다음 실행은 앱 구현과 분리된 로컬 Vite preview와 Playwright 기반으로 준비한다. work/phase1/browser_probe.mjs는 이전 실패 로그를 가진 참고 코드이며 실행하면 예전 결과를 덮어쓸 수 있으므로 그대로 재실행하지 않는다. 새 실행 코드는 scripts/validation/browser_smoke.mjs이며 work/repository-foundation/browser에 새로운 결과를 남긴다.

확인 순서는 production build HTTP200→독립된 headless browser→한글2노드/간선→첫 노드 클릭→원문 앵커 값 동기화→console/pageerror0→외부 요청0→screenshot이다. node_modules/package-lock가 없는 경우 설치 단계와 browser 실행 단계를 구별한다. 고정 localhost 포트 충돌은 FAIL로 기록하며 다른 프로세스를 종료하지 않는다.

기본 Playwright browser가 없으면 설치된 Edge 또는 승인된 테스트용 Chromium 경로를 지정할 수 있다. 일반 사용자 browser 프로필은 사용하지 않고 작업 폴더 안의 별도 임시 프로필만 사용한다. 이전 Edge는 sandbox TEMP 경로 문제와 실행 중 종료로 실패했으므로 자동화 성공을 가정하지 않는다. 무분별한 보안 플래그/시스템 정책 변경으로 우회하지 않는다. 실행 불가 시 browser/정책 확인이 필요한 BLOCKED로 남긴다.

로컬 테스트가 통과해도 공개 HTTPS·CORS/Auth callback·기관 권한·재배포/모바일·다른 PC가 자동 PASS가 아니다. 노드 클릭/목록 동기화는 G1-B(해당 UI 전), 공개 URL/HTTPS는 G1-C, 평가자 브라우저/독립 실행은 G1-D다.
