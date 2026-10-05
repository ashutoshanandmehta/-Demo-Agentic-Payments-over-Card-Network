# [Demo] Agentic Payments over Card Network

This is a command-line demo of an agent buying groceries within a user's permission, handing a seller-scoped payment token to a merchant, and completing a simulated card payment through settlement and payout.


This is an offline simulation with the mock data. It does not contact Stripe, Blinkit, RuPay, an issuer, or a bank. 
## Requirements and installation

- Python 3.10 or later.
- A terminal; the command examples below use Bash or Zsh on macOS/Linux.
- No third-party Python packages, service accounts, real API keys, or internet connection to run the demo.

Download the repository ZIP from GitHub and extract it, or clone your repository. Open a terminal in the folder containing this README and the Python files. Enter the demo folder first with `cd '[Demo] Agentic Payments over Card Network'`.

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

`requirements.txt` intentionally contains no package requirements: all imports use Python's standard library. The virtual environment is optional. On Windows, use `py -3` instead of `python3`, and activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell. Adapt multiline shell quoting when using the JSON command below; Bash/Zsh examples are not PowerShell commands.

## What each file does

| File | Responsibility |
| --- | --- |
| `card_input.py` | Collect dummy card details privately; persist only masked card identity. |
| `network_token.py` | Simulate card-network token provisioning after a demo OTP. |
| `save_card.py` | Save the network token in the private vault; expose only the payment method reference. |
| `user_permission.py` | Create a signed permission for an agent, merchant, category, caps, and delivery address. |
| `blinkit_mcp.py` | Simulate tool discovery, catalog search, cart, checkout, and the agent's SPT handoff. |
| `permission_verifier.py` | Evaluate permission, reserve budget, and create an approved scope mandate. |
| `credential_service.py` | Model trusted backend issuance of a seller-scoped Shared Payment Token (SPT). |
| `payment_processor.py` | Authenticate the merchant, redeem its SPT, resolve the vaulted credential, and build authorization. |
| `rupay_network.py` | Simulate issuer authorization, capture, clearing, settlement, payout, and audit. |
| `status.py` | Display agent permission and transaction status, or revoke permission. |
| `common.py` | Provide state persistence, locking, signatures, money handling, and shared CLI helpers. |

The flow is: **card setup → user permission → merchant checkout → verification → SPT issuance → agent handoff → merchant payment request → authorization → capture → clearing → settlement → payout → audit**.

## Example purchase and conventions

Follow the examples with these values:

| Field | Demo value |
| --- | --- |
| Dummy card number | `4111111111111111` (never use a real card) |
| Cardholder / expiry | `Demo User` / `12/2099` |
| Enrolment OTP | `123456` (no SMS is sent) |
| Agent / category / merchant | `12` / `grocery` / `blinkit` |
| Delivery address / postal code | `Hall 12, IIT Kanpur` / `208016` |
| Transaction cap / monthly cap | INR 500 / INR 3,000 |
| Initial monthly spend | INR 0 |
| Product / quantity / unit price | Banana, product ID `4`, 12 pieces, INR 13.75 each |
| Item subtotal / delivery / handling | INR 165 / INR 10 / INR 10 |
| Checkout amount | INR 185 (`18500` paise) |
| Illustrative fee / merchant payout | INR 1.70 / INR 183.30 |

Press Enter to accept displayed defaults. Card number, cardholder, and expiry are required and have no defaults. Card-number entry is hidden while typing. The RuPay label is a fixed demo choice, independent of the dummy card number.

Amounts ending in `_minor` are paise: `18500` means INR 185. CLI amounts such as `--price_upto`, `--amount`, and `--fee` are in rupees. Agent `12` is stored as `shopping-agent-12`.

Identifiers such as `pm_user_77`, `scope-101`, `cart-101`, `checkout-101`, and `order-101` are fixed for this example. The SPT and checkout hash are generated during your run. **Replace every `spt_demo_TOKEN_ID` and `CHECKOUT_HASH_FROM_BLINKIT` placeholder with the exact value from your output.**

## 1. Save a payment method and set permission

```bash
python3 card_input.py
python3 network_token.py
python3 save_card.py
python3 user_permission.py --agent-id 12 --category grocery
```

Enter only dummy card details. Step 3 prints only `payment_method_id: pm_user_77`; the network token is kept in the private vault state. Merchant setup happens later when Blinkit is connected.

Permission asks for category, transaction cap, monthly cap, and delivery address. Product and quantity are chosen later during search. Monthly spend always begins at zero paise and is updated when a payment is captured.

