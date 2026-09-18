list = [1,2,3,4]
it = iter(list)
print(next(it))
print(next(it))
print(*it, sep=',')


class Num:
    def __iter__(self):
        self.a = 1
        return self

    def __next__(self):
        if self.a > 20:
            raise StopIteration
        x = self.a
        self.a += 1
        return x


testN = Num()
testIter = iter(testN)
print(*testIter, sep=',')


def fibonacci(n):
    a, b, cnt = 0, 1, 0
    while True:
        if cnt > n:
            return
        yield a
        a, b = b, a + b
        cnt += 1


f = fibonacci(100000)
print(*f, sep=',')
