"""Authenticate the merchant API request, redeem its SPT, and build authorization."""
from common import *


def validate_request(s,args):
    require('merchant_account' in s and 'scoped_token' in s,'RUN_TOKEN_ISSUANCE_FIRST')
    require(args.merchant_api_key==s['merchant_account']['api_key'],'MERCHANT_API_KEY_INVALID')
    require(s['merchant_account']['status']=='active','MERCHANT_ACCOUNT_INVALID')
    data=args.payment_input
    require(isinstance(data,dict),'MERCHANT_INPUT_MUST_BE_JSON_OBJECT')
    token_id=data.get('SPT') or data.get('STP')
    require(isinstance(token_id,str) and bool(token_id),'SPT_REQUIRED')
    if 'SPT' in data and 'STP' in data:
        require(data['SPT']==data['STP'],'SPT_ALIAS_MISMATCH')
    required=('checkout_id','order_id','amount_minor','currency','checkout_hash','idempotency_key')
    require(all(k in data for k in required),'MERCHANT_INPUT_MISSING_FIELDS')
    require(set(data)<=set(required)|{'SPT','STP'},'MERCHANT_INPUT_UNSUPPORTED_FIELDS')
    require(type(data['amount_minor']) is int and data['amount_minor']>0,'INVALID_AMOUNT_MINOR')
    require(all(isinstance(data[k],str) and data[k].strip() for k in required if k!='amount_minor'),
            'INVALID_MERCHANT_INPUT_VALUE')
    c=s['checkout'];t=s['scoped_token'];m=s['merchant_account']
    require(t['token_id']==token_id,'SPT_NOT_FOUND')
    require(t['seller_profile']==m['stripe_profile_id'],'SPT_SELLER_MISMATCH')
    require(data['checkout_id']==c['checkout_id'],'CHECKOUT_ID_MISMATCH')
    require(data['order_id']==c['order_id']==t['order_id'],'ORDER_ID_MISMATCH')
    require(data['amount_minor']==c['amount_minor']==t['amount_minor'],'AMOUNT_MINOR_MISMATCH')
    require(data['currency']==c['currency']==t['currency'],'CURRENCY_MISMATCH')
    require(data['checkout_hash']==c['checkout_hash']==t['checkout_hash'],'CHECKOUT_HASH_MISMATCH')
    submission={'authenticated_merchant_account':m['merchant_account_id'],'order_id':data['order_id'],'amount_minor':data['amount_minor'],'currency':data['currency'],'scoped_token':token_id,'checkout_hash':data['checkout_hash'],'idempotency_key':data['idempotency_key']}
    if 'submission' in s:
        require(s['submission']==submission,'IDEMPOTENCY_REQUEST_MISMATCH')
    if 'payment' not in s:
        live_permission(s);trusted_checkout(s)
        scope=s['scope']
        require(check_signature(scope,s['verifier_signing_key']),'SCOPE_SIGNATURE_INVALID')
        require(valid_until(scope['expires_at']),'SCOPE_EXPIRED')
        require(valid_until(t['expires_at']),'TOKEN_EXPIRED')
        require(not t['revoked'],'TOKEN_REVOKED')
        require(t['status']=='issued','TOKEN_ALREADY_REDEEMED')
        require(s['reservation']['status']=='active','BUDGET_RESERVATION_NOT_ACTIVE')
    return submission


def submit(s,args):
    s['submission']=validate_request(s,args)
    data=args.payment_input;token_id=s['submission']['scoped_token']
    return ({'merchant_authenticated':True,'checkout_id':data['checkout_id'],'order_id':data['order_id'],'amount_minor':data['amount_minor'],'currency':data['currency'],'SPT':token_id,'idempotency_key':data['idempotency_key']},['Authenticate Blinkit API key; read scoped payment source from the provider-side token record.'],{'merchant_api_request':'accepted','submission':s['submission']},True)


