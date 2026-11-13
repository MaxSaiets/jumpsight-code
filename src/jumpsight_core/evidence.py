"""Compatibility of old saved features with the current evidence contract."""


def normalize_result(result):
    if not isinstance(result, dict) or result.get("engine") != "jumpsight" or result.get("error_checks_version") == 1:
        return result
    errors = result.get("errors")
    if not isinstance(errors, dict):
        return result
    found = errors.get("found") or []
    clean = errors.get("checked_and_clean") or []
    code = "two_foot_landing"
    # Before version 1, this code in jumpsight came only from the 2D ankles.
    if code not in clean and not any(isinstance(item, dict) and item.get("code") == code for item in found):
        return result
    uncertain = list(errors.get("uncertain") or [])
    if not any(isinstance(item, dict) and item.get("code") == code for item in uncertain):
        uncertain.append({"code": code, "reason": "BLADE_CONTACT_NOT_OBSERVED"})
    return {
        **result,
        "error_checks_version": 1,
        "errors": {
            **errors,
            "found": [item for item in found if not (isinstance(item, dict) and item.get("code") == code)],
            "checked_and_clean": [item for item in clean if item != code],
            "uncertain": uncertain,
        },
    }


def normalize_history(record):
    if not isinstance(record, dict):
        return record
    legacy = {
        "engine": record.get("engine"),
        "error_checks_version": record.get("error_checks_version"),
        "errors": {
            "found": [{"code": code} for code in (record.get("errors") or [])],
            "checked_and_clean": record.get("errors_checked_clean") or [],
            "uncertain": record.get("errors_uncertain") or [],
        },
    }
    fixed = normalize_result(legacy)
    if fixed is legacy:
        return record
    errors = fixed["errors"]
    found = [item["code"] for item in errors["found"]]
    clean = errors["checked_and_clean"]
    return {
        **record,
        "error_checks_version": 1,
        "errors": found,
        "errors_conf": {
            code: confidence
            for code, confidence in (record.get("errors_conf") or {}).items()
            if code != "two_foot_landing"
        },
        "errors_checked_clean": clean,
        "errors_uncertain": errors["uncertain"],
        "checks_run": len(clean),
        "clean": False,
        "execution_state": "assessed" if found else "partial" if clean else "unavailable",
    }


def summary_error_checks(result):
    """One projection of the evidence for the final summary and the live coach."""
    errors = normalize_result(result).get("errors") or {}
    found = errors.get("found") or []
    return {
        "errors": [item["code"] for item in found],
        "errors_conf": {item["code"]: item.get("confidence") or "low" for item in found},
        "clean": len(errors.get("checked_and_clean") or []),
        # Names of the passed checks: '<No errors found — 2 checks
        # passed>' on a video with a fall was read as 'no fall', although
        # there was no fall among the checked ones
        "clean_codes": [
            item if isinstance(item, str) else (item or {}).get("code")
            for item in (errors.get("checked_and_clean") or [])
        ],
        "errors_uncertain": [
            {"code": item["code"], "reason": item.get("reason")} for item in (errors.get("uncertain") or [])
        ],
    }
