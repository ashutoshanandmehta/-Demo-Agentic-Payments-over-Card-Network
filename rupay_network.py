"""Run RuPay authorization, capture, clearing, settlement, payout, and audit."""
from common import *


def authorize(s,args):
    p=s['payment'];request=s['authorization_request'];require(p['status']!='declined','PAYMENT_ALREADY_DECLINED: reset for a new run.')
    decision=pick(args,'decision','Issuer decision (approve/decline/challenge)','approve');require(decision in ('approve','decline','challenge'),'Choose approve, decline or challenge.')
    balance_default=str(Decimal(s.get('challenge_balance_minor',1000000))/100);balance=money(pick(args,'available_balance','Simulated available balance (INR)',balance_default))
    if s.get('challenge_pending'):decision='challenge'
    if decision=='challenge':
        otp=pick(args,'otp','Purchase OTP (leave blank to pause)','')
        if otp!='123456':
            s['challenge_pending']=True;s['challenge_balance_minor']=balance
            return ({'payment_id':p['payment_id'],'issuer_scenario':'challenge'},['Pause the same payment for simulated customer authentication.'],{'status':'requires_customer_action','challenge_type':'simulated_3ds_otp','message':'Rerun with --authorize --decision challenge --otp 123456.'},False)
        s['challenge_pending']=False
    if decision=='decline' or balance<p['amount_minor']:
        p['status']='declined';s['budget']['reserved_minor']-=s['reservation']['amount_minor'];s['reservation']['status']='released'
        return ({'payment_id':p['payment_id'],'available_balance_minor':balance},['Issuer declines; release the monthly budget reservation.'],{'status':'declined','reason':'ISSUER_DECLINE' if decision=='decline' else 'INSUFFICIENT_FUNDS','budget':s['budget']},False)
    require(p['status'] in ('created','authentication_pending'),'PAYMENT_NOT_AUTHORIZABLE');live_permission(s)
    require(valid_until(s['scoped_token']['expires_at']),'TOKEN_SCOPE_EXPIRED_BEFORE_AUTHORIZATION')
    p['status']='authorized';p['authorization_code']='AUTH_DEMO_7812';p['authorized_amount_minor']=p['amount_minor']
    s['issuer']={'available_before_minor':balance,'hold_minor':p['amount_minor'],'available_after_hold_minor':balance-p['amount_minor'],'posted_debit_minor':0}
    return ({'authorization_request':{'payment_id':request['payment_id'],'amount_minor':request['amount_minor'],'currency':'INR'},'scenario':decision,'available_balance_minor':balance},['Bank independently authorizes and places a simulated hold.'],{'status':'authorized','payment_id':p['payment_id'],'authorization_code':p['authorization_code'],'issuer':s['issuer']},True)


def capture(s,args):
    p=s['payment'];require(p['status']=='authorized','PAYMENT_NOT_AUTHORIZED')
    amount=money(pick(args,'amount','Capture amount (INR)',str(Decimal(p['amount_minor'])/100)));require(amount==p['authorized_amount_minor']==s['scoped_token']['amount_minor'],'CAPTURE_AMOUNT_OUTSIDE_SCOPE');require(s['reservation']['status']=='active','RESERVATION_NOT_ACTIVE')
    p['status']='captured';p['captured_amount_minor']=amount;p['captured_at']=stamp();s['budget']['reserved_minor']-=amount;s['budget']['captured_minor']+=amount;s['reservation']['status']='converted_to_captured'
    return ({'payment_id':p['payment_id'],'capture_amount_minor':amount},['Convert reserved budget to captured spend.'],{'payment_id':p['payment_id'],'status':'captured','amount_minor':amount,'budget':s['budget']},True)


def clear(s,args):
    p=s['payment'];require(p['status']=='captured','PAYMENT_NOT_CAPTURED');fee=money(pick(args,'fee','Illustrative total fee (INR)','1.70'));require(fee<=p['captured_amount_minor'],'FEE_EXCEEDS_CAPTURE')
    s['clearing']={'payment_id':p['payment_id'],'authorization_code':p['authorization_code'],'gross_minor':p['captured_amount_minor'],'fee_minor':fee,'merchant_net_minor':p['captured_amount_minor']-fee,'status':'accepted','fee_note':'invented teaching fee'}
    return ({'payment_id':p['payment_id'],'captured_amount_minor':p['captured_amount_minor'],'illustrative_fee_minor':fee},['Match capture to authorization and calculate demo fees.'],s['clearing'],True)


