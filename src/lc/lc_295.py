import copy
from collections import deque


class Solution:
    def maxCoins(self, nums):
        ret = 0
        for i in range(len(nums)):
            cur = 0
            if i != 0 or i != len(nums) - 1:
                cur = nums[i - 1] * nums[i] * nums[i + 1]
            new_nums = copy.deepcopy(nums)
            del new_nums[i]
            ret = max(ret, cur + self.maxCoins(new_nums))
        return ret

if __name__ == "__main__":
    hq = []
    q = deque()
    s = Solution()
    print(s.maxCoins([3,1,5,8]))