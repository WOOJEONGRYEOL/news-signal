"""HTTP helper — stdlib only, gzip aware, small retry, charset sniffing."""
from __future__ import annotations

import gzip
import re
import socket
import time
import urllib.error
import urllib.request

UA_DESKTOP = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
BARE_AMP = re.compile(r"&(?!#?\w{1,8};)")


def clean_xml(text: str) -> str:
    """RSS에 가끔 섞이는 제어문자와 홑 & 를 정리한다 (연합뉴스 피드가 종종 깨져 들어온다)."""
    return BARE_AMP.sub("&amp;", CTRL.sub("", text)).lstrip("\ufeff \t\r\n")


def online(host: str = "news.google.com", port: int = 443, timeout: float = 3.0) -> bool:
    """망이 끊겼는지 빠르게 확인한다. 끊긴 채로 수집을 시작하면 출처마다 시간제한을 기다리느라
    한 회차가 몇 시간씩 매달리고, 그동안 다음 정시 회차가 통째로 밀린다."""
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


class FetchError(RuntimeError):
    pass


def get(url: str, *, mobile: bool = False, timeout: float = 8, retries: int = 1,
        encoding: str | None = None) -> str:
    headers = {
        "User-Agent": UA_MOBILE if mobile else UA_DESKTOP,
        "Accept": "*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip",
    }
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                enc = encoding
                if not enc:
                    m = re.search(r"charset=([\w-]+)", r.headers.get("Content-Type", ""), re.I)
                    enc = m.group(1) if m else None
                if not enc:
                    head = raw[:2048].decode("ascii", "ignore")
                    m = re.search(r'charset=["\']?([\w-]+)', head, re.I)
                    enc = m.group(1) if m else "utf-8"
                if enc.lower() in ("euc-kr", "ks_c_5601-1987", "euckr"):
                    enc = "cp949"
                return raw.decode(enc, "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"{url}: {last}")
