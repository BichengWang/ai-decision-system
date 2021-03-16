class BinarySearch:

    def binary1(self, nums, tgt):
        """
        list:   1, 3, 5
        tgt:    1, 2, 3
        return: 0, 0, 1
        """
        l, r = 0, len(nums) - 1
        while l < r:
            mid = (l + r + 1) // 2
            if nums[mid] > tgt:
                r = mid - 1
            else:
                l = mid
        print(l)
        return l

