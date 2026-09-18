from collections import deque
from unittest import TestCase


class TestBinary1(TestCase):
    def test1(self):
        q = deque()
        q.append(1)
        q.append(2)
        q.append(3)
        print(q.popleft())
