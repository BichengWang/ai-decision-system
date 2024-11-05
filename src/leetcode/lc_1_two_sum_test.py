import pytest
from lc_1_two_sum import TwoSum


def test_two_sum():
    ts = TwoSum()
    
    # Test case 1: Example from the problem statement
    nums = [2, 7, 11, 15]
    target = 9
    assert ts.two_sum(nums, target) == [0, 1]
    
    # Test case 2: No solution
    nums = [2, 7, 11, 15]
    target = 10
    assert ts.two_sum(nums, target) == [-1, -1]
    
    # Test case 3: Multiple solutions
    nums = [3, 2, 4]
    target = 6
    assert ts.two_sum(nums, target) == [1, 2]
    
    # Test case 4: Empty list
    nums = []
    target = 9
    assert ts.two_sum(nums, target) == [-1, -1]
    
    # Test case 5: Single element list
    nums = [9]
    target = 9
    assert ts.two_sum(nums, target) == [-1, -1]
    
    # Test case 6: Large input
    nums = list(range(10**6))
    target = 2*(10**6)
    assert ts.two_sum(nums, target) == [10**6-2, 10**6-1]

pytest.main()