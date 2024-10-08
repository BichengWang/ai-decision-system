from ib_insync import *

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import time


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
    

if __name__ == "__main__":
    app = TradeApp()      
    app.connect("127.0.0.1", 7496, clientId=1)

    time.sleep(1)

    app.reqAccountSummary(9001, "All", 'NetLiquidation')
    app.run()


# if __name__ == "__main__":
#     """_summary_
#     https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
#     tws setup: https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#setup-py-updates
#     install with source lib: https://stackoverflow.com/questions/57618117/installing-the-ibapi-package
#     """
#     ib = IB()
#     app.connect("127.0.0.1", args.port, clientId=0)

#     ib.connect('127.0.0.1', 7497, clientId=1, account='U3955638')

#     contract = Stock('AAPL', 'SMART', 'USD')
#     bars = ib.reqHistoricalData(
#         contract,
#         endDateTime='',
#         durationStr='1 D',
#         barSizeSetting='5 mins',
#         whatToShow='MIDPOINT',
#         useRTH=True,
#         formatDate=1)
#     df = util.df(bars)
#     print(df)