# Security notes

Reviewed against the test plan in the project documentation.

- Access tokens are short-lived JWTs. Refresh tokens are stored hashed and rotated. Logout and deactivation revoke them.
- Every staff route checks a permission on the server. Customers can read only their own orders and inquiries. Unpublished products and private documents return 404.
- Payment proof files require `payment.proof.read`. Payment metadata is a separate permission.
- Uploads must match an allowed type and a file signature, and they have a size cap.
- Login, registration, and password reset requests are rate limited per client address.
- Responses send `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy`.
- Unexpected errors return a generic message. The server log keeps the exception.
- Set `SENTRY_DSN` to send those exceptions to error tracking. Leave it blank to disable tracking.
- Production must set a long `JWT_SECRET` and restrict `CORS_ORIGINS`.
