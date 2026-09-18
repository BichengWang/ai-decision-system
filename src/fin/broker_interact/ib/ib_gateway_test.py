from ib_insync import *
from ibapi import EClient, wrapper


class TestWrapper(wrapper.EWrapper):
    pass


class TestClient(EClient):
    def __init__(self, wrapper):
        EClient.__init__(self, wrapper)


class TestApp(TestWrapper, TestClient):
    def __init__(self):
        TestWrapper.__init__(self)
        TestClient.__init__(self, wrapper=self)
