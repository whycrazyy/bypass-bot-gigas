import logging
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)

from sessions_manager import (
    get_user_session,
    update_user_session,
    delete_user_session,
    STEP_ASK_PHONE,
    STEP_ASK_CODE,
    STEP_MENU,
)

from automation import (
    processar_vivo_free,
    list_campaigns,
    collect_campaigns,
    parse_reward,
)

from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from telegram.error import NetworkError, TimedOut, RetryAfter

# ================= EXECUTORES =================
# executor rápido: login, sms, menu, consulta
EXECUTOR_FAST = ThreadPoolExecutor(max_workers=6)

# executor pesado: coleta (requests + sleep + loop)
EXECUTOR_COLLECT = ThreadPoolExecutor(max_workers=2)

USER_COLLECTING = defaultdict(bool)  # trava só de coleta por usuário

# ================= CONFIG =================
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ================= ERROR HANDLER =================
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    logger.exception("Erro global no update: %s", err)

    try:
        if hasattr(update, "callback_query") and update.callback_query:
            q = update.callback_query
            try:
                await q.answer(
                    "⚠️ Instabilidade de rede. Tente novamente.", show_alert=False
                )
            except Exception:
                pass
            return
    except Exception:
        pass

    try:
        if hasattr(update, "effective_message") and update.effective_message:
            if isinstance(err, (NetworkError, TimedOut, RetryAfter)):
                await update.effective_message.reply_text(
                    "🌐 Instabilidade de conexão. Tenta novamente em alguns segundos."
                )
            else:
                await update.effective_message.reply_text("⚠️ Erro interno.")
    except Exception:
        pass


# ================= EXECUTORES ASYNC =================
async def run_fast(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(EXECUTOR_FAST, lambda: func(*args))


async def run_collect(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(EXECUTOR_COLLECT, lambda: func(*args))


# ================= HELPERS =================
def format_phone_br(phone: str) -> str:
    digits = "".join(filter(str.isdigit, phone))

    if len(digits) == 11:
        ddd = digits[:2]
        first = digits[2]
        part1 = digits[3:7]
        part2 = digits[7:]
        return f"({ddd}) {first} {part1}-{part2}"

    if len(digits) == 10:
        ddd = digits[:2]
        part1 = digits[2:6]
        part2 = digits[6:]
        return f"({ddd}) {part1}-{part2}"

    return phone


# ================= MENUS =================
def get_main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔎 Consultar Campanhas", callback_data="menu_consultar"
                )
            ],
            [InlineKeyboardButton("📥 Coletar Gigas", callback_data="menu_coletar")],
            [InlineKeyboardButton("🚪 Sair", callback_data="menu_sair")],
        ]
    )


def get_after_collect_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔁 Coletar novamente", callback_data="menu_coletar"
                )
            ],
            [InlineKeyboardButton("🏠 Voltar ao menu", callback_data="back_main")],
        ]
    )


def get_start_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🟣 VIVO", callback_data="btn_vivo_login")]]
    )


# ================= TELAS =================
async def send_initial_flow(update: Update):
    name = update.effective_user.first_name or "🙂"

    await update.message.reply_text(
        f"Olá, {name} 👋 Bem-vindo\n\n"
        "Este bot executa campanhas automaticamente para gerar internet, mesmo que seu chip esteja suspenso.\n\n"
        "Toque abaixo para começar:",
        parse_mode="Markdown",
        reply_markup=get_start_keyboard(),
    )


