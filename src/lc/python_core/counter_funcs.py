from collections import Counter


def counter_arithmetic():
    sales_day1 = Counter(apple=4, orange=9, banana=10)
    sales_day2 = Counter({'apple': 10, 'orange': 8, 'banana': 2})
    print("sales_day1", sales_day1)
    print("sales_day2", sales_day2)
    print("sales_day1 + sales_day2", sales_day1 + sales_day2)
    print("sales_day1 - sales_day2", sales_day1 - sales_day2)
    print("sales_day1 & sales_day2", sales_day1 & sales_day2)
    print("sales_day1 | sales_day2", sales_day1 | sales_day2)


def counter_unary_operation():
    counter = Counter(a=2, b=-4, c=0)
    print("+counter", +counter)
    print("-counter", -counter)


def counter_funcs():
    counter = Counter({2: 2, 3: 3, 17: 1})
    print("elements(): ", list(counter.elements()))


if __name__ == "__main__":
    counter_arithmetic()
    counter_unary_operation()
    counter_funcs()
