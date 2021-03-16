class BinarySearch:

    def binary1(self, nums, tgt):
        """
        list:   [1, 3, 5]
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
        return l

    def binary2(self, nums, target):
        """
        rotated binary search
        :param nums: [4,5,6,7,0,1,2]
        :param tgt: 0, 8
        :return: 4, -1
        """
        l, r = 0, len(nums) - 1
        while l < r:
            # the mid value point to mid or left,
            # to avoid dead loop, we should move next l to mid + 1 or r to mid
            mid = (l + r) // 2
            # test l to mid is continual line or mid to r
            if nums[mid] < nums[l]:
                if nums[mid] < target <= nums[r]:
                    l = mid + 1
                else:
                    r = mid
            else:
                if nums[mid] >= target >= nums[l]:
                    r = mid
                else:
                    l = mid + 1
        return l if nums[l] == target else -1




