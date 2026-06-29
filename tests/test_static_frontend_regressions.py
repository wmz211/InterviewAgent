from pathlib import Path


STATIC_HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


def _html() -> str:
    return STATIC_HTML.read_text(encoding="utf-8")


def test_asr_final_appends_to_existing_input_instead_of_replacing_it():
    html = _html()

    assert "appendTranscriptToInput" in html
    assert "$input.value = appendTranscriptToInput($input.value, m.text);" in html
    assert "$input.value = m.text;" not in html


def test_human_messages_wrap_long_unbroken_text_inside_chat_width():
    html = _html()

    assert ".msg-human .msg-body" in html
    assert ".msg-human .msg-body { flex: none; min-width: 0; max-width: 100%; }" in html
    assert "overflow-wrap: anywhere;" in html
    assert "word-break: break-word;" in html


def test_setup_can_reuse_previous_resume_and_jd_materials():
    html = _html()

    assert 'id="reuseResumeSelect"' in html
    assert 'id="reuseJdSelect"' in html
    assert "async function loadReuseOptions()" in html
    assert "fetch('/api/v1/upload/reuse-options'" in html
    assert "fd.append('reuse_resume_session_id', selectedReuseResumeId);" in html
    assert "fd.append('reuse_jd_session_id', selectedReuseJdId);" in html
    assert "if (!f && !selectedReuseResumeId) return;" in html


def test_audio_websocket_includes_auth_token_query_param():
    html = _html()

    assert "encodeURIComponent(getToken() || '')" in html
    assert "api/v1/ws/audio/${S.sessionId}?token=${token}" in html
