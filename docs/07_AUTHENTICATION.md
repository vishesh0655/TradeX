# Authentication

security.py hashes/verifies local passwords, creates/decodes JWTs, extracts OAuth2 Bearer tokens, and loads the active current user.

| Route | Input | Result |
|---|---|---|
| POST /register | name/email/password | local user, password hash, wallet |
| POST /login | email/password | legacy local JWT |
| POST /auth/email | Firebase credential | provider verification and TradeX JWT |
| POST /auth/phone | Firebase credential | phone identity flow and TradeX JWT |
| POST /auth/google | Google credential | Google identity flow and TradeX JWT |

UserIdentity maps a provider subject to a User; provider+subject is unique. password_hash is nullable, allowing provider-only accounts.

~~~text
Firebase or Google sign-in
  → provider credential
  → anonymous /auth/provider
  → verification and identity lookup/create
  → TradeX JWT
  → localStorage when Remember Me; sessionStorage otherwise
  → Bearer JWT on protected API requests
~~~

Actual provider-console setup is outside this repository.
