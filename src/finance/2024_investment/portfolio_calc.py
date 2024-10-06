from datetime import date, timedelta, datetime
import pandas as pd
import numpy as np
import sys


def pnl(robinhood, ib, fidelity, moomoo):
    # spy return rate
    spy_rate = 568.44/467.58
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
    current = moomoo
    
    pnl = current - begin - transfer_base
    spy_expect_return = begin * (daily_rate ** delta) + np.sum(df['spy_expect_return'])
    print(f"pnl: {pnl:.2f}\npnl_rate:{pnl/(begin+transfer_base):.2f}\ncurrent: {current:.2f}\nspy expect: {spy_expect_return:.2f}")
    total_assets = current + robinhood + ib + fidelity
    print(f"moomoo: {current:.2f}\nrobinhood: {robinhood:.2f}\nib: {ib:.2f}\nfidelity: {fidelity:.2f}\ntotal assets: {total_assets:.2f}")


if __name__ == '__main__':
    """
    portfolio
    
    robinhood, ib, fidelity = 626720.13 30844. 100024.19 356489.09
    """
    if len(sys.argv) != 5:
        print("Usage: python portfolio_calc.py <robinhood> <ib> <fidelity>")
        sys.exit(1)
    robinhood = float(sys.argv[1])
    ib = float(sys.argv[2])
    fidelity = float(sys.argv[3])
    moomoo = float(sys.argv[4])
    pnl(robinhood, ib, fidelity, moomoo)
