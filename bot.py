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
    reset_current_month_data,
    delete_answer_current_month,
)
from config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Keep the last message id sent to each user so we can edit it in-place.
LAST_MESSAGE_ID: dict[int, int] = {}

# Minimal in-memory cache for speed. DB is the source of truth!
user_progress: dict[int, int] = {}  # user_id -> next question index (0-based)
selected_region: dict[int, int] = {}  # user_id -> region id chosen in current flow
expected_open_question: dict[int, int] = {}  # user_id -> question_id awaiting free-text

# Regional options
REGIONS: dict[str, list[str]] = {
    "Тошкент шаҳри": [],
    "Тошкент вилояти": [
        "Бекобод тумани", "Бўка тумани", "Бостанлиқ тумани", "Қибрай тумани",
        "Паркент тумани", "Ўртачирчиқ тумани", "Қуйичирчиқ тумани", "Янгийўл тумани",
        "Чиноз тумани", "Зангиота тумани", "Тошкент тумани", "Юқоричирчиқ тумани",
        "Охангарон тумани", "Ангрен (шаҳар ҳуқуқида)", "Олмалиқ (шаҳар ҳуқуқида)", "Чирчиқ (шаҳар ҳуқуқида)",
    ],
    "Самарқанд вилояти": [
        "Булунғур тумани", "Жомбой тумани", "Иштихон тумани", "Каттақўрғон тумани",
        "Қўшработ тумани", "Нарпай тумани", "Оқдарё тумани", "Пастдарғом тумани",
        "Пайариқ тумани", "Самарқанд тумани", "Нурабод тумани", "Тойлоқ тумани", "Ургут тумани",
    ],
    "Фарғона вилояти": [
        "Бувайда тумани", "Бешариқ тумани", "Боғдод тумани", "Учкўприк тумани",
        "Риштон тумани", "Қува тумани", "Қувасой тумани", "Фурқат тумани",
        "Олтиариқ тумани", "Данғара тумани", "Тошлоқ тумани", "Ёзёвон тумани",
        "Сўх тумани", "Ўзбекистон тумани", "Қўштепа тумани",
    ],
    "Андижон вилояти": [
        "Андижон тумани", "Асакa тумани", "Балиқчи тумани", "Бўстон тумани",
        "Булоқбоши тумани", "Жалақудуқ тумани", "Избоскан тумани", "Қўрғонтепа тумани",
        "Марҳамат тумани", "Олтинкўл тумани", "Пахтаобод тумани", "Улуғнор тумани", "Шаҳрихон тумани",
    ],
    "Наманган вилояти": [
        "Наманган тумани", "Косонсой тумани", "Чуст тумани", "Учқўрғон тумани",
        "Тўрақўрғон тумани", "Поп тумани", "Норин тумани", "Уйчи тумани",
        "Янгикўрғон тумани", "Чортоқ тумани",
    ],
    "Бухоро вилояти": [
        "Бухоро тумани", "Когон тумани", "Вобкент тумани", "Ғиждувон тумани",
        "Жондор тумани", "Қоракўл тумани", "Қоровулбозор тумани", "Олот тумани",
        "Пешку тумани", "Ромитан тумани", "Шофиркон тумани",
    ],
    "Хоразм вилояти": [
        "Урганч тумани", "Хонқа тумани", "Хазорасп тумани", "Гурлан тумани",
        "Янгибозор тумани", "Боғот тумани", "Шовот тумани", "Қўшкўпир тумани", "Тупроққалъа тумани",
    ],
    "Қашқадарё вилояти": [
        "Қарши тумани", "Касби тумани", "Китоб тумани", "Қамаши тумани",
        "Миришкор тумани", "Муборак тумани", "Нишон тумани", "Деҳқонобод тумани",
        "Чироқчи тумани", "Шаҳрисабз тумани", "Яккабоғ тумани",
    ],
    "Сурхондарё вилояти": [
        "Термиз тумани", "Ангор тумани", "Бандихон тумани", "Бойсун тумани",
        "Денау тумани", "Жарқўрғон тумани", "Қизириқ тумани", "Қумқўрғон тумани",
        "Музработ тумани", "Олтинсой тумани", "Сариосиё тумани", "Шеробод тумани", "Шўрчи тумани",
    ],
    "Жиззах вилояти": [
        "Арнасой тумани", "Бахмал тумани", "Ғаллаорол тумани", "Дўстлик тумани",
        "Зафаробод тумани", "Зарбдор тумани", "Зомин тумани", "Мирзачўл тумани",
        "Пахтакор тумани", "Фориш тумани", "Шароф Рашидов тумани",
    ],
    "Сирдарё вилояти": [
        "Боёвут тумани", "Гулистон тумани", "Мирзаобод тумани", "Оқолтин тумани",
        "Сайхунобод тумани", "Сардоба тумани", "Сырдарё тумани", "Ховос тумани",
    ],
    "Навоий вилояти": [
        "Кармана тумани", "Қизилтепа тумани", "Конимех тумани", "Навбаҳор тумани",
        "Навоий тумани", "Нуратa тумани", "Томди тумани", "Учқудуқ тумани",
    ],
    "Қорақалпоғистон Республикаси": [
        "Амударё тумани", "Беруний тумани", "Қонликўл тумани", "Қораузак тумани",
        "Қўнғирот тумани", "Мўйноқ тумани", "Нукус тумани", "Тахтакўпир тумани",
        "Тўрткўл тумани", "Хўжайли тумани", "Чимбой тумани", "Шуманай тумани",
    ],
}

