import random


def argv_func1(*argv):
    print(argv)
    print(sum(argv))


def argv_func2(arg1, *argv):
    print(arg1, argv)
    # parse multiple parameters as tuple
    print(sum((arg1, *argv)))


def kwargs_func1(**kwargs):
    # parse multiple parameters as tuple

    print(kwargs)
    print(sum(kwargs.values()))


def kwargs_func2(arg1, **kwargs):
    print(arg1, kwargs)
    print(sum((arg1, *kwargs.values())))


def kwargs_func3(a, b, c):
    print(a, b, c)
    print(sum([a, b, c]))


def args_kwargs(*args, **kwargs):
    print(args, kwargs)
    print(sum((*args, *kwargs.values())))


def matrix_transfer(m):
    print(m)
    print([list(col) for col in zip(*m)])


class StandardArgsKwargs:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        
    def print_args(self):
        print("Args:", self.args)
        print("Kwargs:", self.kwargs)
        
    def get_sum(self):
        return sum((*self.args, *self.kwargs.values()))


if __name__ == '__main__':
    argv_func1(1, 2, 3)
    argv_func2(1, 2, 3)
    kwargs_func1(a=1, b=2, c=3)
    kwargs_func2(1, b=2, c=3)
    kwargs = {'a': 1, 'b': 2, 'c': 3}
    kwargs_func3(**kwargs)
    args_kwargs(1, 2, c=3)
    matrix_transfer([[1, 2, 3], [4, 5, 6]])
    standard_args_kwargs = StandardArgsKwargs(1, 2, 3, a=4, b=5, c=6)
    standard_args_kwargs.print_args()
    print(standard_args_kwargs.get_sum())
