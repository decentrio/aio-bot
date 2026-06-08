import unittest
from unittest.mock import patch


try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    import sys
    import types

    requests = types.ModuleType("requests")
    requests.request = None
    requests_exceptions = types.ModuleType("requests.exceptions")
    requests_exceptions.RequestException = Exception
    sys.modules["requests"] = requests
    sys.modules["requests.exceptions"] = requests_exceptions

from feat.peggo import Peggo


class RecordingPeggo(Peggo):
    def __init__(self, params):
        super().__init__(
            app={"discord": None, "slack": None, "telegram": None},
            params=params,
            apis=[],
        )
        self.messages = []

    def notify(self, message):
        self.messages.append(message)


def operator(last_observed_nonce, last_claim_eth_event_nonce):
    return {
        "valoper_address": "injvaloper1example",
        "orchestrator_address": "inj1orchestrator",
        "moniker": "Innovating Capital",
        "last_observed_nonce": last_observed_nonce,
        "last_claim_eth_event_nonce": last_claim_eth_event_nonce,
        "last_height": 169410376,
        "valset_confirms": [],
        "batch_confirms": [],
    }


class PeggoNonceAlertTest(unittest.TestCase):
    def test_progressing_claim_nonce_suppresses_lag_alert(self):
        peggo = RecordingPeggo({"threshold": 10, "interval": 1200})

        with patch("feat.peggo.time.time", side_effect=[1000, 2301]):
            peggo.check(operator(94215, 94171))
            peggo.check(operator(94216, 94172))

        self.assertEqual([], peggo.messages)

    def test_stale_claim_nonce_alerts_after_grace(self):
        peggo = RecordingPeggo({
            "threshold": 10,
            "interval": 1200,
            "nonce_progress_grace_seconds": 1200,
        })

        with patch("feat.peggo.time.time", side_effect=[1000, 2201]):
            peggo.check(operator(94215, 94171))
            peggo.check(operator(94216, 94171))

        self.assertEqual(1, len(peggo.messages))
        self.assertEqual("nonce_mismatch", peggo.messages[0]["type"])

    def test_claim_nonce_ahead_of_observed_nonce_does_not_alert(self):
        peggo = RecordingPeggo({
            "threshold": 10,
            "interval": 1200,
            "nonce_progress_grace_seconds": 0,
        })

        with patch("feat.peggo.time.time", return_value=1000):
            peggo.check(operator(94171, 94215))

        self.assertEqual([], peggo.messages)

    def test_regressed_claim_nonce_alerts_even_inside_grace_window(self):
        peggo = RecordingPeggo({
            "threshold": 10,
            "interval": 1200,
            "nonce_progress_grace_seconds": 1200,
        })

        with patch("feat.peggo.time.time", side_effect=[1000, 1010]):
            peggo.check(operator(94215, 94171))
            peggo.check(operator(94216, 94170))

        self.assertEqual(1, len(peggo.messages))
        self.assertEqual("nonce_mismatch", peggo.messages[0]["type"])


if __name__ == "__main__":
    unittest.main()
