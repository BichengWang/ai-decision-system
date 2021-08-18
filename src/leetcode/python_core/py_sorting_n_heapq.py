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


class TestSorting(TestCase):
    def test_listSort(self):
        a.sort(key=lambda x: x[1])
        print(a)

    def test_heapqSort(self):
        print(kClosest1(points, 2))
        print(kClosest2(points, 2))
