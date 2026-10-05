"""Have the trusted backend issue a simulated seller-scoped Stripe SPT."""
from common import *


def validate_issuance(s,args):
    require(s.get('verification',{}).get('decision')=='approved' and 'scope' in s,
            'VERIFIER_NOT_APPROVED')
    p=live_permission(s);c=trusted_checkout(s);scope=s['scope'];vault=s['vault'];merchant=s['merchant_account']
    require(args.approved_scope_mandate==scope['scope_id'],'APPROVED_SCOPE_MANDATE_NOT_FOUND')
    require(args.saved_payment==vault['payment_method_id'],'SAVED_PAYMENT_NOT_FOUND')
    require(check_signature(scope,s['verifier_signing_key']),'SCOPE_SIGNATURE_INVALID')
    require(valid_until(scope['expires_at']),'SCOPE_EXPIRED')
    require(scope['checkout_hash']==c['checkout_hash'],'SCOPE_CHECKOUT_MISMATCH')
    require(vault['status']=='active' and vault['customer_id']=='cus_user_77','PAYMENT_REFERENCE_INVALID')
    require(scope['user_id']==p['user_id']=='user-77','USER_OWNERSHIP_MISMATCH')
    require(s['reservation']['status']=='active' or s.get('scoped_token'),
            'BUDGET_RESERVATION_NOT_ACTIVE')
    return scope,vault,merchant


def work(s,args):
    scope,vault,merchant=validate_issuance(s,args)
    expires_at=int(datetime.fromisoformat(scope['expires_at']).timestamp())
    body={'payment_method':vault['payment_method_id'],'seller_details':{'network_business_profile':merchant['stripe_profile_id']},'usage_limits':{'currency':scope['currency'].lower(),'max_amount':scope['amount_minor'],'expires_at':expires_at}}
    request={'method':'POST','endpoint':'/v1/shared_payment/issued_tokens',
             'authentication':'HTTP Basic [trusted backend Stripe secret key; redacted]',
             'headers':{'Stripe-Version':'2026-09-30.preview'},'body':body}
    token_id='spt_demo_'+secrets.token_hex(16)
    t={'token_id':token_id,'payment_method_id':vault['payment_method_id'],'scope_id':scope['scope_id'],'agent_id':scope['agent_id'],'merchant_id':scope['merchant_id'],'seller_profile':merchant['stripe_profile_id'],'order_id':scope['order_id'],'amount_minor':scope['amount_minor'],'currency':scope['currency'],'checkout_hash':scope['checkout_hash'],'expires_at':scope['expires_at'],'status':'issued','revoked':False,'single_use':True}
    s['scoped_token']=t;s['stripe_api_request']=request
    return ({'approved_scope_mandate':scope['scope_id'],'saved_payment':vault['payment_method_id'],'merchant_profile':merchant['stripe_profile_id']},['Trusted backend authenticates to the provider and issues a seller-bound SPT. No network request is made in this offline demo.'],{'provider_request':request,'simulated_provider_response':{'id':token_id,'object':'shared_payment.issued_token','status':'active','usage_limits':body['usage_limits']},'agent_visible_token':token_id},True)


def main():
    p=parser(__doc__);p.add_argument('--approved_scope_mandate',required=True);p.add_argument('--saved_payment',required=True);args=p.parse_args()
    folder=Path(args.state_dir).resolve()
    with locked(folder):
        require((folder/'state.json').exists(),'RUN_CARD_SETUP_FIRST')
        validate_issuance(json.loads((folder/'state.json').read_text(encoding='utf-8')),args)
    execute(13,'Trusted backend issues seller-scoped SPT',work,args,show_next_step=False)

if __name__=='__main__':
    try:main()
    except (DemoError,ValueError,KeyError,OSError) as e:print('\nBLOCKED: '+str(e),file=sys.stderr);raise SystemExit(2)
