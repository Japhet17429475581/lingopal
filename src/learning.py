"""Durable assessment sessions. Answers and rewards are decided by the server."""
import json
import random
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from src import database as db


def _json(value):
    return json.dumps(value, ensure_ascii=False)


def _award(session, user_id, amount):
    user = session.execute(select(db.User).where(db.User.telegram_id == user_id).with_for_update()).scalar_one()
    today = db._now().date()
    old_tier = db.get_streak_tier(user.streak_count)["key"]
    if user.last_activity_date != today.isoformat():
        user.streak_count = user.streak_count + 1 if user.last_activity_date == (today - timedelta(days=1)).isoformat() else 1
        user.last_activity_date = today.isoformat()
    tier = db.get_streak_tier(user.streak_count)
    bonus = round(amount * tier["bonus_pct"] / 100)
    user.exp += amount + bonus
    gained = 0
    while user.exp >= db.exp_needed_for_level(user.level):
        user.exp -= db.exp_needed_for_level(user.level)
        user.level += 1
        gained += 1
    return ({"awarded": amount + bonus, "base": amount, "bonus": bonus, "level": user.level,
             "exp": user.exp, "exp_needed": db.exp_needed_for_level(user.level),
             "leveled_up": gained > 0, "levels_gained": gained},
            {"streak_count": user.streak_count, "tier": tier, "tier_changed": old_tier != tier["key"]})


def require_block_access(user_id, block_id):
    block = db.get_grammar_block_detail(block_id)
    if not block:
        raise LookupError("Блок грамматики не найден")
    status = next(b["status"] for b in db.get_grammar_blocks(user_id, block["level"]) if b["id"] == block_id)
    if status == "locked":
        raise PermissionError("Сначала пройди предыдущий блок этого уровня")
    return block


def public_question(question):
    payload = {key: value for key, value in question["payload"].items() if key not in {"correct", "correct_order"}}
    return {"id": question["id"], "question_type": question["question_type"], "payload": payload}


def start_grammar(user_id, block_id):
    require_block_access(user_id, block_id)
    questions = db.get_grammar_questions(block_id)
    if not questions:
        raise ValueError("В этом блоке пока нет упражнений")
    random.shuffle(questions)
    for question in questions:
        payload = question["payload"]
        if question["question_type"] == "choice":
            random.shuffle(payload["options"])
        elif question["question_type"] == "constructor":
            random.shuffle(payload["words"])
    attempt_id = uuid.uuid4().hex
    with db.get_db() as session:
        session.add(db.LearningAttempt(id=attempt_id, telegram_id=user_id, kind="grammar", block_id=block_id,
                                       questions=_json(questions), answers="[]"))
        session.commit()
    return {"attempt_id": attempt_id, "questions": [public_question(q) for q in questions]}


def _get_attempt(session, user_id, attempt_id, kind):
    attempt = session.get(db.LearningAttempt, attempt_id)
    if not attempt or attempt.telegram_id != user_id or attempt.kind != kind:
        raise LookupError("Попытка не найдена. Начни упражнение заново.")
    return attempt


def _save_answers(session, attempt, answers):
    # Compare-and-swap also protects SQLite, where SELECT FOR UPDATE is ignored.
    changed = session.execute(update(db.LearningAttempt).where(
        db.LearningAttempt.id == attempt.id, db.LearningAttempt.answers == attempt.answers,
        db.LearningAttempt.result.is_(None)).values(answers=_json(answers)),
        execution_options={"synchronize_session": False}).rowcount
    if not changed:
        raise ValueError("Ответ уже обрабатывается. Повтори запрос.")


def answer_grammar(user_id, attempt_id, question_id, answer):
    with db.get_db() as session:
        attempt = _get_attempt(session, user_id, attempt_id, "grammar")
        questions, answers = json.loads(attempt.questions), json.loads(attempt.answers)
        previous = next((a for a in answers if a["question_id"] == question_id), None)
        if previous:
            return previous
        if attempt.result or len(answers) >= len(questions) or questions[len(answers)]["id"] != question_id:
            raise ValueError("Отвечай на вопросы по порядку")
        question = questions[len(answers)]
        payload = question["payload"]
        expected = payload.get("correct_order") if question["question_type"] == "constructor" else payload["correct"]
        if question["question_type"] == "boolean":
            correct = type(answer) is bool and answer == expected
        else:
            correct = type(answer) is type(expected) and answer == expected
        receipt = {"question_id": question_id, "correct": correct, "correct_answer": expected,
                   "given_answer": answer, "explanation": question.get("explanation", "")}
        _save_answers(session, attempt, [*answers, receipt])
        session.commit()
        return receipt


