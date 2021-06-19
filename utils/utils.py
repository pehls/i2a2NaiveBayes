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
def get_secrets():
    secrets_file_directory = "./database/secrets.json"
    secrets_template = {
        "bittrex": {
            "bittrexKey": "BITTREX_API_KEY",
            "bittrexSecret": "BITTREX_SECRET"
        },
        "gmail": {
            "recipientName": "Folks",
            "addressList": [
                "EXAMPLE_RECIPIENT_1@GMAIL.COM",
                "EXAMPLE_RECIPIENT_2@GMAIL.COM",
                "ETC..."
            ],
            "username": "EXAMPLE_EMAIL@GMAIL.COM",
            "password": "GMAIL_PASSWORD"
        },
        "telegram": {
            "channel": "telegram_CHANNEL",
            "token": "telegram_TOKEN"
        }
    }
    secrets_content = get_json_from_file(secrets_file_directory, secrets_template)
    if secrets_content == secrets_template:
        print("Please completed the `secrets.json` file in your `database` directory")
        exit()

    return secrets_content


def get_settings():
    settings_file_directory = "./database/settings.json"
    settings_template = {
        "sound": False,
        "tradeParameters": {
            "tickerInterval": "TICKER_INTERVAL",
            "buy": {
                "btcAmount": 0,
                "rsiThreshold": 0,
                "24HourVolumeThreshold": 0,
                "minimumUnitPrice": 0,
                "maxOpenTrades": 0
            },
            "sell": {
                "lossMarginThreshold": 0,
                "rsiThreshold": 0,
                "minProfitMarginThreshold": 0,
                "profitMarginThreshold": 0
            }
        },
        "pauseParameters": {
            "buy": {
                "rsiThreshold": 0,
                "pauseTime": 0
            },
            "sell": {
                "profitMarginThreshold": 0,
                "pauseTime": 0
            },
            "balance": {
                "pauseTime": 0
            }
        }
    }
    settings_content = get_json_from_file(settings_file_directory, settings_template)
    if settings_content == settings_template:
        print("Please completed the `settings.json` file in your `database` directory")
        #exit()
        return settings_content

    return settings_content

def generate_graph(df, crossovers):
    INCREASING_COLOR = '#3D9970'
    DECREASING_COLOR = '#FF4136'

    df.index = df.Datetime

    fig = make_subplots(rows=4, cols=1)
    fig = fig.add_trace(go.Candlestick(x=df.index,
                                       open=df['Open'],
                                       high=df['High'],
                                       low=df['Low'],
                                       close=df['Close']),
                        row=1, col=1
                       )
    fig = fig.update_layout(xaxis_rangeslider_visible=False, xaxis={'visible':False, 'showticklabels':False})
    # volume bar chart

    colors = []

    for i in range(len(df.Close)):
        if i != 0:
            if df.Close[i] > df.Close[i-1]:
                colors.append(INCREASING_COLOR)
            else:
                colors.append(DECREASING_COLOR)
        else:
            colors.append(DECREASING_COLOR)


    # add vol to graph
    fig.add_trace(
        go.Bar(x=df.index, y=df.Volume,
               marker=dict(color=colors),#
               name='Volume'),
        row=2, col=1

    )
    
    fig = fig.update_layout(xaxis={'visible':False, 'showticklabels':False}, yaxis={'visible':False, 'showticklabels':False})
    
    colors_macd = []

    for i in range(len(df.MACD)):
        if i != 0:
            if df.MACD[i] > df.MACD[i-1]:
                colors_macd.append(INCREASING_COLOR)
            else:
                colors_macd.append(DECREASING_COLOR)
        else:
            colors_macd.append(DECREASING_COLOR)
    # add MACD to graph
    #fig.add_trace(
    #    go.Scatter(x=df.index, y=df.MACD,
    #           marker=dict(color=colors_macd),#
    #           name='MACD'),
    #    row=3, col=1)
    # add 12-EMA
    fig.add_trace(
        go.Scatter(x=df.index, y=df.EMA_Short,#
               name='EMA_Short'),
        row=3, col=1

    )
    # add 26-EMA
    fig.add_trace(
        go.Scatter(x=df.index, y=df.EMA_Long,#
               name='EMA_Long'),
        row=3, col=1

    )
    
    # add buy&sell markers
    fig.add_trace(
        go.Scatter(mode="markers",x=crossovers.Datetime, y=crossovers.EMA_Short, 
               marker_symbol = [(_sygnal_marker.get(x)) for x in crossovers['Signal']],
               marker_color = [(_sygnal_color.get(x)) for x in crossovers['Signal']],
               marker_size=15, name="Buy/Sell"
              ),
        row=3, col=1
    )
    fig = fig.update_layout(xaxis={'visible':False, 'showticklabels':False}, yaxis={'visible':False, 'showticklabels':False})
    
    # add MACD markers
    fig.add_trace(
        go.Scatter(x=df.Datetime, y=df.MACD, 
               marker=dict(color="black"), name='MACD'
              ),
        row=4, col=1
    )
    fig.add_trace(
        go.Scatter(x=df.Datetime, y=df.MACD_7, 
               marker=dict(color="blue")
              ),
        row=4, col=1
    )
    fig = fig.update_layout(yaxis={'visible':False, 'showticklabels':False})
    
    fig.show()
    