# Render 배포

이 프로젝트는 로컬에서는 SQLite를 사용하고, Render에서는 `render.yaml`이 생성하는 PostgreSQL 데이터베이스를 자동으로 사용합니다.

1. 변경 사항을 GitHub에 푸시합니다.
2. Render Dashboard에서 **New +** → **Blueprint**를 선택합니다.
3. GitHub 저장소를 연결하고 `render.yaml`을 선택합니다.
4. 생성되는 `portfolio-map` 웹 서비스와 `portfolio-map-db` PostgreSQL 데이터베이스를 확인한 뒤 배포합니다.

배포가 끝나면 Render가 제공하는 `onrender.com` 주소에서 사이트를 열 수 있습니다. 무료 웹 서비스는 일정 시간 사용하지 않으면 절전 상태가 되어 첫 요청이 느릴 수 있습니다.
