

## Model tuning update (2026-11-20)

The Kaggle vital-sign training script now compares a randomized-CV tuned Random Forest with a tuned XGBoost classifier. Tuning is performed on a bounded sample of the training partition (up to 60,000 rows, 3 folds), then each selected estimator is refit on the full training partition and evaluated on the held-out test partition. The selected model is chosen by held-out balanced accuracy, with high-risk recall and macro-F1 as tie-breakers.

Run from `backend`:

```powershell
python -m pip install -r requirements.txt
python scripts/train_kaggle_vital_risk.py
```

The script saves the model bundle and a comparison report to `data/biotwin/models/`. It reports high-risk precision/recall and low-risk recall separately. Metrics reproduce the dataset's threshold-derived High/Low label only; they do not establish clinical or occupational-health prediction validity.
