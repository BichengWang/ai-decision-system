from ibapi.client import *
from ibapi.wrapper import *
from ibapi.contract import Contract
import threading
import time


class TradeApp(EWrapper, EClient): 
    def __init__(self): 
        EClient.__init__(self, self) 
        
    def historicalData(self, reqId, bar):
        print("HistoricalData. ReqId:", reqId, "BarData.", bar)

    def historicalSchedule(self, reqId: int, startDateTime: str, endDateTime: str, timeZone: str, sessions: ListOfHistoricalSessions):
        print("HistoricalSchedule. ReqId:", reqId, "Start:", startDateTime, "End:", endDateTime, "TimeZone:", timeZone)
        for session in sessions:
            print("\tSession. Start:", session.startDateTime, "End:", session.endDateTime, "Ref Date:", session.refDate)

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        print("HistoricalDataUpdate. ReqId:", reqId, "BarData.", bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        print("HistoricalDataEnd. ReqId:", reqId, "from", start, "to", end)


def websocket_con():
    app.run()


app = TradeApp()
app.connect("127.0.0.1", 7496, clientId=1)

con_thread = threading.Thread(target=websocket_con, daemon=True)
con_thread.start()

time.sleep(1) 

contract = Contract()
contract.symbol = "AAPL"
contract.secType = "STK"
contract.exchange = "SMART"
contract.currency = "USD"

app.reqHistoricalData(reqId=101, 
                      contract=contract,
                      endDateTime='', 
                      durationStr='1 D',
                      barSizeSetting='1 hour',
                      whatToShow='Trades',
                      useRTH=0,                 # 0 = Includes data outside of RTH | 1 = RTH data only 
                      formatDate=1,    
                      keepUpToDate=1,           # 0 = False | 1 = True 
                      chartOptions=[])