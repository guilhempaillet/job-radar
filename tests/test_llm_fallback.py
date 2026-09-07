from job_radar.llm_fallback import FallbackResult, _validated_result


def test_schema_validated_fallback_accepts_only_exact_citations():
    text = "This flexible role pays $180,000 per year and offers commuter benefits."
    result = _validated_result(
        {
            "experience_min": None,
            "workplace": {
                "value": "Hybrid",
                "quote": "This quote was invented",
                "confidence": "high",
            },
            "compensation": {
                "minimum": 180000,
                "maximum": None,
                "currency": "USD",
                "period": "year",
                "quote": "$180,000 per year",
                "confidence": "high",
            },
            "benefits": [
                {
                    "value": "Commuter benefits",
                    "quote": "commuter benefits",
                    "confidence": "medium",
                },
                {
                    "value": "Equity",
                    "quote": "equity",
                    "confidence": "high",
                },
            ],
        },
        text,
    )
    assert result.workplace is None
    assert result.compensation.minimum == 180000
    assert result.compensation.evidence.method == "llm_fallback"
    assert [item.value for item in result.benefits] == ["Commuter benefits"]


def test_ingest_contract_can_be_mocked_without_paid_access():
    class FakeFallback:
        def extract(self, text, missing_fields):
            assert "compensation" in missing_fields
            return FallbackResult()

    assert FakeFallback().extract("No salary listed", {"compensation"}) == FallbackResult()
