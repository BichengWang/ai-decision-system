from unittest import TestCase

from src.leetcode.topic_summary.binary_search_topic import BinarySearch


class TestBinary1(TestCase):
    def test_binary1(self):
        bs = BinarySearch()
        print(bs.binary1([1, 3, 5], 1))
        print(bs.binary1([1, 3, 5], 2))
        print(bs.binary1([1, 3, 5], 3))
        print(bs.binary1([1, 3, 5], 4))
        print(bs.binary1([1, 3, 5], 5))
        print(bs.binary1([1, 3], 0))
        print(bs.binary1([1, 3], 1))
        print(bs.binary1([1, 3], 2))
        print(bs.binary1([1, 3], 3))
        print(bs.binary1([0, 10, 60], 0))

    def test_binary2(self):
        bs = BinarySearch()
        print(bs.binary2([1, 3, 5], 1))
        print(bs.binary2([1, 3, 5], 2))
        print(bs.binary2([1, 3, 5], 3))
        print(bs.binary2([5, 1, 3], 1))
        print(bs.binary2([5, 1, 3], 2))
        print(bs.binary2([5, 1, 3], 5))

    def test_binary_search_lib(self):
        bs = BinarySearch()
        self.assertEqual(2, bs.binary_search_lib([1, 3, 5, 7, 9, 11], 5))
        self.assertEqual(3, bs.binary_search_lib([1, 3, 5, 7, 9, 11], 6))
        self.assertEqual(3, bs.binary_search_lib([1, 3, 5, 7, 9, 11], 7))
