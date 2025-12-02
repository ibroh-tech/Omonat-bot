# bot.py
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database import (
    save_answer,
    init_db,
    get_last_answer_index,
    has_completed_this_month,
    get_users_with_incomplete_forms,
    save_region,
    get_region_this_month,
)
from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Keep the last message id sent to each user so we can edit it in-place.
LAST_MESSAGE_ID: dict[int, int] = {}

# Minimal in-memory cache for speed. DB is the source of truth!
user_progress: dict[int, int] = {}  # user_id -> next question index (0-based)

# Regional options. Adjust to your actual data.
REGIONS: dict[str, list[str]] = {
    "North": ["North-1", "North-2", "North-3"],
    "South": ["South-1", "South-2"],
    "East": ["East-1", "East-2"],
    "West": ["West-1"],
}

# Questions are now defined in this file.
QUESTIONS = [
    {
        "text": "How satisfied are you with our service?",
        "options": ["Very satisfied", "Satisfied", "Neutral", "Dissatisfied", "Very dissatisfied"],
    },
    {
        "text": "How likely are you to recommend us to a friend?",
        "options": ["Very likely", "Likely", "Not sure", "Unlikely", "Very unlikely"],
    },
    {
        "text": "Which channel do you prefer for updates?",
        "options": ["Telegram", "Email", "SMS", "Website"],
    },
]

