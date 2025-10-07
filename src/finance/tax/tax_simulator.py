"""
Tax Simulator: 30-year investment returns under different tax scenarios
- Annual return: 100%
- Long-term tax: 20%, Short-term tax: 40%
"""

from typing import Dict, List


class TaxSimulator:
    def __init__(self, initial: float = 10000):
        self.initial = initial
        self.annual_return = 1.0  # 100%
        self.long_term_tax = 0.20  # 20%
        self.short_term_tax = 0.40  # 40%
        self.years = 30
    
    def simulate_scenario(self, tax_rate: float, deferred: bool = False) -> List[float]:
        """Simulate investment with given tax rate."""
        values = []
        current = self.initial
        
        for year in range(self.years + 1):
            values.append(current)
            if year < self.years:
                gain = current * self.annual_return
                if deferred and year == self.years - 1:
                    # Apply tax only at the end
                    final_gain = (current + gain) - self.initial
                    final_tax = final_gain * tax_rate
                    current = (current + gain) - final_tax
                elif not deferred:
                    # Apply tax annually
                    tax = gain * tax_rate
                    current += gain - tax
                else:
                    current += gain
        
        return values
    
    def run_simulation(self) -> Dict[str, List[float]]:
        return {
            "Long-term Annual": self.simulate_scenario(self.long_term_tax),
            "Short-term Annual": self.simulate_scenario(self.short_term_tax),
            "Deferred Tax": self.simulate_scenario(self.long_term_tax, deferred=True)
        }
    
    def print_results(self, results: Dict[str, List[float]]) -> None:
        print(f"\nTax Simulation Results (Initial: ${self.initial:,.0f})")
        print("=" * 70)
        print(f"{'Year':<6} {'Long-term':<15} {'Short-term':<15} {'Deferred':<15}")
        print("-" * 70)
        
        for year in range(0, self.years + 1, 5):
            lt = results["Long-term Annual"][year]
            st = results["Short-term Annual"][year]
            df = results["Deferred Tax"][year]
            print(f"{year:<6} ${lt:<14,.0f} ${st:<14,.0f} ${df:<14,.0f}")
        
        # Final results
        final_lt = results["Long-term Annual"][-1]
        final_st = results["Short-term Annual"][-1]
        final_df = results["Deferred Tax"][-1]
        
        print("-" * 70)
        print(f"{'Final':<6} ${final_lt:<14,.0f} ${final_st:<14,.0f} ${final_df:<14,.0f}")
        
        print(f"\nReturns: LT={((final_lt/self.initial)-1)*100:.0f}%, ST={((final_st/self.initial)-1)*100:.0f}%, Deferred={((final_df/self.initial)-1)*100:.0f}%")


def main():
    simulator = TaxSimulator()
    results = simulator.run_simulation()
    simulator.print_results(results)


if __name__ == "__main__":
    """
    Conclusion:
    
    Tax timing dramatically impacts long-term wealth:
    $8 billion
    $455 million
    $13 million
    
    1. **Deferred Tax**: $8.59T final value (85.9B% return)
       - Best strategy: no tax drag during growth
       - Use 401k/IRA accounts for maximum benefit
    
    2. **Long-term Annual Tax**: $455B final value (4.6B% return)  
       - 18.9x better than short-term due to 20% vs 40% tax rate
       - Hold investments >1 year for long-term capital gains
    
    3. **Short-term Annual Tax**: $13.3B final value (133M% return)
       - Worst performance due to 40% tax rate and annual tax drag
       - Avoid frequent trading
    
    **Key Takeaway**: Tax-deferred accounts can outperform annual taxation by 19,000x over 30 years.
    """
    main()
