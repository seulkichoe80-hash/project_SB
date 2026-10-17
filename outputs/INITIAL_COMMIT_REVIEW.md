# 초기 커밋 포함 제외 검토

상태: 검토 보고만 작성. git add/stage/commit 미실행, remote 없음. 아래 목록은 현재 .gitignore에 따른 포함 후보이며 최종 커밋 승인/완료가 아니다. user 원본·이전 work 코드/증거는 삭제하지 않고 제외한다.

## 포함 후보

루트 지침/기준 문서·docs·schema·검증 코드/테스트·빈 .env.example·직접 생성한 합성 HWPX/정답 JSON·정제된 보고가 포함 후보다. outputs의 연결 문서와 과거 보고는 이력 보존용이며 실제 동작 기준은 루트다.

| 파일 | bytes | SHA-256 |
|---|---:|---|
| .agents/skills/seomuitda-quality-check/SKILL.md | 4166 | `de46dde10486637696797dbbab4c1ece84284b7e22e302b713721eba4785b965` |
| .env.example | 432 | `9c810c3757f647b23e6e2ef87ad9f5f23d0c1a8dc333affcf63f517a74afb598` |
| .gitattributes | 98 | `6d6554f8a72da0ccc63b0af8fd0bee0928c080b50ae50ffc0723d331fe47a092` |
| .gitignore | 740 | `bab0565c4d2cfe2f575e784f35ee6aff007a8b6a4b48193166f9649b5cb258bb` |
| AGENTS.md | 7994 | `ad166a0018778347347bb8f8d27b629c7fa8d55259fe8e9fc64209ad75a99dc1` |
| ARCHITECTURE.md | 23449 | `3087a5a4097ca0e62b699ee282ae4238559f035ad1f54615f57d7fc914077e07` |
| PRD.md | 18310 | `7f0ddf11505d639f3f924a0c8ab6048737c389f2d079ff9e6f81e6609b3fd098` |
| README.md | 3091 | `f4dd049d157936cacae18629e39e72ebe548714ee6436ebdde708742cf4b8f6a` |
| TASKS.md | 11395 | `8151a72603001bea774b3b9203bb094a5215718e7dcb344448198b6c74d30118` |
| TEST_PLAN.md | 16407 | `05401e9b2048b7eea93f6b2d6dbae692b1ad6f60da371a220426f03071887a38` |
| docs/BROWSER_TEST.md | 1937 | `c6171bc0d8a179559a8ac5cdb64e390a53b234caf5bf9540884654e5e4d39639` |
| docs/G1_GATES.md | 5800 | `10920f86c743f46f42e48d747b0db9f5b829290b0443cce0660e68685c180338` |
| docs/GOLDSET.md | 4509 | `70cb1241a93d92613f3e6a15c359d73ee8ce233377119c68f7fa032768f96e89` |
| docs/LLM_CONFIGURATION.md | 3312 | `fa6cbdbb99a27cf9a6be5eaf1539dccca18414f17f1c816bd28d0cf82ec6f38a` |
| docs/VALIDATION_SETUP.md | 2154 | `217b6bcb848c2114e6c8312f98c1d6f3c378015dc5ba5451a024a0cdc3c2e8f6` |
| docs/WORKFLOW_SCHEMA.md | 1962 | `dedf0542159900eee3d224effd315a778ce71265fa57daa5c9cdd320775764a3` |
| outputs/AGENTS.md | 356 | `8aa2c154f69b554a7b7899b3df2c2abb7b89c28e41db1da927a0c5a1b90ec448` |
| outputs/ARCHITECTURE.md | 374 | `0c66e0cffebd90241af378f5e04a81604da6c892ce28ba1064b1c9f03498acd6` |
| outputs/FOUNDATION_REPORT.md | 12673 | `8833263c4348e87327cd6b2344321dc27bf25b351c91ed759d6f2aa1b9560b1d` |
| outputs/FOUNDATION_VALIDATION.json | 917 | `b8a5b5147d76828cf7fd2d74650def4f9eefa527f9b39d695643afdfb516b832` |
| outputs/INITIAL_COMMIT_REVIEW.md | 38 | `71d08efd9be5913def8f3d261bdf2711d9c6330a794ef89b41ab0fccbe41b12b` |
| outputs/INTERNET_DEPLOYMENT_STRATEGY.md | 20434 | `5ba00881b154353b5fa78945555424030dd78c4a68b50d619917f5a0de983981` |
| outputs/INTERNET_TRANSITION_CHANGELOG.md | 5708 | `ed4e0756b389f9e17f806971aeaffd693b7175019d3dd6053e75e125d0d213fc` |
| outputs/INTERNET_TRANSITION_VALIDATION.json | 3016 | `b97564a9b8dadf3ec2a4cb336a8cc0784c30b2ccb666cb83f8a29cb64a58772d` |
| outputs/PHASE1_DOCUMENT_CHANGES.md | 5544 | `8a55f61e5d111bd6fffca24aaf62abfe958c2391a2bb6021dfdf15a64f44357a` |
| outputs/PHASE1_REPORT.md | 21594 | `f34c3eada0edbbea4f01e18de5da8ecd08c0fb8cf458d85064377e00a227f33b` |
| outputs/PRD.md | 347 | `d440b82733d157f6fba6cf379c5f4a0dc523828a2f742bc982ef01dcecc70a22` |
| outputs/README.md | 356 | `81726517864927d204f6d139b5fe9f380ff0c9e3fd8c675f63f414851d6c53bc` |
| outputs/TASKS.md | 353 | `7f241745b5913489a47b1081fb57b6abdd9188be9bd5b250409bd8dc66879147` |
| outputs/TEST_PLAN.md | 365 | `69175c4450ed200bedeafdbb5f6160a7e68e8f5289a2d92e481a2e71db913fbd` |
| requirements-validation.txt | 141 | `4f1db60394d14641f8e631151903a34e1415e9fd1dc89c103fffb90306c12e68` |
| schemas/workflow.schema.json | 4010 | `167f73ebd15fa99d5477587a1d282271a97cf8a185e2ceacdfa3bc16dae60616` |
| scripts/validation/browser_smoke.mjs | 2941 | `644f1cb2afd87254d4aaef84bbae22b9fd1d1591154056e7f115b4e0d6dcbbf0` |
| scripts/validation/evaluate_retrieval.py | 1632 | `f7150de6da5d1e5a9221980b9c2e65ab3fea2c826a8f4a0030a38135d3b6457c` |
| scripts/validation/generate_hwpx_fixture.py | 2198 | `fd9c5d8f3b8323602de61d1a2f8d48f1d74c0112ca495c810047aa04fd11baaa` |
| scripts/validation/probe_hwpx.py | 5218 | `d969fac6d7bb87245fdc826dc4dc6890b5ee913520d7c484bec610321020d9f7` |
| scripts/validation/workflow_contract.py | 3657 | `a3c609717310bd6868d6c3a6b77ead5b141c352b299a1c82617ad22bb86f0d09` |
| tests/fixtures/synthetic/hwpx-manifest-v2.json | 989 | `c9e8c8442567f14c0995859a0152b03f3d2f51df5cd95ad9a1bff3820aa068bc` |
| tests/fixtures/synthetic/hwpx-manifest.json | 1154 | `eed6fc4f168d2bdbbb9528f7f77c28df83aa68276800c12a6675dbfe5668f8a5` |
| tests/fixtures/synthetic/pdf-manifest.json | 545 | `627f2a14250eeeb7fd6e47ecdb4fbefe12851a448584db00ecde9fbd49ecbbc4` |
| tests/fixtures/synthetic/procedure-v1.hwpx | 8961 | `80db84cd408a9d8ac0b9622493fe1527f70edbe800bf476b22fdf172ed7a3aab` |
| tests/fixtures/synthetic/procedure-v2.hwpx | 8964 | `47d7867e3a366d6a04e18b338785f712819b10f8e0a236d9b9c90fa2292a9226` |
| tests/fixtures/synthetic/queries.json | 974 | `e7d03bb34d0c658bc4923304dda14e670bc1573e968f4c25415475e3d00b92f0` |
| tests/fixtures/synthetic/source-registry.json | 6275 | `154eb54461d2f7e23c0f7e550c9d51c85ac3d281b4432afc724ff2d205a4970c` |
| tests/test_validation_contracts.py | 4604 | `953b5fcfca07fbcdde7026315d6071f72aae8249caf67f83aa32dce0de0460cf` |

