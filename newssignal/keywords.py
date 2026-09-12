"""헤드라인에서 이슈 키워드 뽑기 — 형태소 분석기 없이(stdlib) 쓰는 경험적 규칙.

원리: 제목을 어절로 나눈 뒤, 조사·어미를 '그 줄기가 말뭉치에 따로 등장할 때만' 떼어낸다.
그래서 '삼성전자가'→'삼성전자'는 되지만 '인도'·'결과'처럼 조사로 끝나는 진짜 낱말은 그대로 남는다.
붙어 나온 두 낱말(예: '원자력 발전소')은 2어절 후보로 함께 센다.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

BRACKET = re.compile(r"\[[^\]]{1,14}\]|【[^】]{1,14}】|<[^>]{1,14}>|\([^)]{1,8}\)")
QUOTES = re.compile(r"[\"'“”‘’`´「」『』]")
TOKEN = re.compile(r"[가-힣]+|[A-Za-z][A-Za-z0-9&.\-]*[A-Za-z0-9]|[A-Za-z]{2,}|\d+(?:[.,]\d+)?%?")
CLAUSE_SEP = re.compile(r"[,…:;?!/‥\-–—|]|\.\.+|\s-\s")
CLAUSE_MARK = "§"

# 여러 글자 조사/어미: 줄기가 2글자 이상이면 뗀다
MULTI_SUFFIX = [
    "으로서", "으로써", "에서는", "에게는", "이라고", "이라며", "이라는", "까지는", "부터는", "에서도", "한테는",
    "한다는", "된다는", "했다는", "됐다는", "입니다", "합니다", "됩니다", "했지만", "하지만", "되지만",
    "라고", "라며", "라는", "보다", "처럼", "마다", "조차", "라도", "에서", "에게", "한테", "으로", "까지",
    "부터", "이나", "이든", "에선", "에겐", "했다", "한다", "된다", "됐다", "됐나", "될까", "할까", "하나",
    "하며", "하고", "해야", "하는", "하자", "하게", "해서", "하면", "했던", "하려", "하기", "되며", "되고",
    "되는", "되면", "되자", "이다", "인가", "인데", "일까", "였다", "였던", "하다", "되다", "시켜", "시킨",
    "이라", "에도", "와의", "과의", "로의", "로는", "로도", "에는", "에게로",
    "어지는", "어지", "아야", "어야", "여야", "어서", "아서", "으면", "다면", "라면", "니까", "면서", "으며",
    "지만", "다는", "는데", "은데", "다가", "려고", "으려", "던", "다고", "냐고", "자고",
    "냈다", "냈던", "냈고", "낸다", "겼다", "겼던", "렸다", "렸던", "웠다", "웠던", "았다", "았던", "었다", "었던",
    "네요", "군요", "구나", "네", "죠", "요",
]
# 줄기 길이만 맞으면 떼는 한 글자 어미(관형형)
PARTICIPLE = ["한", "된", "할", "될"]
# 한 글자 조사: 줄기가 말뭉치에 따로 나올 때만 뗀다
SINGLE_SUFFIX = ["은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "나", "든", "께", "들", "등", "선", "엔", "선", "한", "된", "할", "될"]
PAST = set("었았였겠섰렸졌났줬왔갔봤샀쳤렀랐컸떴꼈뒀웠셨")

DEFAULT_STOPWORDS = """
속보 단독 종합 영상 사진 포토 현장 전문 인터뷰 기자 뉴스 연합뉴스 뉴시스 뉴스1 오늘 내일 어제 지난 이번 올해 작년 내년 오전 오후 새벽 밤사이
관련 위해 통해 대해 대한 이날 것으로 것은 것이 것도 등 및 또 더 가장 최대 최고 최초 첫 이후 이전 앞서 현재 당시 이어 다시 계속 함께 직접 모두 전체 일부 각각
때문 경우 가운데 동안 이상 이하 가능성 전망 논란 발표 확인 예정 진행 방침 계획 상황 문제 결과 이유 입장 의혹 조사 추진 검토 강화 확대 지원 마련 대응 촉구 요구
주장 지적 비판 반발 우려 기대 전환 증가 감소 상승 하락 돌파 기록 달성 사상 역대 연속 억원 만원 조원 달러 위안 명 건 개 곳 차례 년 월 일 시 분 초 주 말 초반 중반 후반
전 후 중 내 외 측 씨 사람 남성 여성 국민 시민 정부 국회 서울 한국 국내 해외 전국 지역 우리 위한 따른 따라 대비 향해 향한 맞아 맞춰 앞두고 놓고 두고 한때 이르면
최근 잇단 잇따라 또다시 급증 급감 급등 급락 공개 시작 종료 마감 개최 참석 방문 출시 출연 등장 화제 눈길 관심 사실 이야기 말 얘기 생각 모습 이번주 다음주 지난주
이날부터 오늘부터 내일부터 당일 하루 이틀 사흘 나흘 매일 주말 평일 전날 이튿날 상반기 하반기 분기 연말 연초 연내 총 약 무려 무슨 어떤 어떻게 왜 누가 어디 언제
뭐 뭘 뭔가 그 이 저 그것 이것 저것 여기 거기 대통령실 靑 檢 與 野 美 中 日 北 韓 러 英 獨 佛 등등 vs
없어 없다 없는 없이 없나 없을 있어 있다 있는 있나 있을 않아 않다 않는 아니 아닌 아냐 분간 시간째 일째 시간대 년째 년간 개월 주째 차례 배 만에 만의 위해서 대해서 통해서
까지 부터 조차 마저 진짜 정말 궁금 나란히 내달 내주 이달 다음달 아들 딸 엄마 아빠 남편 아내 부부 사랑 경고 경쟁 승리 패배 감독 선수 배우 가수 앨범 컴백 내한 흥행 출연 방송 예능
영화 드라마 미국 중국 일본 한국 국가 세계 글로벌 전세계 별세 사망 숨져 숨진 부상 논의 검토 협의 회의 회동 만남 방문 발언 언급 강조 밝혀 밝힌 전해 전한 알려 알린 나서 나선 나섰
회장 후보 후보자 투자 주의 필요 번지 얼굴 프로 속도 도움 유럽 아시아 인사 사장 대표 위원장 총장 교수 박사 관계자 당국 기관 단체 협회 업계 직원 회사 기업 그룹 제품 서비스
공식 공동 최종 신규 기존 추가 전면 일제 잇단 대규모 소규모 역사 미래 과거 현실 진실 실제 정도 수준 규모 기준 방식 방향 형태 단계 과정 절차 구조 체계 시스템
상위종목 순매수도 순매수 순매도 거래량 상위 하위 시세 종목 먹는 좋은 나쁜 가는 오는 사는 죽는 보는 같은 다른 많은 적은 마지막 뜻밖의 뜻밖 방법 효과 비결 습관 음식
번째 일이 수요 공포 지키기 시즌 메달 위험 활동 이렇게 저렇게 그렇게 이런 저런 그런 무엇 어느 여러 모든 각종 온갖 갖가지 한번 두번 다시한번 매번
주년 가능 죽일 수도 찾아 출격 반전 격돌 선두 없네 있네 인간 사람들 우리나라 국민들 시민들 여러분 누구 아무 모두가 모든것 이것저것
됐다 된다 했다 한다 하다 되다 이다 것 수 등 때 곳 중 및 더 못 안 잘 또 왜 다 더욱 매우 너무 정말 아주 거의 이미 아직 벌써 다시 바로 곧 늘 항상 자주 가끔 결국 마침내
""".split()


def load_stopwords(extra_file: Path | None = None) -> set[str]:
    words = set(DEFAULT_STOPWORDS)
    if extra_file and extra_file.exists():
        for line in extra_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.add(line)
    return words


def normalize(text: str) -> str:
    text = BRACKET.sub(" ", text)
    text = QUOTES.sub(" ", text)
    return text.replace("…", " ").replace("·", " ").replace("ㆍ", " ")


def _is_number(t: str) -> bool:
    return t.replace(".", "").replace(",", "").replace("%", "").isdigit()


def raw_tokens(text: str) -> list[str]:
    """어절 목록. 절(쉼표·말줄임표 등) 경계에는 CLAUSE_MARK를 끼워 2어절 결합을 막는다."""
    out: list[str] = []
    for clause in CLAUSE_SEP.split(normalize(text)):
        toks = [t for t in TOKEN.findall(clause) if not _is_number(t)]
        if toks:
            if out:
                out.append(CLAUSE_MARK)
            out.extend(toks)
    return out


class Extractor:
    """말뭉치(제목 목록) 전체를 보고 줄기 사전을 만든 뒤, 제목별 키워드 후보를 낸다."""

    def __init__(self, texts: list[str], stopwords: set[str]):
        self.stopwords = stopwords
        counts: Counter[str] = Counter()
        self._raw: list[list[str]] = []
        self.surface: dict[str, Counter[str]] = defaultdict(Counter)  # 줄기 → 원래 표기 빈도 (AI/ai)
        for t in texts:
            toks = raw_tokens(t)
            self._raw.append(toks)
            counts.update(x.lower() for x in toks if x != CLAUSE_MARK)
        self.vocab = set(counts)
        self.stem_cache: dict[str, str | None] = {}

    def stem(self, tok: str) -> str | None:
        key = tok.lower()
        if key in self.stem_cache:
            out = self.stem_cache[key]
        else:
            out = self._stem(key)
            self.stem_cache[key] = out
        if out:
            self.surface[out][tok if out == key else tok[: len(out)] if key.startswith(out) else tok] += 1
        return out

    def display(self, kw: str) -> str:
        """줄기 키워드를 사람이 읽는 표기로 (예: 'ai' → 'AI')"""
        parts = []
        for part in kw.split():
            c = self.surface.get(part)
            parts.append(c.most_common(1)[0][0] if c else part)
        return " ".join(parts)

    def _stem(self, tok: str) -> str | None:
        if tok == CLAUSE_MARK:
            return None
        if not re.fullmatch(r"[가-힣]+", tok):
            # 영문/숫자 혼합 토큰: 2글자 이상, 순수 숫자 제외
            if len(tok) < 2:
                return None
            return None if tok in self.stopwords else tok
        if len(tok) < 2:
            return None
        cand = tok
        for suf in MULTI_SUFFIX:
            if cand.endswith(suf) and len(cand) - len(suf) >= 2:
                cand = cand[: -len(suf)]
                break
        else:
            for suf in PARTICIPLE:
                if cand.endswith(suf) and len(cand) - len(suf) >= 2:
                    cand = cand[: -len(suf)]
                    break
            for suf in SINGLE_SUFFIX:
                if cand.endswith(suf) and len(cand) - len(suf) >= 2:
                    stem = cand[: -len(suf)]
                    if stem in self.vocab or any(stem + s in self.vocab for s in SINGLE_SUFFIX if s != suf):
                        cand = stem
                        break
        if len(cand) < 2 or cand in self.stopwords or cand[-1] in PAST:
            return None
        if cand in self.stopwords:
            return None
        return cand

    def keywords_of(self, idx: int) -> tuple[set[str], list[str]]:
        """제목 idx의 (키워드 집합, 순서 있는 줄기 목록)"""
        stems: list[str | None] = [self.stem(t) for t in self._raw[idx]]
        ordered = [s for s in stems if s]
        kws: set[str] = set(ordered)
        for a, b in zip(stems, stems[1:]):
            if a and b and a != b:
                kws.add(f"{a} {b}")
        return kws, ordered


def extract_candidates(texts: list[str], stopwords: set[str], min_df: int = 2) -> tuple[dict[str, set[int]], Extractor]:
    """키워드 → 등장한 제목 인덱스 집합. 2어절은 2건 이상 등장할 때만 남긴다."""
    ex = Extractor(texts, stopwords)
    hits: dict[str, set[int]] = defaultdict(set)
    for i in range(len(texts)):
        kws, _ = ex.keywords_of(i)
        for k in kws:
            hits[k].add(i)
    out = {k: v for k, v in hits.items() if len(v) >= min_df or " " not in k}
    return out, ex


def query_tokens(query: str) -> list[str]:
    """포털 검색어('김하성 11회 끝내기 득점')를 비교용 토큰으로.
    구글 트렌드가 '캠 브리 콘'처럼 음절을 띄워 보내면(한 글자 한글 토큰이 2개 이상) 붙여서 한 단어로 본다."""
    toks = [t for t in raw_tokens(query) if t != CLAUSE_MARK]
    singles = [t for t in toks if len(t) == 1 and re.fullmatch(r"[가-힣]", t)]
    if len(singles) >= 2 and len(singles) >= len(toks) / 2:
        return [query.replace(" ", "").lower()]
    return [t.lower() for t in toks if len(t) >= 2]


def stems_match(keyword: str, stems: set[str]) -> bool:
    """키워드의 모든 어절이 제목의 줄기 집합에 있으면 관련 기사. 3글자 이상은 앞부분 일치도 허용(김하성 ⊂ 김하성발)."""
    for part in keyword.lower().split():
        if part in stems:
            continue
        if len(part) >= 3 and any(st.startswith(part) for st in stems):
            continue
        return False
    return True
