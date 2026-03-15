from app.llm.mock_clients import MockLLMClient


def test_mock_llm_tiebreak_response_shape():
    client = MockLLMClient()
    out = client.complete_json("tie-break candidate list")
    assert "recommended_match_index" in out
    assert "suggested_confidence" in out


def test_mock_llm_exception_response_shape():
    client = MockLLMClient()
    out = client.complete_json("explain unreconciled exception")
    assert "explanation" in out
    assert "actions" in out
