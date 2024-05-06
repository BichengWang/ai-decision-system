from sortedcontainers import SortedList
from sortedcontainers import SortedDict


def iterate():
    letters = SortedDict({("a", 1), ("b", 2), ("c", 3)})
    for k, v in letters.items():
        print(k, v)
    for k, v in reversed(letters.items()):
        print(k, v)


def create_obj():
    numbers = SortedDict()
    numbers["one"] = 1
    numbers["two"] = 2
    numbers["three"] = 3
    print(numbers)

    letters = SortedDict({("a", 1), ("b", 2), ("c", 3)})
    print(letters)

    letters = SortedDict(b=2, d=4, a=1, c=3)
    print(letters)


if __name__ == "__main__":
    create_obj()
    iterate()
    for i in "ab1 c":
        print(i.islower())
