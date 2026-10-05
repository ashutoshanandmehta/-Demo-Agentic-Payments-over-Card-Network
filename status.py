"""Show per-agent permission, spend, delivery details, and transaction history."""
from common import *


def normalize_agent_id(value):
    value=str(value).strip()
    return 'shopping-agent-'+value if value.isdigit() else value


def revoke_permission(s,agent,record):
    current=s.get('permission',{})
    permission=record.get('permission') or (current if current.get('agent_id')==agent else {})
    require(bool(permission),'AGENT_PERMISSION_NOT_FOUND')
    require(check_signature(permission,s['user_signing_key']),'USER_PERMISSION_SIGNATURE_INVALID')
    body={k:v for k,v in permission.items() if k!='signature'}
    body['revoked']=True
    updated=sign(body,s['user_signing_key'])
    record.update({'permission':updated,'revoked':True,'revoked_at':stamp()})
    if current.get('agent_id')==agent:
        s['permission']=updated
        token=s.get('scoped_token',{})
        if token.get('agent_id')==agent and token.get('status')=='issued':
            token['revoked']=True
        reservation=s.get('reservation',{})
        if (reservation.get('status')=='active' and
            s.get('payment',{}).get('status') not in ('authorized','captured','settled')):
            s['budget']['reserved_minor']-=reservation['amount_minor']
            reservation['status']='released'
    s['events'].append({'event':'permission.revoked','agent_id':agent,'at':stamp()})
    sync_agent_records(s)
    return {'agent_id':agent,'permission_id':body['permission_id'],'revoked':True}


def agent_status(s,agent,record):
    current=s.get('permission',{})
    active=current.get('agent_id')==agent
    permission=current if active else record.get('permission',{})
    budget=s.get('budget',{}) if active else record.get('budget',{})
    transactions=[dict(t) for t in s.get('transaction_history',[]) if t['agent_id']==agent]
    checkout=s.get('checkout',{}) if active else {}
    if checkout and not any(t['order_id']==checkout['order_id'] for t in transactions):
        payment=s.get('payment',{})
        transactions.append({'order_id':checkout['order_id'],'checkout_id':checkout['checkout_id'],
                             'merchant':checkout['merchant_id'],'amount_minor':checkout['amount_minor'],
                             'currency':checkout['currency'],'payment_status':payment.get('status','checkout_created'),
                             'payment_id':payment.get('payment_id')})
    for transaction in transactions:
        transaction['amount']=show_money(transaction.pop('amount_minor'))
    return {
        'agent_id':agent,'permission_id':permission.get('permission_id',record.get('permission_id')),
        'permission_revoked':permission.get('revoked',record.get('revoked',False)),
        'category':permission.get('category',record.get('category')),
        'merchant':(permission.get('allowed_merchants') or record.get('allowed_merchants') or [None])[0],
        'transaction_cap':show_money(permission.get('transaction_limit_minor',record.get('transaction_limit_minor',0))),
        'monthly_cap':show_money(permission.get('monthly_limit_minor',record.get('monthly_limit_minor',0))),
        'budget_month':budget.get('month'),
        'already_spent_this_month':show_money(budget.get('captured_minor',0)),
        'reserved':show_money(budget.get('reserved_minor',0)),
        'delivery_address':permission.get('address',record.get('address')),
        'postal_code':permission.get('postal_code',record.get('postal_code')),
        'expires_at':permission.get('expires_at'),
        'transaction_history':transactions,
        'workflow_history':[e for e in s.get('events',[]) if e.get('agent_id')==agent],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--agent_id','--agent-id','---agent_id',dest='agent_id')
    p.add_argument('--revoke',action='store_true',help='Revoke this agent\'s permission for future payments.')
    p.add_argument('--state-dir',default=str(BASE/'demo_state'))
    args=p.parse_args();folder=Path(args.state_dir).resolve()
    with locked(folder):
        path=folder/'state.json'
        require(path.exists(),'No demo state found. Run setup and permission commands first.')
        s=json.loads(path.read_text(encoding='utf-8'));records=s.get('agent_permissions',{})
        current=s.get('permission',{})
        if not records and current:
            records={current['agent_id']:{'permission':current,'budget':s.get('budget',{})}}
            s['agent_permissions']=records
        if args.agent_id:
            agent=normalize_agent_id(args.agent_id)
            require(agent in records,'AGENT_NOT_FOUND')
            if args.revoke:
                result=revoke_permission(s,agent,records[agent]);atomic_json(path,s)
                print(json.dumps(result,indent=2));return
            chosen={agent:records[agent]}
        else:
            require(not args.revoke,'--agent_id is required with --revoke.')
            chosen=records
        print(json.dumps({'agents':[agent_status(s,a,r) for a,r in chosen.items()]},indent=2,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except (DemoError,ValueError,KeyError,OSError) as e:
        print('BLOCKED: '+str(e),file=sys.stderr);raise SystemExit(2)
