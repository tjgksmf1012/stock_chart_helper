"""app.core.korean 조사 선택 유틸 테스트."""
from app.core.korean import attach_josa, josa


class TestJosa:
    def test_batchim_word_uses_eun(self):
        assert attach_josa("기업은행", "은/는") == "기업은행은"
        assert attach_josa("신한지주", "은/는") == "신한지주는"

    def test_no_batchim_word_uses_neun(self):
        assert attach_josa("삼성전자", "은/는") == "삼성전자는"
        assert attach_josa("오리온", "은/는") == "오리온은"

    def test_object_particle(self):
        assert attach_josa("삼성전자", "을/를") == "삼성전자를"
        assert attach_josa("기업은행", "을/를") == "기업은행을"

    def test_subject_particle(self):
        assert attach_josa("삼성전자", "이/가") == "삼성전자가"
        assert attach_josa("팬오션", "이/가") == "팬오션이"

    def test_pattern_names(self):
        assert attach_josa("헤드 앤 숄더", "은/는") == "헤드 앤 숄더는"
        # 괄호/기호는 건너뛰고 마지막 유효 글자(W, 영문)로 판별 → 받침 없음 취급
        assert attach_josa("이중 바닥 (W)", "은/는") == "이중 바닥 (W)는"

    def test_english_ending_defaults_to_no_batchim(self):
        assert attach_josa("KT&G", "은/는") == "KT&G는"
        assert attach_josa("LG", "은/는") == "LG는"

    def test_digit_ending(self):
        assert attach_josa("종목1", "은/는") == "종목1은"  # 일 → 받침 있음
        assert attach_josa("종목2", "은/는") == "종목2는"  # 이 → 받침 없음

    def test_eu_ro_with_rieul_batchim(self):
        assert attach_josa("서울", "으로/로") == "서울로"
        assert attach_josa("부산", "으로/로") == "부산으로"
        assert attach_josa("삼성전자", "으로/로") == "삼성전자로"

    def test_empty_string(self):
        assert josa("", "은/는") == "는"
