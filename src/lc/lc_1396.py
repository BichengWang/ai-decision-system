class Station:
    def __init__(self):
        self.in_dict = dict()
        self.out_dict = dict()

    def get_in(self):
        return self.in_dict


class UndergroundSystem:

    def __init__(self):
        self.stations = dict()

    def checkIn(self, id: int, stationName: str, t: int) -> None:
        if stationName not in self.stations:
            self.stations[stationName] = Station()
        self.stations[stationName].get_in[id] = t

    def checkOut(self, id: int, stationName: str, t: int) -> None:
        if stationName not in self.stations:
            self.stations[stationName] = Station()
        self.stations[stationName].out_dict[id] = t

    def getAverageTime(self, startStation: str, endStation: str) -> float:
        in_dict = self.stations[startStation].in_dict()
        out_dict = self.stations[endStation].out_dict()
        intersection_key = in_dict.keys().intersection(out_dict.keys())
        sum_time = 0.0
        for k in intersection_key:
            sum_time += out_dict[k] - in_dict[k]
        return sum_time / len(intersection_key)


if __name__ == "__main__":
    obj = UndergroundSystem()
    obj.checkIn('id','A',1)
    obj.checkOut('id','B',3)
    param_3 = obj.getAverageTime('A','B')
