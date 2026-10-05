"""Collect dummy card input. Offline simulation; run this step manually.
See README.md for the full sequence."""
from common import *
from getpass import getpass
import re

def required_input(args, field, label, private=False):
    """Read a required value without displaying or using an example default."""
    value = getattr(args, field, None)
    if value is None:
        require(not args.non_interactive,
                f'Missing required parameter: --{field.replace("_", "-")}')
        prompt = f'{label}: '
        value = getpass(prompt) if private else input(prompt)
    value = value.strip()
    require(bool(value), f'{label} is required.')
    return value

def work(s, args):
    card_number = required_input(args, 'card_number', 'Full dummy card number', private=True)
    card_number = card_number.replace(' ', '').replace('-', '')
    require(bool(re.fullmatch(r'[0-9]{12,19}', card_number)),
            'Card number must contain 12 to 19 digits; spaces and hyphens are allowed.')
    last4 = card_number[-4:]
    # Keep the existing downstream schema. Do not persist the full number.
    del card_number
    args.card_number = None
    name = required_input(args, 'cardholder', 'Cardholder name')
    card_exp = required_input(args, 'card_expiry', 'Card expiry (MM/YYYY)')
    require(bool(re.fullmatch(r'(0[1-9]|1[0-2])/[0-9]{4}', card_exp)),
            'Card expiry must use MM/YYYY with a valid month.')
    month,year=map(int,card_exp.split('/'))
    require(1<=month<=12 and year>=now().year,'Invalid or expired demo card.')
    require((year,month)>=(now().year,now().month),'Invalid or expired demo card.')
    s['enrolment']={'enrolment_id':'enrol-77','customer_id':'cus_user_77',
        'cardholder':name,'network':'RuPay','last4':last4,'card_expiry':card_exp,'status':'pending'}
    return ({'card_number':'**** **** **** '+last4,'last4':last4,'cardholder':name,'card_expiry':card_exp},
        ['Simulate a processor-hosted card form accepting the full dummy card number.',
         'Derive last4; omit the full card number from printed output and saved state.',
         'Build a simulated token-provisioning request; no CVV is collected.'],
        s['enrolment'],True)

if __name__ == "__main__":
    p = parser('Collect dummy card input')
    p.add_argument('--card-number', help='Full dummy card number; prompted privately if omitted.')
    p.add_argument('--cardholder')
    p.add_argument('--card-expiry')
    execute(1, 'Collect dummy card input', work, p.parse_args(),
            show_processing=False, show_next_step=False)
