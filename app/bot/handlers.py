"""Commandes Telegram : /start, /abonner, /mes_alertes, /retirer, /stop, /help (+ admin)."""
import asyncio

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app import config
from app.db.database import PLAN_LIMITS, Database, max_keywords
from app.services.matching import clean_keyword

router = Router()

HELP_TEXT = (
    "📌 Commandes\n"
    "/abonner mot-clé : suivre un sujet (ex. /abonner stage informatique)\n"
    "/mes_alertes : voir vos alertes\n"
    "/retirer mot-clé : supprimer une alerte\n"
    "/stop : mettre les alertes en pause\n"
    "/start : reprendre les alertes"
)

WELCOME = (
    "👋 Bienvenue ! Je vous préviens des bourses, stages, emplois et concours "
    "qui correspondent à vos mots-clés.\n\n"
    "Pour commencer : /abonner stage informatique\n\n" + HELP_TEXT
)


def is_admin(message: Message) -> bool:
    return bool(message.from_user) and config.ADMIN_ID != 0 and message.from_user.id == config.ADMIN_ID


async def register(db: Database, message: Message, reactivate: bool) -> int:
    """Enregistre l'utilisateur s'il est nouveau et retourne son identifiant."""
    user = message.from_user
    await asyncio.to_thread(db.upsert_user, user.id, user.username, user.first_name, reactivate)
    return user.id


@router.message(Command("start"))
async def cmd_start(message: Message, db: Database):
    await register(db, message, reactivate=True)
    await message.answer(WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


@router.message(Command("abonner"))
async def cmd_subscribe(message: Message, command: CommandObject, db: Database):
    if not command.args:
        await message.answer("Indiquez un mot-clé. Exemple : /abonner stage informatique")
        return
    try:
        display, norm = clean_keyword(command.args)
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    user_id = await register(db, message, reactivate=True)
    result = await asyncio.to_thread(db.add_keyword, user_id, display, norm)
    if result == "added":
        await message.answer(f"✅ Alerte ajoutée : « {display} »")
    elif result == "exists":
        await message.answer(f"ℹ️ Vous suivez déjà « {display} ».")
    else:
        user = await asyncio.to_thread(db.get_user, user_id)
        limit = max_keywords(user["plan"])
        await message.answer(
            f"⚠️ Limite atteinte : {limit} mots-clés avec la formule {user['plan']}.\n"
            "Retirez-en un avec /retirer mot-clé."
        )


@router.message(Command("mes_alertes"))
async def cmd_my_alerts(message: Message, db: Database):
    user_id = await register(db, message, reactivate=False)
    keywords = await asyncio.to_thread(db.list_keywords, user_id)
    user = await asyncio.to_thread(db.get_user, user_id)
    if not keywords:
        await message.answer("Vous n'avez aucune alerte. Exemple : /abonner bourse master")
        return
    limit = max_keywords(user["plan"])
    lines = [f"🔔 Vos alertes ({len(keywords)}/{limit}) :"]
    lines += [f"{i}. {kw}" for i, kw in enumerate(keywords, start=1)]
    if not user["active"]:
        lines.append("\n⏸ Alertes en pause : envoyez /start pour reprendre.")
    await message.answer("\n".join(lines))


@router.message(Command("retirer"))
async def cmd_remove(message: Message, command: CommandObject, db: Database):
    if not command.args:
        await message.answer("Indiquez le mot-clé à retirer. Exemple : /retirer stage informatique")
        return
    try:
        display, norm = clean_keyword(command.args)
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}")
        return
    user_id = await register(db, message, reactivate=False)
    removed = await asyncio.to_thread(db.remove_keyword, user_id, norm)
    if removed:
        await message.answer(f"🗑 Alerte retirée : « {display} »")
    else:
        await message.answer(f"Aucune alerte « {display} ». Voir /mes_alertes.")


@router.message(Command("stop"))
async def cmd_stop(message: Message, db: Database):
    user_id = await register(db, message, reactivate=False)
    await asyncio.to_thread(db.set_active, user_id, False)
    await message.answer("🔕 Alertes en pause. Vos mots-clés sont conservés : /start pour reprendre.")


# --- Commandes réservées à l'administrateur ------------------------------------

@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    if not is_admin(message):
        return
    s = await asyncio.to_thread(db.stats)
    await message.answer(
        f"📊 Utilisateurs : {s['users']} (actifs : {s['active']})\nAlertes : {s['keywords']}"
    )


@router.message(Command("plan"))
async def cmd_plan(message: Message, command: CommandObject, db: Database):
    """Usage : /plan 123456789 premium  (change la formule d'un utilisateur)."""
    if not is_admin(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in PLAN_LIMITS:
        await message.answer("Usage : /plan <id> <free|premium>")
        return
    done = await asyncio.to_thread(db.set_plan, int(parts[0]), parts[1])
    await message.answer("✅ Formule mise à jour." if done else "⚠️ Utilisateur introuvable.")


@router.message(Command("verifier"))
async def cmd_check(message: Message, runner):
    """Lance tout de suite une vérification des sources et affiche le rapport."""
    if not is_admin(message):
        return
    await message.answer("⏳ Vérification des sources en cours…")
    report = await runner.run()
    if report is None:
        await message.answer("Une vérification est déjà en cours, réessayez dans un instant.")
    else:
        await message.answer(report.format())
