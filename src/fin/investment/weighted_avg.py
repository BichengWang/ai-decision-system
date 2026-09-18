def target_avg_buy_shares(curr_price, curr_shares, prev_cost, target_cost):
    """
    Calculate the weighted average price of a stock investment portfolio.

    Args:
        curr_price (float): Current price per share of the stock.
        curr_shares (int): Current number of shares held in the portfolio.
    """
    # (purchase_shares + curr_shares) * target_cost = prev_cost * curr_shares + curr_price * purchase_shares    
    # purchase_shares * target_cost + curr_shares * target_cost = prev_cost * curr_shares + curr_price * purchase_shares    
    # purchase_shares * (target_cost - curr_price) = prev_cost * curr_shares - curr_shares * target_cost
    purchase_shares = (prev_cost * curr_shares - curr_shares * target_cost) / (target_cost - curr_price)
    return purchase_shares


if __name__ == "__main__":
    print(target_avg_buy_shares(35., 2850, 61.23, 59.00))
