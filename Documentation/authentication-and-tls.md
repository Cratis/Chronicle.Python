---
title: Authentication and TLS
description: How the Chronicle Python client obtains and refreshes OAuth tokens, which certificates it trusts, and what happens when authentication fails.
---

## Token handling

`OAuthTokenProvider` posts `grant_type=client_credentials`, `client_id` and `client_secret` as
`application/x-www-form-urlencoded` to `/connect/token` on the kernel's own host and port. The channel asks the
provider for the current token when each new gRPC call starts and sends it as `authorization: Bearer <token>`; no
token is baked into the channel.

- A token is reused until shortly before it expires: half of its lifetime for short tokens, otherwise 30 seconds
  early.
- When the response has no `expires_in`, the token is trusted for 30 seconds only.
- Concurrent callers share one request. Cancelling one caller does not cancel the request the others wait for.
- A response that is not JSON, has no `access_token`, a `token_type` other than `Bearer`, or an invalid `expires_in`
  raises `TokenResponseError`. HTTP 400, 401 and 403 raise `TokenAuthorizationError` with the OAuth `error` and
  `error_description`. Redirects are never followed, so the secret only goes to the configured host.
- The client secret and tokens are excluded from `repr()` and from every error message, including text the server
  echoes back.
- A call that receives `UNAUTHENTICATED` is not retried. Reconnect and retry behavior is not part of this milestone.

## Certificate trust

Certificates and host names are verified for every connection. `skipTlsValidation` is `true` by default in the
connection string, as in the .NET client; this client honors it with these rules:

| Situation | Trusted certificate |
| --- | --- |
| `ca_certificates=<PEM bytes>` is passed to `ChronicleClient.connect` | Exactly those roots |
| `skipTlsValidation` is `true` and the host is `localhost` or a loopback address | The certificate the local kernel presents, read once at connect time; the host name is still checked |
| `skipTlsValidation=false` | The platform's default roots |
| `skipTlsValidation` is `true` and the host is **not** loopback | The platform's default roots. The option is ignored |

A remote kernel is therefore never reached with relaxed validation. To reach a remote kernel with a private
certificate authority, pass its certificate as `ca_certificates`. A loopback kernel with a self-signed certificate
works with the defaults; add `?skipTlsValidation=false` to prove it fails without trust.