이 검토 문서 자체는 파일 목록에 포함되지만 자기 SHA-256은 자기참조라 최종 본문 해시와 같을 수 없다. 최종 결과는 FOUNDATION_VALIDATION과 저장소 상태를 확인한다. 새 보고/증거를 추가하면 목록을 재생성해야 한다.

## 제외 확인

| 경로 예시 | ignore 결과 |
|---|---|
| .env | EXCLUDED |
| .env.local | EXCLUDED |
| .venv/Scripts/python.exe | EXCLUDED |
| node_modules/x | EXCLUDED |
| work/phase1/data-results.json | EXCLUDED |
| uploads/internal.hwpx | EXCLUDED |
| private/person.pdf | EXCLUDED |
| data/internal.csv | EXCLUDED |
| raw-secret.docx | EXCLUDED |
| state.sqlite-wal | EXCLUDED |
| outputs/PHASE1_EVIDENCE.zip | EXCLUDED |
| tests/fixtures/synthetic/procedure-v1.pdf | EXCLUDED |

실제 .env/키를 만들지 않고 가상 경로에 check-ignore를 실행했다. work 전체·venv/node_modules·모델/다운로드·원문 입력·SQLite/WAL·로그·증거 ZIP/diff는 제외한다. 기존 raw 증거/로그는 로컬에 보존하고 필요 시 검토/정제 후 별도 제출한다. 합성 PDF는 기존 생성본을 보존했지만 포함 폰트의 재배포 검토 전 Git 제외다. 합성 HWPX는 python-hwpx Apache-2.0 template와 직접 작성한 내용이며 재배포 NOTICE/자료 출처도 커밋 전 확인한다.

## 보안 검사와 한계

현재 포함 후보의 텍스트 파일에서 전형적 OpenAI/Google 키·private key 패턴은 발견하지 못했다. 이는 비밀/개인정보가 전혀 없다는 증명이 아니다. 문서/JSON 내용·합성 binary·저작권·기관 정책과 실제 파일 목록을 사람이 검토해야 한다. 키 값은 보고하지 않았다. .env.example의 API key 변수는 빈 값이다.

현재 Git은 ownership 경고가 있어 이 검토는 현재 루트만 지정한 git -c safe.directory=...로 실행했다. 전역 설정은 변경하지 않았다. 최초 커밋을 진행할 다음 작업에서는 status/ignore/후보 변경을 다시 확인한다. 원격 등록·push·공개 배포는 별도 승인 대상이다.
