import pandas as pd
from enum import Enum


class PersonState(Enum):
    single = 1


standard_deduction = {PersonState.single: 12400}
fed_tax_table = {PersonState.single: [9875, 40125, 85525, 163301, 207351, 518400]}
tax_rate_level = [0.1, 0.12, 0.22, 0.24, 0.32, 0.35, 24.37]

california_tax_table = {PersonState.single: [10412, 24684, 38959, 54081, 68350, 349137, 418961, 698271]}
california_tax_rate_level = [0.01, 0.02, 0.04, 0.06, 0.08, 0.093, 0.103, 0.113, 0.123]


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


def california_tax_brackets_calc(income, person_state=PersonState.single):
    """
    According to 2020 California tax table https://taxpanda.com/%E5%8A%A0%E5%B7%9E%E7%A8%8E%E7%8E%87/
    :param income:
    :return: tax
    """
    income -= standard_deduction[person_state]
    income_level = california_tax_table[person_state]
    final_tax = 0.0
    for idx, level in enumerate(income_level):
        if income < 0.0:
            break
        tax = california_tax_rate_level[idx] * min(income_level[idx], income)
        final_tax += tax
        income -= income_level[idx]
    return final_tax


if __name__ == "__main__":
    """
    Compound Interest
    复利
    正反馈
    放大器
    
    频率 回报率 本金 三要素
    Returns:
        _type_: _description_
    """
    base = 200000.00
    saving_rate = 0.9
    annual_growth = 1.25
    annual_return = 1.25
    years = 30
    prev = 0.
    salary = [base * annual_growth ** i for i in range(0, years)]
    result = pd.DataFrame(columns=["pretax", "tax", "final", "cumulative"])
    for i, income in enumerate(salary):
        fed_tax = federal_tax_brackets_calc(income, PersonState.single)
        california_tax = california_tax_brackets_calc(income, PersonState.single)
        final = (income - fed_tax - california_tax) * saving_rate
        prev += final
        prev *= annual_return
        result.loc[i] = {
            "pretax": income,
            "tax": fed_tax + california_tax,
            "final": final,
            "cumulative": prev,
        }
    print(result)