For the example, enter the dummy card values above, accept OTP `123456`, and accept the permission defaults. Permission is valid for 43,200 minutes (30 days) by default. No product, quantity, or previously spent amount is requested during permission setup.

## 2. Search, cart, and checkout with Blinkit

```bash
python3 blinkit_mcp.py --establish_connection
python3 blinkit_mcp.py --list_tools
python3 blinkit_mcp.py --search_product --price_upto 300
python3 blinkit_mcp.py --create_cart --product_id 4 --quantity 12
python3 blinkit_mcp.py --create_checkout --expires_in_minutes 120
```

Search prompts for product name, quantity, and delivery postal code if omitted. `--price_upto` is a maximum unit price in rupees; the catalog's banana price is fixed at INR 13.75. Use the postal code in the permission.

Accept search defaults (`banana`, quantity `12`, postal code `208016`). The catalog contains only bananas, with stock of 100 pieces. Search prints stock, unit price, fees, and an estimated total; cart prints its item breakdown; checkout prints the signed total, order ID, checkout hash, and expiry.

## 3. Verify permission and create the mandate

```bash
python3 permission_verifier.py
```

The verifier prints the decision and checks adn then creates the approved scope mandate. The mandate automatically lasts at most 60 minutes, bounded by permission and checkout expiry. The existing `--expires_in_minutes 60` option remains supported for setting mandate lifetime; it is never requested interactively or included in the verifier's printed transaction input. The verifier checks category, merchant, address, currency, transaction cap, monthly cap, expiry, revocation, signatures, and checkout hash. A decline stops before credential issuance.

The default purchase returns `approved` with reason `ALL_CONSTRAINTS_SATISFIED` and creates mandate `scope-101`. INR 185 is reserved against the monthly cap. If the decision is `declined`, stop here: no approved mandate or SPT is created, and the credential service rejects issuance.

## 4. Let the trusted backend issue an SPT

Use the mandate ID and saved payment reference printed by the earlier commands:

```bash
python3 credential_service.py --approved_scope_mandate scope-101 --saved_payment pm_user_77
```

The output shows a simulated authenticated backend request to `POST /v1/shared_payment/issued_tokens`, scoped to the checkout amount, INR, seller profile, and expiry. No Stripe secret key is printed or used. Copy the returned `spt_demo_...` identifier.

This command represents the trusted platform backend. Its private token record links the SPT to the saved payment method and approved mandate. The agent shares the SPT identifier with Blinkit; it never supplies the underlying card-network token.

## 5. Agent sends the checkout and SPT to Blinkit

Use the cart ID, order ID, and SPT from the previous outputs:

```bash
python3 blinkit_mcp.py --cart_id cart-101 --order_id order-101 --STP spt_demo_TOKEN_ID
```

This saves the agent's handoff to Blinkit and prints the merchant request data. The agent sends only the cart/order references and SPT. `--SPT` is also accepted as an alias for `--STP`.

## 6. Blinkit submits its authenticated payment request

The old processor flags `--blinkit_checkout` and `--scoped_agentic_token` have been replaced by `--merchant-api-key` and `--input`. If you see an error requiring these arguments, use the command below. First run the agent handoff in section 5 with your actual SPT to get the merchant request JSON.

Copy the JSON details printed by the preceding command into `--input`. Keep the field names and values intact; replace the SPT placeholder with the real demo token ID.

The following JSON assumes the default 12-banana purchase. If you changed the quantity, use the amount and other details printed under `BLINKIT PAYMENT REQUEST DETAILS`, rather than the example amount below. Pass only that JSON object, without its heading. `STP` is retained as the demo's CLI/JSON spelling; `SPT` is also accepted.

```bash
python3 payment_processor.py --merchant-api-key "demo_blinkit_key" \
  --input '{
    "STP": "spt_demo_TOKEN_ID",
    "checkout_id": "checkout-101",
    "order_id": "order-101",
    "amount_minor": 18500,
    "currency": "INR",
    "checkout_hash": "CHECKOUT_HASH_FROM_BLINKIT",
    "idempotency_key": "order-101-payment-1"
  }'
```

The processor authenticates the simulated merchant key and resolves the SPT to its private backing records. The merchant request contains no saved payment method, card/network credential, original permission, or approved scope. The processor requests a synthetic cryptogram and prints a redacted network authorization request. The network token remains stored only in the vault. Identical authenticated retries return the existing result; a changed request or API key is checked and rejected.

`demo_blinkit_key` is a built-in mock merchant key, not a real service credential. The processor prepares the authorization request; run the network commands below to obtain issuer approval and complete payment.

## 7. Authorize, capture, clear, and settle

