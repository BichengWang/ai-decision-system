import numpy as np

class ChecklistHelper:
    def __init__(self):
        return

    def today(self):
        return

    def checkin(self, event):
        return

    def add(self, event_name, freq='DAY', times=45, desc=''):
        return


if __name__ == "__main__":
    cl_helper = ChecklistHelper()
    while True:
        print("0. ADD EVENT")
        print(cl_helper.today())
        event = input("Choose event: ")
        if event == "exit":
            break
        event = int(event)
        if event == 0:
            event_name = input("event name: ")
            freq = input("freq: ")
            times = int(input("times: "))
            desc = input("desc: ")
            cl_helper.add(event_name, freq, times, desc)
        else:
            cl_helper.checkin(event)
        print("Finished.")
