import heapq
from unittest import TestCase

a = [
    [12, 18, 6, 3],
    [4, 3, 1, 2],
    [15, 8, 9, 6]
]

points = [[1, 3], [-2, 2], [3, 3]]


def kClosest1(points, K):
    """
    :type points: List[List[int]]
    :type K: int
    :rtype: List[List[int]]
    """
    dist_points = [[p[0] ** 2 + p[1] ** 2, p[0], p[1]] for p in points]
    return [[p[1], p[2]] for p in heapq.nsmallest(K, dist_points, key=lambda x: x[0])]


def kClosest2(points, K):
    """
    :type points: List[List[int]]
    :type K: int
    :rtype: List[List[int]]
    """
    dist_points = [[p[0] ** 2 + p[1] ** 2, p[0], p[1]] for p in points]
    dist_points.sort(key=lambda x: x[0])
    return [[p[1], p[2]] for p in dist_points[:K]]


class MedianFinder:
    def __init__(self):
        self.min_heap = []
        self.max_heap = []

    def add_num(self, num):
        heapq.heappush(self.min_heap, -heapq.heappushpop(self.max_heap, -num))
        if len(self.min_heap) > len(self.max_heap) + 1:
            heapq.heappush(self.max_heap, -heapq.heappop(self.min_heap))

    def find_median(self):
        if len(self.min_heap) == len(self.max_heap):
            return (self.min_heap[0] - self.max_heap[0]) / 2.0
        return self.min_heap[0]

class TestSorting(TestCase):
    def test_list_sort(self):
        a.sort(key=lambda x: x[1])
        print(a)

    def test_heapq_sort(self):
        print(kClosest1(points, 2))
        print(kClosest2(points, 2))

    def test_heapq_find_median(self):
        mf=MedianFinder()
        mf.add_num(1)
        mf.add_num(2)
        print(mf.find_median())
        mf.add_num(3)
        print(mf.find_median())

