"""Shared utilities for an OFFLINE, single-merchant teaching simulation.
No payment APIs, real credentials, network requests, or production security.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys

BASE = Path(__file__).resolve().parent

class DemoError(Exception):
    pass

def require(condition, message):
    if not condition:
        raise DemoError(message)

def now():
    return datetime.now(timezone.utc)

def stamp():
    return now().isoformat()

def expiry(minutes):
    return (now() + timedelta(minutes=minutes)).isoformat()

def valid_until(value):
    return datetime.fromisoformat(value) > now()

def money(value):
    try:
        x = Decimal(str(value))
        require(x.is_finite() and x >= 0 and x*100 == (x*100).to_integral_value(),
                'Money must be nonnegative, with at most 2 decimal places.')
        return int(x * 100)
    except InvalidOperation:
        raise DemoError('Enter a number such as 185 or 185.50.')

def show_money(value):
    return f'INR {value / 100:.2f}'

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()

def signed(obj, key):
    return hmac.new(bytes.fromhex(key), json.dumps(obj, sort_keys=True,
                    separators=(',', ':'), ensure_ascii=False).encode(), hashlib.sha256).hexdigest()

def check_signature(obj, key):
    payload = {k: v for k, v in obj.items() if k != 'signature'}
    return hmac.compare_digest(obj['signature'], signed(payload, key))

def sign(obj, key):
    return dict(obj, signature=signed(obj, key))

def checkout_body(c):
    return {k: v for k, v in c.items() if k not in ('checkout_hash', 'signature')}

def trusted_checkout(s):
    c = s['checkout']
    require(digest(checkout_body(c)) == c['checkout_hash'], 'CHECKOUT_HASH_MISMATCH')
    require(check_signature(c, s['merchant_signing_key']), 'MERCHANT_SIGNATURE_INVALID')
    require(valid_until(c['expires_at']), 'CHECKOUT_EXPIRED')
    return c

def live_permission(s):
    p=s['permission']
    require(check_signature(p, s['user_signing_key']), 'USER_PERMISSION_SIGNATURE_INVALID')
    require(not p['revoked'], 'PERMISSION_REVOKED')
    require(valid_until(p['expires_at']), 'PERMISSION_EXPIRED')
    return p

def pick(args, name, label, default, cast=str):
    value=getattr(args, name, None)
    if value is None:
        if args.non_interactive:
            value=default
        else:
            raw=input(f'{label} [{default}]: ').strip()
            value=raw if raw else default
    try:
        return cast(value)
    except (ValueError, TypeError):
        raise DemoError(f'Invalid value for {label}: {value}')

def parser(description):
    p=argparse.ArgumentParser(description=description)
    p.add_argument('--state-dir', default=str(BASE/'demo_state'),
                   help='Persisted state folder. Use another folder for an independent run.')
    p.add_argument('--non-interactive', action='store_true',
                   help='Use defaults for omitted input fields; never prompt.')
    return p

@contextmanager
def locked(folder):
    folder.mkdir(parents=True, exist_ok=True)
    lock=folder/'.lock'
    try:
        fd=os.open(str(lock), os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    except FileExistsError:
        raise DemoError('Another script is running (or stale .lock exists after a crash).')
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)

def atomic_json(path, obj):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    try:
        temp.chmod(0o600)
    except OSError:
        pass
    os.replace(temp, path)

def sync_agent_records(s):
    """Persist each agent's permission, budget, and payment history."""
    permission=s.get('permission')
    if permission:
        record=s.setdefault('agent_permissions',{}).setdefault(permission['agent_id'],{})
        record['permission']=dict(permission)
        record['budget']=dict(s.get('budget',{}))
        record['revoked']=permission['revoked']
    payment=s.get('payment')
    if not payment:
        return
    agent_id=payment.get('agent_id') or (permission or {}).get('agent_id')
    require(bool(agent_id),'PAYMENT_AGENT_NOT_FOUND')
    checkout=s['checkout']
    history=s.setdefault('transaction_history',[])
    entry=next((t for t in history if t['payment_id']==payment['payment_id']
                and t['agent_id']==agent_id),None)
    if entry is None:
        entry={'payment_id':payment['payment_id'],'agent_id':agent_id,
               'order_id':payment['order_id'],'checkout_id':checkout['checkout_id'],
               'merchant':checkout['merchant_id'],'created_at':stamp()}
        history.append(entry)
    entry.update({'amount_minor':payment['amount_minor'],'currency':payment['currency'],
                  'payment_status':payment['status'],'updated_at':stamp()})
    if 'captured_at' in payment:
        entry['captured_at']=payment['captured_at']
    if 'clearing' in s:
        entry['clearing_status']=s['clearing']['status']
    if 'payout' in s:
        entry['payout_status']=s['payout']['status']
        entry['payout_amount_minor']=s['payout']['amount_minor']

def execute(number, title, work, args, *, show_processing=False, show_next_step=True, quiet=False):
    """One script performs one step; later stages are never auto-run."""
    folder=Path(args.state_dir).resolve()
    try:
        with locked(folder):
            path=folder/'state.json'
            if path.exists():
                s=json.loads(path.read_text(encoding='utf-8'))
            else:
                s={'completed_step':0, 'created_at':stamp(), 'events':[],
                   'user_signing_key':secrets.token_hex(32),
                   'verifier_signing_key':secrets.token_hex(32),
                   'merchant_signing_key':secrets.token_hex(32)}
            if not quiet:
                print(f'\n=== STEP {number:02d}: {title} ===\nOFFLINE SIMULATION')
            if s['completed_step'] >= number:
                artifact=folder/f'{number:02d}_output.json'
                if not quiet:
                    print('Already completed: returning stored result; no new charge or event.')
                stored_result=json.loads(artifact.read_text(encoding='utf-8'))
                if not show_processing:
                    stored_result.pop('processing', None)
                if not quiet:
                    print(json.dumps(stored_result, indent=2, ensure_ascii=False))
                return
            require(s['completed_step'] == number-1,
                    f'Run step {s["completed_step"]+1:02d} first. Current request is step {number:02d}.')
            inputs, processing, output, completed=work(s,args)
            for label, value in ([] if quiet else [('INPUT',inputs), ('PROCESSING',processing), ('OUTPUT',output)]):
                if label == 'PROCESSING' and not show_processing:
                    continue
                print('\n'+label)
                print(json.dumps(value, indent=2, ensure_ascii=False))
            event={'step':number, 'stage':title, 'at':stamp(),
                   'completed':completed, 'output_digest':digest(output)}
            agent=(s.get('permission') or s.get('intent') or {}).get('agent_id')
            if agent:
                event['agent_id']=agent
            s['events'].append(event)
            if completed:
                s['completed_step']=number
            sync_agent_records(s)
            atomic_json(path,s)
            result={'step':number, 'title':title, 'input':inputs,
                    'processing':processing, 'output':output, 'completed':completed}
            atomic_json(folder/f'{number:02d}_output.json',result)
            if not quiet:
                print(f'\nSaved: {folder / f"{number:02d}_output.json"}')
            if not completed and not quiet:
                print('STOP: this step is not completed. Read the output before continuing.')
            elif completed and show_next_step and not quiet:
                print('Run the next command in README.md manually.')
            if not completed:
                raise SystemExit(2)
    except (DemoError, ValueError, KeyError, OSError) as e:
        print(f'\nBLOCKED: {e}',file=sys.stderr)
        raise SystemExit(2)
