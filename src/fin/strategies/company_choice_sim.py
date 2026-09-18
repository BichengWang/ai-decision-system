import numpy as np
import yfinance as yf
from datetime import datetime

# Download QQQ data
end_date = datetime.today()
start_date = datetime(end_date.year - 10, end_date.month, end_date.day)
qqq_data = yf.download("QQQ", start=start_date, end=end_date, progress=False)
qqq_annual = qqq_data['Adj Close'].resample('Y').last()
qqq_returns = qqq_annual.pct_change().dropna().values  # annual return rates

# Simulation parameters
vesting_years = 4
start_rsu_value = 100
prob_up = 0.5
growth_up = 1.30
growth_down = 0.85
simulations = 10000

# Run simulation
final_values = []

for _ in range(simulations):
    qqq_account = 0.0
    startup_states = []

    for year in range(min(10, len(qqq_returns))):
        # Join new startup each year
        startup_states.append({
            'vest_value': start_rsu_value,
            'years_remaining': vesting_years,
            'active': True,
            'last_move_up': False
        })

        yearly_vest = 0

        # Simulate vesting for all startups
        for startup in startup_states:
            if startup['years_remaining'] > 0 and startup['active']:
                move_up = np.random.rand() < prob_up
                startup['vest_value'] *= growth_up if move_up else growth_down
                if not move_up and startup['last_move_up']:
                    startup['active'] = False
                if move_up:
                    startup['last_move_up'] = True

                yearly_vest += startup['vest_value'] / vesting_years
                startup['years_remaining'] -= 1

        # Sell vested RSU and invest into QQQ
        qqq_account += yearly_vest
        qqq_account *= (1 + qqq_returns[year])  # simulate QQQ growth

    final_values.append(qqq_account)

# Print expected value
expected_reward = np.mean(final_values)
print(f"Expected total reward (RSUs sold yearly & invested in QQQ): ${expected_reward:.2f}")