"""Simulate network token provisioning. Offline simulation; run this step manually.
See README.md for the full sequence."""
from common import *

def work(s, args):
    otp=pick(args,'otp','SIMULATED enrolment OTP','123456')
    require(otp=='123456','DEMO_OTP_INVALID: use 123456 (no SMS is sent).')
    e=s['enrolment']
    s['network_token']={'network_token_id':'ntok_demo_'+secrets.token_hex(12),
     'network':'RuPay','last4':e['last4'],'status':'active','token_requestor_id':'processor-demo-01'}
    return ({'enrolment_id':e['enrolment_id'],'token_requestor_id':'processor-demo-01','demo_otp':'[validated]'},
     ['Simulate issuer verification and network token service. The credential stays private to the vault flow.'],
     {'tokenization_status':'complete','payment_method_ready':True},True)

if __name__ == "__main__":
    p = parser('Simulate network token provisioning')
    p.add_argument('--otp')
    execute(2, 'Simulate network token provisioning', work, p.parse_args())
