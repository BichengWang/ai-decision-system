from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int):
        self.cap = capacity
        self.cache = OrderedDict()

    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1
        val = self.cache.get(key)
        self.cache.move_to_end(key, last=False)
        return val

    def put(self, key:int, val: int) -> None:
        if key in self.cache:
            del self.cache[key]
        self.cache[key] = val
        if len(self.cache) > self.cap:
            self.cache.popitem(last=True)


if __name__ == "__main__":
    c = LRUCache(2)
    print(c.put(1,1))
    print(c.put(2,2))
    print(c.get(1))
    print(c.put(3,3))
    print(c.get(2))
    print(c.put(4,4))
    print(c.get(1))
    print(c.get(3))
    print(c.get(4))
