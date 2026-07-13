"""한국어 조사(은/는, 이/가, 을/를 ...) 선택 유틸.

템플릿 문장에 종목명을 끼워 넣을 때 "삼성전자은", "삼성전자을"처럼 받침을
무시하고 조사를 고정하면 모든 추천 문장이 어색해진다. 마지막 글자의 받침
유무로 조사를 고른다.

한글이 아닌 글자(영문, 기호)로 끝나는 단어는 정확한 판별이 불가능하므로
받침 없는 쪽(는/가/를)을 기본으로 쓴다 — "KT&G는", "LG는"처럼 실제 관용
표기와 대체로 일치한다. 숫자로 끝나면 읽는 소리 기준으로 판별한다.
"""
from __future__ import annotations

# (받침 있음, 받침 없음) 쌍
_JOSA_PAIRS = {
    "은/는": ("은", "는"),
    "이/가": ("이", "가"),
    "을/를": ("을", "를"),
    "과/와": ("과", "와"),
    "으로/로": ("으로", "로"),
}

# 숫자를 한글로 읽었을 때 받침이 있는 숫자: 영(0), 일(1), 삼(3), 육(6), 칠(7), 팔(8)
_DIGITS_WITH_FINAL = set("013678")


def _has_final_consonant(word: str) -> bool | None:
    """마지막 유효 글자의 받침 유무. 판별 불가면 None."""
    for ch in reversed(word):
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:  # 완성형 한글
            return (code - 0xAC00) % 28 != 0
        if ch.isdigit():
            return ch in _DIGITS_WITH_FINAL
        if ch.isalpha():  # 영문 등 — 관용적으로 받침 없는 쪽을 쓴다
            return False
        # 기호/공백은 건너뛰고 그 앞 글자로 판별
    return None


def josa(word: str, pair: str) -> str:
    """조사만 반환. josa("삼성전자", "은/는") == "는"."""
    with_final, without_final = _JOSA_PAIRS[pair]
    has_final = _has_final_consonant(word or "")
    if has_final is None:
        return without_final
    # "으로/로"는 ㄹ 받침이면 "로"를 쓴다
    if pair == "으로/로" and word:
        last = word[-1]
        code = ord(last)
        if 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 == 8:  # ㄹ 받침
            return without_final
    return with_final if has_final else without_final


def attach_josa(word: str, pair: str) -> str:
    """단어에 조사를 붙여 반환. attach_josa("삼성전자", "은/는") == "삼성전자는"."""
    return f"{word}{josa(word, pair)}"
