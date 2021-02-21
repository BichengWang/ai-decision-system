from src.utils import pd_utils

import logging
import pandas as pd
import numpy as np


class LCRecorder:
    def __init__(self):
        self.df = pd_utils.pd_read_csv('files/lc_record.csv')

    def _init_non_record(self):
        self.df = pd.DataFrame({
            "lc_num": np.array([0, 1], dtype='int64'),
            "lc_url": np.array(['st1r', 's2'], dtype='str')
        })

    def print_all(self):
        print("data frame: \n{}".format(self.df))

    def find_dup(self, col_name):
        return self.df.duplicated(subset=[col_name])

    def is_exist(self, col, val):
        return self.df[col].isin([val]).any()

    def drop_dup(self):
        self.df = self.df.drop_duplicates(subset=['lc_num'])

    def save_df(self):
        pd_utils.pd_write_csv(self.df, 'files/lc_record.csv')

    def add_record(self, lc_num, lc_url):
        if self.is_exist('lc_num', lc_num):
            logging.error("Num existed. {}".format(lc_num))
        new_row = {'lc_num': lc_num, 'lc_url': lc_url}
        self.df = self.df.append(new_row, ignore_index=True)
        self.save_df()


if __name__ == "__main__":
    lc_recorder = LCRecorder()
    lc_num, lc_url = 0, ""
    while True:
        lc_num = int(input("lc num: "))
        if not lc_recorder.is_exist('lc_num', lc_num):
            break
        print("lc num existed.")
    lc_url = input("lc url: ")
    lc_recorder.add_record(lc_num, lc_url)
    print("Saved.")