async def send_main_menu_from_query(query, session):
    await query.edit_message_text("🔄 Abrindo menu...")

    text = (
        "📱 **PAINEL VIVO FREE**\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👤 Usuário: {query.from_user.first_name}\n"
        f"📞 Vivo: `{format_phone_br(session.get('phone',''))}`\n"
        "📅 Validade: `Sem`\n"
        "━━━━━━━━━━━━━━━━\n"
        "Escolha uma opção:"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_user_session(user_id)

    if not session.get("token") or not session.get("wallet"):
        update_user_session(user_id, {"step": STEP_ASK_PHONE})
        await send_initial_flow(update)
        return

    await update.message.reply_text(
        "📱 **PAINEL VIVO FREE**\n"
        "━━━━━━━━━━━━━━━━\n"
        f"👤 Usuário: {update.effective_user.first_name}\n"
        f"📞 Vivo: `{format_phone_br(session.get('phone',''))}`\n"
        "📅 Validade: `Sem`\n"
        "━━━━━━━━━━━━━━━━\n"
        "Escolha uma opção:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )


# ================= TEXTO =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_user_session(update.effective_user.id)
    step = session.get("step")
    text = update.message.text.strip()

    try:
        if step == STEP_ASK_PHONE:
            phone = "".join(filter(str.isdigit, text))
            if len(phone) < 11:
                await update.message.reply_text("❌ Número inválido.")
                return

            await update.message.reply_text("🔄 Solicitando código SMS...")
            res = await run_fast(
                processar_vivo_free, phone, None, update.effective_user.id
            )

            if not res["success"]:
                await update.message.reply_text("❌ Erro ao enviar SMS.")
                return

            update_user_session(
                update.effective_user.id, {"step": STEP_ASK_CODE, "phone": phone}
            )

            await update.message.reply_text(
                "✅ **SMS enviado!**\n\nDigite o código de 6 dígitos:",
                parse_mode="Markdown",
            )

        elif step == STEP_ASK_CODE:
            code = "".join(filter(str.isdigit, text))
            phone = session.get("phone")

            await update.message.reply_text("🔄 Validando código...")
            res = await run_fast(
                processar_vivo_free, phone, code, update.effective_user.id
            )

            if not res["success"]:
                await update.message.reply_text("❌ Código inválido.")
                return

            update_user_session(
                update.effective_user.id,
                {
                    "step": STEP_MENU,
                    "token": res["auth_token"],
                    "wallet": res["wallet_id"],
                },
            )

            msg = await update.message.reply_text(
                "📱 **PAINEL VIVO FREE**\n"
                "━━━━━━━━━━━━━━━━\n"
                f"👤 Usuário: {update.effective_user.first_name}\n"
                f"📞 Vivo: `{format_phone_br(session.get('phone',''))}`\n"
                "📅 Validade: `Sem`\n"
                "━━━━━━━━━━━━━━━━\n"
                "Escolha uma opção:",
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard(),
            )

            update_user_session(
                update.effective_user.id, {"menu_message_id": msg.message_id}
            )

        else:
            await update.message.reply_text(
                "⚠️ Use os botões do menu ou clique em 🟣 VIVO para iniciar."
            )

    except Exception as e:
        logger.exception("Erro handle_text: %s", e)
        try:
            await update.message.reply_text("⚠️ Erro interno.")
        except Exception:
            pass


# ================= CALLBACKS =================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    session = get_user_session(uid)

    try:
        if query.data == "btn_vivo_login":
            update_user_session(
                uid,
                {
                    "step": STEP_ASK_PHONE,
                    "token": None,
                    "wallet": None,
                    "phone": None,
                },
            )

            await query.edit_message_text(
                "📱 Digite seu número Vivo com DDD:\n\n(ex: 11987660011)."
            )

        elif query.data == "back_main":
            await send_main_menu_from_query(query, session)

        elif query.data == "menu_consultar":
            await query.edit_message_text("🔄 Analisando campanhas...")

            campaigns = await run_fast(
                list_campaigns, session.get("token"), session.get("wallet"), uid
            )

            total_videos = 0
            total_mb = 0

            for c in campaigns or []:
                name = (c.get("campaignName") or "").lower()
                reward = parse_reward(c)

                if reward <= 0 or "vivo free" in name:
                    continue

                medias = c.get("mainData", {}).get("media", [])
                pendentes = [m for m in medias if m.get("viewed") is not True]

                if not pendentes:
                    continue

                total_videos += len(pendentes)
                total_mb += reward

            if total_videos == 0 or total_mb == 0:
                await query.edit_message_text(
                    "📭 Nenhum vídeo disponível no momento.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🏠 Voltar ao menu", callback_data="back_main"
                                )
                            ]
                        ]
                    ),
                )
                return

            await query.edit_message_text(
                "📊 **Resumo disponível**\n\n"
                f"🎬 Vídeos disponíveis: **{total_videos}**\n"
                f"📶 Internet estimada: **{total_mb:.0f} MB**",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📥 Coletar Gigas", callback_data="menu_coletar"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🏠 Voltar ao menu", callback_data="back_main"
                            )
                        ],
                    ]
                ),
            )

        elif query.data == "menu_coletar":
            if USER_COLLECTING[uid]:
                await query.answer("⏳ Coleta em andamento...", show_alert=False)
                return

            USER_COLLECTING[uid] = True

            try:
                await query.edit_message_text("📥 Coletando gigas... Aguarde ⏳")

                qtd, total = await run_collect(
                    collect_campaigns, session.get("token"), session.get("wallet"), uid
                )

                if not qtd or not total:
                    qtd = 0
                    total = 0

                update_user_session(
                    uid,
                    {
                        "last_collect_qtd": qtd,
                        "last_collect_total": total,
                    },
                )

                await query.edit_message_text(
                    f"✅ **Coleta finalizada!**\n\n"
                    f"🎬 Vídeos concluídos: **{qtd}**\n"
                    f"📶 Internet gerada: **{total:.0f} MB**\n\n"
                    "ℹ️ Agora consulte seu saldo discando `*8000`. "
                    "A quantidade de internet pode ser **maior ou menor** que o valor exibido.",
                    parse_mode="Markdown",
                    reply_markup=get_after_collect_keyboard(),
                )

            except Exception as e:
                logger.exception("Erro na coleta: %s", e)
                await query.edit_message_text(
                    "⚠️ Erro ao coletar gigas. Tente novamente.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🏠 Voltar ao menu", callback_data="back_main"
                                )
                            ]
                        ]
                    ),
                )
            finally:
                USER_COLLECTING[uid] = False

        elif query.data == "menu_sair":
            update_user_session(
                uid,
                {
                    "step": STEP_ASK_PHONE,
                    "token": "",
                    "wallet": "",
                    "phone": "",
                    "menu_message_id": None,
                    "last_collect_qtd": 0,
                    "last_collect_total": 0,
                },
            )

            name = query.from_user.first_name or "🙂"

            await query.edit_message_text(
                f"Olá, {name} 👋 Bem-vindo\n\n"
                "Este bot executa campanhas automaticamente para gerar internet, mesmo que seu chip esteja suspenso.\n\n"
                "Toque abaixo para começar:",
                parse_mode="Markdown",
                reply_markup=get_start_keyboard(),
            )

    except Exception as e:
        logger.exception("Erro handle_callback: %s", e)
        try:
            await query.message.reply_text("⚠️ Falha temporária. Tente novamente.")
        except Exception:
            pass


# ================= MAIN =================
def main():
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=40.0,
        write_timeout=40.0,
        pool_timeout=20.0,
    )

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)

    print("🤖 Bot rodando.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
