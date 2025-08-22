import asyncio
import logging
import os
from datetime import datetime
from urllib.parse import quote

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN,
    OWNER_ID,
    OWNER_USERNAME,
    SOCIAL_YT,
    SOCIAL_IG,
    REQUIRED_CHANNELS,  # list of channel ids or @usernames as strings
    MAIN_ADMIN_ID,
    SECONDARY_ADMINS,
    START_SOCIAL_PROMO,
)
from db import (
    init_db,
    pool,
    ensure_bootstrap_data,
    upsert_user,
    get_admin_ids,
    is_admin,
    add_free_image,
    list_free_images,
    list_channels,
    upsert_channel,
    delete_channel,
    list_admins,
    add_admin,
    remove_admin,
    all_user_ids,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ---------- Helpers ----------
def channel_display_and_link(raw: str) -> tuple[str, str | None]:
    """
    Returns (display_title, url_or_none) for a channel identifier.
    raw can be '@publicchannel' or a numeric ID as string.
    """
    if raw.startswith("@"):
        title = raw
        url = f"https://t.me/{raw[1:]}"
        return title, url
    # numeric id (can’t generate a public URL safely unless bot is admin)
    return f"Channel {raw}", None


async def get_effective_required_channels(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    """
    We store channels in DB for scalability; on first run we prefill from env.
    """
    db_channels = await list_channels()
    if db_channels:
        return db_channels
    # seed from env on first boot
    for ch in REQUIRED_CHANNELS:
        await upsert_channel(ch)
    return await list_channels()


async def is_member_of(context: ContextTypes.DEFAULT_TYPE, user_id: int, channel: str) -> bool:
    """
    channel may be '@name' or numeric id. Use get_chat_member to check.
    """
    chat_id = channel if channel.startswith("@") else int(channel)
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        status = member.status
        return status not in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
    except Exception as e:
        logger.warning(f"Membership check failed for user {user_id} in {channel}: {e}")
        # If we can’t check (e.g., bot lacks rights), treat as not a member
        return False


def owner_deeplink(text: str) -> str | None:
    """
    Builds a button link that opens chat with owner and prefills text.
    Works best with OWNER_USERNAME; falls back to tg://user for ID (no prefill).
    """
    if OWNER_USERNAME:
        return f"tg://resolve?domain={OWNER_USERNAME}&text={quote(text)}"
    if OWNER_ID:
        # prefill not supported by ID scheme; this at least opens the chat
        return f"tg://user?id={OWNER_ID}"
    return None


def main_menu_kb() -> InlineKeyboardMarkup:
    pfp_link = owner_deeplink("I want a paid PFP.")
    vid_link = owner_deeplink("I want a paid video.")
    hi_link = owner_deeplink("Hi!")

    buttons = [
        [
            InlineKeyboardButton("PFP", url=pfp_link) if pfp_link
            else InlineKeyboardButton("PFP", callback_data="noop")
        ],
        [
            InlineKeyboardButton("Video", url=vid_link) if vid_link
            else InlineKeyboardButton("Video", callback_data="noop")
        ],
        [
            InlineKeyboardButton("Talk to Owner", url=hi_link) if hi_link
            else InlineKeyboardButton("Talk to Owner", callback_data="noop")
        ],
        [InlineKeyboardButton("Free Stuff 🎁", callback_data="free_stuff")],
    ]
    return InlineKeyboardMarkup(buttons)


def verify_kb(required_channels: list[str]) -> InlineKeyboardMarkup:
    rows = []
    # Channel open buttons
    for idx, ch in enumerate(required_channels, start=1):
        title, url = channel_display_and_link(ch)
        label = f"Open {title}" if url else f"{title} (make sure you joined)"
        if url:
            rows.append([InlineKeyboardButton(label, url=url)])
        else:
            rows.append([InlineKeyboardButton(label, callback_data="noop")])
    # Verify button
    rows.append([InlineKeyboardButton("✅ Verify", callback_data="verify")])
    return InlineKeyboardMarkup(rows)


async def send_social_promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not START_SOCIAL_PROMO:
        return
    msg = (
        "🎨 Want to learn how to make the best PFPs?\n"
        f"📺 YouTube: {SOCIAL_YT}\n"
        f"📸 Instagram: {SOCIAL_IG}"
    )
    await update.effective_chat.send_message(msg)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_message(
        "Main Menu — choose an option:",
        reply_markup=main_menu_kb(),
    )


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await upsert_user(user.id, user.first_name or "", datetime.utcnow())
    required_channels = await get_effective_required_channels(context)

    # Greeting
    first_name = user.first_name or "there"
    await update.effective_chat.send_message(
        f"👋 Welcome, {first_name}! Please subscribe to our channels to continue."
    )

    # Subscription panel
    await update.effective_chat.send_message(
        "Join all channels below, then tap ✅ Verify:",
        reply_markup=verify_kb(required_channels),
    )


async def cbq_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "verify":
        user_id = query.from_user.id
        required_channels = await get_effective_required_channels(context)
        # Check membership
        checks = await asyncio.gather(
            *[is_member_of(context, user_id, ch) for ch in required_channels]
        )
        if all(checks):
            await query.message.reply_text("✅ Verified! Taking you to the Main Menu…")
            await show_main_menu(update, context)
            # Social promo
            await send_social_promo(update, context)
        else:
            # Which ones are missing?
            missing = [ch for ch, ok in zip(required_channels, checks) if not ok]
            missing_list = "\n".join(f"• {channel_display_and_link(ch)[0]}" for ch in missing)
            await query.message.reply_text(
                "❌ You're not subscribed to all channels.\n"
                "Please join these and try Verify again:\n"
                f"{missing_list}"
            )

    elif query.data == "free_stuff":
        images = await list_free_images()
        if not images:
            await query.message.reply_text("No free PFPs yet—check back soon!")
            return

        # Telegram allows media groups up to 10 items; our pool is images only
        CHUNK = 10
        batch = []
        for i, file_id in enumerate(images, start=1):
            batch.append(InputMediaPhoto(media=file_id))
            if len(batch) == CHUNK or i == len(images):
                # send this batch
                try:
                    await context.bot.send_media_group(
                        chat_id=update.effective_chat.id,
                        media=batch,
                    )
                except Exception as e:
                    logger.error(f"Failed to send free stuff batch: {e}")
                batch = []

    elif query.data == "noop":
        await query.message.reply_text("✅ We’ve opened the chat (or provided the link). Please check your Telegram.")
    else:
        # Unknown / reserved
        pass


async def echo_confirmation_for_owner_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    After PFP/Video/Talk buttons are clicked (they’re URL buttons), we can’t
    detect that click. As a UX nicety, we provide a command users can press:
    /menu always shows main menu; plus a generic confirmation command.
    """
    await update.effective_chat.send_message(
        "✅ We've opened the chat with the owner. Please check your Telegram messages."
    )


# ---------- Admin commands ----------
async def admin_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    if await is_admin(uid):
        return True
    await update.effective_chat.send_message("⛔️ Admins only.")
    return False


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Usage: reply to a photo with /add
    if not await admin_guard(update, context):
        return

    if not update.message or not update.message.reply_to_message:
        await update.effective_chat.send_message("Reply to an uploaded image with /add.")
        return

    reply = update.message.reply_to_message
    if not reply.photo:
        await update.effective_chat.send_message("Please reply to a *photo* with /add.", parse_mode=ParseMode.MARKDOWN)
        return

    # largest size photo has the best quality; we only need file_id
    file_id = reply.photo[-1].file_id
    await add_free_image(file_id, update.effective_user.id)
    await update.effective_chat.send_message("✅ Image added to Free Stuff pool.")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context):
        return

    if not update.message:
        return

    args_text = update.message.text.partition(" ")[2].strip() if update.message.text else ""

    user_ids = await all_user_ids()
    if not user_ids:
        await update.effective_chat.send_message("No users yet.")
        return

    sent = 0
    failed = 0

    async def send_to(uid: int):
        nonlocal sent, failed
        try:
            if update.message.reply_to_message:
                r = update.message.reply_to_message
                if r.photo:
                    await context.bot.send_photo(uid, r.photo[-1].file_id, caption=args_text or None)
                elif r.video:
                    await context.bot.send_video(uid, r.video.file_id, caption=args_text or None)
                elif r.document:
                    await context.bot.send_document(uid, r.document.file_id, caption=args_text or None)
                else:
                    # fallback to text if unknown media
                    await context.bot.send_message(uid, args_text or "(no content)")
            else:
                if args_text:
                    await context.bot.send_message(uid, args_text)
                else:
                    await context.bot.send_message(uid, "(empty broadcast)")
            sent += 1
        except Exception:
            failed += 1

    # Gentle pacing to avoid flood limits
    for uid in user_ids:
        await send_to(uid)
        await asyncio.sleep(0.05)

    await update.effective_chat.send_message(f"Broadcast done. ✅ Sent: {sent} | ❌ Failed: {failed}")


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_menu(update, context)


# ---- Channel/admin management for scalability ----
async def cmd_listchannels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context):
        return
    channels = await list_channels()
    if not channels:
        await update.effective_chat.send_message("No required channels set.")
        return
    text = "Required channels:\n" + "\n".join(f"• {c}" for c in channels)
    await update.effective_chat.send_message(text)


async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /addchannel @channel_or_id")
        return
    ident = context.args[0]
    await upsert_channel(ident)
    await update.effective_chat.send_message(f"✅ Added/updated required channel: {ident}")


async def cmd_removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /removechannel @channel_or_id")
        return
    ident = context.args[0]
    await delete_channel(ident)
    await update.effective_chat.send_message(f"✅ Removed required channel: {ident}")


async def cmd_listadmins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context):
        return
    admins = await list_admins()
    text = "Admins:\n" + "\n".join(f"• {a}" for a in admins)
    await update.effective_chat.send_message(text)


async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /addadmin 123456789")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.effective_chat.send_message("Provide a numeric user ID.")
        return
    await add_admin(uid)
    await update.effective_chat.send_message(f"✅ Added admin {uid}")


async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context):
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /removeadmin 123456789")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.effective_chat.send_message("Provide a numeric user ID.")
        return
    await remove_admin(uid)
    await update.effective_chat.send_message(f"✅ Removed admin {uid}")


# ---------- App ----------
async def on_startup(app):
    await init_db()
    await ensure_bootstrap_data(
        main_admin=MAIN_ADMIN_ID,
        secondary_admins=SECONDARY_ADMINS,
        required_channels=REQUIRED_CHANNELS,
    )
    logger.info("Bot is up.")


def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # scalability helpers
    app.add_handler(CommandHandler("listchannels", cmd_listchannels))
    app.add_handler(CommandHandler("addchannel", cmd_addchannel))
    app.add_handler(CommandHandler("removechannel", cmd_removechannel))
    app.add_handler(CommandHandler("listadmins", cmd_listadmins))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))

    # Callback queries
    app.add_handler(CallbackQueryHandler(cbq_handler))

    # Optional confirmation keyword if you ever want to trigger it
    app.add_handler(MessageHandler(filters.Regex(r"^/confirm$"), echo_confirmation_for_owner_buttons))

    app.post_init = on_startup
    return app


if __name__ == "__main__":
    application = build_app()
    application.run_polling(close_loop=False)
