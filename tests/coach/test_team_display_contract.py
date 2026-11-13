"""The coach card receives the refusal flag together with the count."""


def test_team_projection_keeps_count_refusal(monkeypatch):
    from jumpsight_coach import accounts

    monkeypatch.setattr(accounts, "_uid", lambda: "coach_test_123")
    monkeypatch.setattr(
        accounts,
        "_load",
        lambda: {
            "teams": {"coach_test_123": {"students": ["student_test_123"], "seen": {}}},
            "profiles": {},
            "codes": {},
        },
    )
    monkeypatch.setattr(
        accounts,
        "_history_of",
        lambda _: [
            {
                "job": "job_fixture",
                "ts": 1790700000,
                "jump": "Axel",
                "count_named": "triple",
                "count_supported": False,
                "errors": [],
            }
        ],
    )
    monkeypatch.setattr(accounts, "coach_focus_of", lambda _: None)
    assert accounts.team()[0]["last"]["count_supported"] is False