def settle(s,args):
    p=s['payment'];c=s['clearing'];require(c['status']=='accepted','CLEARING_NOT_ACCEPTED');s['issuer']['hold_minor']=0;s['issuer']['posted_debit_minor']=c['gross_minor'];p['status']='settled'
    s['settlement']={'payment_id':p['payment_id'],'status':'settled','issuer_debit_minor':c['gross_minor'],'acquirer_gross_receivable_minor':c['gross_minor'],'illustrative_fee_minor':c['fee_minor']}
    s['merchant_ledger']={'merchant_account_id':'merchant_blinkit_01','gross_credit_minor':c['gross_minor'],'fees_debit_minor':c['fee_minor'],'available_for_payout_minor':c['merchant_net_minor'],'paid_out_minor':0}
    return (c,['Post issuer debit and merchant net balance in the simulated ledger.'],{'settlement':s['settlement'],'issuer':s['issuer'],'merchant_ledger':s['merchant_ledger']},True)


def payout(s,args):
    ledger=s['merchant_ledger'];m=s['merchant_account'];p=s['payment'];require(p['status']=='settled','PAYMENT_NOT_SETTLED');amount=ledger['available_for_payout_minor'];require(amount>0,'NO_AVAILABLE_PAYOUT_BALANCE')
    s['payout']={'payout_id':'payout-301','merchant_account_id':m['merchant_account_id'],'destination_bank_reference':m['bank_reference'],'amount_minor':amount,'status':'paid_simulated'};ledger['available_for_payout_minor']=0;ledger['paid_out_minor']+=amount
    return ({'merchant_account_id':m['merchant_account_id'],'available_balance_minor':amount},['Pay simulated net proceeds to the merchant bank reference.'],s['payout'],True)


def audit(s,args):
    c=s['checkout'];p=s['payment'];b=s['budget'];m=s['merchant_ledger']
    checks={'no_active_reservation':b['reserved_minor']==0,'token_consumed':s['scoped_token']['status']=='redeemed','posted_debit_matches_capture':s['issuer']['posted_debit_minor']==p['captured_amount_minor'],'gross_equals_fees_plus_payout':m['gross_credit_minor']==m['fees_debit_minor']+m['paid_out_minor'],'merchant_payable_empty':m['available_for_payout_minor']==0,'payout_complete':s['payout']['status']=='paid_simulated'};require(all(checks.values()),'AUDIT_INVARIANT_FAILED')
    report={'order_id':c['order_id'],'merchant':'Blinkit','purchase':str(c['items'][0]['quantity'])+' bananas','gross_charge':show_money(p['amount_minor']),'illustrative_fee':show_money(m['fees_debit_minor']),'merchant_payout':show_money(m['paid_out_minor']),'monthly_grocery_spend':show_money(b['captured_minor']),'token_status':s['scoped_token']['status'],'payment_status':p['status'],'checks':checks,'events':s['events'],'simulation_only':True};s['audit']=report
    return ({'order_id':c['order_id'],'payment_id':p['payment_id'],'payout_id':s['payout']['payout_id']},['Reconcile the simulated purchase, charge, fee, and payout.'],report,True)


ACTIONS={'authorize':(18,'Issuer authorization',authorize),'capture':(19,'Capture payment',capture),'clear':(20,'Clear payment',clear),'settle':(21,'Settle payment',settle),'payout':(22,'Pay out merchant',payout),'audit':(23,'Final audit',audit)}

def main():
    p=parser(__doc__);g=p.add_mutually_exclusive_group(required=True)
    for a in ACTIONS:g.add_argument('--'+a,action='store_true')
    p.add_argument('--decision',choices=['approve','decline','challenge']);p.add_argument('--available_balance','--available-balance',dest='available_balance');p.add_argument('--otp');p.add_argument('--amount');p.add_argument('--fee');args=p.parse_args()
    action=next(a for a in ACTIONS if getattr(args,a));n,title,fn=ACTIONS[action];execute(n,title,fn,args,show_next_step=False)

if __name__=='__main__':
    try:main()
    except (DemoError,ValueError,KeyError,OSError) as e:print('\nBLOCKED: '+str(e),file=sys.stderr);raise SystemExit(2)
