


def minRefuelStops(target, startFuel, stations):
    # if target <= startFuel:
    #     return 0
    intervals = [[0, startFuel]]
    for i, (mile, fuel) in enumerate(stations):
        print(mile)
        idx = len(intervals) - 1
        curr = []
        while idx > -1 and intervals[idx][1] >= mile:
            l, r = intervals[idx][1], fuel + intervals[idx][1]
            curr.append([l, r])
            idx -= 1
        print(curr)
        for l, r in curr[::-1]:
            if r >= intervals[-1][1]:
                while intervals and intervals[-1][0] >= l:
                    intervals.pop()
                if not intervals:
                    intervals.append([l, r])
                elif intervals[-1][0] < r:
                    intervals.append([intervals[-1][1], r])
        print(intervals)
    prev = 0
    ret = 0
    for l, r in intervals:
        if l > prev:
            return -1
        ret += 1
        prev = r
        if target <= prev:
            return ret - 1
    return -1

if __name__ == "__main__":
    print(minRefuelStops(1000, 83, [[47,220],[65,1],[98,113],[126,196],[186,218],[320,205],[686,317],[707,325],[754,104],[781,105]]))