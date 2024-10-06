import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.propagate = True  # Propagate logs to the root logger


def calculate_current_value(cash_flow, annual_interest_rate=0.06, period_factor=52.):
    """
    Calculate the current value of a cash flow array using the Internal Rate of Return (IRR).

    Parameters:
    cash_flow (array-like): Array-like object containing cash flow values.
    annual_interest_rate (float): Annual interest rate used to discount cash flows.

    Returns:
    float: The current value of the cash flow array.
    """
    # Calculate the discount factor based on the annual interest rate
    discount_factor = 1. / (1. + annual_interest_rate/period_factor)

    # Calculate the current value using the IRR and discount factor
    current_value = 0
    for i, cash_flow_value in enumerate(cash_flow):
        current_value += cash_flow_value * (discount_factor ** i)

    return current_value


def calculate_future_value(cash_flow, annual_interest_rate=0.06, period_factor=52.):
    """
    Calculate the future value of a cash flow array.

    Parameters:
    cash_flow (array-like): Array-like object containing cash flow values.
    annual_interest_rate (float): Annual interest rate used to compound cash flows.
    num_periods (int): Number of periods into the future.

    Returns:
    float: The future value of the cash flow array.
    """

    # Calculate the future value using compound interest formula
    future_value = 0
    num_periods = len(cash_flow) - 1
    for i, cash_flow_value in enumerate(cash_flow):
        future_value += cash_flow_value * ((1 + annual_interest_rate / period_factor) ** (num_periods - i))

    return future_value

def generate_cash_flow(
        initial, 
        annual_investment, 
        years, 
        annual_growth_rate, 
        annual_risk_free_rate, 
        mode='weekly',
):
    factor = {'weekly': 52., 'monthly': 12., 'annual': 1.}[mode]
    income = annual_investment / factor
    cash_flow = [income * ((1. + annual_growth_rate / factor) ** i) for i in range(int(years * factor))]
    cash_flow[0] = initial
    pv = calculate_current_value(cash_flow, annual_interest_rate=annual_risk_free_rate, period_factor=factor)
    fv = calculate_future_value(cash_flow, annual_interest_rate=annual_risk_free_rate, period_factor=factor)
    logger.info({
        "pv": pv,
        "fv": fv,
    })
    return cash_flow, pv, fv


print(calculate_current_value([200, 100], annual_interest_rate=0.06))
print(calculate_future_value([100, 100]))
print(generate_cash_flow(initial=1000., annual_investment=120., years=30*52./52., annual_growth_rate=0.1, annual_risk_free_rate=0.05, mode='monthly'))