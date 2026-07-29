# security-copilot — to-do

Status of models/training and remaining work. Last updated 2026-07-29.

## Models — training status

**Nothing needs to be trained to run the project.** All custom models are already
trained and on disk; `run_all.bash` detects them and skips straight to launching.

| Model | Artifact(s) | Status |
|---|---|---|
| Isolation Forest — per-row (labeled datasets) | `backend/model_artifacts/isolation_forest.joblib` + `_scaler.joblib` + `.threshold.json` | ✅ trained |
| Isolation Forest — windowed (live scoring) | `backend/model_artifacts/isolation_forest_window.joblib` + scaler + threshold | ✅ trained |
| TranAD (temporal / sequence) | `backend/model_artifacts/tranad.pt` + `tranad_scaler.joblib` + `tranad.threshold.json` | ✅ trained |
| MITRE ATT&CK index (SecureBERT) | `backend/data/mitre/technique_{embeddings,mean,projection}.npy` + `technique_index.json` | ✅ built (697 techniques) |

**Pretrained models (download once, nothing to train):**
- SecureBERT — already downloaded/cached (during the MITRE index build).
- `content_classifier`: pirocheto phishing-URL (ONNX) + ealvaradob BERT — download on the first
  link/email check. `download_everything.bash` warms them into the Hugging Face cache so the first
  real check isn't slow. If you skipped that, the first `/check-links` pays a one-time download.

## Optional — improve detection quality (not required)

- [ ] Retrain the Isolation Forest / TranAD on the **full** datasets instead of the bundled
      200-row samples + synthetic baselines:
      - CICIDS2017: https://www.unb.ca/cic/datasets/ids-2017.html
      - NSL-KDD: https://www.unb.ca/cic/datasets/nsl.html
      ```bash
      source .venv/bin/activate && cd backend
      python ../scripts/train_isolation_forest.py --input path/to/full.csv
      python ../scripts/train_isolation_forest.py --feature-set window --input path/to/windows.csv
      python ../scripts/train_tranad.py --input path/to/windows.csv
      ```

## Remaining work (deferred by design)

- [ ] **Phase 8 — personalize on your own traffic.** Retrain the Isolation Forest (and TranAD) on
      *this machine's* logged windows instead of the public datasets, excluding confirmed-malicious
      flows (check each window against `history.db` verdicts first), and recompute the percentile
      threshold. Needs a scheduled trigger (cron or a periodic check in `host.py`'s loop). Only
      starts after the native helper has been running for ~2–4 weeks so there's real traffic to
      learn from. Not started.

## Not planned (documented, out of scope)

- LogBERT / CyBERT raw-log semantic analysis — needs log sources this project doesn't capture.
- Whole-home-network monitoring beyond this one machine — needs router-level infrastructure.
- Automatic per-link badging via a content script — the extension is intentionally click-triggered.
