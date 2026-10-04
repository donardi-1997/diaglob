# DIAGLOB Cognito custom email sender

This Lambda is intended for the Cognito `CustomEmailSender` trigger.

It keeps Cognito responsible for generating and validating verification/recovery codes, while DIAGLOB sends the email through its own Spacemail mailbox.

## SMTP secret

Secrets Manager secret:

`/diaglob/prod/spacemail-smtp`

Expected value:

```json
{
  "host": "mail.spacemail.com",
  "port": 465,
  "username": "support@diaglob.tech",
  "password": "REPLACE_IN_SECRETS_MANAGER",
  "from": "DIAGLOB <support@diaglob.tech>",
  "reply_to": "support@diaglob.tech"
}
```

Do not commit the mailbox password.

## Lambda environment

- `KEY_ID`: KMS key ID used by Cognito custom sender encryption
- `KEY_ARN`: same KMS key ARN
- `SMTP_SECRET_ID`: `/diaglob/prod/spacemail-smtp`
- `APP_URL`: `https://diaglob.tech`

## Activation safety

Do not attach the Lambda to the Cognito User Pool until:

1. The SMTP secret contains working credentials.
2. The Lambda can connect to Spacemail and send a test email.
3. The Lambda role can read the secret and decrypt with KMS.
4. Cognito has permission to invoke the Lambda.
5. A signup/resend-code test succeeds.

Until then, keep the User Pool on `COGNITO_DEFAULT`.