# Build region/subregion indices for compact callback_data (avoid 64-byte limit)
REGION_NAMES = list(REGIONS.keys())
REGION_INDEX = {name: i for i, name in enumerate(REGION_NAMES)}
SUB_LISTS = [REGIONS[name] for name in REGION_NAMES]

# Full 37 questions
# question.py

QUESTIONS = [
    # A. Сегментация
    {"text": "3. Ёшингиз неччида?", "options": ["18–24", "25–34", "35–44", "45–54", "55–64", "65+"]},
    {"text": "4. Қаерда ишлайсиз?", "options": ["Давлат ташкилоти", "Нодавлат ташкилоти", "Хусусий ташкилот", "Тадбиркорман", "Ўз-ўзимни банд қилганман"]},

    # C. Омонат турини аниқлаш
    {"text": "5. Қайси турдаги омонатни сақлайсиз?", "options": ["Сандиқ", "Комфорт", "Прогресс", "Нихол", "Бахтли болалик", "Стимул", "Премиум"]},
    {"text": "6. Омонат очишингизга нима туртки бўлган?", "options": ["Фоизлардан даромад олиш", "Пулни хавфсиз сақлаш", "Банкнинг ишончлилиги ва обрўси", "Онлайн ва мобил хизматлар имконияти"]},
    {"text": "7. Бошқа банкларда омонат сақлайсизми?", "options": ["Ҳа", "Йўқ"]},

    # D. Омонатдан фойдаланиш тўғрисида саволлар
    {"text": "8. Иловадан омонат бўйича қандай қийинчиликларга дуч келгансиз?", 
     "options": ["Тизимда техник муаммолар бор", "Маълумот топиш қийин", "Процесс тушунарсиз ва мураккаб", "Тўлов ва аризаларда қийинчиликлар", "Ҳеч қандай қийинчилик йўқ"]},
    {"text": "9. Қандай қўшимча функциялар керак деб ўйлайсиз?", 
     "options": ["Автомат эслатмалар ва хабарномалар", "Онлайн маслаҳат / чат хизмати", "Очиқ жавоб"]},
    {"text": "10. Омонат очиш сиздан қанча вақт олади?", 
     "options": ["5–15 дақиқа", "30 дақиқа", "60 дақиқа", "1 соатдан кўп"]},

    # E. Омонатдан фойдаланиш тўғрисида саволлар
    {"text": "11. Омонат муддатлари неча ойгача бўлиши сизга қулай?", 
     "options": ["13 ой", "18 ой", "24 ой", "24 ойдан кўп"]},
    {"text": "12. Сиз учун қайси турдаги омонат қулай?", 
     "options": ["Тўлдириш мумкин бўлган", "Ечиб олиш мумкин бўлган", "Хорижий валютада", "Муддатли"]},
    {"text": "13. Агробанк омонатларидан келгусида фойдаланиш эҳтимолингизни баҳоланг (0–10)", 
     "options": [str(i) for i in range(0, 11)]},
    {"text": "14. Қайси муддатдаги омонат сизга кўпроқ қулай?", 
     "options": ["13 ой", "18 ой", "24 ой"]},
]

