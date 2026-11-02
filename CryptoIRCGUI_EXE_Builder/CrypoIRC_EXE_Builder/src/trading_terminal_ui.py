"""Tk native chart and PAPER-only trading page. Never connected to wallet funds."""
from __future__ import annotations

from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import math
import os
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from market_server_client import ServerMarketFeed, configured_server_url
from market_terminal import (AlpacaMarketFeed, PaperLedger, Watchlist, Bar,
                             demo_bars, ema, rsi, parse_symbol, positive, TIMEFRAMES)

CARD='#15101e'; BG='#07060b'; FIELD='#0c0914'; GREEN='#47fca3'
RED='#ff636e'; FG='#f2edf9'; MUTED='#a39ab6'; PURPLE='#b363ff'; GRID='#332a3d'


def user_data_dir():
    base=os.getenv('LOCALAPPDATA') if os.name == 'nt' else os.getenv('XDG_DATA_HOME')
    return (Path(base) if base else Path.home()/'.local'/'share')/'CRYPTO_NOCTURNE'/'paper_trading'


class TradingTerminalUI:
    def page_trading_terminal(self):
        self.head('Trading Terminal / Paper Market Lab',
            'Live-capable stock and cryptocurrency charts, watchlists, EMA/RSI and PAPER orders. '
            'Not a brokerage. No real trades, wallet transfers or fiat balances are affected.')
        self._trade_generation=getattr(self,'_trade_generation',0)+1
        generation=self._trade_generation
        self.trade_events=queue.Queue(maxsize=120)
        self.trade_stop=threading.Event()
        self.trade_feed=AlpacaMarketFeed()
        self.trade_server_feed=ServerMarketFeed()
        self.trade_ledger=PaperLedger(user_data_dir()/'paper.db')
        self.trade_watch=Watchlist(user_data_dir()/'watchlist.json')
        self.trade_bars=[]
        self.trade_quote=None  # price, observed_at, source
        self.trade_symbol=tk.StringVar(value='BTC/USD')
        self.trade_market=tk.StringVar(value='crypto')
        self.trade_timeframe=tk.StringVar(value='1Min')
        self.trade_mode=tk.StringVar(value='NOCTURNE SERVER' if self.trade_server_feed.configured else 'SIMULATED DEMO')
        self.trade_qty=tk.StringVar(value='0.01')
        self.trade_source=tk.StringVar(value='DEMO — prices are synthetic, no real quote loaded')
        self.trade_price=tk.StringVar(value='—')
        self.trade_cash=tk.StringVar(value='Paper cash: $—')
        self.trade_zoom=110
        self.trade_last_refresh=0.0
        self._trade_demo_rng=random.Random(451)
        self._trade_demo_next=time.monotonic()+5

        top=tk.Frame(self.content,bg=CARD,padx=12,pady=10)
        top.pack(fill='x',pady=(0,8))
        tk.Label(top,text='PAPER ONLY — NOT REAL ORDERS / NOT WALLET FUNDS',bg=CARD,fg=RED,
                 font=('Consolas',12,'bold')).pack(anchor='w',pady=(0,7))
        params=tk.Frame(top,bg=CARD);params.pack(fill='x')
        for label,var,vals,width in (
            ('MARKET',self.trade_market,('stock','crypto'),9),
            ('SYMBOL',self.trade_symbol,(),14),
            ('INTERVAL',self.trade_timeframe,tuple(TIMEFRAMES),10),
            ('DATA',self.trade_mode,('NOCTURNE SERVER','SIMULATED DEMO','ALPACA REAL DATA'),20),
        ):
            cell=tk.Frame(params,bg=CARD);cell.pack(side='left',padx=(0,10))
            tk.Label(cell,text=label,bg=CARD,fg=MUTED,font=('Consolas',9)).pack(anchor='w')
            if vals:
                widget=ttk.Combobox(cell,textvariable=var,values=vals,width=width,state='readonly')
            else:
                widget=ttk.Entry(cell,textvariable=var,width=width)
            widget.pack()
        ttk.Button(params,text='LOAD CHART',style='Accent.TButton',command=self._trade_reload).pack(side='left',padx=5,pady=(17,0))
        ttk.Button(params,text='RESET ZOOM',command=self._trade_reset_zoom).pack(side='left',padx=5,pady=(17,0))
        tk.Label(top,textvariable=self.trade_source,bg=CARD,fg=PURPLE,font=('Consolas',9),anchor='w').pack(fill='x',pady=(9,0))

        split=tk.Frame(self.content,bg=BG);split.pack(fill='x',pady=7)
        left=tk.Frame(split,bg=CARD,padx=8,pady=8)
        left.pack(side='left',fill='both',expand=True,padx=(0,7))
        row=tk.Frame(left,bg=CARD);row.pack(fill='x')
        tk.Label(row,textvariable=self.trade_price,bg=CARD,fg=GREEN,font=('Consolas',16,'bold')).pack(side='left')
        tk.Label(row,text='EMA12 / EMA26  •  candle body/wick  •  volume',bg=CARD,fg=MUTED,font=('Consolas',8)).pack(side='right')
        self.trade_canvas=tk.Canvas(left,bg=BG,highlightthickness=0,height=385)
        self.trade_canvas.pack(fill='x',expand=True,pady=(8,2))
        self.trade_rsi_canvas=tk.Canvas(left,bg=BG,highlightthickness=0,height=100)
        self.trade_rsi_canvas.pack(fill='x',pady=(0,4))
        self.trade_canvas.bind('<Configure>',lambda e:self._trade_draw())
        self.trade_rsi_canvas.bind('<Configure>',lambda e:self._trade_draw())
        self.trade_canvas.bind('<MouseWheel>',lambda e:self._trade_mousewheel(e))
        self.trade_canvas.bind('<Button-4>',lambda e:self._trade_mousewheel(e))
        self.trade_canvas.bind('<Button-5>',lambda e:self._trade_mousewheel(e))
        self.trade_canvas.bind('<Motion>',self._trade_hover)

        right=tk.Frame(split,bg=CARD,padx=10,pady=11,width=285)
        right.pack(side='right',fill='y');right.pack_propagate(False)
        tk.Label(right,text='WATCHLIST',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        self.trade_watch_tree=ttk.Treeview(right,columns=('market','symbol'),show='headings',height=10)
        self.trade_watch_tree.heading('market',text='Type');self.trade_watch_tree.heading('symbol',text='Symbol')
        self.trade_watch_tree.column('market',width=75,anchor='w');self.trade_watch_tree.column('symbol',width=125,anchor='w')
        self.trade_watch_tree.pack(fill='x',pady=7)
        self.trade_watch_tree.bind('<Double-1>',lambda e:self._trade_watch_select())
        watch_actions=tk.Frame(right,bg=CARD);watch_actions.pack(fill='x')
        ttk.Button(watch_actions,text='ADD',command=self._trade_watch_add).pack(side='left',padx=(0,4))
        ttk.Button(watch_actions,text='REMOVE',command=self._trade_watch_remove).pack(side='left',padx=(0,4))
        ttk.Button(watch_actions,text='OPEN',command=self._trade_watch_select).pack(side='left')
        tk.Frame(right,height=2,bg=GRID).pack(fill='x',pady=13)
        tk.Label(right,text='PAPER ORDER TICKET',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(right,textvariable=self.trade_cash,bg=CARD,fg=FG,font=('Consolas',10)).pack(anchor='w',pady=7)
        tk.Label(right,text='Quantity (shares or crypto units)',bg=CARD,fg=MUTED,font=('Consolas',9)).pack(anchor='w')
        ttk.Entry(right,textvariable=self.trade_qty).pack(fill='x',pady=(4,6))
        orderbuttons=tk.Frame(right,bg=CARD);orderbuttons.pack(fill='x',pady=6)
        ttk.Button(orderbuttons,text='PAPER BUY',style='Accent.TButton',command=lambda:self._trade_order('BUY')).pack(side='left',padx=(0,5))
        ttk.Button(orderbuttons,text='PAPER SELL',command=lambda:self._trade_order('SELL')).pack(side='left')
        tk.Label(right,text='No fees, spread/slippage or market execution.\nFills use last fresh reference price.\nNo margin, short sales, or live orders.',
                 justify='left',bg=CARD,fg=RED,font=('Consolas',8),wraplength=240).pack(anchor='w',pady=9)

        bottom=tk.Frame(self.content,bg=CARD,padx=12,pady=10);bottom.pack(fill='x',pady=6)
        tk.Label(bottom,text='PAPER PORTFOLIO / TRADE LOG (separate from money hub)',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        self.trade_position_tree=ttk.Treeview(bottom,columns=('symbol','market','qty','basis'),show='headings',height=4)
        for col,w in (('symbol',140),('market',100),('qty',160),('basis',170)):
            self.trade_position_tree.heading(col,text=col.title());self.trade_position_tree.column(col,width=w,anchor='w')
        self.trade_position_tree.pack(fill='x',pady=5)
        self.trade_orders_tree=ttk.Treeview(bottom,columns=('when','symbol','side','qty','price','source'),show='headings',height=4)
        for col,w in (('when',185),('symbol',110),('side',65),('qty',120),('price',100),('source',170)):
            self.trade_orders_tree.heading(col,text=col.title());self.trade_orders_tree.column(col,width=w,anchor='w')
        self.trade_orders_tree.pack(fill='x',pady=5)
        self._trade_fill_watch()
        self._trade_fill_portfolio()
        self._trade_reload()
        self._trade_pump(generation)

    def _trade_valid_page(self):
        return self.current_page=='Trading Terminal' and hasattr(self,'trade_canvas') and self.trade_canvas.winfo_exists()

    def _trade_mousewheel(self,event):
        delta=getattr(event,'delta',0)
        change=-15 if delta>0 or getattr(event,'num',0)==4 else 15
        self.trade_zoom=max(30,min(220,self.trade_zoom+change))
        self._trade_draw()

    def _trade_reset_zoom(self):
        self.trade_zoom=110;self._trade_draw()

    def _trade_hover(self,event):
        bars=self.trade_bars[-self.trade_zoom:]
        if not bars:return
        width=max(200,self.trade_canvas.winfo_width())
        x0=38; usable=width-100
        index=min(len(bars)-1,max(0,int((event.x-x0)/max(1,usable)*len(bars))))
        b=bars[index]
        self.trade_price.set(f'{self.trade_symbol.get()}  O {b.open:,.4f}  H {b.high:,.4f}  L {b.low:,.4f}  C {b.close:,.4f}')

    def _trade_draw(self):
        canvas=getattr(self,'trade_canvas',None)
        if canvas is None or not canvas.winfo_exists():return
        canvas.delete('all')
        rsi_canvas=getattr(self,'trade_rsi_canvas',None)
        if rsi_canvas is None or not rsi_canvas.winfo_exists():return
        rsi_canvas.delete('all')
        bars=self.trade_bars[-self.trade_zoom:]
        w=max(250,canvas.winfo_width());h=max(260,canvas.winfo_height())
        if not bars:
            canvas.create_text(w//2,h//2,text='NO CHART DATA — configure Alpaca or choose SIMULATED DEMO',fill=MUTED,font=('Consolas',11))
            return
        n=len(bars);x0=36; plot_w=max(40,w-112);top=20;lower=h-97
        highs=[b.high for b in bars];lows=[b.low for b in bars]
        lo=min(lows);hi=max(highs);span=max(hi-lo,hi*.0001)
        lo-=span*.08;hi+=span*.08
        def y(price):return top+(hi-price)/(hi-lo)*(lower-top)
        def x(i):return x0+(i+.5)*plot_w/n
        for j in range(6):
            level=lo+(hi-lo)*j/5
            yy=y(level)
            canvas.create_line(x0,yy,x0+plot_w,yy,fill=GRID)
            canvas.create_text(x0+plot_w+6,yy,text=f'{level:,.2f}',anchor='w',fill=MUTED,font=('Consolas',8))
        candle_width=max(1,min(13,plot_w/n*.7))
        for i,b in enumerate(bars):
            xx=x(i);color=GREEN if b.close>=b.open else RED
            canvas.create_line(xx,y(b.high),xx,y(b.low),fill=color,width=1)
            y1=y(b.open);y2=y(b.close)
            canvas.create_rectangle(xx-candle_width/2,min(y1,y2),xx+candle_width/2,max(y1+1,y2),fill=color,outline=color)
        for period,color in ((12,'#fff069'),(26,'#ff9d53')):
            curve=ema([b.close for b in bars],period)
            points=[]
            for i,v in enumerate(curve):points.extend((x(i),y(v)))
            if len(points)>3:canvas.create_line(*points,fill=color,width=1.7,smooth=False)
        max_vol=max(b.volume for b in bars) or 1
        base=h-18; volume_top=lower+14
        for i,b in enumerate(bars):
            hh=(b.volume/max_vol)*max(3,base-volume_top)
            canvas.create_rectangle(x(i)-max(1,candle_width/3),base-hh,x(i)+max(1,candle_width/3),base,
                                    fill=GREEN if b.close>=b.open else RED,outline='')
        canvas.create_text(x0+2,lower+7,text='VOLUME',anchor='nw',fill=MUTED,font=('Consolas',8))
        rw=max(250,rsi_canvas.winfo_width());rh=max(80,rsi_canvas.winfo_height())
        rsi_canvas.create_text(10,8,text='RSI (14)',fill=FG,anchor='nw',font=('Consolas',8))
        def ry(val):return 15+(100-val)/100*(rh-28)
        for mark in (30,50,70):
            rsi_canvas.create_line(x0,ry(mark),x0+plot_w,ry(mark),fill=GRID,dash=(3,4))
            rsi_canvas.create_text(min(rw-32,x0+plot_w+6),ry(mark),text=str(mark),fill=MUTED,anchor='w',font=('Consolas',8))
        vals=rsi([b.close for b in bars]); pts=[]
        for i,v in enumerate(vals):
            if v is not None:pts.extend((x(i),ry(v)))
        if len(pts)>=4:rsi_canvas.create_line(*pts,fill='#c084fc',width=1.6)
        if self.trade_quote:
            price,_,_=self.trade_quote
            self.trade_price.set(f'{self.trade_symbol.get()}  {price:,.4f} USD')
        else:self.trade_price.set(f'{self.trade_symbol.get()}  {bars[-1].close:,.4f} (historical)')

    def _trade_fill_watch(self):
        tree=self.trade_watch_tree
        for child in tree.get_children():tree.delete(child)
        try:
            for k,s in self.trade_watch.get():tree.insert('', 'end',values=(k,s))
        except (ValueError,OSError):
            self.trade_source.set('Watchlist invalid; reset its local JSON file')

    def _trade_watch_add(self):
        try:
            pair=(self.trade_market.get(),parse_symbol(self.trade_symbol.get(),self.trade_market.get()))
            self.trade_watch.put(self.trade_watch.get()+[pair]);self._trade_fill_watch()
        except (ValueError,OSError) as e:messagebox.showerror('Watchlist',str(e))

    def _trade_watch_remove(self):
        sel=self.trade_watch_tree.selection()
        if not sel:return
        val=self.trade_watch_tree.item(sel[0])['values']
        try:self.trade_watch.put([p for p in self.trade_watch.get() if p!=(val[0],val[1])]);self._trade_fill_watch()
        except (ValueError,OSError) as e:messagebox.showerror('Watchlist',str(e))

    def _trade_watch_select(self):
        sel=self.trade_watch_tree.selection()
        if not sel:return
        typ,sym=self.trade_watch_tree.item(sel[0])['values']
        self.trade_market.set(typ);self.trade_symbol.set(sym);self._trade_reload()

    def _trade_fill_portfolio(self):
        self.trade_cash.set(f'Paper cash: ${self.trade_ledger.cash():,.2f}')
        for tree in (self.trade_position_tree,self.trade_orders_tree):
            for item in tree.get_children():tree.delete(item)
        for sym,kind,qty,basis in self.trade_ledger.positions():
            self.trade_position_tree.insert('', 'end',values=(sym,kind,str(qty),f'${basis:,.2f}'))
        for at,sym,kind,side,qty,price,notional,source in self.trade_ledger.orders(12):
            self.trade_orders_tree.insert('', 'end',values=(at[:19],sym,side,qty,price,source))

    def _trade_reload(self):
        try:
            symbol=parse_symbol(self.trade_symbol.get(),self.trade_market.get())
            timeframe=self.trade_timeframe.get()
            if timeframe not in TIMEFRAMES:raise ValueError('Invalid timeframe')
        except ValueError as e:
            messagebox.showerror('Market',str(e));return
        self.trade_quote=None
        self.trade_bars=[]
        self._trade_demo_next=time.monotonic()+5
        self._trade_draw()
        generation=self._trade_generation
        # Stop previous stream, then isolate the new symbol in its own generation.
        self.trade_stop.set()
        self.trade_stop=threading.Event()
        self._trade_token=object()  # invalidate old live results even when changing to demo
        stop=self.trade_stop
        mode=self.trade_mode.get()
        kind=self.trade_market.get()
        if mode=='SIMULATED DEMO':
            self.trade_bars=demo_bars(symbol,kind,timeframe=timeframe)
            self.trade_quote=(Decimal(str(self.trade_bars[-1].close)),datetime.now(timezone.utc),'SIMULATED-DEMO')
            self.trade_source.set('DEMO / SYNTHETIC CANDLES — prices are not real; paper orders only')
            self._trade_draw()
            return
        if mode=='NOCTURNE SERVER':
            if not self.trade_server_feed.configured:
                self.trade_source.set('SERVER NOT CONFIGURED — administrator must publish an HTTPS market-server endpoint in the release')
                return
            self.trade_source.set('Loading provider-authorized quotes from NOCTURNE SERVER over HTTPS...')
            token=self._trade_token
            threading.Thread(target=self._trade_server_poll,
                   args=(symbol,kind,timeframe,stop,generation,token),
                   name='NocturneServerMarketPoll',daemon=True).start()
            return
        if not self.trade_feed.configured:
            self.trade_source.set('NO LOCAL ALPACA KEY — choose NOCTURNE SERVER or SIMULATED DEMO')
            return
        self.trade_source.set('Connecting to Alpaca historical + live stream (TLS, stock feed: IEX only)...')
        token=self._trade_token
        def worker():
            try:
                bars=self.trade_feed.bars(symbol,kind,timeframe)
                self._trade_post(('bars',generation,token,bars,'ALPACA-IEX' if kind=='stock' else 'ALPACA-CRYPTO'))
                if stop.is_set():return
                self._trade_stream(symbol,kind,timeframe,stop,generation,token)
            except Exception as exc:
                # No URLs or API credentials in GUI errors.
                self._trade_post(('error',generation,token,type(exc).__name__))
        threading.Thread(target=worker,name='NocturneMarketData',daemon=True).start()

    def _trade_server_poll(self,symbol,kind,timeframe,stop,generation,token):
        """Read-only HTTPS polling. No brokerage keys and no synthetic fallback."""
        try:
            bars=self.trade_server_feed.bars(symbol,kind,timeframe)
            source=('NOCTURNE SERVER / SYNTHETIC DEMO — NOT REAL' if self.trade_server_feed.last_mode=='demo'
                    else 'NOCTURNE SERVER / '+str(self.trade_server_feed.last_source or 'DATA'))
            self._trade_post(('bars',generation,token,bars,source))
        except Exception as exc:
            self._trade_post(('error',generation,token,type(exc).__name__))
            return
        while not stop.is_set() and self._trade_valid_generation(generation,token):
            try:
                bar,src,mode=self.trade_server_feed.latest(symbol,kind)
                label=('SERVER / SIMULATED DATA — NOT LIVE' if mode=='demo'
                       else 'NOCTURNE SERVER / '+src)
                self._trade_post(('bar',generation,token,bar,kind,timeframe))
                if mode=='licensed':
                    moment=datetime.fromisoformat(bar.time.replace('Z','+00:00'))
                    self._trade_post(('trade',generation,token,Decimal(str(bar.close)),moment,label))
                else:
                    self._trade_post(('status',generation,token,label))
            except Exception as exc:
                self._trade_post(('status',generation,token,'Server market data unavailable ('+type(exc).__name__+'); retrying'))
            stop.wait(20)

    def _trade_post(self,event):
        try:self.trade_events.put_nowait(event)
        except queue.Full:
            try:self.trade_events.get_nowait()
            except queue.Empty:pass
            try:self.trade_events.put_nowait(event)
            except queue.Full:pass

    def _trade_stream(self,symbol,kind,timeframe,stop,generation,token):
        try:
            from websockets.sync.client import connect
        except ImportError:
            self._trade_post(('error',generation,token,'WebSocket dependency unavailable'))
            return
        url = ('wss://stream.data.alpaca.markets/v2/iex' if kind=='stock'
               else 'wss://stream.data.alpaca.markets/v1beta3/crypto/us')
        backoff=2
        while not stop.is_set() and self._trade_valid_generation(generation,token):
            try:
                with connect(url,open_timeout=8,close_timeout=3,max_size=100000,ping_interval=20) as ws:
                    ws.send(__import__('json').dumps({'action':'auth','key':self.trade_feed.key,'secret':self.trade_feed.secret}))
                    ws.send(__import__('json').dumps({'action':'subscribe','bars':[symbol],'trades':[symbol]}))
                    self._trade_post(('status',generation,token,'ALPACA STREAM CONNECTED • '+ ('IEX stock feed' if kind=='stock' else 'crypto venue feed')))
                    backoff=2
                    while not stop.is_set():
                        try:raw=ws.recv(timeout=3)
                        except TimeoutError:continue
                        messages=__import__('json').loads(raw)
                        if not isinstance(messages,list):continue
                        for msg in messages:
                            if msg.get('T') in ('b','u') and msg.get('S')==symbol:
                                try:bar=Bar.parse(msg)
                                except (ValueError,TypeError,KeyError):continue
                                self._trade_post(('bar',generation,token,bar,kind,timeframe))
                            elif msg.get('T')=='t' and msg.get('S')==symbol:
                                try:price=positive(msg['p'])
                                except (ValueError,KeyError):continue
                                # The exchange timestamp must be fresh before paper execution.
                                try:moment=datetime.fromisoformat(str(msg['t']).replace('Z','+00:00'))
                                except ValueError:continue
                                self._trade_post(('trade',generation,token,price,moment,
                                                       'ALPACA-IEX' if kind=='stock' else 'ALPACA-CRYPTO'))
                            elif msg.get('T')=='error':
                                raise ValueError('Market data subscription denied')
            except Exception as exc:
                if not stop.is_set():
                    self._trade_post(('status',generation,token,f'MARKET STREAM INTERRUPTED ({type(exc).__name__}); reconnecting'))
                if stop.wait(backoff):break
                backoff=min(30,backoff*2)

    def _trade_valid_generation(self,generation,token):
        return generation==getattr(self,'_trade_generation',None) and token is getattr(self,'_trade_token',None)

    def _trade_pump(self,generation):
        if not self._trade_valid_page() or generation!=self._trade_generation:
            self.trade_stop.set();return
        if self.trade_mode.get()=='SIMULATED DEMO' and self.trade_bars and time.monotonic()>=self._trade_demo_next:
            self._trade_demo_advance()
            self._trade_demo_next=time.monotonic()+5
        for _ in range(60):
            try:event=self.trade_events.get_nowait()
            except queue.Empty:break
            typ,gen,token,*payload=event
            if gen != generation or token is not getattr(self,'_trade_token',None):continue
            if typ=='bars':
                bars,src=payload
                self.trade_bars=bars
                self.trade_source.set(src+' / authenticated historical data; bar timestamps shown in UTC')
                if bars:
                    b=bars[-1]
                    self.trade_quote=(Decimal(str(b.close)),datetime.fromisoformat(b.time.replace('Z','+00:00')),src)
                self._trade_draw()
            elif typ=='bar':
                bar,kind,timeframe=payload
                if timeframe=='1Min':
                    if self.trade_bars and self.trade_bars[-1].time==bar.time:self.trade_bars[-1]=bar
                    elif not self.trade_bars or bar.time>self.trade_bars[-1].time:self.trade_bars.append(bar)
                    self.trade_bars=self.trade_bars[-500:]
                self._trade_draw()
            elif typ=='trade':
                price,moment,src=payload
                self.trade_quote=(price,moment,src)
                self.trade_price.set(f'{self.trade_symbol.get()}  {price:,.4f} USD')
            elif typ=='status':self.trade_source.set(payload[0])
            elif typ=='error':self.trade_source.set(f'Market data unavailable ({payload[0]}). Check server status, network and data entitlement.')
        self.root.after(140,lambda:self._trade_pump(generation))

    def _trade_demo_advance(self):
        # Explicitly synthetic animated market; no remote quote or real price.
        if not self.trade_bars:return
        current=self.trade_bars[-1]
        now=datetime.now(timezone.utc)
        current_interval=TIMEFRAMES[self.trade_timeframe.get()]
        bar_bucket=int(now.timestamp())//current_interval
        last_bucket=int(datetime.fromisoformat(current.time.replace('Z','+00:00')).timestamp())//current_interval
        open_price=current.open if last_bucket==bar_bucket else current.close
        price=current.close*(1+self._trade_demo_rng.uniform(-.002,.002))
        bar=Bar(datetime.fromtimestamp(bar_bucket*current_interval,timezone.utc).isoformat(),
                open_price,max(open_price,price,current.high if last_bucket==bar_bucket else price),
                min(open_price,price,current.low if last_bucket==bar_bucket else price),
                price,current.volume+self._trade_demo_rng.uniform(1,30) if last_bucket==bar_bucket else 1.)
        if last_bucket==bar_bucket:self.trade_bars[-1]=bar
        else:self.trade_bars.append(bar)
        self.trade_bars=self.trade_bars[-500:]
        self.trade_quote=(Decimal(str(price)),now,'SIMULATED-DEMO')
        self._trade_draw()

    def _trade_order(self,side):
        if not self.trade_quote:
            messagebox.showwarning('Paper order','No price available. Load market data first.');return
        try:
            symbol=parse_symbol(self.trade_symbol.get(),self.trade_market.get())
            qty=positive(self.trade_qty.get(),max_value='100000000')
            price,observed_at,source=self.trade_quote
            age=(datetime.now(timezone.utc)-observed_at).total_seconds()
            if age>120 or age< -10:raise ValueError('Quote is stale: refresh or wait for stream update')
            notional=price*qty
        except ValueError as exc:
            messagebox.showerror('Paper order',str(exc));return
        prompt=f'{side} {qty} {symbol} at reference ${price:,.6f}?\nEstimated notional: ${notional:,.2f}\nSource: {source}\n\nSIMULATED ORDER ONLY. No brokerage, exchange or wallet transfer.'
        if not messagebox.askyesno('CONFIRM PAPER ORDER',prompt,parent=self.root):return
        try:
            result=self.trade_ledger.execute(symbol=symbol,asset_type=self.trade_market.get(),side=side,
                    quantity=qty,quote_price=price,observed_at=observed_at.isoformat(),source=source)
        except ValueError as exc:
            messagebox.showerror('Paper order rejected',str(exc),parent=self.root);return
        self._trade_fill_portfolio()
        self.trade_source.set(f'PAPER {side} COMPLETE: {result["qty"]} {symbol} @ ${result["price"]} • not real')
