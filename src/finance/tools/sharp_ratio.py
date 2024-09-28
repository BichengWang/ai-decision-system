def sharp_ratio(returns, risk_free_rate):
    """
    Calculate the Sharp ratio of a series of returns.

    Parameters
    ----------
    returns : pd.Series
        The returns of the asset.
    risk_free_rate : float
        The risk-free rate.

    Returns
    -------
    float
        The Sharp ratio.
    """
    return (returns.mean() - risk_free_rate) / returns.std()

