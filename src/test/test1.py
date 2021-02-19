if __name__ == '__main__':
    random = [(2, 2), (3, 4), (4, 1), (1, 3)]
    random.sort(key=lambda a: a[1])
    random.sort(key=lambda x: x[0] ** 2 + x[1])
    sorted(random, key=lambda x: x[0], reverse=True)
    print(random)
