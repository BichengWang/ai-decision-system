from collections import OrderedDict

def iterate():
    letters = OrderedDict({("a", 1), ("b", 2), ("c", 3)})
    for k, v in letters.items():
        print(k, v)
    for k, v in reversed(letters.items()):
        print(k, v)

def create_obj():
    numbers = OrderedDict()
    numbers["one"] = 1
    numbers["two"] = 2
    numbers["three"] = 3
    print(numbers)

    letters = OrderedDict({("a", 1), ("b", 2), ("c", 3)})
    print(letters)

    letters = OrderedDict(b=2, d=4, a=1, c=3)
    print(letters)


if __name__ == "__main__":
    create_obj()
    iterate()

