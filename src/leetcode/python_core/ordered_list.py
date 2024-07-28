from sortedcontainers import SortedList, SortedSet, SortedDict


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
    sorted_list = SortedList([1, 3, 2, 4])
    print(sorted_list)
    sorted_set = SortedSet([1, 3, 2, 4])
    print(sorted_set)
    sorted_dict = SortedDict({1: 3, 3: 1, 2: 4, 4: 2})
    sorted_dict.bisect_key_left
    print(sorted_dict)
    
