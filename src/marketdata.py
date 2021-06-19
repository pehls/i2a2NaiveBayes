import pandas as pd
import numpy as np
import yfinance as yf

class MarketData(object):
    """
    Used for requesting Binance with API key and API secret
    """
    client = ""
    api_key = ""
    api_secret = ""
    
    def __init__(self, secrets):
        _api_key = secrets["market.data"]["apiKey"]
        _api_secret = secrets["market.data"]["apiSecret"]
        self.api_key = str(_api_key) if _api_key is not None else ""
        self.api_secret = str(_api_secret) if _api_secret is not None else ""
        self.client = (_api_key, _api_secret)
    def get_historical_data(self, coin_pair, period=None, unit=None):
            """
            Get historical data from binance
            original format:
            [
                    [
                        1499040000000,      // Open time
                        "0.01634790",       // Open
                        "0.80000000",       // High
                        "0.01575800",       // Low
                        "0.01577100",       // Close
                        "148976.11427815",  // Volume
                        1499644799999,      // Close time
                        "2434.19055334",    // Quote asset volume
                        308,                // Number of trades
                        "1756.87402397",    // Taker buy base asset volume
                        "28.46694368",      // Taker buy quote asset volume
                        "17928899.62484339" // Ignore.
                  ]
                ]
            """

            df = yf.download(coin_pair,'2016-01-26').reset_index()
            df.Close = df['Adj Close']
            df['T'] = pd.to_datetime(df.Date)
            df['O'] = df[['Open']].astype(float)
            df['BV'] = df[['Volume']].astype(float)
            df['C'] = df[['Close']].astype(float)
            df['H'] = df[['High']].astype(float)
            df['L'] = df[['Low']].astype(float)
            df['V'] = df[['Volume']].astype(float)
            df = df[['T','O','BV','C','H','L','V']]
            return df.to_dict('records')