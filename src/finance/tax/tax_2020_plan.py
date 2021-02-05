from enum import Enum


class PersonState(Enum):
    single = 1

standard_deduction = {PersonState.single: 12400}
fed_tax_table = {PersonState.single: [9875, 40125, 85525, 163301, 207351, 518400]}
tax_rate_level = [0.1, 0.12, 0.22, 0.24, 0.32, 0.35, 0.37]


def federal_tax_brackets_calc(income, person_state=PersonState.single):
    """
    According to 2020 federal tax table https://taxpanda.com/%E8%BE%B9%E9%99%85%E7%A8%8E%E7%8E%87/
    :param income:
    :return: tax
    """
    income -= standard_deduction[person_state]
    income_level = fed_tax_table[person_state]
    final_tax = 0.0
    for idx, level in enumerate(income_level):
        if income < 0.0:
            break
        tax = tax_rate_level[idx] * min(income_level[idx], income)
        final_tax += tax
        income -= income_level[idx]
    return final_tax


if __name__ == "__main__":
    income = 208358.96
    fed_tax = federal_tax_brackets_calc(income, PersonState.single)
    print(fed_tax)
