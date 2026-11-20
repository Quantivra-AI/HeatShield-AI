from app.biotwin.heat_health_evidence import build_heat_health_dataset_context


def test_project_research_datasets_are_included_in_context():
    result = build_heat_health_dataset_context(
        {"body_temperature_c": 38.2, "heart_rate_bpm": 124, "spo2_pct": 97},
        {"air_temperature_c": 39.0, "relative_humidity_pct": 65, "exposure_minutes": 45},
    )
    assert result["counts"]["project_physiological_rows"] == 20
    assert result["counts"]["project_prospie_rows"] == 155
    assert "Final core temperature" in result["context"]
    assert "Closest environmental condition examples" in result["context"]
    assert "not a labelled disease-outcome cohort" in result["context"]
    assert len(result["sources"]) >= 3
