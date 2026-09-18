# https://treyhunner.com/2016/04/how-to-loop-with-indexes-in-python/


presidents = ["Washington", "Adams"]
colors = ["red", "green"]
ratios = [0.2, 0.3]


def list_for_loop():
    print("========list_for_loop========")
    for i in range(len(presidents)):
        print("President {}: {}".format(i + 1, presidents[i]))

    for i, color in enumerate(colors):
        print("{}% {}".format(i, color))

    for color, ratio in zip(colors, ratios):
        print("{}: {}".format(color, ratio))


a_dict = {'color': 'blue'}


def dict_for_loop():
    print("========dict_for_loop========")
    for a in a_dict:
        print(a, a_dict[a])

    for item in a_dict.items():
        print(item)

    for k, v in a_dict.items():
        print(k, v)

    #
    for k, v in zip(a_dict.keys(), a_dict.values()):
        print(k, v)

    # How to delete key in for loop
    for k in list(a_dict.keys()):
        if k == 'color':
            del a_dict[k]
    print(a_dict)


if __name__ == '__main__':
    list_for_loop()
    dict_for_loop()