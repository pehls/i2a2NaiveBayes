from src.logger import logger
from src.directory_utilities import get_json_from_file
from src.database import Database
from src.bittrex import Bittrex
from src.trader import Trader
import utils.utils
from datetime import datetime, timedelta

import plotly.graph_objects as go

from plotly.subplots import make_subplots

import logging
import pandas as pd
import numpy as np

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)
class Botche(object):
    def __init__(self, bittrex):
        self.bittrex = bittrex
        

    def get_markets(self, main_market_filter=None):
        """
        Gets all the Bittrex markets and filters them based on the main market filter

        :param main_market_filter: Main market to filter on (ex: BTC, ETH, USDT)
        :type main_market_filter: str

        :return: All Bittrex markets (with filter applied, if any)
        :rtype: list
        """
        markets = self.bittrex.get_markets()
        if not markets["success"]:
            error_str = print("market", True)
            logger.error(error_str)
            exit()

        markets = markets["result"]
        #return markets
        markets = list(map(lambda item: (item['MarketName']), markets))
        if main_market_filter is not None:
            market_check = main_market_filter + "-"
            markets = list(filter(lambda market: market_check in market, markets))
        return markets
    def analyze_just_price():
        _prev_day = _trader.get_current(_crypto, 'PrevDay')
        _last = _trader.get_current(_crypto, 'Last')
        _volume = _trader.get_current(_crypto, 'Volume')
        _high = _trader.get_current(_crypto, 'High')
        _low = _trader.get_current(_crypto, 'Low')
        _ask_venda = _trader.get_current(_crypto, 'Ask')
        _bid_compra = _trader.get_current(_crypto, 'Bid')
        _percent_ = round((1 - (_prev_day / _last)) * 100,2)
        return ("High: $"+str(_high)
                +"\nLow: $" + str(_low) 
                +"\nLast: $" + str(_last) 
                +"\nVolume: " + str(_volume) 
                +"\nDia Anterior: $" + str(_prev_day)
                +"\nPercentual: " + str(_percent_) + "%")
    def analyze_5min():
        prices, dates = _trader.get_closing_prices(_crypto, 12, 'fiveMin')
        _12_avg = sum(prices) / len(prices)

        prices, dates = _trader.get_closing_prices(_crypto, 26, 'fiveMin')
        _26_avg = sum(prices) / len(prices)

        _26subt12 = _26_avg - _12_avg

        df = pd.DataFrame([prices, dates], index=["Price",'Date']).transpose()
        df.Date = pd.to_datetime(df.Date)

        return ("Média 12: $"+str(_12_avg)
                +"\nMédia 26: $"+str(_26_avg)
                +"\nMACD: $"+str(_26subt12)), df
    def analyze_30min():
        prices, dates = _trader.get_closing_prices(_crypto, 12, 'thirtyMin')
        _12_avg = sum(prices) / len(prices)

        prices, dates = _trader.get_closing_prices(_crypto, 26, 'thirtyMin')
        _26_avg = sum(prices) / len(prices)

        _26subt12 = _26_avg - _12_avg

        df = pd.DataFrame([prices, dates], index=["Price",'Date']).transpose()
        df.Date = pd.to_datetime(df.Date)

        return ("Média 12: $"+str(_12_avg)
                +"\nMédia 26: $"+str(_26_avg)
                +"\nMACD: $"+str(_26subt12)), df
    def analyze_hour():
        prices, dates = _trader.get_closing_prices(_crypto, 12, 'hour')
        _12_avg = sum(prices) / len(prices)

        prices, dates = _trader.get_closing_prices(_crypto, 26, 'hour')
        _26_avg = sum(prices) / len(prices)

        _26subt12 = _26_avg - _12_avg

        df = pd.DataFrame([prices, dates], index=["Price",'Date']).transpose()
        df.Date = pd.to_datetime(df.Date)

        return ("Média 12: $"+str(_12_avg)
                +"\nMédia 26: $"+str(_26_avg)
                +"\nMACD: $"+str(_26subt12)), df

    global _analyzer   
    _analyzer = {
        'Apenas o \nPreço/volume' : analyze_just_price,
        'Últimos \n5 min' : analyze_5min,
        'Últimos \n30 min' : analyze_30min,
        'Última Hora' : analyze_hour
    }

    def _format_priceDate(Price, Date):
        return ("Data/Hora: " + Date + " | Preço (Fech): $"+ Price)

    _sygnal_marker = {
        "Buy":"triangle-up",
        "Sell":"triangle-down"
    }
    _sygnal_color = {
        "Buy":"green",
        "Sell":"red"
    }
    
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
    )

    logger = logging.getLogger(__name__)

    CRYPTO, TYPE,END = range(3)

    def start(update: Update, _: CallbackContext) -> int:
        update.message.reply_text(
            'Olá, que moeda vamos analisar agora? (formato: $coin-$pair)',
            reply_markup=ReplyKeyboardRemove(),
        )

        return TYPE

    def _type(update: Update, _: CallbackContext) -> int:
        reply_keyboard = [['Apenas o \nPreço/volume', 'Últimos \n5 min','Últimos \n30 min','Última Hora']]
        global _crypto
        _crypto = update.message.text
        print(_crypto)
        user = update.message.from_user

        update.message.reply_text(
            'Show, e qual período? (Agora, 5min, 30min, hour)?',
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
        )

        return END

    def the_end(update: Update, _: CallbackContext) -> int:
        global _item
        _item = update.message.text
        print(_crypto + " |" + _item)
        if (_item=='Apenas o Preço/volume'):
            update.message.reply_text(_analyzer.get(_item)())
        else:
            _str_formatada, df = _analyzer.get(_item)()
            update.message.reply_text(_str_formatada)
            update.message.reply_text("Valores:\n")
            [update.message.reply_text(str) for str in [_format_priceDate("$"+str(x[1]['Price']), str(x[1]['Date'])) for x in df.iterrows()]]
        update.message.reply_text('- END -')
        return ConversationHandler.END
    
    def cancel(update: Update, _: CallbackContext) -> int:
        user = update.message.from_user
        logger.info("User %s canceled the conversation.", user.first_name)
        update.message.reply_text(
            'Bye! I hope we can talk again some day.', reply_markup=ReplyKeyboardRemove()
        )

        return ConversationHandler.END


    def main() -> None:
        # Create the Updater and pass it your bot's token.
        updater = Updater(bot_token)

        # Get the dispatcher to register handlers
        dispatcher = updater.dispatcher

        # Add conversation handler with the states GENDER, PHOTO, LOCATION and BIO
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                TYPE: [MessageHandler(Filters.text, _type)],
                END: [MessageHandler(Filters.text, the_end)]
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        dispatcher.add_handler(conv_handler)

        # Start the Bot
        updater.start_polling()

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        updater.idle()


    if __name__ == '__main__':
        main()