# ---------------------------
# Keyboards
# ---------------------------
def build_region_keyboard() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [InlineKeyboardButton(text=name, callback_data=f"REG:{i}")]
        for i, name in enumerate(REGION_NAMES)
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def build_subregion_keyboard(region: str) -> InlineKeyboardMarkup:
    rid = REGION_INDEX.get(region, -1)
    subs = SUB_LISTS[rid] if 0 <= rid < len(SUB_LISTS) else []
    inline_keyboard = [
        [InlineKeyboardButton(text=sub, callback_data=f"SUB:{rid}|{j}")]
        for j, sub in enumerate(subs)
    ]
    inline_keyboard.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data="BACK:REG")])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def build_keyboard_for_question(question_id: int) -> InlineKeyboardMarkup:
    q = QUESTIONS[question_id]
    options = q.get("options") or []
    inline_keyboard = [
        [InlineKeyboardButton(text=o, callback_data=f"{question_id}:{i}")]
        for i, o in enumerate(options)
    ]
    # Always include back button
    inline_keyboard.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"BACKQ:{question_id}")])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
async def send_or_edit_question(chat_id: int, question_id: int):
    """
    Edit existing message if present, otherwise send a new one.
    The message contains inline keyboard for choices.
    """
    question = QUESTIONS[question_id]
    text = f"❓ {question['text']}"

    options = question.get("options") or []
    # If open-ended (no options), prompt user to type the answer and set waiting state
    if len(options) == 0:
        text_open = f"❓ {question['text']}\n\nJavobingizni matn ko'rinishida yuboring."
        expected_open_question[chat_id] = question_id
        if chat_id in LAST_MESSAGE_ID:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=LAST_MESSAGE_ID[chat_id],
                    text=text_open,
                    reply_markup=None,
                )
                return
            except Exception:
                pass
        msg = await bot.send_message(chat_id=chat_id, text=text_open)
        LAST_MESSAGE_ID[chat_id] = msg.message_id
        return

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
    # Enforce: only one completed submission per month
    if has_completed_this_month(user_id, total_questions=len(QUESTIONS)):
        await message.answer("Siz bu oy uchun allaqachon formani to'ldirgansiz. Iltimos keyingi oy urinib ko'ring")
        return

    # Prompt region selection to begin the survey
    text = "Hududingizni tanlang:"
    kb = build_region_keyboard()
    msg = await message.answer(text, reply_markup=kb)
    LAST_MESSAGE_ID[user_id] = msg.message_id
    user_progress[user_id] = 0
    return

@dp.message(Command("my_region"))
async def my_region(message: types.Message):
    user_id = message.from_user.id
    info = get_region_this_month(user_id)
    if not info:
        await message.answer("No region saved for this month.")
        return
    region, sub = info
    await message.answer(f"Current month region: {region} / {sub}")

