# AENZO LABS Telegram Lead Hunter

This folder will contain the Telegram user-account scanning worker.

## Important
- Uses the Telegram account owner's authorized session through Telegram's official MTProto API.
- Scans only groups the account has legitimately joined and can access.
- Does not bypass private-group invitations, membership checks, or Telegram access controls.
- Never commit `api_id`, `api_hash`, phone numbers, login codes, 2FA passwords, session files, Supabase service-role keys, or `.env` files.

## Current status
Setup notes only. The worker is not implemented or deployed yet. A secure runtime and database integration must be configured before any messages can be collected.
