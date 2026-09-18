import json

from src.utils.general import pd_utils
from datetime import date
from ast import literal_eval

import numpy as np
import logging
import pandas as pd

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)


class LCRecorder:
    """
    LC Recorder is used to record every day LC num and url
    """
    def __init__(self):
        self.df = pd_utils.pd_read_csv('../../data/files/lc_record.csv')
        self.df['tags'] = self.df['tags'].astype(object)

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
        new_row = {
            'lc_num': lc_num,
            'lc_url': lc_url,
            'date': date.today().strftime("%Y-%m-%d"),
            'tags': "[]",
            'cnt': 1,
        }
        self.df = self.df.append(new_row, ignore_index=True)
        self.save_df()

    def today_records(self):
        return self.df[self.df['date'] == date.today().strftime("%Y-%m-%d")]

    def may_add_tags(self, lc_n):
        if not self.is_exist('lc_num', lc_n):
            return
        if len(self.df.loc[self.df.lc_num == lc_n]['tags']) < 1:
            print('tags existed')
            return
        print(self.df.at[self.df[self.df.lc_num == lc_n].index[0], 'tags'])
        tags = set(eval(self.df.at[self.df[self.df.lc_num == lc_n].index[0], 'tags']))
        while True:
            lc_tag = input('add tag:')
            if lc_tag == 'exit' or lc_tag == '':
                break
            tags.add(lc_tag)
            print(list(tags))
            self.df.at[self.df[self.df.lc_num == lc_n].index[0], 'tags'] = str(list(tags))
            self.save_df()
            print('saved tag')

    def may_add_cnt(self, lc_n):
        if not self.is_exist('lc_num', lc_n):
            return
        receive = input('cnt +1?')
        if receive == 'exit':
            return
        self.df.loc[self.df.lc_num == lc_n, 'cnt'] += 1
        self.df.loc[self.df.lc_num == lc_n, 'date'] = date.today().strftime("%Y-%m-%d")
        self.save_df()


if __name__ == "__main__":
    lc_recorder = LCRecorder()
    lc_num, lc_url = 0, ""
    while True:
        print("Today's lc: \n{}".format(lc_recorder.today_records()))
        lc_n = input("lc num: ")
        if lc_n == "exit":
            break
        lc_num = int(lc_n)
        if lc_recorder.is_exist('lc_num', lc_num):
            print("lc num existed.")
            lc_recorder.may_add_tags(lc_num)
            lc_recorder.may_add_cnt(lc_num)
            continue
        lc_url = input("lc url: ")
        lc_recorder.add_record(lc_num, lc_url)
        lc_recorder.may_add_tags(lc_num)
        print("Saved.")
