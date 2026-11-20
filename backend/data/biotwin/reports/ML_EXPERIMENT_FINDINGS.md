# BioTwin ML Experiment Findings

## Dataset
- Dataset: PROSPIE occupational heat-stress study
- Participant-condition samples: 155
- Unique participants: 40
- Experimental conditions: 9
- Target: Mean work-phase rectal core temperature
- Validation: Nested GroupKFold by participant
- Outer folds: 5
- Inner folds: 4

## Model Comparison

| Model | MAE | RMSE | R2 |
|---|---:|---:|---:|
| Ridge: All features + condition | 0.184202 | 0.243428 | -0.026530 |
| Condition-aware baseline | 0.188685 | 0.239835 | 0.003553 |
| Condition-only Ridge | 0.190691 | 0.240887 | -0.005211 |
| Environmental + condition | 0.192670 | 0.245719 | -0.045942 |
| Dummy baseline | 0.193112 | 0.243516 | -0.027273 |
| Environmental + workload + condition | 0.198390 | 0.249807 | -0.081030 |

## Findings

1. Ridge with all features and protocol context achieved the lowest MAE.
2. The condition-aware baseline achieved the best RMSE and R2.
3. Adding workload features did not improve overall predictive performance.
4. Experimental condition identifiers contain useful protocol-related information.
5. Performance varied across participant-held-out folds.

## Scientific Limitations

- Only 40 independent participants were available.
- The model estimates contemporaneous work-phase mean core temperature.
- It does not forecast future heat illness or individual medical risk.
- Experimental condition IDs are not portable workplace measurements.
- Generalisation to unseen experimental conditions and real-world worksites remains untested.
- No validated worker-safety prediction capability is established.

## Decision

Do not claim a validated predictive model.

Retain Ridge as an exploratory benchmark, alongside the condition-aware and dummy baselines.

Prioritise explainable research insights, evidence traceability, and uncertainty reporting in BioTwin.
