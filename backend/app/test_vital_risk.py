
from app.biotwin.vital_risk import assess_dataset_vital_risk


def test_dataset_model_does_not_fabricate_prediction_when_not_trained():
    result = assess_dataset_vital_risk({
        "heart_rate_bpm": 120,
        "respiratory_rate_bpm": 24,
        "body_temperature_c": 38.2,
        "temperature_type": "oral",
        "spo2_pct": 92,
        "systolic_bp_mmhg": 145,
        "diastolic_bp_mmhg": 92,
        "weight_kg": 70,
        "height_m": 1.75,
    })

    print("MODEL DEBUG:", result)

    assert result["status"] in {
        "dataset_not_downloaded_or_model_not_trained",
        "generated"
    }

    if result["status"] != "generated":
        assert result["label"] is None


def test_insufficient_values_do_not_get_dataset_label():
    result = assess_dataset_vital_risk({
        "heart_rate_bpm": 110,
        "temperature_type": "skin",
        "body_temperature_c": 37.8
    })

    assert result["status"] == "insufficient_vitals"
    assert result["label"] is None