Run each action separately. Use the checkout amount shown by Blinkit for capture (the default 12-banana example totals INR 185).

```bash
python3 rupay_network.py --authorize --decision approve --available-balance 10000
python3 rupay_network.py --capture --amount 185
python3 rupay_network.py --clear --fee 1.70
python3 rupay_network.py --settle
python3 rupay_network.py --payout
python3 rupay_network.py --audit
```

To simulate an issuer challenge, authorize with `--decision challenge`, then repeat with `--otp 123456`.

For the default purchase, the final audit shows `payment_status: settled`, `token_status: redeemed`, gross charge INR 185, merchant payout INR 183.30, monthly grocery spend INR 185, and every reconciliation check set to `true`. Capture changes reserved spend into captured spend; settlement posts the simulated debit; payout records Blinkit's receipt of the net amount.

## Agent status and revocation

```bash
python3 status.py
python3 status.py --agent_id 12
python3 status.py --agent_id 12 --revoke
```

Status reports each agent's stored transaction history, captured monthly spend, transaction and monthly caps, delivery address, merchant, category, permission expiry, and revocation state. Spend is recorded in the state when capture succeeds. Revocation blocks future authorization and invalidates an unconsumed SPT. It can be requested after settlement as well; an existing authorized or completed payment keeps its recorded history.

## State and restart

The commands save workflow state, per-agent budgets, transaction history, and per-stage JSON under `demo_state/`. Each state directory supports one agent and one order in this demo. Use the same `--state-dir PATH` on every command to run an independent demo for another agent. To restart, delete the generated state and output JSON files under `demo_state/` and run the setup commands again; a reset also clears that run's spending history.

The state directory is created automatically on the first command. No prebuilt state is needed in the repository. Printed `INPUT` and `OUTPUT` describe each action; detailed processing notes are saved in the stage JSON rather than printed between them. Internal stage numbers and filenames such as `01_output.json` are bookkeeping, even though the setup scripts have no numeric prefixes.

To keep an existing run and start another, supply a fresh directory on **every** command, for example:

```bash
python3 card_input.py --state-dir ./demo_state/fresh-run
# Continue the remaining commands with --state-dir ./demo_state/fresh-run.
python3 status.py --state-dir ./demo_state/fresh-run
```

Completed stages usually return their saved result without repeating the action. To change a completed cart or permission, start a fresh run. SPT issuance and merchant processing also validate current credentials and bindings before accepting retries. Each script supports `--help`; workflow scripts support `--non-interactive` to use defaults for omitted prompt fields. The card-input script still requires explicit cardholder, card number, and expiry in that mode.

## Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| `Run step ... first` | Follow the command order above using the same state directory. |
| Required `--merchant-api-key`, `--input` | Use the merchant JSON command in section 6; the older processor flags are unsupported. |
| `SPT_NOT_FOUND` or hash/amount mismatch | Copy the token and entire payment request JSON from this run's Blinkit handoff output. |
| `CHECKOUT_EXPIRED`, `SCOPE_EXPIRED`, or `TOKEN_EXPIRED` | Start a fresh run; do not edit signed expiry values in state. |
| `DEMO_NO_RESULTS` | Search for banana with a maximum unit price of at least INR 13.75. |
| `LOCATION_NOT_AUTHORIZED` | Use the postal code entered in the permission. |
| `PERMISSION_REVOKED` | Create a new permission in a fresh state directory. |
| `Another script is running` | Wait for it to finish. If a previous process crashed, remove only its stale `.lock` file after confirming no demo command is running. |
| Invalid JSON passed to `--input` | Use valid JSON with double-quoted keys/strings, wrapped in single quotes in Bash/Zsh. |

To demonstrate a policy decline, begin a fresh run and set `--transaction-limit 100` or `--monthly-limit 100` on `user_permission.py`. The default INR 185 checkout then fails verification. To demonstrate issuer decline, use `--decision decline` at authorization; the monthly reservation is released and settlement must not continue.


## Simulation boundaries

- MCP messages, catalog stock, delivery estimates, cryptograms, bank balances, fees, and all payment service calls are simulated locally.
- The role separation is educational: every component runs locally and shares a JSON state file. This is not a production vault or security boundary.
- Permission verification and issuer authorization are separate decisions. A verifier approval does not guarantee a bank approval.
- Revocation blocks future authorization; it does not reverse an already authorized or completed payment.
- Each state directory models one agent and one order. Multiple purchases, refunds, disputes, partial captures, automatic expiry cleanup, and month rollover are not implemented.
- There is no live Stripe, Blinkit, or RuPay integration. Do not use real card details, service credentials, or personal data.
