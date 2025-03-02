import asyncio
import click

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer, Static, Log
from textual.containers import ScrollableContainer
from monitors.spread import TickerSpreadMonitor, OrderbookSpreadMonitor


class TickerSpreadPanel(Static):
    def compose(self) -> ComposeResult:
        yield DataTable()

    async def load_data(self):
        top_n = self.app.monitor_params['top_n']
        params = self.app.monitor_params.copy()
        del params["top_n"]
        monitor = TickerSpreadMonitor(**params)

        table = self.query_one(DataTable)
        try:
            await monitor.load_markets()
            monitor.start()
            while True:
                await asyncio.sleep(1)
                table.clear()
                data = monitor.top(top_n)
                for i, row in enumerate(data):
                    table.add_row(
                        i,
                        row['pair_name'],
                        f'{(row["spread_pct"] * 100):4f}%',
                        str(row['spread']),
                        str(row['price_a']),
                        str(row['price_b']),
                        f'{row["elapsed_time_a"]:2f}ms',
                        f'{row["elapsed_time_b"]:2f}ms',
                    )
        except BaseException as e:
            await monitor.stop()

    async def on_mount(self):
        self.query_one(DataTable).add_columns(
            "序号",
            "交易对",
            "价差（%）",
            "价差",
            "最新价（A）",
            "最新价（B）",
            "实时（A）",
            "实时（B）"
        )
        asyncio.create_task(self.load_data())


class OrderbookSpreadPanel(Static):
    def compose(self) -> ComposeResult:
        yield DataTable()

    async def load_data(self):
        top_n = self.app.monitor_params['top_n']

        params = self.app.monitor_params.copy()
        del params["top_n"]
        monitor = OrderbookSpreadMonitor(**params)

        table = self.query_one(DataTable)
        try:
            await monitor.load_markets()
            monitor.start()
            while True:
                await asyncio.sleep(1)
                table.clear()
                data = monitor.top(top_n)
                for i, row in enumerate(data):
                    table.add_row(
                        i,
                        row['pair_name'],
                        f"{row['spread_pct']*100:4f}%",
                        f"{(row['buy_a_sell_b_spread_pct']*100):4f}%",
                        f"{(row['buy_b_sell_a_spread_pct']*100):4f}%",
                        f"{row['bid_price_a']}/{row['bid_volume_a']}",
                        f"{row['ask_price_a']}/{row['ask_volume_a']}",
                        f"{row['bid_price_b']}/{row['bid_volume_b']}",
                        f"{row['ask_price_b']}/{row['ask_volume_b']}",
                        f"{row['elapsed_time_a']:2f}ms/{row['elapsed_time_b']:2f}ms",
                    )
        except BaseException as e:
            await monitor.stop()

    async def on_mount(self):
        self.query_one(DataTable).add_columns(
            "序号",
            "交易对",
            "价差",
            "买A卖B",
            "买B卖A",
            "买一价/量（A）",
            "卖一价/量（A）",
            "买一价/量（B）",
            "卖一价/量（B）",
            "实时（A/B）",
        )
        asyncio.create_task(self.load_data())


class MonitorApp(App):

    CSS = """
        #scroll {
            width: 100%;
            height: 100%;
            overflow-x: auto;
            overflow-y: auto;
        }
        #content {
            width: 1000vw;
            height: 1000vh;
            min-width: 100vw;
            min-height: 100vh;
        }
        """

    def __init__(self, monitor_panel, monitor_params):
        self.TITLE = f"交易监控: A-{monitor_params['market_a']} B-{monitor_params['market_b']}"

        super().__init__()
        self.monitor_panel = monitor_panel
        self.monitor_params = monitor_params

    def create_monitor_panel(self, id):
        if self.monitor_panel == "ticker":
            return TickerSpreadPanel(id=id)
        elif self.monitor_panel == "orderbook":
            return OrderbookSpreadPanel(id=id)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield Log()
        with ScrollableContainer(id="scroll"):
            yield self.create_monitor_panel(id="content")


@click.command()
@click.option("--monitor-panel", 
              type=click.Choice(['orderbook', 'ticker'], case_sensitive=False),
              default="ticker",
              required=True,
              help="Monitoring panel type (orderbook/ticker)")
@click.option("--market-a", 
              type=click.STRING,
              default='binance.spot',
              required=True,
              help="Market A structure: exchange.type[.subtype], e.g. binance.spot, okx.future.linear")
@click.option("--market-b", 
              type=click.STRING,
              default='okx.swap.linear',
              required=True,
              help="Market A structure: exchange.type[.subtype], e.g. binance.spot, okx.future.linear")
@click.option("--quote-currency", 
              default="USDT",
              show_default=True,
              help="Base quote currency")
@click.option("--symbols",
              default=None,
              help="Filter symbols, comma-separated (e.g. BTC-USDT,ETH-USDT)")
@click.option("--topn",
              type=int,
              default=20,
              show_default=True,
              help="Number of top items to monitor")
def main(monitor_panel, market_a, market_b, quote_currency, symbols, topn):
    symbols = set(symbols.split(',')) if symbols else None
    monitor_params = {
        'market_a': market_a,
        'market_b': market_b,
        'quote_currency': quote_currency,
        'symbols': symbols,
        'top_n': topn,
    }
    MonitorApp(monitor_panel, monitor_params=monitor_params).run()


if __name__ == "__main__":
    main()
