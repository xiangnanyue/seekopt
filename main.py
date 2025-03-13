import asyncio
import click

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer, Static, Log
from textual.containers import HorizontalScroll
from monitors.spread import TickerSpreadMonitor, OrderbookSpreadMonitor


class TickerSpreadPanel(Static):
    def compose(self) -> ComposeResult:
        yield DataTable()

    def _add_or_update_row(self, table: DataTable, index, row):
        row_key = str(index)
        if index < table.row_count:
            table.update_cell(row_key, self.column_keys[0], index)
            table.update_cell(row_key, self.column_keys[1], row["pair_name"])
            table.update_cell(
                row_key, self.column_keys[2], f"{(row['spread_pct'] * 100):4f}%"
            )
            table.update_cell(row_key, self.column_keys[3], str(row["spread"]))
            table.update_cell(row_key, self.column_keys[4], str(row["price_a"]))
            table.update_cell(row_key, self.column_keys[5], str(row["price_b"]))
            table.update_cell(
                row_key, self.column_keys[6], f"{row['elapsed_time_a']:2f}ms"
            )
            table.update_cell(
                row_key, self.column_keys[7], f"{row['elapsed_time_b']:2f}ms"
            )
        else:
            table.add_row(
                index,
                row["pair_name"],
                f"{(row['spread_pct'] * 100):4f}%",
                str(row["spread"]),
                str(row["price_a"]),
                str(row["price_b"]),
                f"{row['elapsed_time_a']:2f}ms",
                f"{row['elapsed_time_b']:2f}ms",
                key=row_key,
            )

    async def load_data(self):
        top_n = self.app.monitor_params["top_n"]
        params = self.app.monitor_params.copy()
        del params["top_n"]

        monitor = TickerSpreadMonitor(**params)

        table = self.query_one(DataTable)
        try:
            await monitor.load_markets()
            monitor.start()
            while True:
                await asyncio.sleep(1)
                data = monitor.top(top_n)
                for i, row in enumerate(data):
                    self._add_or_update_row(table, i, row)
                while table.row_count > len(data):
                    table.remove_row(str(table.row_count - 1))
        except BaseException:
            await monitor.stop()

    async def on_mount(self):
        self.column_keys = self.query_one(DataTable).add_columns(
            "序号",
            "交易对",
            "价差（%）",
            "价差",
            "最新价（A）",
            "最新价（B）",
            "实时（A）",
            "实时（B）",
        )

        asyncio.create_task(self.load_data())


class OrderbookSpreadPanel(Static):
    def compose(self) -> ComposeResult:
        yield DataTable()

    def _add_or_update_row(self, table: DataTable, index, row):
        row_key = str(index)
        if index < table.row_count:
            table.update_cell(row_key, self.column_keys[0], index)
            table.update_cell(row_key, self.column_keys[1], row["pair_name"])
            table.update_cell(
                row_key, self.column_keys[2], f"{(row['spread_pct'] * 100):4f}%"
            )
            table.update_cell(
                row_key,
                self.column_keys[3],
                f"{(row['buy_a_sell_b_spread_pct'] * 100):4f}%",
            )
            table.update_cell(
                row_key,
                self.column_keys[4],
                f"{(row['buy_b_sell_a_spread_pct'] * 100):4f}%",
            )
            table.update_cell(
                row_key,
                self.column_keys[5],
                f"{row['bid_price_a']}/{row['bid_volume_a']}",
            )
            table.update_cell(
                row_key,
                self.column_keys[6],
                f"{row['ask_price_a']}/{row['ask_volume_a']}",
            )
            table.update_cell(
                row_key,
                self.column_keys[7],
                f"{row['bid_price_b']}/{row['bid_volume_b']}",
            )
            table.update_cell(
                row_key,
                self.column_keys[8],
                f"{row['ask_price_b']}/{row['ask_volume_b']}",
            )
            table.update_cell(
                row_key,
                self.column_keys[9],
                f"{row['elapsed_time_a']:2f}ms/{row['elapsed_time_b']:2f}ms",
            )
        else:
            table.add_row(
                index,
                row["pair_name"],
                f"{row['spread_pct'] * 100:4f}%",
                f"{(row['buy_a_sell_b_spread_pct'] * 100):4f}%",
                f"{(row['buy_b_sell_a_spread_pct'] * 100):4f}%",
                f"{row['bid_price_a']}/{row['bid_volume_a']}",
                f"{row['ask_price_a']}/{row['ask_volume_a']}",
                f"{row['bid_price_b']}/{row['bid_volume_b']}",
                f"{row['ask_price_b']}/{row['ask_volume_b']}",
                f"{row['elapsed_time_a']:2f}ms/{row['elapsed_time_b']:2f}ms",
                key=row_key,
            )

    async def load_data(self):
        top_n = self.app.monitor_params["top_n"]
        params = self.app.monitor_params.copy()
        del params["top_n"]

        monitor = OrderbookSpreadMonitor(**params)

        table = self.query_one(DataTable)
        try:
            await monitor.load_markets()
            monitor.start()
            while True:
                await asyncio.sleep(1)
                data = monitor.top(top_n)
                for i, row in enumerate(data):
                    self._add_or_update_row(table, i, row)
                while table.row_count > len(data):
                    table.remove_row(str(table.row_count - 1))
        except BaseException:
            await monitor.stop()

    async def on_mount(self):
        self.column_keys = self.query_one(DataTable).add_columns(
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
        #content {
            overflow-x: auto;
            overflow-y: auto;
        }
        """

    def __init__(self, monitor_panel, monitor_params):
        self.TITLE = (
            f"交易监控: A-{monitor_params['market_a']} B-{monitor_params['market_b']}"
        )
        super().__init__()

        self.monitor_panel = monitor_panel
        self.monitor_params = monitor_params

    def create_monitor_panel(self, id):
        if self.monitor_panel == "ticker":
            return TickerSpreadPanel(id=id)
        elif self.monitor_panel == "orderbook":
            return OrderbookSpreadPanel(id=id)
        else:
            raise ValueError(f"Unsupported panel type: {self.monitor_panel}")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        yield self.create_monitor_panel(id="content")


@click.command()
@click.option(
    "--monitor-panel",
    type=click.Choice(["orderbook", "ticker"], case_sensitive=False),
    default="ticker",
    required=True,
    help="Monitoring panel type (orderbook/ticker)",
)
@click.option(
    "--market-a",
    type=click.STRING,
    default="binance.spot",
    required=True,
    help="Market A structure: exchange.type[.subtype], e.g. binance.spot, okx.future.linear",
)
@click.option(
    "--market-b",
    type=click.STRING,
    default="okx.swap.linear",
    required=True,
    help="Market A structure: exchange.type[.subtype], e.g. binance.spot, okx.future.linear",
)
@click.option(
    "--quote-currency", default="USDT", show_default=True, help="Base quote currency"
)
@click.option(
    "--symbols",
    default=None,
    help="Filter symbols, comma-separated (e.g. BTC-USDT,ETH-USDT)",
)
@click.option(
    "--topn",
    type=int,
    default=20,
    show_default=True,
    help="Number of top items to monitor",
)
def main(monitor_panel, market_a, market_b, quote_currency, symbols, topn):
    symbols = set(symbols.split(",")) if symbols else None
    monitor_params = {
        "market_a": market_a,
        "market_b": market_b,
        "quote_currency": quote_currency,
        "symbols": symbols,
        "top_n": topn,
    }
    MonitorApp(monitor_panel, monitor_params=monitor_params).run()


if __name__ == "__main__":
    main()
