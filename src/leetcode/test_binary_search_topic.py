from unittest import TestCase

from src.leetcode.binary_search_topic import BinarySearch


class TestBinary1(TestCase):
    def test_binary1(self):
        bs = BinarySearch()
        bs.binary1([1, 3, 5], 1)
        bs.binary1([1, 3, 5], 2)
        bs.binary1([1, 3, 5], 3)
        bs.binary1([1, 3, 5], 4)
        bs.binary1([1, 3, 5], 5)
        bs.binary1([1, 3], 0)
        bs.binary1([1, 3], 1)
        bs.binary1([1, 3], 2)
        bs.binary1([1, 3], 3)


        bs.binary1([0,10,60], 0)
