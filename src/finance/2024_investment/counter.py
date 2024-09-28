from datetime import date, timedelta, datetime
import pandas as pd
import numpy as np


def pnl():
    # spy return rate
    spy_rate = 571.30/467.58
    today = datetime.today()
    delta = (today - datetime(2024, 1, 1)).days
    daily_rate = spy_rate ** (1./delta)
    path = 'src/finance/2024_investment/records.csv'
    df = pd.read_csv(path)
    df['spy_expect_return'] = df['price'] * df['number'] * (daily_rate ** (
        df['datestr'].apply(lambda x: (today - datetime.strptime(x, '%Y-%m-%d')).days)
    ))
    transfer_base = np.sum(df['price'] * df['number'])
    begin = 2294.66
    current = 317145.05
    pnl = current - begin - transfer_base
    spy_expect_return = begin * (daily_rate ** delta) + np.sum(df['spy_expect_return'])
    print(f"pnl: {pnl:.2f}\npnl_rate:{pnl/current:.2f}\ncurrent: {current:.2f}\nspy expect: {spy_expect_return:.2f}")


if __name__ == '__main__':
    pnl()
