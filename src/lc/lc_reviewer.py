from src.utils.general import pd_utils
from datetime import date
import logging
import pandas as pd

pd.set_option('display.width', None)


class LCReviewer:
    """
    LC Reviewer help review LC
    """
    def __init__(self):
        self.df = pd_utils.pd_read_csv('../../data/files/lc_record.csv')
        self.review_df = pd_utils.pd_read_csv('../../data/files/lc_review.csv')
        today_datestr = date.today().strftime("%Y-%m-%d")
        if self.review_df.iloc[-1]['datestr'] != today_datestr:
            new_row = {'row_num': self.review_df.iloc[-1]['row_num'], 'datestr': date.today().strftime("%Y-%m-%d")}
            self.review_df = self.review_df.append(new_row, ignore_index=True)
        self.cur_row = self.review_df.iloc[-1]['row_num']
        self.today_num = 0
        self.save_df()

    def save_df(self):
        pd_utils.pd_write_csv(self.review_df, '../../data/files/lc_review.csv')

    def next(self):
        self.cur_row = self.review_df.iloc[-1]['row_num']
        if self.cur_row >= len(self.df):
            print("Good job! All LC review done.")
            return
        self.save()
        row = self.df.iloc[self.cur_row]
        print("\nNext Question:\nNum:\t{}\nURL:\t{}\nDate:\t{}\nToday:\t{}\n".format(
            row['lc_num'], row['lc_url'], row['date'], self.today_num))

    def save(self):
        self.cur_row += 1
        self.review_df.iloc[-1, self.review_df.columns.get_loc('row_num')] = self.cur_row
        self.today_num = self.cur_row - self.review_df.iloc[-2]['row_num']
        self.save_df()


if __name__ == "__main__":
    lc_reviewer = LCReviewer()
    print("Start review")
    while True:
        lc_reviewer.next()
        receive = input("input: ")
        if receive == "exit":
            break
