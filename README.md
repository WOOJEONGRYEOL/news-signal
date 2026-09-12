# 뉴스 시그널 (News Signal)

뉴스룸용 실시간 관심사 보드. 포털 실시간 검색어(구글 트렌드·네이트·줌), 언론 발행량(네이버 섹션·연합뉴스·구글 뉴스 피드), 실제 소비(네이버 언론사별 많이 본 기사)를 한 화면에 모아 **카테고리별 Top 10 키워드**를 보여주고, 키워드를 누르면 **관련 기사 목록**과 **시간대별 흐름**이 나옵니다. 과거 시점도 골라서 볼 수 있습니다.

- 파이썬 표준 라이브러리만 씁니다. 설치할 패키지가 없고, API 키도 필요 없고, 비용도 0원입니다.
- 브라우저 화면(`site/index.html`)은 정적 파일이라 그대로 GitHub Pages나 사내 웹서버에 올릴 수 있습니다.

## 바로 쓰기

```bash
cd "/Users/woo/News Signal"
python3 -m newssignal doctor      # 출처 8곳 연결 점검
python3 -m newssignal collect     # 지금 한 번 수집 (약 30초)
python3 -m newssignal serve       # http://127.0.0.1:8770/ 에서 보기
```

30분마다 자동으로 쌓으려면 둘 중 하나:

```bash
python3 -m newssignal loop --every 30          # 터미널을 켜둔 채로 반복
bash scripts/install_launchagent.sh             # macOS 로그인 시 자동 실행(LaunchAgent) 등록
```

수집이 쌓일수록 좋아집니다. **급상승** 신호는 지난 7일 평균과 비교하므로 하루쯤 지나야 의미가 생기고, 키워드별 **흐름 곡선**도 수집 횟수만큼 점이 찍힙니다.

## 화면 구성

| 영역 | 내용 |
|---|---|
| 카테고리 Top 10 | 전체·정치·경제·사회·생활/문화·세계·IT/과학·스포츠·연예. 순위·변동·신호 구성 막대·종합점수·검색 출처(G 구글, N 네이트, Z 줌) |
| 키워드 상세 | 왜 올라왔는지 한 문장 설명, 24시간/7일 흐름 곡선(최고점 표시), 관련 기사(최신순, 출처 표시) |
| 포털 원본 | 구글 트렌드 전국 급상승, 네이트 실시간 이슈, 줌 AI 이슈트렌드, 네이버 많이 본 기사(우리 회사 Top 5 / 언론사별 1위) |
| 지역별 관심사 | 구글 트렌드 시·도별 급상승 검색어. 전국 목록엔 없고 그 지역에서만 뜨는 검색어를 '이 지역만 / 지역 n곳'으로 표시 |
| 시점 선택 | 상단에서 날짜·시각을 고르면 그 시점의 순위·기사·포털 원본으로 되돌아감. '지금'을 누르면 실시간 |

## 종합점수 (설정값이며 바꿀 수 있음)

| 신호 | 뜻 | 기본 가중치 |
|---|---|---|
| 검색 | 구글 트렌드·네이트·줌 실시간 검색어에 올라 있는가 (순위와 트래픽 반영) | 35% |
| 발행 | 그 카테고리 기사 제목에 등장한 건수 (최근 24시간 말뭉치) | 30% |
| 소비 | 네이버 언론사별 '많이 본 기사' 제목에 등장한 건수 | 15% |
| 급상승 | 지난 7일 스냅샷당 평균 기사 수 대비 몇 배인가 | 20% |

가중치는 `config.toml`의 `[weights]`에서 바꿉니다(`config.toml.example` 참고). 순위에서 빼고 싶은 단어는 `data/stopwords.txt`에 한 줄씩 적으면 됩니다.

## 데이터 출처 (2026-09-12 확인)

| 출처 | 쓰임 | 비고 |
|---|---|---|
| Google Trends RSS `trends.google.com/trending/rss?geo=KR` | 검색 신호, 관련 기사 | 시·도별 `geo=KR-11` 등 16곳. 세종(KR-50)은 400 오류라 제외 |
| 네이버 랭킹뉴스 `news.naver.com/main/ranking/popularDay.naver` | 소비 신호, 우리 회사 랭킹 | 언론사 80여 곳 × Top 5, EUC-KR |
| 네이버 섹션 헤드라인 `news.naver.com/section/100~105` | 발행 신호(정치~IT/과학) | 섹션당 40여 건 |
| 연합뉴스 RSS `yna.co.kr/rss/*.xml` | 발행 신호 | politics·economy·society·local·international·culture·sports·entertainment·industry·market·health |
| Google News 주제 피드 `news.google.com/rss/headlines/section/topic/*` | 발행 신호(연예·스포츠·경제·IT·과학·세계·건강) | 302 리다이렉트 자동 추적 |
| Google News 검색 RSS | 관련 기사가 3건 미만인 키워드 보강 | 수집 1회당 최대 25개 키워드 |
| 네이트 실시간 이슈 `nate.com/js/data/jsonLiveKeywordDataV1.js` | 검색 신호 | CP949 JSON |
| 줌 AI 이슈트렌드 `zum.com` | 검색 신호 | 서버 렌더링된 5개만 |

### 넣지 못한 것과 이유

- **다음(Daum)**: 2025년 개편 이후 랭킹·연령별 인기 뉴스 페이지가 사라져(404) 가져올 데이터가 없습니다. 대신 네이트·줌 실시간 이슈어를 넣었습니다.
- **연령·성별 관심사**: 무료로 믿을 만한 출처가 없습니다. 네이버 데이터랩 API는 호출마다 최댓값을 100으로 놓는 상대값이라 연령대별로 따로 부른 결과를 서로 비교할 수 없고, 구글 트렌드는 인구통계를 주지 않습니다. 방송사 자체 홈페이지·앱 분석(GA4 등)이 유일하게 정확한 경로입니다.
- **신뢰도 주의**: 한글 형태소 분석기 없이 규칙으로 키워드를 뽑기 때문에 가끔 어미가 남거나 일반어가 올라옵니다. 급상승 신호가 쌓이면 상시 등장하는 일반어(AI, 대통령 등)는 자연히 내려갑니다. 눈에 띄는 단어는 `data/stopwords.txt`에 추가하세요.

## 파일 구조

```
newssignal/            수집·분석 패키지 (stdlib only)
  collect.py           한 번의 수집: 출처 → 신호 결합 → 순위 → 관련 기사 → 지역
  keywords.py          헤드라인 키워드 추출(조사·어미 규칙, 불용어)
  store.py             SQLite (data/newssignal.sqlite3)
  export.py            site/data/*.json 내보내기
  sources/             출처별 파서
site/index.html        대시보드 (정적, 외부 라이브러리 없음)
site/data/latest.json  최신 스냅샷 전체
site/data/days/        날짜별 스냅샷 순위(시계열용)
site/data/extras/      날짜별 포털 원본·지역·우리 회사 랭킹
site/data/articles/    날짜별 키워드 관련 기사
data/stopwords.txt     불용어 추가 목록
scripts/               자동 실행 스크립트
```

## 공유 방법

`site/` 폴더를 통째로 올리면 됩니다. 사내 PC에서 보려면 `python3 -m newssignal serve --host 0.0.0.0`로 띄우고 `http://<이 맥의 IP>:8770/`로 접속합니다. GitHub Pages에 올리려면 `site/`를 저장소의 Pages 경로로 두고 수집 후 `site/data`를 푸시하면 됩니다(KBO 날씨 보드와 같은 방식).
