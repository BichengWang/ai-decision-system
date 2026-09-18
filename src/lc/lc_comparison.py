from src.leetcode.lc_recorder import LCRecorder
from src.utils.general import pd_utils
from datetime import date
import logging
import pandas as pd
import numpy as np
import re


class LCComparison:
    """
    LC Comparison could compare https://leetcode.com/problemset/all/ num with exist num data/files/cache.txt to find new
    """
    def __init__(self, file_name='../../data/files/cache.txt'):
        self.file_name = file_name
        self.lc_r = LCRecorder()

    def find_not_exist(self):
        all_nums = self._search_content()
        not_exist_nums = self._compare_with_exit(all_nums, self.lc_r.is_exist)
        return not_exist_nums

    def _search_content(self):
        with open(self.file_name, 'r', encoding='UTF-8') as fp:
            content = fp.read()
            _, start = re.compile('#	Title	Solution	Acceptance	Difficulty	Frequency').search(content).span()
            end, _ = re.compile("LeetCode\'s Pick Problem").search(content).span()
            content = content[start:end]
            print(content)
            reg_ret = re.findall(r'\n\d+\n', content)
            ret = []
            for reg in reg_ret:
                ret.append(reg[1:-1])
        # drop per row content
        return ret[:-1]

    def _compare_with_exit(self, targets, is_exist):
        not_exist_nums = []
        for num in targets:
            if not is_exist('lc_num', int(num)):
                not_exist_nums.append(num)
        return not_exist_nums

if __name__ == "__main__":
    print("Today's targets: {}".format(LCComparison().find_not_exist()))
