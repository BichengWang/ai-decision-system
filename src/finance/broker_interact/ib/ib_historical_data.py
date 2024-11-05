from ibapi.client import *
from ibapi.wrapper import *
from ibapi.contract import Contract
import threading
import time
import csv


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

time.sleep(5)  # Sleep interval to allow time for connection to server
# Define a function to save historical data to CSV


def save_to_csv(data, filename):
    keys = data[0].keys()
    with open(filename, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)


# Create a list to store historical data
historical_data = []


# Override the historicalData method to save data to the list
def historicalData(self, reqId, bar):
    print("HistoricalData. ReqId:", reqId, "BarData.", bar)
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
save_to_csv(historical_data, 'historical_data.csv')