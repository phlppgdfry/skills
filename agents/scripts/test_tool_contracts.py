import unittest
from unittest.mock import Mock

from tool_contracts import Context, dispatch


class ToolContractTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.backend.lookup.return_value = {"reference": "ORD-0001", "status": "held"}
        self.backend.request_review.return_value = {
            "reference": "ORD-0001",
            "review_id": "REV-0001",
            "status": "pending_review",
        }
        self.context = Context("ORD-0001")

    def call(self, name="lookup_order", arguments=None, context=None):
        return dispatch(
            name,
            {"reference": "ORD-0001"} if arguments is None else arguments,
            context or self.context,
            self.backend,
        )

    def test_known_facts_are_exact_and_copied(self):
        result = self.call()
        self.assertEqual(
            result,
            {"outcome": "known", "facts": {"reference": "ORD-0001", "status": "held"}},
        )
        result["facts"]["status"] = "shipped"
        self.assertEqual(self.backend.lookup.return_value["status"], "held")

    def test_invalid_arguments_never_reach_backend(self):
        for arguments in [
            {},
            [],
            "ORD-0001",
            {"reference": 1},
            {"reference": True},
            {"reference": "ORD-0001\n"},
            {"reference": "ORD-0001 extra"},
            {"reference": "ord-0001"},
            {"reference": "ORD-١٢٣٤"},
            {"reference": "ORD-0001", "authorized": True},
        ]:
            with self.subTest(arguments=arguments):
                self.assertEqual(
                    self.call(arguments=arguments), {"outcome": "invalid_arguments"}
                )
        self.backend.lookup.assert_not_called()
        self.backend.request_review.assert_not_called()

    def test_null_arguments_are_rejected(self):
        self.assertEqual(
            dispatch("lookup_order", None, self.context, self.backend),
            {"outcome": "invalid_arguments"},
        )

    def test_unknown_tool_is_not_dispatched(self):
        self.assertEqual(self.call(name="delete_order"), {"outcome": "invalid_tool"})
        self.backend.lookup.assert_not_called()
        self.backend.request_review.assert_not_called()

    def test_reference_scope_precedes_lookup_and_write(self):
        for name in ["lookup_order", "request_review"]:
            self.assertEqual(
                self.call(
                    name=name,
                    arguments={"reference": "ORD-0002"},
                    context=Context("ORD-0001", True),
                ),
                {"outcome": "forbidden"},
            )
        self.backend.lookup.assert_not_called()
        self.backend.request_review.assert_not_called()

    def test_unknown_is_not_inferred_from_an_empty_object(self):
        self.backend.lookup.return_value = None
        self.assertEqual(self.call(), {"outcome": "unknown", "reference": "ORD-0001"})
        self.backend.lookup.return_value = {}
        self.assertEqual(self.call(), {"outcome": "invalid_response"})

    def test_malformed_backend_results_fail_closed(self):
        for result in [
            False,
            [],
            "held",
            {},
            {"reference": "ORD-0001"},
            {"reference": "ORD-0002", "status": "held"},
            {"reference": "ORD-0001", "status": None},
            {"reference": "ORD-0001", "status": []},
            {"reference": "ORD-0001", "status": "released"},
            {"reference": "ORD-0001", "status": "held", "secret": "private"},
        ]:
            with self.subTest(result=result):
                self.backend.lookup.return_value = result
                self.assertEqual(self.call(), {"outcome": "invalid_response"})

    def test_all_documented_statuses_are_accepted(self):
        for status in ["processing", "shipped", "held"]:
            self.backend.lookup.return_value = {
                "reference": "ORD-0001",
                "status": status,
            }
            self.assertEqual(self.call()["facts"]["status"], status)

    def test_lookup_timeout_and_error_do_not_leak_messages(self):
        for error, reason in [
            (TimeoutError("private"), "timeout"),
            (RuntimeError("credential"), "backend_error"),
        ]:
            self.backend.lookup.side_effect = error
            self.assertEqual(self.call(), {"outcome": "unavailable", "reason": reason})

    def test_review_requires_real_boolean_capability(self):
        for grant in [False, "true", 1, None]:
            self.assertEqual(
                self.call(name="request_review", context=Context("ORD-0001", grant)),
                {"outcome": "forbidden"},
            )
        self.backend.request_review.assert_not_called()

    def test_authorized_review_is_pending_not_approved(self):
        result = self.call(name="request_review", context=Context("ORD-0001", True))
        self.assertEqual(result["outcome"], "pending_review")
        self.assertEqual(result["facts"]["status"], "pending_review")
        self.backend.request_review.assert_called_once_with("ORD-0001")
        self.backend.lookup.assert_not_called()

    def test_review_response_validation(self):
        for result in [
            None,
            {},
            {"reference": "ORD-0001", "review_id": "REV-0001", "status": "approved"},
            {
                "reference": "ORD-0002",
                "review_id": "REV-0001",
                "status": "pending_review",
            },
            {"reference": "ORD-0001", "review_id": None, "status": "pending_review"},
            {
                "reference": "ORD-0001",
                "review_id": "REV-0001\n",
                "status": "pending_review",
            },
            {
                "reference": "ORD-0001",
                "review_id": "REV-0001",
                "status": "pending_review",
                "secret": "private",
            },
        ]:
            with self.subTest(result=result):
                self.backend.request_review.return_value = result
                self.assertEqual(
                    self.call(name="request_review", context=Context("ORD-0001", True)),
                    {"outcome": "invalid_response"},
                )

    def test_review_failure_is_not_retried(self):
        self.backend.request_review.side_effect = TimeoutError()
        self.assertEqual(
            self.call(name="request_review", context=Context("ORD-0001", True)),
            {"outcome": "unavailable", "reason": "timeout"},
        )
        self.backend.request_review.assert_called_once()

    def test_success_then_failure_does_not_reuse_known_facts(self):
        self.backend.lookup.side_effect = [
            {"reference": "ORD-0001", "status": "held"},
            TimeoutError(),
            None,
        ]
        self.assertEqual(self.call()["outcome"], "known")
        self.assertEqual(self.call(), {"outcome": "unavailable", "reason": "timeout"})
        self.assertEqual(self.call(), {"outcome": "unknown", "reference": "ORD-0001"})


if __name__ == "__main__":
    unittest.main()
