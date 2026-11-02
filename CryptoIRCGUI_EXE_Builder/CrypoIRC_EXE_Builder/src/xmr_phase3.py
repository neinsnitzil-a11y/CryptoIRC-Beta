"""Phase 3: local Monero wallet-RPC coordination, never online seed entry.

Prepared relay metadata stays in this process's memory ONLY. Restarting after
preparation cannot relay; reconciliation requires wallet-RPC history.
"""
from __future__ import annotations
from decimal import Decimal
import re
from chain_journal import ChainJournal
from core.transfer import TransferError, MoneroRPC, amount_decimal, units, safe_loopback_url

TXID=re.compile(r'[0-9a-fA-F]{64}\Z')
ATOMIC=Decimal('1000000000000')

class MoneroPhaseThree:
    def __init__(self,url,user,password,journal=None,rpc=None,network="mainnet"):
        if network not in ("mainnet","stagenet"):
            raise TransferError("Monero network must be explicitly mainnet or stagenet.")
        self.network=network
        self.url=safe_loopback_url(url)
        self.rpc=rpc or MoneroRPC(self.url,user,password)
        self.journal=journal or ChainJournal()
        self._session_metadata={}

    def health(self):
        # Official wallet-RPC get_height/get_address/validate_address methods.
        h=self.rpc.call('get_height').get('height')
        if not isinstance(h,int) or h<1:raise TransferError('Monero wallet is not synchronized. Block height unavailable.')
        resp=self.rpc.call('get_address',{'account_index':0})
        address=resp.get('address')
        if not isinstance(address,str):raise TransferError('Monero wallet public address unavailable.')
        checked=self.rpc.call('validate_address',{'address':address,'any_net_type':False,'allow_openalias':False})
        if not checked.get('valid') or checked.get('nettype')!=self.network:
            raise TransferError('Wallet RPC network does not match selected Monero network.')
        return {'wallet_height':h,'address':address,'network':self.network}

    def balance(self):
        h=self.health()
        amounts=self.rpc.call('get_balance',{'account_index':0})
        total=int(amounts.get('balance',-1));unlocked=int(amounts.get('unlocked_balance',-1))
        if total<0 or unlocked<0 or unlocked>total:raise TransferError('Monero RPC reported invalid wallet balances.')
        return {'total':str(Decimal(total)/ATOMIC),'unlocked':str(Decimal(unlocked)/ATOMIC),
                'locked':str(Decimal(total-unlocked)/ATOMIC),'wallet_height':h['wallet_height']}

    def check_restored_address(self,expected_public_address):
        # Identity comparison is NOT an independent seed or balance restore proof.
        info=self.health()
        if not isinstance(expected_public_address,str) or info['address']!=expected_public_address.strip():
            raise TransferError('Monero restored wallet address DOES NOT MATCH your independently recorded address.')
        return {'address_matches':True,'height':info['wallet_height'],
                'warning':'Public address matches. Still verify recovery words, restore height, synced wallet scan and balance externally.'}

    def new_subaddress(self,label='NOCTURNE receive'):
        self.health()
        result=self.rpc.call('create_address',{'account_index':0,'label':str(label)[:64]})
        addr=result.get('address')
        checked=self.rpc.call('validate_address',{'address':addr,'any_net_type':False,'allow_openalias':False})
        if not checked.get('valid') or checked.get('nettype')!=self.network:
            raise TransferError('Monero wallet-RPC returned an invalid receiving subaddress.')
        return {'address':addr,'address_index':int(result.get('address_index',-1))}

    def transfers(self):
        self.health()
        rows=self.rpc.call('get_transfers',{'in':True,'out':True,'pending':True,'failed':True,'pool':True,'account_index':0})
        results=[]
        for key in ('in','out','pending','failed','pool'):
            for item in rows.get(key,[])[:100]:
                results.append({'type':key,'txid':item.get('txid',''),
                                'amount':str(Decimal(int(item.get('amount',0)))/ATOMIC),
                                'confirmations':int(item.get('confirmations',0)),
                                'locked':item.get('locked',None)})
        return results

    def prepare(self,destination,amount,max_fee):
        health=self.health()
        checked=self.rpc.call('validate_address',{'address':destination,'any_net_type':False,'allow_openalias':False})
        if not checked.get('valid') or checked.get('nettype')!=self.network:
            raise TransferError('Invalid Monero destination for selected network; no OpenAlias.')
        amount_atomic=units(amount_decimal(amount,12,'Monero amount'),12)
        fee_cap=units(amount_decimal(max_fee,12,'maximum network fee'),12)
        bal=self.balance()
        unlocked=int(Decimal(bal['unlocked'])*ATOMIC)
        if amount_atomic+fee_cap>unlocked:raise TransferError('Unlocked XMR insufficient for amount and selected fee cap.')
        ident=self.journal.new(chain='XMR',network=self.network,source=health['address'],destination=destination,
            asset='XMR',amount_units=amount_atomic,max_fee_units=fee_cap,
            payload={'account_index':0,'wallet_height':health['wallet_height']})
        try:
            planned=self.rpc.call('transfer',{'destinations':[{'address':destination,'amount':amount_atomic}],
                           'account_index':0,'priority':1,'unlock_time':0,'do_not_relay':True,
                           'get_tx_metadata':True})
            fee=int(planned.get('fee',-1));txid=planned.get('tx_hash','')
            metadata=planned.get('tx_metadata','')
            if not isinstance(metadata,str) or not metadata or not TXID.fullmatch(txid or ''):
                raise TransferError('Monero did not return usable prepared transfer metadata.')
            if int(planned.get('amount',-1))!=amount_atomic or fee<=0 or fee>fee_cap or amount_atomic+fee>unlocked:
                raise TransferError('Prepared Monero amount/fee failed user-defined safety checks.')
            self._session_metadata[ident]=metadata
            return self.journal.transition(ident,('PREPARING',),'PREPARED',tx_hash=txid,
                                           payload_json='{"network":"'+self.network+'","fee_atomic":'+str(fee)+'}')
        except Exception:
            self._session_metadata.pop(ident,None)
            # RPC may have constructed a transaction even when the request timed out.
            self.journal.transition(ident,('PREPARING',),'UNKNOWN')
            raise TransferError('Monero preparation uncertain/invalid. Wallet may have reserved outputs; review wallet-RPC history.')

    def cancel(self,ident):
        row=self.journal.get(ident)
        if row['chain']!='XMR' or row['network']!=self.network:raise TransferError('Wrong chain or Monero network.')
        if row['status'] not in ('PREPARED','UNSPENDABLE'):
            raise TransferError('Only unrelayed prepared transfers may be cancelled here.')
        if row['status']=='UNSPENDABLE':
            # A restarted client must check local wallet records before explicit
            # abandonment. Absence of history is not independently final proof.
            self.health()
            history=self.rpc.call('get_transfers',{'in':True,'out':True,'pending':True,'failed':True,'pool':True})
            if any(r.get('txid','').lower()==row['tx_hash'].lower()
                   for group in ('in','out','pending','failed','pool') for r in history.get(group,[])):
                raise TransferError('Prepared transaction found in Monero wallet history. Reconcile before another send.')
        self._session_metadata.pop(ident,None)
        return self.journal.transition(ident,('PREPARED',),'CANCELLED')

    def relay(self,ident,approval):
        row=self.journal.get(ident)
        if row['chain']!='XMR' or row['network']!=self.network or row['status']!='PREPARED':raise TransferError('Monero request cannot be relayed in this state.')
        amount=Decimal(int(row['amount_units']))/ATOMIC
        expected=f"SEND {amount:f} XMR {row['destination'][-8:]}"
        if approval!=expected:raise TransferError('Exact Monero authorization required.')
        metadata=self._session_metadata.pop(ident,None)
        if not metadata:
            # Restarted application cannot safely relay absent relay metadata.
            self.journal.transition(ident,('PREPARED',),'UNSPENDABLE')
            raise TransferError('Prepared relay metadata unavailable after restart; never reprepare blindly. Review Monero wallet history.')
        self.journal.transition(ident,('PREPARED',),'BROADCASTING')
        try:
            sent=self.rpc.call('relay_tx',{'hex':metadata})
            if sent.get('tx_hash','').lower()!=row['tx_hash'].lower():
                raise TransferError('Monero wallet returned a different hash.')
            return self.journal.transition(ident,('BROADCASTING',),'PENDING')
        except Exception:
            self.journal.transition(ident,('BROADCASTING',),'UNKNOWN')
            raise TransferError('Monero relay result UNKNOWN. Check transaction ID through wallet-RPC; do not send again.')

    def reconcile(self,ident):
        row=self.journal.get(ident)
        if row['chain']!='XMR' or row['network']!=self.network:raise TransferError('Not a matching Monero network transaction.')
        if row['status'] not in ('BROADCASTING','UNKNOWN','PENDING','CONFIRMED','REORG_REVIEW') or not row['tx_hash']:
            return row
        self.health()
        try:
            result=self.rpc.call('get_transfer_by_txid',{'txid':row['tx_hash'],'account_index':0})
            item=result.get('transfer') or {}
        except Exception:
            # Not found != failed. Keep the original intent for later reconciliation.
            return self.journal.transition(ident,(row['status'],),'UNKNOWN',confirmations=0)
        if item.get('txid','').lower()!=row['tx_hash'].lower():
            raise TransferError('Monero transaction ID mismatch in wallet history.')
        kind=str(item.get('type','')).lower()
        actual_amount=item.get('amount')
        if kind not in ('out','pending','pool','failed') or actual_amount is None or int(actual_amount)!=int(row['amount_units']):
            return self.journal.transition(ident,(row['status'],),'REQUIRES_REVIEW')
        confirmations=max(0,int(item.get('confirmations',0)))
        status=('FAILED' if kind=='failed' else ('CONFIRMED' if confirmations>=10 else 'PENDING'))
        if status=='FAILED':
            # Can't infer whether funds are safely released; needs manual review.
            status='UNKNOWN'
        if row['status']=='CONFIRMED' and confirmations<10:
            status='REORG_REVIEW'
        return self.journal.transition(ident,(row['status'],),status,confirmations=confirmations)
