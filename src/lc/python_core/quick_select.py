from unittest import TestCase


def quick_select(nums, start, end, k):
    pivot = nums[(start + end) // 2]
    l, r = start, end
    while l <= r:
        while l <= r and nums[l] < pivot:
            l += 1
        while l <= r and nums[r] > pivot:
            r -= 1
        if l <= r:
            nums[l], nums[r] = nums[r], nums[l]
            l += 1
            r -= 1
    if k <= r:
        return quick_select(nums, start, r, k)
    elif k >= l:
        return quick_select(nums, l, end, k)
    else:
        return pivot


def findKthLargest(nums, k):
    """
    find Kth largest
    :param nums:
    :param k:
    :return:
    """
    return quick_select(nums, 0, len(nums) - 1, len(nums) - k)


class TestSelect(TestCase):
    def test_qs(self):
        self.assertEqual(5, findKthLargest([1, 5, 3, 2, 7, 6, 2], 3))
