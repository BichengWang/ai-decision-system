from ib_insync import *
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import time
import pandas as pd
import threading
import csv


class TradeApp(EWrapper, EClient): 
    """_summary_
    Request Account Summary
    Args:
        EWrapper (_type_): _description_
        EClient (_type_): _description_
    """
    def __init__(self): 
        EClient.__init__(self, self) 

    def accountSummary(self, reqId: int, account: str, tag: str, value: str,currency: str):
        print("AccountSummary. ReqId:", reqId, "Account:", account, "Tag: ", tag, "Value:", value, "Currency:", currency)
    
    def accountSummaryEnd(self, reqId: int):
        print("AccountSummaryEnd. ReqId:", reqId)
    

def df_format(bars):
    data = []
    for bar in bars:
        data.append([bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume])
    return pd.DataFrame(data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])


def save_to_csv(data, filename):
    keys = data[0].keys()
    with open(filename, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)


if __name__ == "__main__":
    """_summary_
    https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
    tws setup: https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#setup-py-updates
    install with source lib: https://stackoverflow.com/questions/57618117/installing-the-ibapi-package
    """
    app = TradeApp()      
    app.connect("127.0.0.1", 7497, clientId=1)

    time.sleep(1)

    app.reqAccountSummary(9001, "All", 'NetLiquidation')
    
    def websocket_con():
        app.run()

    # app.connect("127.0.0.1", 7496, clientId=1)
    app.connect("127.0.0.1", 7497, clientId=0)

    con_thread = threading.Thread(target=websocket_con, daemon=True)
    con_thread.start()
    time.sleep(1)
    
    contract = Contract()
    contract.symbol = "AAPL"
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"
    
    # bars = app.reqHistoricalData(
    #     contract,
    #     endDateTime='',
    #     durationStr='1 D',
    #     barSizeSetting='5 mins',
    #     whatToShow='MIDPOINT',
    #     useRTH=True,
    #     formatDate=1)
    
    
    # Create a list to store historical data
    historical_data = []


    # Override the historicalData method to save data to the list
    def historicalData(self, reqId, bar):
        # print("HistoricalData. ReqId:", reqId, "BarData.", bar)
        historical_data.append(bar.__dict__)


    # Bind the new method to the class
    TradeApp.historicalData = historicalData

    # Request historical data
    app.reqHistoricalData(reqId=102, 
                        contract=contract,
                        endDateTime='',
                        durationStr='10 Y',
                        barSizeSetting='1 day',
                        whatToShow='TRADES',
                        useRTH=1,                 # 0 = Includes data outside of RTH | 1 = RTH data only 
                        formatDate=1,    
                        keepUpToDate=0,           # 0 = False | 1 = True 
                        chartOptions=[])

    time.sleep(5)  # Sleep interval to allow time for data retrieval

    # Save the historical data to a CSV file
    save_to_csv(historical_data, f'data/finance/{contract.symbol}_historical_data.csv')