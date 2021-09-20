from unittest import TestCase


class Test(TestCase):
    def test_exact_match(self):
        self.assertEqual(
            (['FB,B,0100,UUID1'], ['FB,S,0100,UUID1']),
            facebook_interview_prepare.delete1([
                "AAPL,B,0100,UUID1",
                "FB,B,0100,UUID1",
            ], [
                "AAPL,B,0100,UUID1",
                "FB,S,0100,UUID1",
            ]),
        )