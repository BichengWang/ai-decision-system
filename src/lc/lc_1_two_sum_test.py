import unittest
from src.leetcode.lc_1_two_sum import TwoSum

class TestTwoSum(unittest.TestCase):
    def setUp(self):
        self.ts = TwoSum()

    def test_example_case(self):
        nums = [2, 7, 11, 15]
        target = 9
        self.assertEqual(self.ts.two_sum(nums, target), [0, 1])

    def test_no_solution(self):
        nums = [2, 7, 11, 15]
        target = 10
        self.assertEqual(self.ts.two_sum(nums, target), [-1, -1])

    def test_multiple_solutions(self):
        nums = [3, 2, 4]
        target = 6
        self.assertEqual(self.ts.two_sum(nums, target), [1, 2])

    def test_empty_list(self):
        nums = []
        target = 9
        self.assertEqual(self.ts.two_sum(nums, target), [-1, -1])

    def test_single_element_list(self):
        nums = [9]
        target = 9
        self.assertEqual(self.ts.two_sum(nums, target), [-1, -1])

    def test_large_input(self):
        nums = list(range(10**6))
        target = 2 * (10**6)
        self.assertEqual(self.ts.two_sum(nums, target), [10**6 - 2, 10**6 - 1])

# Run the test suite from the root project folder like this:
# $ python3 -m unittest src/leetcode/lc_1_two_sum_test.py
if __name__ == "__main__":
    unittest.main()