def build_region_keyboard() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(text=region, callback_data=f"REG:{region}")]
        for region in REGIONS.keys()
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def build_subregion_keyboard(region: str) -> InlineKeyboardMarkup:
    subs = REGIONS.get(region, [])
    inline_keyboard = [
        [InlineKeyboardButton(text=sub, callback_data=f"SUB:{region}|{sub}")]
        for sub in subs
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def build_keyboard_for_question(question_id: int) -> InlineKeyboardMarkup:
    q = QUESTIONS[question_id]
    # callback_data: "<question_id>:<option_index>"
    inline_keyboard = [
        [InlineKeyboardButton(text=o, callback_data=f"{question_id}:{i}")]
        for i, o in enumerate(q["options"])
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

async def send_or_edit_question(chat_id: int, question_id: int):
    """
    Edit existing message if present, otherwise send a new one.
    The message contains inline keyboard for choices.
    """
    question = QUESTIONS[question_id]
    text = f"❓ {question['text']}"

    reply_markup = build_keyboard_for_question(question_id)

    # If there's a previous message for this chat, edit it in place; else send new.
    if chat_id in LAST_MESSAGE_ID:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=LAST_MESSAGE_ID[chat_id],
                text=text,
                reply_markup=reply_markup
            )
            return
        except Exception:
            # if edit fails (message deleted or too old), we'll send a new message
            pass

    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    LAST_MESSAGE_ID[chat_id] = msg.message_id

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id

    # Enforce monthly completion limit
    if has_completed_this_month(user_id, total_questions=len(QUESTIONS)):
        await message.answer("You have already completed the form for this month. Please try again next month.")
        return

    # Ensure region/subregion is captured for this month before questions
    region_info = get_region_this_month(user_id)
    if not region_info:
        text = "Please select your region:"
        kb = build_region_keyboard()
        msg = await message.answer(text, reply_markup=kb)
        LAST_MESSAGE_ID[user_id] = msg.message_id
        return

    # compute current progress from DB (answers this month) after region is set
    index = get_last_answer_index(user_id)
    user_progress[user_id] = index

    if index >= len(QUESTIONS):
        await message.answer("You have already completed all questions.")
        return

    await send_or_edit_question(user_id, index)

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data or ""
    # Handle region selection
    if data.startswith("REG:"):
        region = data.split(":", 1)[1]
        if region not in REGIONS:
            await callback.answer("Invalid region.", show_alert=True)
            return
        try:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"Selected region: {region}. Now select your subregion:",
                reply_markup=build_subregion_keyboard(region),
            )
        except Exception:
            # fallback to sending new message
            msg = await bot.send_message(user_id, f"Selected region: {region}. Now select your subregion:", reply_markup=build_subregion_keyboard(region))
            LAST_MESSAGE_ID[user_id] = msg.message_id
        await callback.answer()
        return

    if data.startswith("SUB:"):
        try:
            payload = data.split(":", 1)[1]
            region, sub = payload.split("|", 1)
        except Exception:
            await callback.answer("Invalid subregion.", show_alert=True)
            return
        if region not in REGIONS or sub not in REGIONS.get(region, []):
            await callback.answer("Invalid subregion.", show_alert=True)
            return
        try:
            save_region(user_id, region, sub)
        except Exception:
            await callback.answer("Failed to save region.", show_alert=True)
            return
        # Confirm and move to first question
        try:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"✅ Region saved: {region} / {sub}.",
                reply_markup=None,
            )
        except Exception:
            pass
        await callback.answer("Saved!")
        # Start questions
        next_index = get_last_answer_index(user_id)
        user_progress[user_id] = next_index
        if next_index < len(QUESTIONS):
            await send_or_edit_question(user_id, next_index)
        else:
            msg = await bot.send_message(user_id, "🎉 Thank you! You have completed all questions for this month.")
            LAST_MESSAGE_ID[user_id] = msg.message_id
        return

    # Otherwise expect question answer: "qid:opt_index"
    try:
        qid_str, opt_index_str = data.split(":", 1)
        qid = int(qid_str)
        opt_index = int(opt_index_str)
    except Exception:
        await callback.answer("Invalid response.", show_alert=True)
        return

    # guard: qid must be within QUESTIONS
    if qid < 0 or qid >= len(QUESTIONS):
        await callback.answer("Question not found.", show_alert=True)
        return

    options = QUESTIONS[qid]["options"]
    if opt_index < 0 or opt_index >= len(options):
        await callback.answer("Invalid option.", show_alert=True)
        return

    answer_text = options[opt_index]
    question_text = QUESTIONS[qid]["text"]

    # store answer
    try:
        save_answer(user_id, qid, question_text, answer_text)
    except Exception as e:
        # DB error — notify user but try to continue
        await callback.answer("Failed to save answer (DB error).", show_alert=True)
        return

    # remove inline keyboard (so old options disappear) and update message to show chosen answer
    try:
        # Replace message text to show chosen answer for clarity (optional)
        edited_text = f"✅ {question_text}\n\nYour answer: {answer_text}"
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=edited_text,
            reply_markup=None
        )
    except Exception:
        # ignore edit errors
        pass

    await callback.answer("Saved!")

    # recompute progress from DB and send next question in same message (edit if possible)
    next_index = get_last_answer_index(user_id)
    user_progress[user_id] = next_index

    if next_index >= len(QUESTIONS):
        # finished: send a final message (we'll attempt to edit the same message; if fails, send new)
        final_text = "🎉 Thank you! You have completed all questions for this month."
        try:
            # try to reuse same message id if possible
            if callback.message and callback.message.message_id:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text=final_text,
                    reply_markup=None
                )
                # update LAST_MESSAGE_ID to this final message id
                LAST_MESSAGE_ID[user_id] = callback.message.message_id
                return
        except Exception:
            pass

        # fallback: send new message
        msg = await bot.send_message(user_id, final_text)
        LAST_MESSAGE_ID[user_id] = msg.message_id
        return

    # send next question by editing same message (send_or_edit_question will do that)
    await send_or_edit_question(user_id, next_index)


async def resume_incomplete_on_start():
    """
    On bot startup: find users who have started this month but haven't finished,
    and send them their next question (so the flow continues across restarts).
    """
    user_ids = get_users_with_incomplete_forms(total_questions=len(QUESTIONS))
    for uid in user_ids:
        try:
            # If user hasn't set region for this month, prompt for it first
            if not get_region_this_month(uid):
                msg = await bot.send_message(uid, "Please select your region:", reply_markup=build_region_keyboard())
                LAST_MESSAGE_ID[uid] = msg.message_id
                continue
            next_index = get_last_answer_index(uid)
            user_progress[uid] = next_index
            if next_index < len(QUESTIONS):
                await send_or_edit_question(uid, next_index)
        except Exception:
            # ignore per-user errors (e.g., bot blocked)
            pass

async def main():
    init_db()
    await resume_incomplete_on_start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
