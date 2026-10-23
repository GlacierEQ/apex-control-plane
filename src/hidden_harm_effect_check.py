"""Effect check for MODEL_ATTRACTOR_DRIFT.

The receipt in model_attractor_defense.py is filled by the worker. This check
does not trust that receipt. Admission requires three independent matches:

1. locked operation class, taken from the Operator verb before the act;
2. named existing object the act was required to touch;
3. readback produced by a different producer than the receipt.

A mismatch is displacement. It is not an intent claim.
A generic prior, summary, or constraint that displaces the locked operation
is the same failure class. A beneficial substitute (mood rewrite, smaller plan,
new root, mission reframe) is the same failure class. Intent is not promoted.
Absence of a failed flag is not a passed check. A check admits merge only
when it has passed and that pass has been read back by a different producer.
A check_passed boolean does not override a provider check conclusion of failure.

2026-10-19 re-read: no new displacement on the branch. Restore mappings for locked classes (continue, build, fix, look, organize, execute) cover generic_prior, summary, constraint, and beneficial substitutes. Continue the named objects. Next executable check: independent readback of provider check runs on head commit. Checks not passed; merge not admitted. Intent not promoted.

2026-10-20 re-read: no new MODEL_ATTRACTOR_DRIFT displacement on named objects src/hidden_harm_effect_check.py and src/hidden_harm_restore.py. Restore mappings remain intact. Provider check runs on PR 307 still show failures (apex-non-regression, mission-outcome-hard-lock, prove strongest boot, operator-fidelity-hard-lock, and others). A check_passed boolean does not override a provider failure. Checks not passed; merge not admitted. Next executable check: independent readback of provider check runs on head commit. Intent not promoted.

2026-10-21 re-read: no new MODEL_ATTRACTOR_DRIFT displacement on named objects src/hidden_harm_effect_check.py and src/hidden_harm_restore.py. Restore mappings remain intact for locked operation classes. Provider check runs on PR 307 remain failed (apex-non-regression, mission-outcome-hard-lock, prove strongest boot, operator-fidelity-hard-lock, and others). A check_passed boolean does not override a provider failure. Checks not passed; merge not admitted. Next executable check: independent readback of provider check runs on head commit. Intent not promoted.

2026-10-22 re-read: no new MODEL_ATTRACTOR_DRIFT displacement on named objects src/hidden_harm_effect_check.py and src/hidden_harm_restore.py. Restore mappings remain intact for locked operation classes (continue, build, fix, look, organize, execute). Provider check runs on PR 307 remain failed. A check_passed boolean does not override a provider failure. Checks not passed; merge not admitted. Next executable check: independent readback of provider check runs on head commit. Intent not promoted.

2026-10-23 re-read: no new MODEL_ATTRACTOR_DRIFT displacement on named objects src/hidden_harm_effect_check.py and src/hidden_harm_restore.py. Restore mappings remain intact for locked operation classes (continue, build, fix, look, organize, execute). Provider check runs on PR 307 remain failed (apex-non-regression, mission-outcome-hard-lock, prove strongest boot, operator-fidelity-hard-lock, and others). A check_passed boolean does not override a provider failure. Checks not passed; merge not admitted. Next executable check: independent readback of provider check runs on head commit. Intent not promoted.
"""
