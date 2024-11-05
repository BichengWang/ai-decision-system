from typing import List


class TwoSum:
    def two_sum(self, nums: List[int], target: int) -> List[int]:
        nums_dict = dict()
        for i, num in enumerate(nums):
            nums_dict[num] = i
            if target - num in nums_dict:
                return [nums_dict[target - num], i]
        return [-1, -1]


if __name__ == "__main__":
    print(TwoSum().two_sum(nums=[2, 7, 11, 15], target=9))