def finish_grammar(user_id, block_id, attempt_id):
    with db.get_db() as session:
        attempt = _get_attempt(session, user_id, attempt_id, "grammar")
        if attempt.block_id != block_id:
            raise ValueError("Попытка относится к другому блоку")
        if attempt.result:
            return {**json.loads(attempt.result), "replayed": True}
        questions, answers = json.loads(attempt.questions), json.loads(attempt.answers)
        if len(answers) != len(questions):
            raise ValueError("Сначала ответь на все вопросы")
        # Claim completion and reward in the same transaction.
        claimed = session.execute(update(db.LearningAttempt).where(
            db.LearningAttempt.id == attempt_id, db.LearningAttempt.result.is_(None)
        ).values(result="{}"), execution_options={"synchronize_session": False}).rowcount
        if not claimed:
            raise ValueError("Результат уже сохраняется. Повтори запрос.")
        block = session.get(db.GrammarBlock, block_id)
        correct = sum(a["correct"] for a in answers)
        total = len(questions)
        score = round(correct * 100 / total)
        passed = correct * 100 >= block.pass_percent * total
        progress = session.execute(select(db.UserGrammarProgress).where(
            db.UserGrammarProgress.telegram_id == user_id, db.UserGrammarProgress.block_id == block_id
        ).with_for_update()).scalar_one_or_none()
        if progress is None:
            progress = db.UserGrammarProgress(telegram_id=user_id, block_id=block_id, attempts=0,
                                               best_score=0, is_completed=False)
            session.add(progress)
        already = progress.is_completed
        # Only reward improvement; repeating an identical result cannot farm XP.
        improvement = max(0, correct - round(progress.best_score * total / 100))
        reward = improvement * db.GRAMMAR_EXP_PER_CORRECT + (block.exp_reward if passed and not already else 0)
        progress.attempts += 1
        progress.best_score = max(progress.best_score, score)
        if passed and not already:
            progress.is_completed = True
            progress.completed_at = db._now()
        exp, streak = _award(session, user_id, reward)
        result = {"block_id": block_id, "passed": passed, "score": score, "pass_percent": block.pass_percent,
                  "correct_answers": correct, "total_questions": total, "best_score": progress.best_score,
                  "already_completed": already, "exp_result": exp, "streak_result": streak,
                  "mistakes": [a for a in answers if not a["correct"]], "replayed": False}
        session.execute(update(db.LearningAttempt).where(db.LearningAttempt.id == attempt_id).values(result=_json(result)))
        session.commit()
    result["unlocked_achievements"] = db.check_achievements(user_id)
    result["quest_events"] = db.record_quest_progress(user_id, "grammar_tests", 1)
    return result


def start_review(user_id):
    with db.get_db() as session:
        existing = session.execute(select(db.LearningAttempt).where(
            db.LearningAttempt.telegram_id == user_id, db.LearningAttempt.kind == "review",
            db.LearningAttempt.result.is_(None)).order_by(db.LearningAttempt.created_at.desc())).scalars().first()
        if existing:
            answered = len(json.loads(existing.answers))
            words = json.loads(existing.questions)
            return {"session_id": existing.id, "words": words[answered:], "total_count": len(words)}
        words = db.get_due_review_words(user_id)
        if not words:
            return {"session_id": None, "words": [], "total_count": 0}
        attempt_id = uuid.uuid4().hex
        session.add(db.LearningAttempt(id=attempt_id, telegram_id=user_id, kind="review", questions=_json(words), answers="[]"))
        session.commit()
        return {"session_id": attempt_id, "words": words, "total_count": len(words)}


def answer_review(user_id, attempt_id, word_id, correct):
    with db.get_db() as session:
        attempt = _get_attempt(session, user_id, attempt_id, "review")
        words, answers = json.loads(attempt.questions), json.loads(attempt.answers)
        previous = next((a for a in answers if a["word_id"] == word_id), None)
        if previous:
            return previous
        if attempt.result or len(answers) >= len(words) or words[len(answers)]["word_id"] != word_id:
            raise ValueError("Повторяй слова по порядку")
        row = session.execute(select(db.UserWord).where(db.UserWord.telegram_id == user_id,
                                                        db.UserWord.word_id == word_id)).scalar_one()
        row.box_number = min(db.LEITNER_MAX_BOX, row.box_number + 1) if correct else 1
        row.next_review_at = db._now() + timedelta(days=db.LEITNER_INTERVALS_DAYS[row.box_number])
        receipt = {"word_id": word_id, "correct": correct, "box_number": row.box_number,
                   "next_review_at": row.next_review_at.isoformat()}
        _save_answers(session, attempt, [*answers, receipt])
        session.commit()
        return receipt


def finish_review(user_id, attempt_id):
    with db.get_db() as session:
        attempt = _get_attempt(session, user_id, attempt_id, "review")
        if attempt.result:
            return {**json.loads(attempt.result), "replayed": True}
        answers = json.loads(attempt.answers)
        if len(answers) != len(json.loads(attempt.questions)):
            raise ValueError("Сначала заверши повторение")
        claimed = session.execute(update(db.LearningAttempt).where(
            db.LearningAttempt.id == attempt_id, db.LearningAttempt.result.is_(None)
        ).values(result="{}"), execution_options={"synchronize_session": False}).rowcount
        if not claimed:
            raise ValueError("Результат уже сохраняется")
        correct = sum(a["correct"] for a in answers)
        exp, streak = _award(session, user_id, correct * db.REVIEW_EXP_PER_CORRECT)
        result = {"exp_result": exp, "streak_result": streak, "correct_count": correct,
                  "total_count": len(answers), "replayed": False}
        session.execute(update(db.LearningAttempt).where(db.LearningAttempt.id == attempt_id).values(result=_json(result)))
        session.commit()
        return result
