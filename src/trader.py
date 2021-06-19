import pydash as py_
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

from src.bittrex import Bittrex
from src.messenger import Messenger
from src.database import Database
from src.logger import logger


class Trader(object):
    """
    Used for handling all trade functionality
    """
    operator = ""
    def __init__(self, secrets, settings, operator):
        self.trade_params = settings["tradeParameters"]
        self.pause_params = settings["pauseParameters"]

        self.Messenger = Messenger(secrets, settings)
        self.Database = Database()
        self.operator = operator(secrets)

    def initialise(self):
        """
        Fetch the initial coin pairs to track and to print the header line
        """
        try:
            if len(self.Database.app_data["coinPairs"]) < 1:
                self.Database.store_coin_pairs(self.get_markets("BTC"))
            self.Messenger.print_header(len(self.Database.app_data["coinPairs"]))
        except ConnectionError as exception:
            self.Messenger.print_error("connection", [], True)
            logger.exception(exception)
            exit()

    def analyse_buys(self):
        """
        Analyse all the un-paused coin pairs for buy signals and apply buys
        """
        trade_len = len(self.Database.trades["trackedCoinPairs"])
        pause_trade_len = len(self.Database.app_data["pausedTrackedCoinPairs"])
        if (trade_len < 1 or pause_trade_len == trade_len) and trade_len < self.trade_params["buy"]["maxOpenTrades"]:
            for coin_pair in self.Database.app_data["coinPairs"]:
                self.buy_strategy(coin_pair)

    def analyse_sells(self):
        """
        Analyse all the un-paused tracked coin pairs for sell signals and apply sells
        """
        for coin_pair in self.Database.trades["trackedCoinPairs"]:
            if coin_pair not in self.Database.app_data["pausedTrackedCoinPairs"]:
                self.sell_strategy(coin_pair)

    def buy_strategy(self, coin_pair):
        """
        Applies the buy checks on the coin pair and handles the results appropriately

        :param coin_pair: Coin pair market to check (ex: BTC-ETH, BTC-FCT)
        :type coin_pair: str
        """
        if (len(self.Database.trades["trackedCoinPairs"]) >= self.trade_params["buy"]["maxOpenTrades"] or
                coin_pair in self.Database.trades["trackedCoinPairs"]):
            return
        rsi = self.calculate_rsi(coin_pair=coin_pair, period=14, unit=self.trade_params["tickerInterval"])
        day_volume = self.get_current_24hr_volume(coin_pair)
        current_buy_price = self.get_current_price(coin_pair, "ask")

        if rsi is None:
            return

        if self.check_buy_parameters(rsi, day_volume, current_buy_price):
            buy_stats = {
                "rsi": rsi,
                "24HrVolume": day_volume
            }
            self.buy(coin_pair, self.trade_params["buy"]["btcAmount"], current_buy_price, buy_stats)
        elif "buy" in self.pause_params and rsi >= self.pause_params["buy"]["rsiThreshold"] > 0:
            self.Messenger.print_pause(coin_pair, [rsi, day_volume], self.pause_params["buy"]["pauseTime"], "buy")
            self.Database.pause_buy(coin_pair)
        else:
            self.Messenger.print_no_buy(coin_pair, rsi, day_volume, current_buy_price)

    def sell_strategy(self, coin_pair):
        """
        Applies the sell checks on the coin pair and handles the results appropriately

        :param coin_pair: Coin pair market to check (ex: BTC-ETH, BTC-FCT)
        :type coin_pair: str
        """
        if (coin_pair in self.Database.app_data["pausedTrackedCoinPairs"] or
                coin_pair not in self.Database.trades["trackedCoinPairs"]):
            return
        rsi = self.calculate_rsi(coin_pair=coin_pair, period=14, unit=self.trade_params["tickerInterval"])
        current_sell_price = self.get_current_price(coin_pair, "bid")
        profit_margin = self.Database.get_profit_margin(coin_pair, current_sell_price)

        if rsi is None:
            return

        if self.check_sell_parameters(rsi, profit_margin):
            sell_stats = {
                "rsi": rsi,
                "profitMargin": profit_margin
            }
            self.sell(coin_pair, current_sell_price, sell_stats)
        elif "sell" in self.pause_params and profit_margin <= self.pause_params["sell"]["profitMarginThreshold"] < 0:
            self.Messenger.print_pause(coin_pair, [profit_margin, rsi], self.pause_params["sell"]["pauseTime"], "sell")
            self.Database.pause_sell(coin_pair)
        else:
            self.Messenger.print_no_sell(coin_pair, rsi, profit_margin, current_sell_price)

    def buy(self, coin_pair, btc_quantity, price, stats, trade_time_limit=2):
        """
        Used to place a buy order to Bittrex. Wait until the order is completed.
        If the order is not filled within trade_time_limit minutes cancel it.

        :param coin_pair: String literal for the market (ex: BTC-LTC)
        :type coin_pair: str
        :param btc_quantity: The amount of BTC to buy with
        :type btc_quantity: float
        :param price: The price at which to buy
        :type price: float
        :param stats: The buy stats object
        :type stats: dict
        :param trade_time_limit: The time in minutes to wait fot the order before cancelling it
        :type trade_time_limit: float
        """
        buy_quantity = round(btc_quantity / price, 8)
        buy_data = self.operator.buy_limit(coin_pair, buy_quantity, price)
        if not buy_data["success"]:
            error_str = self.Messenger.print_error("buy", [coin_pair, buy_data["message"]])
            logger.error(error_str)
            return
        self.Database.store_initial_buy(coin_pair, buy_data["result"]["uuid"])

        buy_order_data = self.get_order(buy_data["result"]["uuid"], trade_time_limit * 60)
        self.Database.store_buy(buy_order_data["result"], stats)

        self.Messenger.print_buy(coin_pair, price, stats["rsi"], stats["24HrVolume"])
        self.Messenger.send_buy_telegram(coin_pair, stats["rsi"], stats["24HrVolume"])
        self.Messenger.send_buy_gmail(buy_order_data["result"], stats)
        self.Messenger.play_sw_imperial_march()

    def sell(self, coin_pair, price, stats, trade_time_limit=2):
        """
        Used to place a sell order to Bittrex. Wait until the order is completed.
        If the order is not filled within trade_time_limit minutes cancel it.

        :param coin_pair: String literal for the market (ex: BTC-LTC)
        :type coin_pair: str
        :param price: The price at which to buy
        :type price: float
        :param stats: The buy stats object
        :type stats: dict
        :param trade_time_limit: The time in minutes to wait fot the order before cancelling it
        :type trade_time_limit: float
        """
        trade = self.Database.get_open_trade(coin_pair)
        sell_data = self.operator.sell_limit(coin_pair, trade["quantity"], price)
        if not sell_data["success"]:
            error_str = self.Messenger.print_error("sell", [coin_pair, sell_data["message"]])
            logger.error(error_str)
            return

        sell_order_data = self.get_order(sell_data["result"]["Exchange"], sell_data["result"]["uuid"], trade_time_limit * 60)
        # TODO: Handle partial/incomplete sales.
        self.Database.store_sell(sell_order_data["result"], stats)

        self.Messenger.print_sell(coin_pair, price, stats["rsi"], stats["profitMargin"])
        self.Messenger.send_sell_telegram(coin_pair, stats["rsi"], stats["profitMargin"])
        self.Messenger.send_sell_gmail(sell_order_data["result"], stats)
        self.Messenger.play_sw_theme()

    def get_current(self, coin_pair, item):
        """
        Get current item for a coin pair. ex of response:
        
        [{'MarketName': 'USD-BTC', 
        'High': 61800.0, 'Low': 56103.07, 
        'Volume': 736.7149564, 'Last': 61293.493, 
        'BaseVolume': 43744317.6799586, 
        'TimeStamp': '2021-03-13T23:37:29.19', 
        'Bid': 61296.24, 'Ask': 61318.407, 
        'OpenBuyOrders': 7273, 'OpenSellOrders': 1447, 
        'PrevDay': 57359.66, 'Created': '2018-05-31T13:24:40.77'}]
        """
        coin_summary = self.operator.get_market_summary(coin_pair)
        if not coin_summary["success"]:
            error_str = self.Messenger.print_error("coinMarket", [coin_pair])
            logger.error(error_str)
            return None
        return coin_summary["result"][0][item]
    def get_current_price(self, coin_pair, price_type):
        """
        Gets current market price for a coin pair
        :param coin_pair: Coin pair market to check (ex: BTC-ETH, BTC-FCT)
        :type coin_pair: str
        :param price_type: The type of price to get (one of: 'ask', 'bid')
        :type price_type: str

        :return: Coin pair's current market price
        :rtype: float
        """
        coin_summary = self.operator.get_market_summary(coin_pair)
        if not coin_summary["success"]:
            error_str = self.Messenger.print_error("coinMarket", [coin_pair])
            logger.error(error_str)
            return None
        if price_type == "ask":
            print(coin_summary)
            return coin_summary["result"][0]["Ask"]
        if price_type == "bid":
            print(coin_summary)
            return coin_summary["result"][0]["Bid"]
        return coin_summary["result"][0]["Last"]
    
    def get_historical_prices(self, coin_pair, period = None, unit = None):
        """
        Returns closing prices within a specified time frame for a coin pair

        :param coin_pair: String literal for the market (ex: BTC-LTC)
        :type coin_pair: str
        :param period: Number of periods to query
        :type period: int
        :param unit: Ticker interval (one of: 'oneMin', 'fiveMin', 'thirtyMin', 'hour', 'week', 'day', and 'month')
        :type unit: str

        :return: Array of historical prices, array of signals
        :rtype: list, list
        """
        
        import warnings
        warnings.filterwarnings("ignore")
        if (period != None):
            period*=2
        df = self.operator.get_historical_data(coin_pair, period, unit)
        df = pd.DataFrame(df).rename(columns={
            'O':"Open", 
            "BV":"Base Volume",
            "C":"Close",
            "H":"High",
            "L":"Low",
            "T":"Datetime",
            "V":"Volume"
        })
        df.Datetime = pd.to_datetime(df.Datetime)
        df.Datetime = df.Datetime - timedelta(hours=3)
        df.loc[:,'Open'] = df[["Open"]].astype(float)
        df.loc[:,'Close'] = df[["Close"]].astype(float)
        df.loc[:,'High'] = df[["High"]].astype(float)
        df.loc[:,'Low'] = df[["Low"]].astype(float)
        df.loc[:,'Volume'] = df[["Volume"]].astype(float)
        period_short = "EMA9"
        period_long = "EMA26"
        df = self.get_EMA(df, period_short, period_long)
        if (period != None):
            df = df[-int(period):]
        df = df.reset_index(drop=True)
        df = df.sort_values(['Datetime'])
        df = self.get_willians_percent(self.max_14(self.min_14(df)))
        suportes, df = self.get_supports(df)
        resistencias, df = self.get_resistences(df)
        hammers, df = self.get_hammers(df)
        df = df.sort_values(['Datetime'], ascending=True)
        df = self.get_tendencia_alta_baixa_divergencia(df)
        return df, self.get_signals(df), hammers, suportes, resistencias
    def get_tendencia_alta_baixa_divergencia(self, df):
        df = df.sort_values(['Datetime'])
        df[['divergencia_alta']] = 0
        df[['divergencia_baixa']] = 0
        for i in range(2, len(df)):
            if ((df.loc[i-2, ['Low']][0]) > ((df.loc[i-1, ['Low']][0])) > (df.loc[i, ['Low']][0])):
                if ((df.loc[i-2, ['MACD_Histogram']][0]) < ((df.loc[i-1, ['MACD_Histogram']][0])) < (df.loc[i, ['MACD_Histogram']][0])):
                    if (df.loc[i, ['Support']][0] == 1 and df.loc[i, ['MACD']][0]<0):
                        df.loc[i,['divergencia_alta']] = 1
            if ((df.loc[i-2, ['High']][0]) < ((df.loc[i-1, ['High']][0])) < (df.loc[i, ['High']][0])):
                if ((df.loc[i-2, ['MACD_Histogram']][0]) > ((df.loc[i-1, ['MACD_Histogram']][0])) > (df.loc[i, ['MACD_Histogram']][0])):
                    df.loc[i,['divergencia_baixa']] = 1
        return df.sort_values(['Datetime'], ascending=True)
        
    def max_14(self, df):
        df['MAX_14'] = df['High'].rolling(14).max()
        return df

    def min_14(self, df):
        df['MIN_14'] = df['Low'].rolling(14).min()
        return df
    def get_willians_percent(self, df):
        df[['Willians_percent']] = ((df['MAX_14'] - df['Close'])/(df['MAX_14']-df['MIN_14']))*-100
        return df
    def get_hammers(self, df):
        hammers = []
        df[['Hammer']] = 0
        for i in range(2, len(df)):
            if ((df.iloc[i - 2].Close - df.iloc[i - 2].Open) < 0):
                if ((df.iloc[i - 1].Close - df.iloc[i - 1].Open) < 0):
                    if (((df.iloc[i].Open - df.iloc[i].Low) / (df.iloc[i].High - df.iloc[i].Low)) > 0.666):
                        if ((df.iloc[i].High - df.iloc[i].Low) > (2 * (df.iloc[i].Open - df.iloc[i].Close)) ):
                            hammers.append(df.iloc[i])
                            df.loc[i,['Hammer']] = 1
        return pd.DataFrame(hammers), df
    def get_supports(self, df):
        suportes = []
        df[["Support"]] = 0
        ref = len(df)-22
        for i in range(0, len(df)):
            sup0 = 0
            sup1 = 0
            sup2 = 0
            sup = 0
            if (i > 0 & i < ref):
                sup0 = (min((df.iloc[i-1:i+20][['Low']]).to_numpy())[0])
            if (i < ref):
                sup1 = (min((df.iloc[i:i+21][['Low']]).to_numpy())[0])
                sup2 = (min((df.iloc[i+1:i+22][['Low']]).to_numpy())[0])
                if (sup1 == sup2):
                    sup = sup1
                elif (sup0 != 0):
                    sup = sup0
                else:
                    sup = sup1
            else:
                sup1 = (min((df.iloc[i:len(df)][['Low']]).to_numpy())[0])
                sup2 = (min((df.iloc[i-1:len(df)][['Low']]).to_numpy())[0])
                sup = min(sup1, sup2)
            if (df.iloc[i][['Low']].to_numpy()[0] == sup):
                suportes.append(df.iloc[i])
                df.loc[i,['Support']] = 1
            #print(sup)
        return pd.DataFrame(suportes), df
    def get_resistences(self, df):
        Resistencia = []
        df[["Resistance"]] = 0
        ref = len(df)-22
        for i in range(0, len(df)):
            res0 = 0
            res1 = 0
            res2 = 0
            res = 0
            if (i > 0 & i < ref):
                res0 = (max((df.iloc[i-1:i+20][['High']]).to_numpy())[0])
            if (i < ref):
                res1 = (max((df.iloc[i:i+21][['High']]).to_numpy())[0])
                res1 = (max((df.iloc[i+1:i+22][['High']]).to_numpy())[0])
                if (res1 == res2):
                    res = res1
                elif (res0 != 0):
                    res = res0
                else:
                    res = res1
            else:
                res1 = (max((df.iloc[i:len(df)][['High']]).to_numpy())[0])
                res2 = (max((df.iloc[i-1:len(df)][['High']]).to_numpy())[0])
                res = max(res1, res2)
            if (df.iloc[i][['High']].to_numpy()[0] == res):
                Resistencia.append(df.iloc[i])
                df.loc[i,['Resistance']] = 1
            #print(res)
        return pd.DataFrame(Resistencia), df
    def get_EMA(self, df, period_short, period_long):
        df["EMA_Short"] = df.Close.ewm(span=int(period_short.replace("EMA","")), adjust=False).mean()
        df["EMA_Long"] = df.Close.ewm(span=int(period_long.replace("EMA","")), adjust=False).mean()
        df['MACD'] = df.Close.ewm(span=26, adjust=False).mean() - df.Close.ewm(span=12, adjust=False).mean()
        df['MACD_9'] = df.MACD.ewm(span=9, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD_9'] - df['MACD']
        df['MACD_Signal'] = ""
        for i in range(1,len(df["MACD_Signal"])):
            if (df.MACD[i] >= df.MACD_9[i]):
                df.MACD_Signal[i] = "Buy"
            elif (df.MACD[i] <= df.MACD_9[i]):
                df.MACD_Signal[i] = "Sell"
        df["Prev_MACD_Signal"] = df['MACD_Signal'].shift(1)
        for i in range(1,len(df["MACD_Signal"])):
            if (df.MACD_Signal[i] == df.Prev_MACD_Signal[i]):
                df.MACD_Signal[i] = ""
        df.MACD_Signal[0] = ""
        df.drop(columns="Prev_MACD_Signal", inplace=True)
        return df
    def get_signals(self, df):
        crossovers = pd.DataFrame()
        idx = df['Datetime']
        crossovers['Price'] = [i for i in df['Close']]
        crossovers["EMA_Short"] = df["EMA_Short"]
        crossovers["EMA_Long"] = df["EMA_Long"]
        crossovers['MACD_Signal'] = df['MACD_Signal']
        crossovers['position'] = crossovers["EMA_Short"] >= crossovers["EMA_Long"]
        crossovers.index = idx
        crossovers['pre-position'] = crossovers['position'].shift(1)
        crossovers['Crossover'] = np.where(crossovers['position'] == crossovers['pre-position'], False, True)
        crossovers = crossovers.reset_index()
        crossovers.Crossover[0] = False
        #print(crossovers)

        crossovers = crossovers.loc[crossovers['Crossover'] == True]
        crossovers = crossovers.reset_index()
        crossovers = crossovers.drop(['position', 'pre-position', 'Crossover'], axis=1)
        crossovers['Signal'] = np.nan
        crossovers['Binary_Signal'] = 0.0
        for i in range(len(crossovers["EMA_Short"])):
            if crossovers["EMA_Short"][i] > crossovers["EMA_Long"][i]:
                crossovers['Binary_Signal'][i] = 1.0
                crossovers['Signal'][i] = 'Sell'
            else:
                crossovers['Signal'][i] = 'Buy'
        
        crossovers = (crossovers[["Datetime","Price", "EMA_Short","Signal","MACD_Signal"]])
        return crossovers
    def get_closing_prices(self, coin_pair, period, unit):
        """
        Returns closing prices within a specified time frame for a coin pair

        :param coin_pair: String literal for the market (ex: BTC-LTC)
        :type coin_pair: str
        :param period: Number of periods to query
        :type period: int
        :param unit: Ticker interval (one of: 'oneMin', 'fiveMin', 'thirtyMin', 'hour', 'week', 'day', and 'month')
        :type unit: str

        :return: Array of closing prices and dates
        :rtype: list, list
        """
        historical_data = self.operator.get_historical_data(coin_pair, period, unit)
        #print(historical_data)
        closing_prices = []
        for i in historical_data:
            closing_prices.append(i["C"])
        dates = []
        for i in historical_data:
            dates.append(i["T"])
        return closing_prices, pd.to_datetime(dates) - timedelta(hours=3)

    def get_order(self, coin_pair, order_uuid, trade_time_limit):
        """
        Used to get an order from Bittrex by it's UUID.
        First wait until the order is completed before retrieving it.
        If the order is not completed within trade_time_limit seconds, cancel it.

        :param order_uuid: The order's UUID
        :type order_uuid: str
        :param trade_time_limit: The time in seconds to wait fot the order before cancelling it
        :type trade_time_limit: float

        :return: Order object
        :rtype: dict
        """
        start_time = time.time()
        if (self.operator._get_type()=="Binance"):
            order_data = self.operator.get_order(coin_pair, order_uuid)
        else:
            order_data = self.operator.get_order(order_uuid)
        while time.time() - start_time <= trade_time_limit and order_data["result"]["IsOpen"]:
            time.sleep(10)
            order_data = self.operator.get_order(order_uuid)

        if order_data["result"]["IsOpen"]:
            error_str = self.Messenger.print_error(
                "order", [order_uuid, trade_time_limit, order_data["result"]["Exchange"]]
            )
            logger.error(error_str)
            if order_data["result"]["Type"] == "LIMIT_BUY":
                self.operator.cancel(order_uuid)

        return order_data

    def calculate_rsi(self, coin_pair, period, unit):
        """
        Calculates the Relative Strength Index for a coin_pair
        If the returned value is above 75, it's overbought (SELL IT!)
        If the returned value is below 25, it's oversold (BUY IT!)

        :param coin_pair: String literal for the market (ex: BTC-LTC)
        :type coin_pair: str
        :param period: Number of periods to query
        :type period: int
        :param unit: Ticker interval (one of: 'oneMin', 'fiveMin', 'thirtyMin', 'hour', 'week', 'day', and 'month')
        :type unit: str

        :return: RSI
        :rtype: float
        """
        closing_prices = self.get_closing_prices(coin_pair, period * 3, unit)[0]
        count = 0
        change = []
        # Calculating price changes
        for i in closing_prices:
            if count != 0:
                change.append(i - closing_prices[count - 1])
            count += 1
            if count == 15:
                break
        # Calculating gains and losses
        advances = []
        declines = []
        for i in change:
            if i > 0:
                advances.append(i)
            if i < 0:
                declines.append(abs(i))
        average_gain = (sum(advances) / 14)
        average_loss = (sum(declines) / 14)
        new_avg_gain = average_gain
        new_avg_loss = average_loss
        for _ in closing_prices:
            if 14 < count < len(closing_prices):
                close = closing_prices[count]
                new_change = close - closing_prices[count - 1]
                add_loss = 0
                add_gain = 0
                if new_change > 0:
                    add_gain = new_change
                if new_change < 0:
                    add_loss = abs(new_change)
                new_avg_gain = (new_avg_gain * 13 + add_gain) / 14
                new_avg_loss = (new_avg_loss * 13 + add_loss) / 14
                count += 1

        if new_avg_loss == 0:
            return None

        rs = new_avg_gain / new_avg_loss
        new_rs = 100 - 100 / (1 + rs)
        return new_rs
