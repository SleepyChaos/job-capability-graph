from app.modules.talent.evaluation import (
    evaluate_active_acquisition,
    evaluate_matching_labels,
    evaluate_resume_entities,
)


def test_resume_evaluation_reports_micro_prf_and_quote_validity() -> None:
    gold = [
        {
            "sample_id": "r1",
            "source_text": "姓名：林舟。项目使用 Python 完成控制算法。",
            "entities": [
                {"type": "name", "value": "林舟"},
                {"type": "skill", "value": "Python"},
                {"type": "project", "value": "控制算法"},
            ],
        }
    ]
    predicted = [
        {
            "sample_id": "r1",
            "entities": [
                {"type": "name", "value": "林 舟", "evidence_quote": "姓名：林舟"},
                {"type": "skill", "value": "Python", "evidence_quote": "使用 Python"},
            ],
        }
    ]
    report = evaluate_resume_entities(gold, predicted)
    assert report["micro"]["tp"] == 2
    assert report["micro"]["fn"] == 1
    assert report["evidence_quote_validity"] == 1.0


def test_matching_evaluation_returns_three_class_confusion_matrix() -> None:
    gold = [
        {"pair_id": "1", "label": "match"},
        {"pair_id": "2", "label": "partial_match"},
        {"pair_id": "3", "label": "nonmatch"},
    ]
    predicted = [
        {"pair_id": "1", "label": "match"},
        {"pair_id": "2", "label": "match"},
        {"pair_id": "3", "label": "nonmatch"},
    ]
    report = evaluate_matching_labels(gold, predicted)
    assert report["accuracy"] == 0.666667
    assert report["confusion_matrix"]["rows_gold_columns_predicted"] == [
        [1, 0, 0],
        [1, 0, 0],
        [0, 0, 1],
    ]


def test_active_acquisition_evaluation_reports_safety_and_efficiency() -> None:
    report = evaluate_active_acquisition(
        [
            {
                "gold_label": "match",
                "baseline_prediction": "partial_match",
                "final_prediction": "match",
                "final_status": "safe_match",
                "initial_width": 30,
                "final_width": 10,
                "question_count": 2,
            }
        ]
    )
    assert report["accuracy_gain"] == 1.0
    assert report["mean_interval_shrink"] == 20.0
    assert report["unsafe_decision_rate"] == 0.0