@dp.message(Command("region"))
async def region_cmd(message: types.Message):
    user_id = message.from_user.id
    if has_completed_this_month(user_id, total_questions=len(QUESTIONS)):
        await message.answer("Siz bu oy uchun allaqachon formani to'ldirgansiz. Iltimos keyingi oy urinib ko'ring")
        return
    text = "Iltimos hududingizni tanlang!:"
    kb = build_region_keyboard()
    msg = await message.answer(text, reply_markup=kb)
    LAST_MESSAGE_ID[user_id] = msg.message_id
    user_progress[user_id] = 0
    return
@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data or ""
    # 1) Region selection
    if data.startswith("REG:"):
        try:
            rid = int(data.split(":", 1)[1])
        except Exception:
            return await callback.answer("Invalid region.", show_alert=True)
        if not (0 <= rid < len(REGION_NAMES)):
            return await callback.answer("Invalid region.", show_alert=True)
        region = REGION_NAMES[rid]
        selected_region[user_id] = rid
        subs = SUB_LISTS[rid]
        if not subs:
            try:
                save_region(user_id, region, region)
            except Exception:
                return await callback.answer("Failed to save region.", show_alert=True)
            await callback.answer("Saved!")
            next_index = get_last_answer_index(user_id)
            user_progress[user_id] = next_index
            if next_index < len(QUESTIONS):
                return await send_or_edit_question(user_id, next_index)
            msg = await bot.send_message(user_id, "🎉 E'tiboringiz uchun rahmat! Siz allaqachon bu oy uchun so'rovnama to'ldirgansiz.")
            LAST_MESSAGE_ID[user_id] = msg.message_id
            return
        try:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text=f"Tanlangan hudud: {region}. Endi tumanni tanlashingiz mumkin!",
                reply_markup=build_subregion_keyboard(region),
            )
        except Exception:
            msg = await bot.send_message(user_id, f"Tanlangan viloyat: {region}. Tanlangan tuman:", reply_markup=build_subregion_keyboard(region))
            LAST_MESSAGE_ID[user_id] = msg.message_id
        return await callback.answer()

    # 2) Subregion selection
    if data.startswith("SUB:"):
        try:
            rid_str, sid_str = data.split(":", 1)[1].split("|", 1)
            rid, sid = int(rid_str), int(sid_str)
        except Exception:
            return await callback.answer("Invalid subregion.", show_alert=True)
        if not (0 <= rid < len(REGION_NAMES)):
            return await callback.answer("Invalid subregion.", show_alert=True)
        subs = SUB_LISTS[rid]
        if not (0 <= sid < len(subs)):
            return await callback.answer("Invalid subregion.", show_alert=True)
        region, sub = REGION_NAMES[rid], subs[sid]
        try:
            save_region(user_id, region, sub)
        except Exception:
            return await callback.answer("Failed to save region.", show_alert=True)
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
        next_index = get_last_answer_index(user_id)
        user_progress[user_id] = next_index
        if next_index < len(QUESTIONS):
            return await send_or_edit_question(user_id, next_index)
        msg = await bot.send_message(user_id, "🎉E'tiboringiz uchun rahmat! Siz barcha savollarga savob berdingiz!")
        LAST_MESSAGE_ID[user_id] = msg.message_id
        return

    # 3) Back from subregion to region list
    if data.startswith("BACK:"):
        _, target = data.split(":", 1)
        if target == "REG":
            selected_region.pop(user_id, None)
            try:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text="Please select your region:",
                    reply_markup=build_region_keyboard(),
                )
            except Exception:
                msg = await bot.send_message(user_id, "Ilitmos hududingizni tanlang:", reply_markup=build_region_keyboard())
                LAST_MESSAGE_ID[user_id] = msg.message_id
            return await callback.answer()

    # 4) Back in questions
    if data.startswith("BACKQ:"):
        try:
            qid = int(data.split(":", 1)[1])
        except Exception:
            return await callback.answer("Noma'lum buyruq.")
        if qid <= 0:
            try:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text="Iltimost hududni tanlang:",
                    reply_markup=build_region_keyboard(),
                )
            except Exception:
                msg = await bot.send_message(user_id, "Iltimos hududingizni tanlang:", reply_markup=build_region_keyboard())
                LAST_MESSAGE_ID[user_id] = msg.message_id
            return await callback.answer()
        try:
            delete_answer_current_month(user_id, qid - 1)
        except Exception:
            pass
        await callback.answer()
        return await send_or_edit_question(user_id, qid - 1)

    # 5) Question answer "qid:opt"
    try:
        qid_str, opt_index_str = data.split(":", 1)
        qid = int(qid_str)
        opt_index = int(opt_index_str)
    except Exception:
        return await callback.answer("Invalid response.", show_alert=True)
    if not (0 <= qid < len(QUESTIONS)):
        return await callback.answer("Question not found.", show_alert=True)
    options = QUESTIONS[qid].get("options") or []
    if not (0 <= opt_index < len(options)):
        return await callback.answer("Invalid option.", show_alert=True)
    answer_text = options[opt_index]
    question_text = QUESTIONS[qid]["text"]
    region_info = get_region_this_month(user_id)
    if not region_info:
        await callback.answer("Iltimos birinchi hududingizni tanlang.", show_alert=True)
        try:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                text="Iltimos Viloyatni tanlang:",
                reply_markup=build_region_keyboard(),
            )
        except Exception:
            msg = await bot.send_message(user_id, "Iltimos Viloyatni tanlang:", reply_markup=build_region_keyboard())
            LAST_MESSAGE_ID[user_id] = msg.message_id
        return
    region, subregion = region_info
    try:
        save_answer(user_id, qid, question_text, answer_text, region, subregion)
    except Exception:
        return await callback.answer("Failed to save answer (DB error).", show_alert=True)
    try:
        edited_text = f"✅ {question_text}\n\nYour answer: {answer_text}"
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=edited_text,
            reply_markup=None
        )
    except Exception:
        pass
    await callback.answer("Saved!")
    next_index = get_last_answer_index(user_id)
    user_progress[user_id] = next_index
    if next_index >= len(QUESTIONS):
        final_text = "🎉 Rahmat! Siz barcha savollarga javob berdingiz"
        try:
            if callback.message and callback.message.message_id:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                    text=final_text,
                    reply_markup=None
                )
                LAST_MESSAGE_ID[user_id] = callback.message.message_id
                return
        except Exception:
            pass
        msg = await bot.send_message(user_id, final_text)
        LAST_MESSAGE_ID[user_id] = msg.message_id
        return
    return await send_or_edit_question(user_id, next_index)


