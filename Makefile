PYTHON ?= python3

.PHONY: test verify-reference legacy-test regression-test
test: verify-reference legacy-test regression-test

verify-reference:
	"$(PYTHON)" scripts/verify_reference.py

legacy-test:
	cd workflow && "$(PYTHON)" -m unittest -v test_core test_statistics test_mb_config test_reuse_cache

regression-test:
	"$(PYTHON)" -m unittest -v tests.test_regression tests.test_submission tests.test_end_to_end
