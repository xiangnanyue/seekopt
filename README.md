# seekopt
交易监控工具

原文来自：https://mp.weixin.qq.com/s/0qJ2qEV9VFlX-njOe84t_g

## operation

1. 基于最新成交（Binance 现货和 OKX 正向永续合约的全量监控)：

```
$ python main.py --monitor-panel ticker \
                 --market-a binance.spot \
                 --market-b okx.swap.linear
```

如上所示，默认展示的 USDT 合约，如果要切换成 USDC，可通过选项 --quote-currency USDC 实现。

而排序规则上，固定按价差百分比从大到小排序

```
$ python main.py --monitor-panel ticker \
                 --market-a binance.spot \
                 --market-b okx.swap.linear \
                 --quote-currency USDC
```

如果是反向合约，如 binance.swap.inverse，计价币种要切换成 USD，配置选项 --quote-currency USD。

监控给定的币对：
```
$ python main.py --monitor-panel ticker \
                 --market-a binance.spot \
                 --market-b okx.swap.linear \
                 --symbols BTC-USDT,ETH-USDT
```

支持订单簿监控：
```

$ python main.py --monitor-panel orderbook \
                 --market-a binance.spot \
                 --market-b okx.swap.linear \
                 --symbols TRUMP-USDT,BTC-USDT,ETH-USDT,SOL-USDT,ADA-USDT,BNB-USDT,XRP-USDT
```

2. web服务

这个监控工具的界面用的是 textual 开发的，textual 是一个 Tui 终端应用开发库。我暂时还不想整 Web 开发，就先用它实现了。

如果有意将其通过 web 访问，textual 也有命令可将其作为 web 服务。
```
$ textual serve "python main.py \
                --market-a binance.swap.linear \
                --market-b --bybit.swap.linear"
```


3. 参数

这个工具是基于 ccxt 实现，按理说 ccxt 支持的市场都是支持的，不过我测试的时候，也发现了一些不适配的情况。我当前只测试了 binance、okx 和 bybit 三个交易所。

参数 market 格式是 exchange.type.subtype，支持类型如下所示：
```
exchange.spot -> 现货
exchange.spot.margin -> 保证金杠杆
exchange.swap.linear -> 永续正向合约
exchange.swap.inverse -> 永续反向合约
exchagne.future.linear -> 交割正向合约 
exchagne.future.inverse -> 交割反向合约
```

使用时，请把 exchange 替换为具体的交易所名称。