import os
import time
import itertools
import traceback
import asyncio
import ccxt.pro as ccxtpro
from typing import Dict, Tuple
from collections import defaultdict


params = {
    "enableRateLimit": True,
    "proxies": {
        "http": os.getenv("http_proxy"),
        "https": os.getenv("https_proxy"),
    },
    "aiohttp_proxy": os.getenv("http_proxy"),
    "ws_proxy": os.getenv("http_proxy"),
}


def create_exchange(name):
    return getattr(ccxtpro, name)(params)


class SpreadMonitorBase:
    def __init__(self, market_a, market_b, symbols=None, quote_currency="USDT"):
        self.exchange_a_name, self.type_a, self.subtype_a = self.parse_market(market_a)
        self.exchange_b_name, self.type_b, self.subtype_b = self.parse_market(market_b)

        self.exchange_a: ccxtpro.Exchange = create_exchange(self.exchange_a_name)
        self.exchange_b: ccxtpro.Exchange = create_exchange(self.exchange_b_name)

        if symbols is not None:
            self.symbols = symbols
            self.quote_currency = None
        else:
            self.quote_currency = quote_currency

        self.symbol_map = defaultdict(dict)
        self.pair_data: Dict[Tuple[str, str], dict] = {}
        self.monitor_tasks = []
        self.running = False

        self.latencies = defaultdict(dict)

    async def sync_time(self, exchange: ccxtpro.Exchange):
        while self.running:
            try:
                start_time = time.time() * 1000
                server_time = await exchange.fetch_time()
                end_time = time.time() * 1000

                rtt = end_time - start_time
                latency = rtt / 2
                time_diff = end_time - (server_time + latency)

                self.latencies[exchange.name.lower()] = {
                    "latency": latency,
                    "time_diff": time_diff,
                }
            except Exception as e:
                print(f"Excpetion: {traceback.format_exc()}")
            await asyncio.sleep(10)

    def parse_market(self, market):
        market_params = market.split(".")
        if len(market_params) == 2:
            exchange_name, type_ = market_params
            return exchange_name, type_, None
        elif len(market_params) == 3:
            exchange_name, type_, subtype = market_params
            return exchange_name, type_, subtype
        else:
            raise ValueError(
                "Market parameter must match format as follows:"
                "\t- <exchange>.<type> (e.g. binance.spot)"
                "\t- <exchange>.<type>.<subtype> (e.g. okx.swap.linear)"
            )

    async def load_markets(self):
        await self.exchange_a.load_markets()
        await self.exchange_b.load_markets()

        def format_markets(markets, type_, subtype):
            new_markets = defaultdict(list)
            for m in markets.values():
                if (
                    m["type"] == type_
                    and (subtype is None or m[subtype])
                    and (
                        m["quote"] == self.quote_currency
                        or (
                            self.quote_currency is None
                            and f"{m['base']}-{m['quote']}" in self.symbols
                        )
                    )
                ):
                    new_markets[m["base"], m["quote"]].append(m["symbol"])
            return new_markets

        markets_a = format_markets(self.exchange_a.markets, self.type_a, self.subtype_a)
        markets_b = format_markets(self.exchange_b.markets, self.type_b, self.subtype_b)

        keys = set(markets_a.keys()).intersection(set(markets_b.keys()))
        pairs = [
            {
                "base": base,
                "quote": quote,
                "symbols_a": markets_a[(base, quote)],
                "symbols_b": markets_b[(base, quote)],
            }
            for base, quote in keys
        ]
        self.symbol_map = self._build_symbol_map(pairs)

    def _build_symbol_map(self, pairs):
        symbol_map = defaultdict(dict)
        for pair in pairs:
            for symbol_a, symbol_b in itertools.product(
                pair["symbols_a"], pair["symbols_b"]
            ):
                pair_name = f"{symbol_a}-{symbol_b}"
                if symbol_a not in symbol_map["a"]:
                    symbol_map["a"][symbol_a] = {
                        "index": "a",
                        "pair_names": [pair_name],
                    }
                else:
                    symbol_map["a"][symbol_a]["pair_names"].append(pair_name)
                if symbol_b not in symbol_map["b"]:
                    symbol_map["b"][symbol_b] = {
                        "index": "b",
                        "pair_names": [pair_name],
                    }
                else:
                    symbol_map["b"][symbol_b]["pair_names"].append(pair_name)
        return symbol_map

    async def monitor(self, exchange, index, symbols):
        raise NotImplementedError("Method is not implemented")

    def top(self, n):
        data = list(self.pair_data.values())
        return sorted(data, key=lambda x: x["spread_pct"], reverse=True)[
            : min(n, len(data))
        ]

    def start(self):
        self.running = True

        batch_size = 50
        a_symbols = list(self.symbol_map["a"].keys())
        b_symbols = list(self.symbol_map["b"].keys())
        self.monitor_tasks = [
            asyncio.create_task(self.sync_time(self.exchange_a)),
            asyncio.create_task(self.sync_time(self.exchange_b)),
            *[
                asyncio.create_task(
                    self.monitor(self.exchange_a, "a", a_symbols[i : i + batch_size])
                )
                for i in range(0, len(a_symbols), batch_size)
            ],
            *[
                asyncio.create_task(
                    self.monitor(self.exchange_b, "b", b_symbols[i : i + batch_size])
                )
                for i in range(0, len(b_symbols), batch_size)
            ],
        ]

    async def stop(self):
        """优雅关闭"""
        self.running = False
        for task in self.monitor_tasks:
            task.cancel()
        try:
            await asyncio.gather(*self.monitor_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass

        await self.exchange_a.close()
        await self.exchange_b.close()


class TickerSpreadMonitor(SpreadMonitorBase):
    async def monitor(self, exchange, index: str, symbols):
        """
        统一监控方法
        :param exchange: 交易所实例
        :param index: 来源索引 ('a'或'b')
        """
        exchange_name = exchange.name.lower()
        while self.running:
            try:
                tickers = await exchange.watch_tickers(symbols)
                for symbol, ticker in tickers.items():
                    await self.process_ticker(
                        symbol,
                        ticker,
                        index,
                        self.latencies[exchange_name].get("time_diff", 0),
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Excpetion({index}): {str(e)}")
                await asyncio.sleep(5)

    async def process_ticker(self, symbol, ticker, index, time_diff):
        if symbol not in self.symbol_map[index]:
            return

        pair_map = self.symbol_map[index][symbol]
        pair_names = pair_map["pair_names"]
        for pair_name in pair_names:
            if pair_name not in self.pair_data:
                self.pair_data[pair_name] = {
                    "pair_name": pair_name,
                    "spread": 0,
                    "spread_pct": 0,
                    "price_a": 0,
                    "price_b": 0,
                    "elapsed_time_a": 0,
                    "elapsed_time_b": 0,
                }
            self.pair_data[pair_name][f"price_{index}"] = ticker["last"]
            self.pair_data[pair_name][f"elapsed_time_{index}"] = time.time() * 1e3 - (
                ticker["timestamp"] + time_diff
            )

            await self.calculate_spread(pair_name)

    async def calculate_spread(self, pair_key):
        data = self.pair_data[pair_key]
        try:
            if data["price_a"] and data["price_b"]:
                min_price = min(data["price_a"], data["price_b"])
                spread = abs(data["price_a"] - data["price_b"])
                spread_pct = spread / min_price
                data["spread"] = spread
                data["spread_pct"] = spread_pct
        except (TypeError, ZeroDivisionError) as e:
            print(f"Calculate spread error for {pair_key}: {str(e)}")


class OrderbookSpreadMonitor(SpreadMonitorBase):
    support_depths = {
        "binance": [5],
        "bybit": [1, 50],
        "okx": [1, 50],
    }

    async def monitor(self, exchange: ccxtpro.Exchange, index: str, symbols):
        """
        统一监控方法
        :param exchange: 交易所实例
        :param index: 来源索引 ('a'或'b')
        """
        exchange_name = exchange.name.lower()
        limit = self.support_depths.get(exchange_name, [None])[0]
        while self.running:
            try:
                order_book = await exchange.watch_order_book_for_symbols(
                    symbols, limit=limit
                )
                await self.process_order_book(
                    order_book, index, self.latencies[exchange_name].get("time_diff", 0)
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Excpetion({index}): {traceback.format_exc()}")
                await asyncio.sleep(5)

    async def process_order_book(self, order_book, index, time_diff):
        symbol = order_book["symbol"]
        if symbol not in self.symbol_map[index]:
            return

        pair_map = self.symbol_map[index][symbol]
        pair_names = pair_map["pair_names"]
        for pair_name in pair_names:
            if pair_name not in self.pair_data:
                self.pair_data[pair_name] = {
                    "pair_name": pair_name,
                    "spread_pct": 0,
                    "buy_a_sell_b_spread_pct": 0,
                    "buy_b_sell_a_spread_pct": 0,
                    "bid_price_a": 0,
                    "bid_volume_a": 0,
                    "ask_price_a": 0,
                    "ask_volume_a": 0,
                    "bid_price_b": 0,
                    "bid_volume_b": 0,
                    "ask_price_b": 0,
                    "ask_volume_b": 0,
                    "elapsed_time_a": 0,
                    "elapsed_time_b": 0,
                }

            if len(order_book["bids"]):
                self.pair_data[pair_name][f"bid_price_{index}"] = order_book["bids"][0][
                    0
                ]
                self.pair_data[pair_name][f"bid_volume_{index}"] = order_book["bids"][
                    0
                ][1]

            if len(order_book["asks"]):
                self.pair_data[pair_name][f"ask_price_{index}"] = order_book["asks"][0][
                    0
                ]
                self.pair_data[pair_name][f"ask_volume_{index}"] = order_book["asks"][
                    0
                ][1]

            self.pair_data[pair_name][f"elapsed_time_{index}"] = time.time() * 1e3 - (
                order_book["timestamp"] + time_diff
            )
            await self.calculate_spread(pair_name)

    async def calculate_spread(self, pair_name):
        data = self.pair_data[pair_name]
        try:
            if (
                data["ask_price_a"]
                and data["bid_price_a"]
                and data["ask_price_b"]
                and data["bid_price_b"]
            ):
                data["buy_b_sell_a_spread"] = data["bid_price_a"] - data["ask_price_b"]
                data["buy_b_sell_a_spread_pct"] = (
                    data["buy_b_sell_a_spread"] / data["ask_price_b"]
                )
                data["buy_a_sell_b_spread"] = data["bid_price_b"] - data["ask_price_a"]
                data["buy_a_sell_b_spread_pct"] = (
                    data["buy_a_sell_b_spread"] / data["ask_price_a"]
                )
                data["spread_pct"] = max(
                    data["buy_b_sell_a_spread_pct"], data["buy_a_sell_b_spread_pct"]
                )
        except (TypeError, ZeroDivisionError) as e:
            print(f"Calculate spread error for {pair_name}: {str(e)}")


async def run_monitor(market_a, market_b, symbols=None):
    monitor = TickerSpreadMonitor(market_a, market_b, symbols=symbols)

    try:
        await monitor.load_markets()
        monitor.start()
        while True:
            print(monitor.top(5))
            await asyncio.sleep(10)
    except BaseException as e:
        print(f"监控已停止: {e}")
        await monitor.stop()


if __name__ == "__main__":
    try:
        asyncio.run(
            run_monitor("binance.swap.inverse", "okx.swap.inverse", symbols=["BTC-USD"])
        )
    except KeyboardInterrupt:
        print("程序已终止")