@dp.message()
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    if user_id not in expected_open_question:
        return
    qid = expected_open_question.pop(user_id)
    answer_text = (message.text or "").strip()
    if not answer_text:
        return
    region_info = get_region_this_month(user_id)
    if not region_info:
        msg = await message.answer("Hududingizni tanlang:", reply_markup=build_region_keyboard())
        LAST_MESSAGE_ID[user_id] = msg.message_id
        return
    region, subregion = region_info
    question_text = QUESTIONS[qid]["text"]
    try:
        save_answer(user_id, qid, question_text, answer_text, region, subregion)
    except Exception:
        await message.answer("Failed to save answer (DB error). Try again.")
        return
    try:
        if user_id in LAST_MESSAGE_ID:
            edited_text = f"✅ {question_text}\n\nSizning javobingiz: {answer_text}"
            await bot.edit_message_text(chat_id=user_id, message_id=LAST_MESSAGE_ID[user_id], text=edited_text, reply_markup=None)
    except Exception:
        pass
    next_index = get_last_answer_index(user_id)
    user_progress[user_id] = next_index
    if next_index >= len(QUESTIONS):
        msg = await bot.send_message(user_id, "🎉E'tiboringiz uchun rahmat! Siz barcha savollarga savob berdingiz")
        LAST_MESSAGE_ID[user_id] = msg.message_id
        return
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
                msg = await bot.send_message(uid, "Ilitingizni tanlang:", reply_markup=build_region_keyboard())
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
