from collections import deque

from src.utils import pd_utils
from datetime import date
import logging
import pandas as pd
import numpy as np


class LCRecorder:
    def __init__(self):
        self.df = pd_utils.pd_read_csv('../../data/files/lc_record.csv')

    def _init_non_record(self):
        self.df = pd.DataFrame({
            "lc_num": np.array([0, 1], dtype='int64'),
            "lc_url": np.array(['st1r', 's2'], dtype='str'),
            "date": np.array(['2020-01-01', '2020-01-01'], dtype='str')
        })

    def print_df(self, df=None):
        if not df:
            df = self.df
        print("data frame: \n{}".format(df))

    def find_dup(self, col_name):
        return self.df.duplicated(subset=[col_name])

    def is_exist(self, col, val):
        return self.df[col].isin([val]).any()

    def drop_dup(self):
        self.df = self.df.drop_duplicates(subset=['lc_num'])

    def save_df(self):
        pd_utils.pd_write_csv(self.df, '../../data/files/lc_record.csv')

    def add_record(self, lc_num, lc_url):
        if self.is_exist('lc_num', lc_num):
            logging.error("Num existed. {}".format(lc_num))
        new_row = {'lc_num': lc_num, 'lc_url': lc_url, 'date': date.today().strftime("%Y-%m-%d")}
        self.df = self.df.append(new_row, ignore_index=True)
        self.save_df()

    def today_records(self):
        return self.df[self.df['date'] == date.today().strftime("%Y-%m-%d")]


if __name__ == "__main__":
    lc_recorder = LCRecorder()
    lc_num, lc_url = 0, ""
    print(lc_recorder.today_records())
    while True:
        lc_n = input("lc num: ")
        if lc_n == "exit":
            break
        lc_num = int(lc_n)
        if lc_recorder.is_exist('lc_num', lc_num):
            print("lc num existed.")
            continue
        lc_url = input("lc url: ")
        lc_recorder.add_record(lc_num, lc_url)
        print("Saved.")
