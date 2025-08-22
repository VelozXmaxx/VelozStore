# Telegram Bot: Channel Verification + Menu + Free Stuff + Broadcast

## Features
- **User verification** across 3+ channels (flexible)
- **Main Menu** buttons:
  - PFP → opens owner chat with prefilled text
  - Video → opens owner chat with prefilled text
  - Talk to Owner → opens owner chat with "Hi!"
  - Free Stuff 🎁 → sends all saved PFP images
- **/add** (admin): reply to a photo to add to Free Stuff pool
- **/broadcast** (admin): 
  - `/broadcast Your message` → text to all users
  - Reply to media + `/broadcast Your message` → media + caption to all users
- **Scalable admin/channel mgmt**:
  - `/listchannels`, `/addchannel @name_or_id`, `/removechannel @name_or_id`
  - `/listadmins`, `/addadmin 123`, `/removeadmin 123`
- **Persists across Railway redeploys** via **PostgreSQL**

## Deploy on Railway
1. **Create a new project** from your GitHub repo.
2. Add the **PostgreSQL** plugin in Railway (This provides `DATABASE_URL` automatically).
3. Add **Environment Variables** (from `.env.example`):
   - `BOT_TOKEN`
   - `OWNER_USERNAME` (recommended) and/or `OWNER_ID`
   - `REQUIRED_CHANNELS` (e.g. `@Channel1,@Channel2,@Channel3`)
   - `MAIN_ADMIN_ID`, `SECONDARY_ADMINS`
   - (Optional) `SOCIAL_YT`, `SOCIAL_IG`, `START_SOCIAL_PROMO`
4. Add a **Procfile** with: `worker: python main.py`
5. **Deploy**. The bot will run as a worker process.

## Notes / Tips
- For the “open owner chat with a **prefilled message**”, Telegram deep links
  work best with **usernames**:
  - `tg://resolve?domain=USERNAME&text=Your%20Message`
  - So **set `OWNER_USERNAME`** if you can. Using only numeric ID opens the chat
    but can’t prefill the text on all clients.
- For required channels that are **public**, prefer `@channelname` so the UI can
  display a clickable link to each channel. For private channels or numeric IDs,
  the bot can’t create a public URL button unless it’s an admin there.
- **Free Stuff** sends all images in media groups of up to 10 per batch.

## Admin Usage
- Make yourself admin (via env `MAIN_ADMIN_ID`) before first run.
- Add others: `/addadmin 6129189597`
- Add/Remove channels: `/addchannel @MyChannel` or `/removechannel @MyChannel`
