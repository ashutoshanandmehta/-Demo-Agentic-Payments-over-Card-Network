"""Verify purchase permission, then create the approved scope mandate."""
import time
from common import *


def spin(label,seconds=2):
    frames='|/-\\';steps=10
    for n in range(steps):
        print(f'\r{label} {frames[n%len(frames)]}',end='',flush=True)
        time.sleep(seconds/steps)
    print(f'\r{label} complete.      ',flush=True)


def verify(s,args):
    p=s['permission'];c=s['checkout'];i=s['intent'];b=s['budget']
    checks={'user_permission_signature':check_signature(p,s['user_signing_key']),'merchant_checkout_signature':check_signature(c,s['merchant_signing_key']),'checkout_hash':digest(checkout_body(c))==c['checkout_hash'],'agent_matches':p['agent_id']==i['agent_id'],'merchant_allowed':c['merchant_id'] in p['allowed_merchants'],'category_matches':c['category']==p['category']==i['category'],'currency_matches':c['currency']==p['currency']==i['currency'],'address_matches':c['address']==p['address'] and c['postal_code']==p['postal_code'],'transaction_limit':c['amount_minor']<=p['transaction_limit_minor'],'monthly_limit':b['captured_minor']+b['reserved_minor']+c['amount_minor']<=p['monthly_limit_minor'],'permission_unexpired':valid_until(p['expires_at']),'checkout_unexpired':valid_until(c['expires_at']),'not_revoked':not p['revoked'],'budget_month_current':b['month']==(now()+timedelta(hours=5,minutes=30)).strftime('%Y-%m')}
    ok=all(checks.values());failed=[k for k,v in checks.items() if not v]
    reason='ALL_CONSTRAINTS_SATISFIED' if ok else {'monthly_limit':'MONTHLY_LIMIT_EXCEEDED','transaction_limit':'TRANSACTION_LIMIT_EXCEEDED','permission_unexpired':'PERMISSION_EXPIRED','checkout_unexpired':'CHECKOUT_EXPIRED','not_revoked':'PERMISSION_REVOKED','checkout_hash':'CHECKOUT_HASH_INVALID'}.get(failed[0],failed[0].upper())
    s['verification']={'decision':'approved' if ok else 'declined','reason_code':reason,'checks':checks,'failed_checks':failed,'permission_id':p['permission_id'],'checkout_hash':c['checkout_hash']}
    before=dict(b)
    if ok:
        b['reserved_minor']+=c['amount_minor'];s['reservation']={'reservation_id':'reservation-101','order_id':c['order_id'],'amount_minor':c['amount_minor'],'status':'active'}
    return ({'permission':p,'checkout':c,'monthly_spend_before_minor':before['captured_minor'],'monthly_limit_minor':p['monthly_limit_minor']},['Verify authenticated permission and checkout; reserve against the monthly cap only on approval.'],{'decision':s['verification']['decision'],'reason_code':reason,'verification':s['verification'],'budget_after':b,'reservation':s.get('reservation')},ok)


def create_mandate(s,args):
    p=live_permission(s);c=trusted_checkout(s);require(s['verification']['decision']=='approved','VERIFIER_NOT_APPROVED')
    minutes=args.expires_in_minutes
    require(minutes>0,'Mandate lifetime must be positive.')
    ends=min(expiry(minutes),p['expires_at'],c['expires_at'])
    scope={'scope_id':'scope-101','permission_id':p['permission_id'],'user_id':p['user_id'],'agent_id':p['agent_id'],'merchant_id':c['merchant_id'],'order_id':c['order_id'],'items':c['items'],'category':c['category'],'amount_minor':c['amount_minor'],'currency':c['currency'],'address':c['address'],'postal_code':c['postal_code'],'checkout_hash':c['checkout_hash'],'reservation_id':s['reservation']['reservation_id'],'expires_at':ends,'single_use':True}
    s['scope']=sign(scope,s['verifier_signing_key'])
    return ({'verification':s['verification'],'reservation':s['reservation']},['Create a signed, single-checkout approved scope mandate.'],s['scope'],True)


def main():
    p=parser(__doc__);p.add_argument('--expires_in_minutes','--expires-in-minutes',dest='expires_in_minutes',type=int,default=60,help=argparse.SUPPRESS);args=p.parse_args()
    require(args.expires_in_minutes>0,'Mandate lifetime must be positive.')
    print('Verifying permission and checkout...');spin('Verifying')
    try:execute(11,'Verify permission and reserve monthly budget',verify,args,show_next_step=False)
    except SystemExit:
        state=json.loads((Path(args.state_dir)/'state.json').read_text(encoding='utf-8'))
        if state.get('verification',{}).get('decision')=='declined':
            print('Declined. Do not call credential_service.py.');return
        raise
    print('Creating approved scope mandate...');spin('Preparing mandate')
    execute(12,'Create approved scope mandate',create_mandate,args,show_next_step=False)

if __name__=='__main__':
    try:main()
    except (DemoError,ValueError,KeyError,OSError) as e:print('\nBLOCKED: '+str(e),file=sys.stderr);raise SystemExit(2)
