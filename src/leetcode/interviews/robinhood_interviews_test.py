from unittest import TestCase

from src.leetcode.interviews import robinhood_interviews


class Test(TestCase):
    def test_exact_match(self):
        self.assertEqual(
            (['FB,B,0100,UUID1'], ['FB,S,0100,UUID1']),
            robinhood_interviews.delete1([
                "AAPL,B,0100,UUID1",
                "FB,B,0100,UUID1",
            ], [
                "AAPL,B,0100,UUID1",
                "FB,S,0100,UUID1",
            ]),
        )

    def test_match_fuzzy(self):
        self.assertEqual(
            (['FB,B,0100,UUID1'], ['FB,S,0100,UUID1']),
            robinhood_interviews.delete2([
                "AAPL,B,0100,UUID1",
                "FB,B,0100,UUID1",
            ], [
                "AAPL,B,0100,UUID2",
                "FB,S,0100,UUID1",
            ]),
        )

    def test_match_buy_sell(self):
        self.assertEqual(
            (['AAPL,S,0100,UUID1'], ['AAPL,B,0100,UUID2']),
            robinhood_interviews.delete3([
                "AAPL,B,0100,UUID1",
                "FB,B,0100,UUID1",
            ], [
                "AAPL,B,0100,UUID2",
                "FB,S,0100,UUID1",
            ]),
        )

