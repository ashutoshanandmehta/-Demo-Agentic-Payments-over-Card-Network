"""Save card in the shared processor vault. Offline simulation; run this step manually.
See README.md for the full sequence."""
from common import *

def work(s, args):
    n=s['network_token']
    s['vault']={'payment_method_id':'pm_user_77','customer_id':'cus_user_77','network_token_id':n['network_token_id'],
     'network':'RuPay','last4':n['last4'],'status':'active'}
    s.pop('network_token',None)
    s.pop('enrolment',None)
    return ({'tokenization_status':'complete'},
     ['Store the network token in the private processor vault.',
      'Expose only the saved payment method reference to the agent. Merchant setup is independent.'],
     {'payment_method_id':s['vault']['payment_method_id']},True)

if __name__ == "__main__":
    p = parser('Save card in the shared processor vault')
    execute(3, 'Save card in the shared processor vault', work, p.parse_args())