def redeem(s,args):
    live_permission(s);c=trusted_checkout(s);t=s['scoped_token'];r=s['submission'];m=s['merchant_account'];scope=s['scope']
    require(check_signature(scope,s['verifier_signing_key']),'SCOPE_SIGNATURE_INVALID');require(valid_until(t['expires_at']),'TOKEN_EXPIRED');require(not t['revoked'],'TOKEN_REVOKED');require(t['status']=='issued','TOKEN_ALREADY_REDEEMED');require(s['reservation']['status']=='active','BUDGET_RESERVATION_NOT_ACTIVE');require(m['status']=='active' and r['authenticated_merchant_account']==m['merchant_account_id'],'MERCHANT_ACCOUNT_INVALID');require(t['merchant_id']==m['merchant_id'],'MERCHANT_MISMATCH')
    for k in ('amount_minor','currency','order_id','checkout_hash'):require(r[k]==t[k]==scope[k]==c[k],k.upper()+'_MISMATCH')
    t['status']='redeemed';s['payment']={'payment_id':'pay-501','merchant_account_id':m['merchant_account_id'],'order_id':r['order_id'],'payment_method_id':t['payment_method_id'],'agent_id':t['agent_id'],'amount_minor':r['amount_minor'],'currency':r['currency'],'status':'created','idempotency_key':r['idempotency_key']}
    return ({'merchant_submission':r,'SPT':t['token_id']},['Consume the seller-bound SPT once and resolve its saved payment reference within the processor.'],{'redemption_status':'accepted','payment_id':'pay-501','SPT_status':t['status']},True)


def resolve(s,args):
    p=s['payment'];v=s['vault'];require(p['payment_method_id']==v['payment_method_id'] and v['status']=='active','VAULT_REFERENCE_INVALID')
    s['resolved_credential']={'network':'RuPay','vault_reference':v['payment_method_id'],'cryptogram':'crypt_demo_'+secrets.token_hex(16),'payment_id':p['payment_id']}
    return ({'payment_id':p['payment_id'],'SPT_redeemed':True},['Request a synthetic card-network cryptogram using the vault token.'],{'network_request':{'network':'RuPay','operation':'request_transaction_cryptogram','payment_id':p['payment_id']},'network_token_resolved':True,'cryptogram_generated':True,'payment_id':p['payment_id']},True)


def authorize_request(s,args):
    live_permission(s);p=s['payment'];m=s['merchant_account'];c=s['resolved_credential']
    request={'payment_id':p['payment_id'],'amount_minor':p['amount_minor'],'currency':p['currency'],'merchant_id':m['network_merchant_id'],'merchant_category':s['checkout']['category'],'network':'RuPay','network_token_id':s['vault']['network_token_id'],'cryptogram':c['cryptogram'],'transaction_type':'proposed_agent_delegated_purchase','scope_reference':s['scope']['scope_id']}
    public={k:v for k,v in request.items() if k not in ('network_token_id','cryptogram')};public.update({'network_token_id':'[processor-only credential]','cryptogram':'[processor-only cryptogram]'})
    s['authorization_request']=public
    c.pop('cryptogram',None)
    return ({'payment_id':p['payment_id'],'credential_resolved':True},['Build authorization request; hide backing network credentials from the merchant.'],public,True)


def main():
    p=parser(__doc__);p.add_argument('--merchant-api-key',required=True);p.add_argument('--input',required=True,help='Merchant JSON request.');args=p.parse_args()
    try:args.payment_input=json.loads(args.input)
    except json.JSONDecodeError as e:raise DemoError('Invalid JSON passed to --input.') from e
    folder=Path(args.state_dir).resolve()
    with locked(folder):
        require((folder/'state.json').exists(),'RUN_CARD_SETUP_FIRST')
        state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
        validate_request(state,args)
    stages=[(14,'Authenticate merchant payment request',submit),(15,'Redeem SPT and create processor payment',redeem),(16,'Resolve vaulted network credential',resolve),(17,'Construct card-network authorization request',authorize_request)]
    for n,title,fn in stages:execute(n,title,fn,args,show_next_step=False)

if __name__=='__main__':
    try:main()
    except (DemoError,ValueError,KeyError,OSError) as e:print('\nBLOCKED: '+str(e),file=sys.stderr);raise SystemExit(2)
