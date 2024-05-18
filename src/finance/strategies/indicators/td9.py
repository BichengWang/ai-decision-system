import pandas as pd
from tabulate import tabulate

def loader(ticker='SPX'):
    return pd.read_csv('/Users/bichengwang/Documents/codes/python-notebook/src/finance/data/{} GOOGLEFINANCE.csv'.format(ticker.upper()))

df = loader()
# Now df contains your data with the 'date' column parsed as datetime objects
print(df.head())


"""
COUNTUP:=BARSLASTCOUNT(C>REF(C,4));
NINEUPOTHER:=ISLASTBAR AND BETWEEN(COUNTUP, 5,8);
NUMBERUP:=COUNTUP*( BACKSET((COUNTUP=9) > 0, 9)  OR BACKSET(NINEUPOTHER > 0, COUNTUP))
DRAWNUMBER((NUMBERUP > 4 AND NUMBERUP < 9), H*1.005, NUMBERUP), COLORGREEN;
DRAWTEXT(COUNTUP = 9, H*1.005, '🍅'), COLORGREEN;
COUNTDOWN:= BARSLASTCOUNT(C<REF(C,4));
NINEDOWNOTHER:=ISLASTBAR AND BETWEEN(COUNTDOWN, 5,8);
NUMBERDOWN:= COUNTDOWN*( BACKSET((COUNTDOWN =9) > 0, 9)  OR BACKSET(NINEDOWNOTHER > 0, COUNTDOWN))
DRAWNUMBER((NUMBERDOWN > 6 AND NUMBERDOWN < 9), L*0.995, NUMBERDOWN), COLORRED;
DRAWTEXT(COUNTDOWN = 9, L*0.995, '🤢'), COLORRED;
"""
def calculate_td_sequential(close_prices, td_val = 9):
    countup = 0
    countdown = 0
    trend_down = []
    trend_up = []
    for i in range(4, len(close_prices)):
        if close_prices[i] >= close_prices[i - 4]:
            countdown += 1
        elif close_prices[i] < close_prices[i - 4]:
            countdown = 0
        if countdown >= td_val:
            countdown = 0
            trend_down.append(i)
    for i in range(4, len(close_prices)):
        if close_prices[i] <= close_prices[i - 4]:
            countup += 1
        elif close_prices[i] > close_prices[i - 4]:
            countup = 0
        if countup >= td_val:
            countup = 0
            trend_up.append(i)
    return trend_up, trend_down

# Example usage:
close_prices =  df['Close'].values
trend_up, trend_down = calculate_td_sequential(close_prices)
print("Trend Reversal Signals:", trend_up, trend_down)
from IPython.display import display

display("trend_up\n", df.iloc[trend_up])
display("trend_down\n", df.iloc[trend_down])