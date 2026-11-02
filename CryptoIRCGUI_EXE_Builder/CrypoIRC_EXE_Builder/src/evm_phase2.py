"""Phase 2: conservative EVM transaction coordinator.

Explicit network & signer, per-account durable nonce reservation, EIP-1559
caps, token checks, broadcast ambiguity and receipt/reorg reconciliation.
No secret/signed raw transaction is written to the journal.
"""
from __future__ import annotations
from decimal import Decimal
from pathlib import Path
import re
from chain_journal import ChainJournal
from core.transfer import TransferError,COIN_NETWORKS,ERC20_ABI,amount_decimal,units,safe_evm_rpc_url,load_keystore_header,evm_fee_params

NETWORKS = {k:(v[1],v[2]) for k,v in COIN_NETWORKS.items()}
NETWORKS['SEPOLIA']=(11155111,'ETH')
HASH_RE=re.compile(r'0x[0-9a-fA-F]{64}\Z')

def _hex(v):
    return v.hex() if isinstance(v,bytes) else str(v)

class EVMPhaseTwo:
    def __init__(self,code,rpc_url,journal=None,w3=None,confirmation_depth=12):
        code=code.upper().strip()
        if code not in NETWORKS:raise TransferError('Unsupported EVM network.')
        self.code=code;self.chain_id,self.gas_asset=NETWORKS[code]
        self.rpc_url=safe_evm_rpc_url(rpc_url)
        self.journal=journal or ChainJournal()
        self.depth=confirmation_depth
        if not 1<=self.depth<=256:raise TransferError('Invalid finality policy.')
        if w3 is None:
            try:from web3 import Web3
            except ImportError as e:raise TransferError('web3 dependency required.') from e
            w3=Web3(Web3.HTTPProvider(self.rpc_url,request_kwargs={'timeout':20}))
        self.w3=w3

    def health(self):
        if int(self.w3.eth.chain_id)!=self.chain_id:raise TransferError('RPC is on wrong EVM chain. Refusing.')
        block=int(self.w3.eth.block_number)
        if block<1:raise TransferError('RPC chain height unavailable.')
        return {'chain':self.code,'chain_id':self.chain_id,'block':block}

    def _address(self,raw):
        w=self.w3
        if not w.is_address(raw):raise TransferError('Invalid EVM address.')
        return w.to_checksum_address(raw)

    def balance(self,address,token=None):
        self.health();address=self._address(address)
        wei=int(self.w3.eth.get_balance(address))
        data={'native':str(Decimal(wei)/Decimal(10**18)), 'gas_asset':self.gas_asset,'block':int(self.w3.eth.block_number)}
        if token:
            contract=self._contract(token)
            decimals=int(contract.functions.decimals().call())
            data['token_contract']=self._address(token)
            data['token_symbol']=str(contract.functions.symbol().call())
            data['token_units']=str(contract.functions.balanceOf(address).call())
            data['decimals']=decimals
            data['token_balance']=str(Decimal(data['token_units'])/Decimal(10**decimals))
        return data

    def _contract(self,address):
        addr=self._address(address)
        if not self.w3.eth.get_code(addr):raise TransferError('No token contract deployed on selected chain.')
        return self.w3.eth.contract(address=addr,abi=ERC20_ABI)

    def prepare(self,keystore_path,recipient,amount,max_fee,*,token_contract='',expected_symbol='',expected_decimals=None):
        self.health()
        # Metadata only; do not decrypt until the user explicitly authorizes send.
        _,ks_address=load_keystore_header(Path(keystore_path))
        sender=self._address(ks_address);recipient=self._address(recipient)
        if sender.lower()==recipient.lower():raise TransferError('Cannot send to same account.')
        token=bool(token_contract)
        if token:
            if not expected_symbol or expected_decimals is None:
                raise TransferError('Token contract must be independently checked: enter its expected symbol and decimals.')
            contract=self._contract(token_contract)
            decimals=int(contract.functions.decimals().call())
            symbol=str(contract.functions.symbol().call())
            if not 0<=decimals<=36 or decimals != int(expected_decimals) or symbol!=expected_symbol:
                raise TransferError('Token symbol/decimals do not match expected values. Verify the exact contract independently.')
            raw_amount=units(amount_decimal(amount,decimals),decimals)
            balance=int(contract.functions.balanceOf(sender).call())
            if balance < raw_amount:raise TransferError('Insufficient token balance.')
            data=contract.encode_abi('transfer',args=[recipient,raw_amount])
            to=self._address(token_contract);value=0;asset=symbol
        else:
            raw_amount=units(amount_decimal(amount,18),18)
            to=recipient;value=raw_amount;data='0x';asset=self.gas_asset
        # max_fee specified in native gas currency, NEVER token units.
        fee_cap=units(amount_decimal(max_fee,18,'maximum native-coin network fee'),18)
        nonce=int(self.w3.eth.get_transaction_count(sender,'pending'))
        tx={'chainId':self.chain_id,'nonce':nonce,'to':to,'value':value,'data':data,'from':sender}
        gas=int(self.w3.eth.estimate_gas(tx))
        if gas<=0 or gas>15_000_000:raise TransferError('Unsafe gas estimate.')
        gas=min(int(gas*1.2)+1000,15_000_000)
        fee_fields,max_cost=evm_fee_params(self.w3,gas)
        if max_cost>fee_cap:raise TransferError('Estimated worst-case gas cost exceeds user-defined fee cap.')
        balance_native=int(self.w3.eth.get_balance(sender))
        if balance_native < value+max_cost:raise TransferError('Insufficient native-coin balance for amount and worst-case fee.')
        tx.pop('from');tx.update({'gas':gas,**fee_fields})
        # Conservative per-account outstanding send lock spans process restarts.
        ident=self.journal.new(chain='EVM',network=str(self.chain_id),source=sender,destination=recipient,
            asset=asset,amount_units=raw_amount,max_fee_units=fee_cap,nonce=nonce,
            payload={'tx':tx,'token_contract':to if token else None,'decimals':decimals if token else 18,
                     'network_label':self.code,'gas_max_wei':max_cost})
        self.journal.transition(ident,('PREPARING',),'PREPARED')
        return self.journal.get(ident)

    def cancel(self,ident):
        row=self.journal.get(ident)
        if row['chain']!='EVM' or row['network']!=str(self.chain_id):raise TransferError('Wrong EVM chain.')
        return self.journal.transition(ident,('PREPARED',),'CANCELLED')

    def submit(self,ident,approval,keystore_path,password):
        row=self.journal.get(ident)
        if row['chain']!='EVM' or row['network']!=str(self.chain_id) or row['status']!='PREPARED':
            raise TransferError('Transaction is no longer prepared. Cannot rebroadcast.')
        amount=Decimal(row['amount_units'])/Decimal(10**row['payload']['decimals'])
        expected=f"SEND {amount:f} {row['asset']} {row['destination'][-8:]}"
        if approval!=expected:raise TransferError('Full send authorization did not match.')
        self.health()
        _,addr=load_keystore_header(Path(keystore_path))
        if addr.lower()!=row['source'].lower():raise TransferError('Signer does not match the prepared source address.')
        pending=int(self.w3.eth.get_transaction_count(row['source'],'pending'))
        if pending!=row['nonce']:
            raise TransferError('Network account nonce changed. Cancel and review; never silently re-sign.')
        try:from eth_account import Account
        except ImportError as e:raise TransferError('eth-account missing.') from e
        rawdata=Path(keystore_path).read_text(encoding='utf-8')
        import json
        key=Account.decrypt(json.loads(rawdata),password)
        account=Account.from_key(key)
        if account.address.lower()!=row['source'].lower():raise TransferError('Decrypted keystore address mismatch.')
        signed=account.sign_transaction(row['payload']['tx'])
        if Account.recover_transaction(signed.raw_transaction).lower()!=row['source'].lower():
            raise TransferError('Signed sender verification failed.')
        txhash=_hex(signed.hash)
        if not txhash.startswith('0x'):txhash='0x'+txhash
        if not HASH_RE.fullmatch(txhash):raise TransferError('Invalid signed transaction hash.')
        # Persist the identity BEFORE a network call; timeout is ambiguous.
        self.journal.transition(ident,('PREPARED',),'BROADCASTING',tx_hash=txhash)
        try:
            returned=_hex(self.w3.eth.send_raw_transaction(signed.raw_transaction))
            if not returned.startswith('0x'):returned='0x'+returned
            if returned.lower()!=txhash.lower():raise TransferError('Node returned a different transaction hash.')
            return self.journal.transition(ident,('BROADCASTING',),'PENDING')
        except Exception:
            self.journal.transition(ident,('BROADCASTING',),'UNKNOWN')
            # IMPORTANT: never auto-resign or resend on RPC failures.
            raise TransferError('EVM broadcast result UNKNOWN. Reconcile the original hash; do not send again.')

    def reconcile(self,ident):
        row=self.journal.get(ident)
        if row['chain']!='EVM' or row['network']!=str(self.chain_id):raise TransferError('Wrong EVM transaction network.')
        if row['status'] not in ('BROADCASTING','UNKNOWN','PENDING','CONFIRMED','REORG_REVIEW'):
            return row
        self.health()
        if not row['tx_hash']:return row
        try:
            receipt=self.w3.eth.get_transaction_receipt(row['tx_hash'])
        except Exception as exc:
            # Web3 raises TransactionNotFound for unknown and still-pending hashes.
            if type(exc).__name__ != 'TransactionNotFound':
                raise TransferError('RPC receipt lookup unavailable; transaction result remains uncertain.') from exc
            receipt=None
        # Web3 raises TransactionNotFound; treat as still unknown if no authoritative receipt.
        if receipt is None:
            target='REORG_REVIEW' if row['status']=='CONFIRMED' else 'UNKNOWN'
            return self.journal.transition(ident,(row['status'],),target,confirmations=0)
        block_hash=_hex(receipt.get('blockHash',''))
        if not block_hash.startswith('0x'):block_hash='0x'+block_hash
        if row['block_hash'] and row['block_hash'].lower()!=block_hash.lower():
            return self.journal.transition(ident,(row['status'],),'REORG_REVIEW',block_hash=block_hash,confirmations=0)
        # An ERC-20 receipt with status=1 is NOT sufficient proof of delivery.
        # Check an exact Transfer event from the expected contract, sender, recipient and value.
        if row['payload'].get('token_contract'):
            transfer_sig='ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
            contract=row['payload']['token_contract'].lower()
            found=False
            for item in receipt.get('logs',[]) or []:
                topics=item.get('topics',[])
                def topic_hex(t):
                    return (_hex(t).removeprefix('0x')).lower()
                if (str(item.get('address','')).lower()==contract and len(topics)>=3 and
                    topic_hex(topics[0])==transfer_sig and
                    topic_hex(topics[1])[-40:]==row['source'][2:].lower() and
                    topic_hex(topics[2])[-40:]==row['destination'][2:].lower() and
                    int(topic_hex(item.get('data','0')),16)==int(row['amount_units'])):
                    found=True;break
            if not found and int(receipt.get('status',-1))==1:
                return self.journal.transition(ident,(row['status'],),'REQUIRES_REVIEW',
                     block_hash=block_hash,confirmations=0)
        status=int(receipt.get('status',-1));block=int(receipt.get('blockNumber',0))
        if status not in (0,1) or block<=0:raise TransferError('Receipt does not yet prove transaction execution.')
        count=max(0,int(self.w3.eth.block_number)-block+1)
        target='REVERTED' if status==0 else ('CONFIRMED' if count>=self.depth else 'PENDING')
        return self.journal.transition(ident,(row['status'],),target,block_hash=block_hash,confirmations=count)
