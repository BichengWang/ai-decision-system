import bisect


def saving_from_salary(salary):
    # tax: 40%, cost 30%
    return salary * 0.6 * 0.7


def calc_year_over_year_saving(annualRates, annualSalary):
    rst = 0.0
    print(len(annualRates))
    print(len(annualSalary))
    i = 0
    for r, w in zip(annualRates, annualSalary):
        i += 1
        rst += saving_from_salary(w)
        rst *= (1.0 + r / 100.0)
        print("year: {}, saving: {}".format(i, rst))
    bisect.bisect_left()
    return r


if __name__ == "__main__":
    print("beyond fang simulation:")
    calc_year_over_year_saving(
        [-27.4, 51.3, 16.2, 18.5, 31.6, 3.3, 3.0, 54.6, 33.4, 48.4, 297.7],
        range(170, 550, 40)
    )
    print("annual rate 30% simulation:")
    calc_year_over_year_saving(
        [40] * 10,
        range(170, 550, 40)
    )